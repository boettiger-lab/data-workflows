#!/usr/bin/env bash
# Sequential carbon hex workflow runner
# Run with: nohup bash catalog/carbon/k8s/v2/run-remaining-sequential.sh > /tmp/carbon-seq.log 2>&1 &

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }

wait_for_hex() {
  local dataset=$1
  LOG "Waiting for hex job: ${dataset}-hex ..."
  kubectl wait job/${dataset}-hex \
    --for=condition=complete \
    --timeout=259200s \
    && LOG "DONE: ${dataset}" \
    || LOG "WARNING: ${dataset}-hex did not complete cleanly"
}

apply_and_wait() {
  local dataset=$1
  if kubectl get job/${dataset}-hex &>/dev/null; then
    LOG "${dataset}-hex already exists, waiting..."
  else
    LOG "Applying: ${dataset}"
    kubectl apply \
      -f "${SCRIPT_DIR}/${dataset}/configmap.yaml" \
      -f "${SCRIPT_DIR}/${dataset}/workflow.yaml"
  fi
  wait_for_hex "${dataset}"
}

# Wait for the currently-running vulnerable-carbon-2010 hex job
wait_for_hex vulnerable-carbon-2010

# Submit and wait for the 3 manageable datasets one at a time
for dataset in manageable-carbon-2024 manageable-carbon-2018 manageable-carbon-2010; do
  apply_and_wait "${dataset}"
done

# Step 3: Submit the move-to-v2 job
LOG "All hex workflows complete. Submitting move-hex-to-v2 job..."
kubectl apply -f "${SCRIPT_DIR}/move-hex-to-v2.yaml"
kubectl wait job/carbon-v2-move-hex-2 \
  --for=condition=complete \
  --timeout=86400s \
  && LOG "DONE: move-hex-to-v2" \
  || LOG "WARNING: move-hex-to-v2 did not complete cleanly"

LOG "All done!"
