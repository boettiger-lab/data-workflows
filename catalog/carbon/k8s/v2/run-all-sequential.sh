#!/usr/bin/env bash
# Run all 10 remaining v2 carbon hex workflows sequentially.
# vulnerable-carbon-2024 already complete; this handles the rest.
# Usage: nohup bash catalog/carbon/k8s/v2/run-all-sequential.sh > /tmp/carbon-v2.log 2>&1 &

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }

apply_and_wait() {
  local dataset=$1
  LOG "=== Starting ${dataset} ==="
  kubectl apply \
    -f "${SCRIPT_DIR}/${dataset}/configmap.yaml" \
    -f "${SCRIPT_DIR}/${dataset}/workflow.yaml"
  kubectl wait "job/${dataset}-workflow" \
    --for=condition=complete \
    --timeout=7200s \
    && LOG "DONE: ${dataset}" \
    || { LOG "FAILED: ${dataset}"; exit 1; }
}

for dataset in \
  irrecoverable-carbon-2024 \
  irrecoverable-carbon-2023 \
  irrecoverable-carbon-2022 \
  irrecoverable-carbon-2018 \
  irrecoverable-carbon-2010 \
  manageable-carbon-2024 \
  manageable-carbon-2018 \
  manageable-carbon-2010 \
  vulnerable-carbon-2018 \
  vulnerable-carbon-2010; do
  apply_and_wait "${dataset}"
done

LOG "All 10 v2 carbon hex workflows complete."
