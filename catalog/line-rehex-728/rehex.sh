#!/usr/bin/env bash
# HAND-ROLLED driver (data-workflows#728): re-hex an already-published line dataset without
# re-running convert or PMTiles. The flat GeoParquet and PMTiles are correct and stay; only the
# hex was built with the pre-0.8.1 line buffer. Several recipes convert from a raw/ source that
# was deleted after their build, so the generated orchestrator (workflow.yaml) cannot be reused.
#
# Runs the generated manifests from <recipe-dir> in the orchestrator's own order and with its
# own plan -> hex sizing: plan, hex (completions from the plan), repartition, checksums.
#
#   catalog/line-rehex-728/rehex.sh <recipe-dir> <job-prefix>
#   e.g. catalog/line-rehex-728/rehex.sh catalog/american-rivers/k8s/campaigns american-rivers-campaigns
set -euo pipefail
dir=$1 p=$2 ns=geo-workflows

wait_job() {  # wait_job <job> <timeout-s>; fails on Failed, returns on Complete
  local job=$1 t=$2 waited=0 state
  while :; do
    state=$(kubectl get job "$job" -n $ns -o jsonpath='{.status.conditions[?(@.status=="True")].type}' 2>/dev/null || true)
    case "$state" in
      *Failed*) echo "FAILED: $job"; kubectl -n $ns get job "$job" -o jsonpath='{.status}{"\n"}'; return 1 ;;
      *Complete*) echo "done: $job"; return 0 ;;
    esac
    [ "$waited" -ge "$t" ] && { echo "TIMEOUT: $job"; return 1; }
    sleep 30; waited=$((waited + 30))
  done
}

for j in plan hex repartition checksums; do
  kubectl -n $ns delete job "$p-$j" --ignore-not-found --wait=true >/dev/null
done
kubectl apply -n $ns -f "$dir/configmap.yaml" >/dev/null

kubectl apply -n $ns -f "$dir/$p-plan.yaml"
wait_job "$p-plan" 7200
msg=$(kubectl get pods -n $ns -l job-name="$p-plan" \
  -o jsonpath='{.items[*].status.containerStatuses[0].state.terminated.message}')
chunks=$(echo "$msg" | tr ' ' '\n' | sed -n 's/^chunks=\([0-9][0-9]*\)$/\1/p' | tail -1)
[ -n "$chunks" ] && [ "$chunks" -ge 1 ] || { echo "plan reported no chunk count: '$msg'"; exit 1; }
par=$(( chunks < 50 ? chunks : 50 ))
echo "plan: $chunks hex chunks, parallelism $par"
kubectl patch --local -f "$dir/$p-hex.yaml" --type merge \
  -p "{\"spec\":{\"completions\":$chunks,\"parallelism\":$par}}" -o yaml | kubectl apply -n $ns -f -
wait_job "$p-hex" 172800

kubectl apply -n $ns -f "$dir/$p-repartition.yaml"
wait_job "$p-repartition" 3600
kubectl apply -n $ns -f "$dir/$p-checksums.yaml"
wait_job "$p-checksums" 3600
echo "REHEX OK: $p"
