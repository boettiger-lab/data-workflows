#!/usr/bin/env bash
# #735: for each staged PMTiles (staging/735-fid/<key>), back up the live file to
# staging/735-nofid-backup/<key>, then copy the staged file over the live href.
# Server-side rclone copies; run only after the footer check on the staged file.
#   ./swap.sh                 # all 21
#   ./swap.sh public-hazard:flood-hazard.pmtiles   # one
set -euo pipefail
cd "$(dirname "$0")"
if [ $# -gt 0 ]; then ITEMS=("$@"); else
  mapfile -t ITEMS < <(python3 -c "from assets import ASSETS; [print(f\"{a['bucket']}:{a['key']}\") for a in ASSETS]")
  ITEMS+=("public-hazard:flood-hazard.pmtiles")
fi
for it in "${ITEMS[@]}"; do
  b=${it%%:*}; k=${it#*:}
  rclone lsf "nrp:$b/staging/735-fid/$k" | grep -q . || { echo "MISSING staged $b/$k"; exit 1; }
  rclone lsf "nrp:$b/staging/735-nofid-backup/$k" | grep -q . || \
    rclone copyto "nrp:$b/$k" "nrp:$b/staging/735-nofid-backup/$k"
  rclone copyto "nrp:$b/staging/735-fid/$k" "nrp:$b/$k"
  echo "swapped $b/$k"
done
