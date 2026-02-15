
cng-datasets raster-workflow \
  --dataset irrecoverable-carbon \
  --source-url s3://public-carbon/cogs/irrecoverable_c_total_2018.tif \
  --bucket public-carbon \
  --h3-resolution 8 \
  --parent-resolutions 0 \
  --value-column carbon

# 2. Submit to cluster
kubectl apply -f k8s/workflow-rbac.yaml
kubectl apply -f k8s/configmap.yaml
