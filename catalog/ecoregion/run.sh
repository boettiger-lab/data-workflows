#!/bin/bash

source ../.venv/bin/activate

# Clean up
kubectl delete -f k8s/configmap.yaml


cng-datasets workflow \
  --dataset ecoregion \
  --source-url /vsicurl/https://s3-west.nrp-nautilus.io/public-ecoregion/raw/ecoregions.gdb \
  --bucket public-ecoregion \
  --h3-resolution 8 \
  --hex-memory 64Gi \
  --max-completions 200 \
  --max-parallelism 50 \
  --parent-resolutions "9,8,0"

 # Apply all workflow files (safe to re-run)
 kubectl apply -f k8s/configmap.yaml
 kubectl apply -f k8s/workflow.yaml

sleep(4)

kubectl get jobs

