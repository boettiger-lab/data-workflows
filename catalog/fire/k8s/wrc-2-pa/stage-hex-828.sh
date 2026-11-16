#!/bin/bash
# #828: run the HURisk `sum` hex jobs against the STAGED COGs, writing to staging/828/, one domain at
# a time (AGENTS.md: one hex job at a time). The committed *-hex.yaml publish in place; this runs
# them with input and output under s3://public-fire/staging/828/ so the live `mean` layer stays
# whole until swap-828.yaml replaces it after the gates pass.
set -euo pipefail
cd "$(dirname "$0")"
for d in conus ak; do
  j=wrc-2-pa-hurisk-$d-hex
  sed -e "s#s3://public-fire/wrc-2-pa-hurisk-$d-cog.tif#s3://public-fire/staging/828/wrc-2-pa-hurisk-$d-cog.tif#" \
      -e "s#s3://public-fire/wrc-2-pa-hurisk-$d/hex/#s3://public-fire/staging/828/wrc-2-pa-hurisk-$d/hex/#" \
      $j.yaml > /tmp/$j-828.yaml
  grep -q "staging/828/wrc-2-pa-hurisk-$d-cog.tif" /tmp/$j-828.yaml
  grep -q "staging/828/wrc-2-pa-hurisk-$d/hex/" /tmp/$j-828.yaml
  kubectl delete job -n geo-workflows $j --ignore-not-found
  kubectl create -n geo-workflows -f /tmp/$j-828.yaml
  # Stop on Failed as well as Complete: `kubectl wait --for=condition=complete` alone would sit
  # out its whole timeout on a failed job.
  until c=$(kubectl get job -n geo-workflows $j -o jsonpath='{range .status.conditions[?(@.status=="True")]}{.type} {end}'); \
        [[ "$c" == *Complete* || "$c" == *Failed* ]]; do sleep 120; done
  echo "$j: $c"; [[ "$c" == *Complete* ]]
done
