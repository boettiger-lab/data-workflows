#!/usr/bin/env bash
# Acceptance criteria from #677, run against the source rather than the collection's metadata.
set -uo pipefail
SP=/tmp/claude-1000/-home-jovyan-data-workflows/24cc8516-56e2-4d76-b670-6315fcc7bd38/scratchpad
UP="https://rangeland.ntsg.umt.edu/data/rap/rap-vegetation-biomass/v3/vegetation-biomass-v3-2024.tif"
OUR="https://s3-west.nrp-nautilus.io/public-rap/rap-pfg-biomass-cog.tif"

echo "=== 1. COG band count (cache-busted) ==="
curl -s --max-time 120 "https://titiler.nrp-nautilus.io/cog/info?url=$(python3 -c "import urllib.parse;print(urllib.parse.quote('$OUR?cb='+__import__('time').strftime('%s'),safe=''))")" \
 | python3 -c "import json,sys;d=json.load(sys.stdin);print('  count:',d.get('count'),'(expect 1)  dtype:',d.get('dtype'))"

echo "=== 2. old key gone ==="
echo "  perennial-biomass-2024-cog.tif -> HTTP $(curl -s -o /dev/null -w '%{http_code}' --max-time 60 https://s3-west.nrp-nautilus.io/public-rap/perennial-biomass-2024-cog.tif)"

echo "=== 3. hex vs upstream band 2, windows wholly inside one h0 cell ==="
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
