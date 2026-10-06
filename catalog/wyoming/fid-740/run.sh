#!/usr/bin/env bash
# #740: run the 10 regenerated workflows one at a time (one hex fan-out at a time).
# ungulate-migration has no hex by scope: only setup-bucket, convert and pmtiles.
set -euo pipefail
cd "$(dirname "$0")/.."
NS=geo-workflows
wait_job() {  # wait_job <job> <timeout-s>
  local t=0 c
  while [ $t -lt $2 ]; do
    c=$(kubectl -n $NS get job/$1 -o jsonpath='{.status.conditions[*].type}' 2>/dev/null || true)
    case "$c" in *Failed*) echo "FAILED $1"; exit 1;; *Complete*) return 0;; esac
    sleep 30; t=$((t + 30))
  done
  echo "TIMEOUT $1"; exit 1
}
for spec in sage-grouse-priority:sage-grouse-priority/k8s \
            wgfd-elk-crucial:wgfd-elk/crucial/k8s wgfd-elk-seasonal:wgfd-elk/seasonal/k8s \
            wgfd-mule-deer-crucial:wgfd-mule-deer/crucial/k8s wgfd-mule-deer-seasonal:wgfd-mule-deer/seasonal/k8s \
            wgfd-pronghorn-crucial:wgfd-pronghorn/crucial/k8s wgfd-pronghorn-seasonal:wgfd-pronghorn/seasonal/k8s \
            wy-counties:wy-counties/k8s wyoming-places:wyoming-places/k8s; do
  d=${spec%%:*}; dir=${spec#*:}
  kubectl -n $NS delete job $d-workflow --ignore-not-found
  kubectl apply -f $dir/workflow-rbac.yaml -f $dir/configmap.yaml -f $dir/workflow.yaml
  wait_job $d-workflow 14400
  echo "DONE $d"
done
d=ungulate-migration; dir=ungulate-migration/k8s
for s in setup-bucket convert pmtiles; do
  kubectl -n $NS delete job $d-$s --ignore-not-found
  kubectl apply -f $dir/$d-$s.yaml
  wait_job $d-$s 7200
done
echo "DONE $d"
