#!/bin/bash
# One Ocean Tipping Points layer per index (#851); see k8s/ocean-tipping-points/ocean-tipping-points-stage.yaml.
set -euo pipefail
layer=$(sed -n "$((JOB_COMPLETION_INDEX + 1))p" /scripts/layers.txt)
short=${layer#hi_otp_all_}
R="nrp:$BUCKET/raw/ocean-tipping-points"
if rclone lsf "$R/$layer.tif.json" 2>/dev/null | grep -q .; then echo "$layer done, skipping"; exit 0; fi
mkdir -p /tmp/w && cd /tmp/w
python3 -I /scripts/stage.py "$layer" /tmp/w
rclone copyto "$layer.tif" "$R/$layer.tif"
rclone copyto "$short-cog.tif" "nrp:$BUCKET/ocean-tipping-points/$short-cog.tif"
rclone copyto "$layer.tif.json" "$R/$layer.tif.json"      # last: marks the layer done
echo "$layer staged"
