#!/usr/bin/env bash
# Run the #440 global hex in order: height hex, height merge, sd hex, sd merge. Idempotent: a step
# whose Job already reports Complete is skipped, a running one is waited on, a missing one is
# applied. Safe to re-run from any session after an interruption. Deletes pods whose container has
# waited more than 5 minutes (bad node; nrp-kubernetes skill).
set -uo pipefail
G="$(cd "$(dirname "$0")" && pwd)/global"
NS=geo-workflows
unstick() {
  kubectl -n $NS get pods -l job-name="$1" -o json | python3 -c '
import json, sys, datetime as d
now = d.datetime.now(d.timezone.utc)
for p in json.load(sys.stdin)["items"]:
    cs = (p["status"].get("containerStatuses") or [{}])[0].get("state", {})
    age = (now - d.datetime.fromisoformat(p["metadata"]["creationTimestamp"].replace("Z", "+00:00"))).total_seconds()
    if "waiting" in cs and age > 300: print(p["metadata"]["name"])' |
  while read -r p; do echo "$(date -u +%H:%M) stuck pod $p, deleting"; kubectl -n $NS delete pod "$p" --ignore-not-found >/dev/null; done
}
state() { kubectl -n $NS get job "$1" -o jsonpath='{range .status.conditions[?(@.status=="True")]}{.type} {end}' 2>&1 || true; }
step() {  # step <job> <manifest>
  local s; s=$(state "$1")
  case "$s" in
    *Complete*) echo "$(date -u +%H:%M) already complete $1"; return 0 ;;
    *Failed*)   echo "$(date -u +%H:%M) $1 is Failed; inspect before re-running"; return 1 ;;
    *NotFound*) kubectl apply -n $NS -f "$2" >/dev/null || return 1; echo "$(date -u +%H:%M) started $1" ;;
    *)          echo "$(date -u +%H:%M) waiting on running $1" ;;
  esac
  while :; do
    unstick "$1"; s=$(state "$1")
    case "$s" in
      *Complete*) echo "$(date -u +%H:%M) complete $1 $(kubectl -n $NS get job "$1" -o jsonpath='succeeded={.status.succeeded} failed={.status.failed} failedIndexes={.status.failedIndexes}')"; return 0 ;;
      *Failed*|*NotFound*) echo "$(date -u +%H:%M) FAILED $1: $s"; return 1 ;;
    esac
    sleep 60
  done
}
for L in height sd; do
  step canopy-height-2020-$L-hex "$G/$L/canopy-height-2020-$L-hex.yaml" || exit 1
  step canopy-height-2020-$L-merge "$G/$L/canopy-height-2020-$L-merge.yaml" || exit 1
done
echo "GLOBAL-DONE"
