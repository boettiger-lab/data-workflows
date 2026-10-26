#!/bin/bash
# Apply the committed ecoregion workflow manifests to geo-workflows.
#
# This script deliberately does NOT regenerate the manifests with `cng-datasets workflow`.
# The YAMLs under k8s/ were hand-tuned after generation (#404): the convert step reads the
# staged raw/ecoregion-src.parquet, the hex job runs 170 chunks of 5 features with per-index
# retries at --parent-resolutions 0, and pmtiles raises `ulimit -n`. Regenerating overwrites
# all of that (the hex job becomes 1 chunk of 1000 features with backoffLimit: 0) without any
# error. Edit the standalone YAMLs and re-sync k8s/configmap.yaml instead (see its header).
set -euo pipefail

cd "$(dirname "$0")"

# The orchestrator applies the job specs embedded in the ConfigMap. Completed Jobs with the
# same names must be deleted first, or `kubectl apply` on them is a no-op.
kubectl delete -n geo-workflows --ignore-not-found job \
  ecoregion-workflow ecoregion-setup-bucket ecoregion-convert \
  ecoregion-pmtiles ecoregion-hex ecoregion-repartition

kubectl apply -n geo-workflows -f k8s/workflow-rbac.yaml
kubectl apply -n geo-workflows -f k8s/configmap.yaml
kubectl apply -n geo-workflows -f k8s/workflow.yaml

sleep 4

kubectl get jobs -n geo-workflows | grep ecoregion || true
