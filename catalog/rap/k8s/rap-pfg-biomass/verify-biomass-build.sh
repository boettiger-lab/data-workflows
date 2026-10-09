#!/usr/bin/env bash
# Acceptance criteria from #677, run against the source rather than the collection's metadata.
set -uo pipefail
SP=$(mktemp -d); trap 'rm -rf "$SP"' EXIT
HERE=$(cd "$(dirname "$0")" && pwd)
VERIFY_STAC="$HERE/../../../../scripts/verify-stac.py"   # supplies the duckdb-geo MCP client
UP="https://rangeland.ntsg.umt.edu/data/rap/rap-vegetation-biomass/v3/vegetation-biomass-v3-2024.tif"
OUR="https://s3-west.nrp-nautilus.io/public-rap/rap-pfg-biomass-cog.tif"

echo "=== 1. COG band count (cache-busted) ==="
curl -s --max-time 120 "https://titiler.nrp-nautilus.io/cog/info?url=$(python3 -c "import urllib.parse;print(urllib.parse.quote('$OUR?cb='+__import__('time').strftime('%s'),safe=''))")" \
 | python3 -c "import json,sys;d=json.load(sys.stdin);print('  count:',d.get('count'),'(expect 1)  dtype:',d.get('dtype'))"

echo "=== 2. old key gone ==="
echo "  perennial-biomass-2024-cog.tif -> HTTP $(curl -s -o /dev/null -w '%{http_code}' --max-time 60 https://s3-west.nrp-nautilus.io/public-rap/perennial-biomass-2024-cog.tif)"

echo "=== 3. upstream band 1 / band 2 vs our COG (TiTiler zonal mean), windows wholly inside one h0 cell ==="
# Chosen to sit inside a single base cell, so the comparison is not diluted by a partition
# that is present in one source and absent in the other.
for w in "-99.0 -98.0 39.0 40.0 Kansas" "-118.0 -117.0 40.0 41.0 Nevada"; do
  set -- $w
  cat > $SP/w.json <<JSON
{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[$1,$3],[$2,$3],[$2,$4],[$1,$4],[$1,$3]]]}}
JSON
  for spec in "band1:$UP:1" "band2:$UP:2" "ourcog:$OUR:1"; do
    lbl=${spec%%:*}; rest=${spec#*:}; url=${rest%:*}; bidx=${rest##*:}
    m=$(curl -s --max-time 300 -X POST "https://titiler.nrp-nautilus.io/cog/statistics?url=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=''))" "$url")&max_size=512&bidx=$bidx" \
      -H "Content-Type: application/json" -d @$SP/w.json \
      | python3 -c "
import json,sys
try:
  d=json.load(sys.stdin); st=d.get('properties',d).get('statistics',{}); k=list(st)[0]
  print(f\"{st[k]['mean']:.1f}\")
except Exception: print('ERR')")
    echo "  $5 $lbl: $m"
  done
done

echo "=== 4. hex vs the same windows (duckdb-geo MCP) ==="
# Plain mean of the res-10 cells whose centres fall in the window. Cells are near-equal-area over
# a 1-degree window, so this is comparable to the band-2 zonal mean above. Each window is checked
# to sit inside a single h0 cell (all four corners map to the same h0), and the query reads only
# that partition. Check n before trusting m: ~600,000 cells is a full 1x1 degree window; a much
# smaller n means the window reaches into a partition that is missing.
python3 - "$VERIFY_STAC" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("verify_stac", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
mcp = m.MCPClient()
HEX = "s3://public-rap/rap-pfg-biomass/hex/h0=*/data_0.parquet"
for name, w, e, s, n in [("Kansas", -99.0, -98.0, 39.0, 40.0), ("Nevada", -118.0, -117.0, 40.0, 41.0)]:
    corners = mcp.query(
        "SELECT count(DISTINCT h3_latlng_to_cell(lat, lng, 0)) k FROM (VALUES "
        f"({s},{w}),({s},{e}),({n},{w}),({n},{e})) t(lat, lng)")[0]["k"]
    if int(corners) != 1:
        print(f"  {name}: window spans {corners} h0 cells -- pick another window"); continue
    r = mcp.query(
        f"SELECT count(*) n, round(avg(biomass), 1) m FROM read_parquet('{HEX}', hive_partitioning=true) "
        f"WHERE h0 = h3_latlng_to_cell({(s+n)/2}, {(w+e)/2}, 0) "
        f"AND h3_cell_to_lng(h10) BETWEEN {w} AND {e} AND h3_cell_to_lat(h10) BETWEEN {s} AND {n}")[0]
    print(f"  {name} hex: {r['m']}  (n={r['n']} cells)")
PY
