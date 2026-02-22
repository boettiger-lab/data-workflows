#!/bin/bash
# Run this AFTER all individual COG jobs complete (10 datasets - irrecoverable-carbon-2010 is skipped).
# See irrecoverable-2010-gdal-bug.md for why 2010 irrecoverable is excluded.
#
# Check preprocessing status first:
#   kubectl get jobs | grep carbon-v2-cog
#   rclone ls nrp:public-carbon/v2/cogs/   # should show 10 files
#
# Once all 10 COGs are in S3, run this script.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DATASETS=(
  irrecoverable-carbon-2024
  irrecoverable-carbon-2023
  irrecoverable-carbon-2022
  irrecoverable-carbon-2018
  vulnerable-carbon-2024
  vulnerable-carbon-2018
  vulnerable-carbon-2010
  manageable-carbon-2024
  manageable-carbon-2018
  manageable-carbon-2010
)

for dataset in "${DATASETS[@]}"; do
  dir="${SCRIPT_DIR}/${dataset}"
  echo "=== Applying workflow: $dataset ==="
  kubectl apply \
    -f "${dir}/configmap.yaml" \
    -f "${dir}/workflow.yaml"
  echo "  Started: ${dataset}-workflow"
done

echo ""
echo "All 10 hex workflows submitted. Monitor with:"
echo "  kubectl get jobs | grep -E 'irrecoverable|vulnerable|manageable'"
echo "  kubectl logs job/{name}-workflow"
