#!/bin/bash
# Weekly FracTracker sync, step 1 (#931): download both sheets, vet them, and stage whichever changed.
#
# Writes its decision to the termination message, read by sync.sh:
#   dc=<0|1> ndc=<rows> mo=<0|1> nmo=<rows> snap=<snapshot id>
#
# A changed layer is staged twice: to raw/fractracker/snapshots/<snap>/<layer>/ (kept), and over
# the fixed raw paths the generated convert jobs read. raw/fractracker/CURRENT and
# raw/fractracker/moratoriums/CURRENT name the snapshot behind what is published; gen_stac.py
# cites it.
set -euo pipefail
R=nrp:public-datacenters/raw/fractracker
RC="--retries 10 --low-level-retries 20 --retries-sleep 20s --s3-no-check-bucket"
C="curl -fsSL --retry 8 --retry-all-errors --retry-delay 30 --max-time 600"
DC_SHEET=https://docs.google.com/spreadsheets/d/1JJ6kcVo-NjlAYtznwHOki2DVl4WWV6lhy-eXhFCdKKU
MO_SHEET=https://docs.google.com/spreadsheets/d/1OLJ-EkkxLfX6l4dTBHsIdtn_zRSyOraS02vd3LMfbEI
DICT_SHEET=https://docs.google.com/spreadsheets/d/1KVab4niu8X_GGne3WyyH_CdTP9Bt4uJSe6iK0fu9C48
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SNAP=$(date -u +%Y-%m-%dT%H%MZ)
pip install --quiet openpyxl
mkdir -p /work/dc /work/mo/derived /work/prev && cd /work

manifest() {  # manifest <dir> <files...>: sha256, size, name relative to dir
  local d=$1; shift
  (cd "$d" && for f in "$@"; do echo "$(sha256sum "$f" | cut -d' ' -f1)  $(stat -c %s "$f")  $f"; done)
}
rows() { python3 -I -c "import csv,sys; print(sum(1 for _ in csv.DictReader(open(sys.argv[1], encoding='utf-8'))))" "$1"; }

# ---- download
$C -o dc/data-centers.csv "$DC_SHEET/export?format=csv&gid=386766486"
$C -o dc/data-centers-workbook.xlsx "$DC_SHEET/export?format=xlsx"
$C -o dc/data-dictionary.xlsx "$DICT_SHEET/export?format=xlsx"
$C -o mo/moratoriums-workbook.xlsx "$MO_SHEET/export?format=xlsx"
echo "accessed $NOW"
python3 -I /scripts/sheet_to_csv.py mo/moratoriums-workbook.xlsx "Live Data" mo/moratoriums.csv

# ---- vet against the published snapshot: same columns, known codes, no sharp drop in rows
rclone copyto $R/data-centers.csv prev/dc.csv $RC
rclone copyto $R/moratoriums/moratoriums.csv prev/mo.csv $RC
PDC=$(rows prev/dc.csv); PMO=$(rows prev/mo.csv)
python3 -I /sync/gen_stac.py check dc/data-centers.csv mo/moratoriums.csv \
  --min-dc $((PDC * 9 / 10)) --min-mo $((PMO * 9 / 10))
NDC=$(rows dc/data-centers.csv); NMO=$(rows mo/moratoriums.csv)
same() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$(sha256sum "$2" | cut -d' ' -f1)" ]; }
DC=1; MO=1
same dc/data-centers.csv prev/dc.csv && DC=0
same mo/moratoriums.csv prev/mo.csv && MO=0
echo "data centers: $NDC rows (was $PDC), changed=$DC; moratoriums: $NMO rows (was $PMO), changed=$MO"
msg="dc=$DC ndc=$NDC mo=$MO nmo=$NMO snap=$SNAP"
if [ $DC = 0 ] && [ $MO = 0 ]; then
  echo "$msg" > /dev/termination-log; echo "no change"; exit 0
fi

# ---- first sync only: archive the initial 2026-11-15 staging before the fixed paths are overwritten
if [ -z "$(rclone lsf $R/snapshots/ 2>/dev/null)" ]; then
  echo "archiving the initial staging"
  for f in data-centers.csv data-centers-workbook.xlsx data-dictionary.xlsx MANIFEST.sha256; do
    rclone copyto $R/$f $R/snapshots/2026-11-15T2257Z/data-centers/$f $RC
  done
  rclone copyto $R/moratoriums/MANIFEST.sha256 prev/mo-manifest $RC
  for f in moratoriums.csv moratoriums-workbook.xlsx derived/matched.csv derived/moratoriums-boundaries.parquet; do
    rclone copyto $R/moratoriums/$f $R/snapshots/2026-11-15T2325Z/moratoriums/$f $RC
  done
  grep -E '  (moratoriums\.csv|moratoriums-workbook\.xlsx|derived/.*)$' prev/mo-manifest > prev/mo-snap-manifest
  rclone copyto prev/mo-snap-manifest $R/snapshots/2026-11-15T2325Z/moratoriums/MANIFEST.sha256 $RC
  printf 'accessed=2026-11-15T22:57:10Z\nsnapshot=raw/fractracker/snapshots/2026-11-15T2257Z/data-centers\n' > prev/dc-current
  printf 'accessed=2026-11-15T23:25:24Z\nsnapshot=raw/fractracker/snapshots/2026-11-15T2325Z/moratoriums\n' > prev/mo-current
  rclone copyto prev/dc-current $R/CURRENT $RC
  rclone copyto prev/mo-current $R/moratoriums/CURRENT $RC
fi

# ---- data centers
if [ $DC = 1 ]; then
  D=raw/fractracker/snapshots/$SNAP/data-centers
  manifest dc data-centers.csv data-centers-workbook.xlsx data-dictionary.xlsx > dc/MANIFEST.sha256
  cat dc/MANIFEST.sha256
  rclone copy dc nrp:public-datacenters/$D $RC
  rclone copy dc $R $RC
  printf 'accessed=%s\nsnapshot=%s\n' "$NOW" "$D" > prev/dc-current
  rclone copyto prev/dc-current $R/CURRENT $RC
  echo "staged -> $D"
fi

# ---- moratoriums: match each jurisdiction to its Census 2024 boundary (as fractracker-moratoriums-build.yaml)
if [ $MO = 1 ]; then
  D=raw/fractracker/snapshots/$SNAP/moratoriums
  rclone copy $R/moratoriums mo --include '2024_Gaz_*' --include 'tl_2024_*' $RC
  mkdir -p gaz && for z in mo/2024_Gaz_*_national.zip; do unzip -oq "$z" -d gaz; done
  python3 -I /scripts/match_jurisdictions.py mo/moratoriums.csv gaz mo/derived/matched.csv
  T=https://www2.census.gov/geo/tiger/TIGER2024
  for ss in $(python3 -I -c "import csv; print(' '.join(sorted({r['geoid'][:2] for r in csv.DictReader(open('mo/derived/matched.csv')) if r['geo_level'] == 'county_subdivision'})))"); do
    [ -f mo/tl_2024_${ss}_cousub.zip ] || $C -o mo/tl_2024_${ss}_cousub.zip "$T/COUSUB/tl_2024_${ss}_cousub.zip"
  done
  python3 -I /scripts/attach_boundaries.py mo/derived/matched.csv /work/mo mo/derived/moratoriums-boundaries.parquet
  SNAPFILES="moratoriums.csv moratoriums-workbook.xlsx derived/matched.csv derived/moratoriums-boundaries.parquet"
  manifest mo $SNAPFILES > prev/mo-snap-manifest
  (cd mo && find . -type f ! -name MANIFEST.sha256 | sed 's#^\./##' | sort) > prev/mo-all
  manifest mo $(cat prev/mo-all) > mo/MANIFEST.sha256
  cat prev/mo-snap-manifest
  for f in $SNAPFILES; do rclone copyto mo/$f nrp:public-datacenters/$D/$f $RC; done
  rclone copyto prev/mo-snap-manifest nrp:public-datacenters/$D/MANIFEST.sha256 $RC
  rclone copy mo $R/moratoriums $RC
  printf 'accessed=%s\nsnapshot=%s\n' "$NOW" "$D" > prev/mo-current
  rclone copyto prev/mo-current $R/moratoriums/CURRENT $RC
  echo "staged -> $D"
fi
echo "$msg" > /dev/termination-log
echo "$msg"
