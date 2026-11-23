#!/bin/bash
# #944: run the three regenerated workflows one at a time (AGENTS.md: one hex workflow at a time).
set -uo pipefail
cd "$(dirname "$0")/../../../.."
for d in final proposed species-ranges; do
  dir=catalog/usfws/k8s/$d
  [ -d "$dir" ] || dir=catalog/usfws/k8s/$d
  j=$(grep -h "^  name:" $dir/workflow.yaml | head -1 | awk '{print $2}')
  kubectl delete job -n geo-workflows "$j" --ignore-not-found
  kubectl apply -n geo-workflows -f $dir/configmap.yaml -f $dir/workflow.yaml
  until c=$(kubectl get job -n geo-workflows "$j" -o jsonpath='{range .status.conditions[?(@.status=="True")]}{.type} {end}'); \
        [[ "$c" == *Complete* || "$c" == *Failed* ]]; do sleep 60; done
  echo "$(date -u +%T) $j: $c"
  [[ "$c" == *Complete* ]] || exit 1
done
