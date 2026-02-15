#!/bin/bash
source ../.venv/bin/activate
# Clean up
kubectl delete -f k8s/configmap.yaml


cng-datasets workflow \
  --dataset amphibians \
  --source-url https://s3-west.nrp-nautilus.io/public-iucn/raw/rangemaps/AMPHIBIANS.zip \
  --bucket public-iucn \
  --h3-resolution 10 \
  --hex-memory 24Gi \
  --max-completions 200 \
  --max-parallelism 50 \
  --parent-resolutions "9,8,0"

 # Apply all workflow files (safe to re-run)
 kubectl apply -f k8s/configmap.yaml
 kubectl apply -f k8s/workflow.yaml

sleep(4)

kubectl get jobs

