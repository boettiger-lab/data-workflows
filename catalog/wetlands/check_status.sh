#!/bin/bash
# Quick status check for wetlands job

echo "=== Job Status ==="
kubectl get jobs -n biodiversity -l app=wetlands -o wide

echo ""
echo "=== Detailed Progress ==="
kubectl get job -n biodiversity -l app=wetlands -o json | jq -r '.items[] | "\(.metadata.name): \(.status.succeeded // 0)/\(.spec.completions) succeeded, \(.status.failed // 0) failed, \(.status.active // 0) active"'

echo ""
echo "=== Failed Indexes (if any) ==="
kubectl get job -n biodiversity -l app=wetlands -o json | jq -r '.items[] | select(.status.failedIndexes != null) | "\(.metadata.name): \(.status.failedIndexes)"'

echo ""
echo "=== Recent Pod Failures (OOM or other) ==="
kubectl get pods -n biodiversity -l app=wetlands --field-selector=status.phase=Failed -o json | jq -r '.items[] | "\(.metadata.labels.tier // "?")/\(.metadata.annotations["batch.kubernetes.io/job-completion-index"]): \(.status.containerStatuses[0].state.terminated.reason // "Unknown")"' | head -20
