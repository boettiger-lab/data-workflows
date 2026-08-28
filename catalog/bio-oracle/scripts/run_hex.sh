#!/usr/bin/env bash
# Submit the Bio-ORACLE hex jobs in batches (data-workflows #53).
# Batch of 3 x parallelism 61 = 183 pods, under the 200-pod good-practice target.
set -uo pipefail
cd "$(dirname "$0")/../../.."
export PATH="$HOME/.local/bin:$PATH"
NS=geo-workflows
BATCH=${BATCH:-3}

LAYERS="$*"
i=0
for spec in $LAYERS; do
  PREFIX=${spec%%/*}; NAME=${spec##*/}
  Y="catalog/bio-oracle/k8s/$PREFIX/$NAME/$PREFIX-$NAME-hex.yaml"
  kubectl apply -n $NS -f "$Y" >/dev/null 2>&1 && echo "submitted $PREFIX/$NAME"
  i=$((i+1))
  if [ $((i % BATCH)) -eq 0 ]; then
    echo "--- waiting for batch (through $PREFIX/$NAME) ---"
    for spec2 in $LAYERS; do
      P2=${spec2%%/*}; N2=${spec2##*/}
      kubectl -n $NS get job "$P2-$N2-hex" >/dev/null 2>&1 && \
        kubectl -n $NS wait --for=condition=complete --timeout=3600s "job/$P2-$N2-hex" >/dev/null 2>&1
    done
  fi
done
echo "--- final wait ---"
for spec in $LAYERS; do
  PREFIX=${spec%%/*}; NAME=${spec##*/}
  kubectl -n $NS wait --for=condition=complete --timeout=3600s "job/$PREFIX-$NAME-hex" >/dev/null 2>&1
  ST=$(kubectl -n $NS get job "$PREFIX-$NAME-hex" -o jsonpath='{.status.succeeded}/{.status.conditions[?(@.type=="Complete")].status}/fail={.status.failedIndexes}' 2>/dev/null)
  echo "RESULT $PREFIX/$NAME $ST"
done
