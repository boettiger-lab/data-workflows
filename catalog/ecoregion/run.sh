#!/bin/bash

# scripts/setup-venv.sh creates .venv at the repo root, two levels up from here.
source ../../.venv/bin/activate

# Clean up
kubectl delete -n geo-workflows --ignore-not-found -f k8s/configmap.yaml

cng-datasets workflow \
  --dataset ecoregion \
  --source-url /vsicurl/https://s3-west.nrp-nautilus.io/public-ecoregion/ecoregions.gdb \
  --bucket public-ecoregion \
  --namespace geo-workflows \
  --h3-resolution 8 \
  --hex-memory 64Gi \
  --max-completions 200 \
  --max-parallelism 50 \
  --parent-resolutions "9,8,0"

# Apply all workflow files (safe to re-run)
kubectl apply -n geo-workflows -f k8s/configmap.yaml
kubectl apply -n geo-workflows -f k8s/workflow.yaml

sleep 4

kubectl get jobs -n geo-workflows
