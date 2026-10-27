#!/usr/bin/env bash
# HAND-ROLLED: cng-datasets has no mode that adds one time slice to a rolling
# series or emits a CronJob, so this script drives `cng-datasets mdim` itself
# (boettiger-lab/data-workflows#802).
#
# NOAA Coral Reef Watch 5 km daily tier: stage raw, COG, H3 res-6 hex, and the
# NE Pacific blob summary, for every day in [START, END] not already published.
#
#   update-daily.sh [START END]     dates as YYYY-MM-DD, inclusive
#
# With no dates it covers the last LOOKBACK_DAYS ending yesterday (UTC), which
# also catches days NOAA posted late or reprocessed. A day/product is done when
# its COG exists; the COG is uploaded last, so a failed run is redone next time.
#
# Hex layout: one file per h0 cell, hex/h0=<cell>/data_0.parquet, sorted by time. A new day
# lands as hex/h0=<cell>/part-tYYYYMMDD-0.parquet beside it; once its month has closed,
# COMPACT=1 (the default) folds those daily files into data_0.parquet. COMPACT=0 is for
# parallel backfill pods, which must not rewrite the same files concurrently.
# PRUNE=1 also removes whole months older than WINDOW_MONTHS, from the hex, COGs and raw.
set -euo pipefail

BUCKET=${BUCKET:-public-coral-reef-watch}
WINDOW_MONTHS=${WINDOW_MONTHS:-13}
LOOKBACK_DAYS=${LOOKBACK_DAYS:-10}
PRUNE=${PRUNE:-0}
COMPACT=${COMPACT:-1}
SRC=https://www.star.nesdis.noaa.gov/pub/sod/mecb/crw/data/5km/v3.1_op/nc/v1.0/daily
PREFIX=${PREFIX:-crw-5km-daily}

END=${2:-$(date -u -d yesterday +%F)}
START=${1:-$(date -u -d "$END -$((LOOKBACK_DAYS - 1)) days" +%F)}
# First day kept: the first of the month WINDOW_MONTHS before END's month.
CUTOFF=$(date -u -d "$(date -u -d "$END" +%Y-%m-01) -$WINDOW_MONTHS months" +%Y%m%d)
# Guard: never prune anything less than ~12 months old, whatever the env says.
if [ "$PRUNE" = 1 ] && (( CUTOFF > $(date -u -d "-360 days" +%Y%m%d) )); then
  echo "refusing to prune: cutoff $CUTOFF is under 12 months old" >&2; exit 1
fi

# product -> netCDF variable, reducer (#802: mean for continuous, max for ordinal alert levels)
declare -A VAR=([sst]=analysed_sst [ssta]=sea_surface_temperature_anomaly [hs]=hotspot
                [dhw]=degree_heating_week [baa]=bleaching_alert_area [baa-max-7d]=bleaching_alert_area)
declare -A REDUCER=([sst]=mean [ssta]=mean [hs]=mean [dhw]=mean [baa]=max [baa-max-7d]=max)
PRODUCTS=(${ONLY_PRODUCTS:-sst ssta hs dhw baa baa-max-7d})  # ONLY_PRODUCTS: a space-separated subset

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

src_name() {  # product, YYYYMMDD
  if [ "$1" = sst ]; then echo "coraltemp_v3.1_$2.nc"; else echo "ct5km_$1_v3.1_$2.nc"; fi
}

blob_summary() {  # YYYYMMDD, YYYY-MM-DD; box and threshold fixed in #802
  python3 - "$1" "$2" <<'EOF'
import os, sys, duckdb
ymd, iso = sys.argv[1], sys.argv[2]
bucket, prefix = os.environ.get("BUCKET", "public-coral-reef-watch"), os.environ.get("PREFIX", "crw-5km-daily")
con = duckdb.connect()
con.execute("INSTALL h3 FROM community; LOAD h3; INSTALL httpfs; LOAD httpfs")
con.execute(f"""CREATE SECRET (TYPE S3, KEY_ID '{os.environ["AWS_ACCESS_KEY_ID"]}',
  SECRET '{os.environ["AWS_SECRET_ACCESS_KEY"]}', ENDPOINT '{os.environ["AWS_S3_ENDPOINT"]}',
  USE_SSL false, URL_STYLE 'path')""")
src = f"s3://{bucket}/{prefix}/ssta/hex/h0=*/part-t{ymd}-*.parquet"
out = f"s3://{bucket}/{prefix}/ne-pacific-blob/part-{ymd}.parquet"  # folded into data_0.parquet by compact_blob
con.execute(f"""COPY (
  WITH cells AS (
    SELECT h3_cell_to_lat(h6) AS lat, h3_cell_to_lng(h6) AS lng,
           h3_cell_area(h6, 'km^2') AS km2, sea_surface_temperature_anomaly AS ssta
    FROM read_parquet('{src}')
    WHERE sea_surface_temperature_anomaly IS NOT NULL)
  SELECT DATE '{iso}' AS date,
         sum(km2) FILTER (WHERE ssta >= 2) AS area_km2_ssta_ge_2,
         sum(km2) AS area_km2_with_data,
         sum(lat * km2) FILTER (WHERE ssta >= 2) / sum(km2) FILTER (WHERE ssta >= 2) AS centroid_lat,
         sum(lng * km2) FILTER (WHERE ssta >= 2) / sum(km2) FILTER (WHERE ssta >= 2) AS centroid_lng,
         max(ssta) AS max_ssta,
         arg_max(lat, ssta) AS max_ssta_lat, arg_max(lng, ssta) AS max_ssta_lng
  FROM cells WHERE lat BETWEEN 20 AND 60 AND lng BETWEEN -180 AND -110
) TO '{out}' (FORMAT PARQUET)""")
print(con.sql(f"SELECT * FROM read_parquet('{out}')"))
EOF
}

compact() {  # product; folds daily files from closed months into each h0's data_0.parquet
  local p=$1 cutoff=""
  [ "$PRUNE" = 1 ] && cutoff=$CUTOFF
  rclone lsf -R --files-only --include "h0=*/*.parquet" --include "_manifest/*.parquet" \
    "nrp:$BUCKET/$PREFIX/$p/hex/" > "$WORK/hex-$p.txt"
  python3 - "$p" "$WORK/hex-$p.txt" "$(date -u +%Y%m01)" "$cutoff" "$WORK" "$PREFIX" <<'EOF'
import os, re, subprocess, sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import duckdb
p, listing, month_start, cutoff, work, prefix = sys.argv[1:7]
bucket = os.environ.get("BUCKET", "public-coral-reef-watch")
hexdir = f"{bucket}/{prefix}/{p}/hex"
# CELL_SHARD=i/n compacts the cells whose base cell number is i mod n, so a first pass can fan out over pods.
shard = os.environ.get("CELL_SHARD")
compacted, parts, manifests = set(), defaultdict(list), []
for line in open(listing):
    line = line.strip()
    m = re.fullmatch(r"_manifest/chunk-(\d{8})\.parquet", line)
    if m and m.group(1) < month_start:
        manifests.append(line)
    m = re.fullmatch(r"(h0=\d+)/(?:data_0|part-t(\d{8})-\d+)\.parquet", line)
    if not m:
        continue
    if m.group(2) is None:
        compacted.add(m.group(1))
    elif m.group(2) < month_start:
        parts[m.group(1)].append(line)
if manifests and not shard:  # mdim's per-day manifests; nothing reads them once the day is compacted
    lst = os.path.join(work, "manifest.txt")
    open(lst, "w").write("\n".join(manifests) + "\n")
    subprocess.run(["rclone", "delete", "--files-from-raw", lst, f"nrp:{hexdir}/"], check=True)
# REWRITE_ALL=1 rewrites every cell even with nothing new, e.g. to apply a fix to data_0 files.
rewrite = os.environ.get("REWRITE_ALL") == "1"
if not parts and not rewrite:
    sys.exit(print(f"{p}: no daily files from closed months to compact"))
days = sorted({re.search(r"part-t(\d{8})", f).group(1) for fs in parts.values() for f in fs})
# Without a cutoff, only cells with new days change; with one, every cell drops expired months.
cells = sorted(set(parts) | (compacted if cutoff or rewrite else set()))
if shard:
    i, n = map(int, shard.split("/"))
    cells = [c for c in cells if (int(c[3:]) >> 45 & 127) % n == i]  # by H3 base cell, stable across retries
print(f"{p}: compacting {len(days)} days ({days[0]}..{days[-1]}) into {len(cells)} h0 files" if days
      else f"{p}: rewriting {len(cells)} h0 files")
con = duckdb.connect()
# Without an explicit limit DuckDB sizes itself to the node, not the pod, and is OOM-killed.
con.execute(f"""SET memory_limit = '{os.environ.get("DUCKDB_MEMORY_LIMIT", "1800MiB")}'; SET threads = 2;
  SET preserve_insertion_order = false; SET temp_directory = '{work}/duckdb-tmp'""")
con.execute("INSTALL httpfs; LOAD httpfs")
con.execute(f"""CREATE SECRET (TYPE S3, KEY_ID '{os.environ["AWS_ACCESS_KEY_ID"]}',
  SECRET '{os.environ["AWS_SECRET_ACCESS_KEY"]}', ENDPOINT '{os.environ["AWS_S3_ENDPOINT"]}',
  USE_SSL false, URL_STYLE 'path')""")
keep = f"WHERE time >= DATE '{cutoff[:4]}-{cutoff[4:6]}-{cutoff[6:]}'" if cutoff else ""

def one(cell):
    # hive_partitioning=false keeps h0 as the UBIGINT stored in the files.
    new = [f"s3://{hexdir}/{f}" for f in parts.get(cell, [])]
    sel = []
    if new:
        sel.append(f"SELECT * FROM read_parquet({new!r}, hive_partitioning=false)")
    if cell in compacted:
        # A day present in both (reprocessed or posted late) takes the daily file's values.
        redo = f"WHERE time NOT IN (SELECT DISTINCT time FROM read_parquet({new!r}, hive_partitioning=false))" if new else ""
        sel.append(f"SELECT * FROM read_parquet('s3://{hexdir}/{cell}/data_0.parquet', hive_partitioning=false) {redo}")
    out = os.path.join(work, f"{cell}.parquet")
    # DISTINCT ON keeps one row per cell per day: mdim splits a day's cell into part-t...-0, -1, ...
    # files as it sees fit, so files from an earlier run of the same day can repeat its rows.
    con.cursor().execute(f"""COPY (SELECT DISTINCT ON (time, h6) * FROM ({" UNION ALL BY NAME ".join(sel)}) {keep}
      ORDER BY time, h6)
      TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)""")
    subprocess.run(["rclone", "copyto", out, f"nrp:{hexdir}/{cell}/data_0.parquet"], check=True)
    os.remove(out)
    if new:  # only the daily files read above, so a file added meanwhile is kept for next time
        lst = os.path.join(work, f"{cell}.txt")
        open(lst, "w").write("\n".join(parts[cell]) + "\n")
        subprocess.run(["rclone", "delete", "--files-from-raw", lst, f"nrp:{hexdir}/"], check=True)

with ThreadPoolExecutor(2) as pool:
    list(pool.map(one, cells))
EOF
}

compact_blob() {  # folds the blob summary's one-row daily files into ne-pacific-blob/data_0.parquet
  rclone lsf -R --files-only "nrp:$BUCKET/$PREFIX/ne-pacific-blob/" > "$WORK/blob.txt"
  python3 - "$WORK/blob.txt" "$WORK" "$PREFIX" <<'EOF'
import os, re, subprocess, sys
import duckdb
listing, work, prefix = sys.argv[1:4]
blobdir = f"{os.environ.get('BUCKET', 'public-coral-reef-watch')}/{prefix}/ne-pacific-blob"
files = [l.strip() for l in open(listing)]
# part-YYYYMMDD.parquet, or date=YYYY-MM-DD/data_0.parquet as the first backfill wrote them
new = [f"s3://{blobdir}/{f}" for f in files if re.fullmatch(r"part-\d{8}\.parquet|date=[\d-]{10}/data_0\.parquet", f)]
if not new:
    sys.exit()
con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs")
con.execute(f"""CREATE SECRET (TYPE S3, KEY_ID '{os.environ["AWS_ACCESS_KEY_ID"]}',
  SECRET '{os.environ["AWS_SECRET_ACCESS_KEY"]}', ENDPOINT '{os.environ["AWS_S3_ENDPOINT"]}',
  USE_SSL false, URL_STYLE 'path')""")
sel = [f"SELECT * FROM read_parquet({new!r}, hive_partitioning=false)"]
if "data_0.parquet" in files:
    sel.append(f"""SELECT * FROM read_parquet('s3://{blobdir}/data_0.parquet')
      WHERE date NOT IN (SELECT date FROM read_parquet({new!r}, hive_partitioning=false))""")
out = os.path.join(work, "blob.parquet")
con.execute(f"COPY (SELECT * FROM ({' UNION ALL BY NAME '.join(sel)}) ORDER BY date) TO '{out}' (FORMAT PARQUET)")
subprocess.run(["rclone", "copyto", out, f"nrp:{blobdir}/data_0.parquet"], check=True)
lst = os.path.join(work, "blob-new.txt")
open(lst, "w").write("".join(f[len(f"s3://{blobdir}/"):] + "\n" for f in new))
subprocess.run(["rclone", "delete", "--files-from-raw", lst, f"nrp:{blobdir}/"], check=True)
print(f"ne-pacific-blob: folded {len(new)} days into data_0.parquet")
EOF
}

d=$START
while [[ ! "$d" > "$END" ]]; do
  ymd=${d//-/}
  for p in "${PRODUCTS[@]}"; do
    cog="$PREFIX/$p/cog/$p-$ymd.tif"
    if rclone lsf "nrp:$BUCKET/$cog" 2>/dev/null | grep -q .; then
      continue
    fi
    name=$(src_name "$p" "$ymd")
    url="$SRC/$p/${ymd:0:4}/$name"
    f="$WORK/$name"
    code=$(curl -sS --retry 5 --retry-all-errors -w '%{http_code}' -o "$f" "$url" || true)
    if [ "$code" != 200 ]; then
      echo "$d $p: not available upstream (HTTP $code), skipping"
      rm -f "$f"; continue
    fi
    echo "$d $p: $(stat -c %s "$f") bytes"

    # Provenance sidecar: source URL, access time, upstream Last-Modified, size, checksum.
    lastmod=$(curl -sSI --retry 5 --retry-all-errors "$url" | tr -d '\r' | sed -n 's/^[Ll]ast-[Mm]odified: //p')
    printf '{"source_url":"%s","accessed":"%s","upstream_last_modified":"%s","bytes":%s,"sha256":"%s"}\n' \
      "$url" "$(date -u +%FT%TZ)" "$lastmod" "$(stat -c %s "$f")" "$(sha256sum "$f" | cut -d' ' -f1)" \
      > "$f.json"
    rclone copyto "$f" "nrp:$BUCKET/raw/daily/$p/$name"
    rclone copyto "$f.json" "nrp:$BUCKET/raw/daily/$p/$name.json"

    # A rerun of a day must replace its daily files, not add to them: mdim splits a cell's day into
    # part-t<day>-0, -1, ... as it sees fit, and a file left from an earlier split repeats rows.
    rclone delete --include "h0=*/part-t$ymd-*.parquet" "nrp:$BUCKET/$PREFIX/$p/hex/"

    # Eight batches of h0 grid positions (0-121): the whole grid in one call peaks above 4.5 GiB
    # in DuckDB, and the densest quarter-grid batches exceeded a 1800MiB cap. Batches write
    # disjoint h0 partitions.
    for s0 in $(seq 0 16 121); do
      batch=$(seq -s, "$s0" $((s0 + 15 > 121 ? 121 : s0 + 15)))
      cng-datasets mdim --input "$f" --variable "${VAR[$p]}" \
        --output-parquet "s3://$BUCKET/$PREFIX/$p/hex/" \
        --resolution 6 --parent-resolutions 0 --hex-resampling "${REDUCER[$p]}" \
        --fan-out time --unit-index "$ymd" --h0-subset "$batch"
    done

    if [ "$p" = ssta ]; then
      blob_summary "$ymd" "$d"
    fi

    gdal_translate -q -of COG -a_srs EPSG:4326 -co COMPRESS=DEFLATE -co PREDICTOR=2 \
      "NETCDF:\"$f\":${VAR[$p]}" "$WORK/$p-$ymd.tif"
    rclone copyto "$WORK/$p-$ymd.tif" "nrp:$BUCKET/$cog"
    rm -f "$f" "$f.json" "$WORK/$p-$ymd.tif"
  done
  d=$(date -u -d "$d +1 day" +%F)
done

if [ "$COMPACT" = 1 ]; then
  for p in "${PRODUCTS[@]}"; do compact "$p"; done
  if [[ "${CELL_SHARD:-0/1}" == 0/* ]]; then compact_blob; fi  # one shard only
fi

if [ "$PRUNE" = 1 ]; then
  cutoff=$CUTOFF
  echo "Pruning daily outputs dated before $cutoff"
  for p in "${PRODUCTS[@]}"; do
    # Only names carrying an 8-digit date strictly before the cutoff are listed.
    rclone lsf -R --files-only "nrp:$BUCKET/$PREFIX/$p/" | python3 -c '
import re, sys
cut = sys.argv[1]
for line in sys.stdin:
    m = re.search(r"(?:-|part-t|chunk-)(\d{8})(?:-\d+)?\.(?:tif|parquet)$", line.strip())
    if m and m.group(1) < cut:
        print(line.strip())' "$cutoff" > "$WORK/old-$p.txt"
    rclone lsf --files-only "nrp:$BUCKET/raw/daily/$p/" | python3 -c '
import re, sys
cut = sys.argv[1]
for line in sys.stdin:
    m = re.search(r"_(\d{8})\.nc(?:\.json)?$", line.strip())
    if m and m.group(1) < cut:
        print(line.strip())' "$cutoff" > "$WORK/old-raw-$p.txt"
    echo "$p: $(wc -l < "$WORK/old-$p.txt") outputs, $(wc -l < "$WORK/old-raw-$p.txt") raw files"
    [ -s "$WORK/old-$p.txt" ] && rclone delete --files-from-raw "$WORK/old-$p.txt" "nrp:$BUCKET/$PREFIX/$p/"
    [ -s "$WORK/old-raw-$p.txt" ] && rclone delete --files-from-raw "$WORK/old-raw-$p.txt" "nrp:$BUCKET/raw/daily/$p/"
  done
  # Keep each rolling collection's STAC temporal start at the oldest day still published.
  # (The ne-pacific-blob table is not pruned, so its collection keeps its own start.)
  start=$(date -u -d "$cutoff" +%F)
  for c in "${PRODUCTS[@]/#/$PREFIX/}" "$PREFIX"; do
    stac="nrp:$BUCKET/$c/stac-collection.json"
    rclone cat "$stac" > "$WORK/stac.json" 2>/dev/null || continue
    python3 - "$WORK/stac.json" "$start" <<'EOF'
import json, sys
from datetime import datetime, timezone
path, start = sys.argv[1], sys.argv[2]
d = json.load(open(path))
interval = d["extent"]["temporal"]["interval"][0]
if interval[0] and interval[0][:10] < start:
    interval[0] = f"{start}T00:00:00Z"
    d["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
json.dump(d, open(path, "w"), indent=2, ensure_ascii=False)
EOF
    rclone copyto "$WORK/stac.json" "$stac"
  done
fi
echo "done: $START .. $END"
