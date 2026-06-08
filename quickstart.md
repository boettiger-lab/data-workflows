---
title: Quickstart
subtitle: Generate a pipeline on your laptop, run it on the cluster
---

The CLI runs on your laptop and only ever **generates** Kubernetes job manifests.
The cluster does all the processing; your laptop just talks to `kubectl`. Outputs
land on object storage as cloud-native Parquet and derived indexes, described by STAC.

:::{tip} The mental model
You never process data locally. `cng-datasets` turns a dataset description into
job YAML; `kubectl apply` hands that work to the cluster, which autoscales across
many pods.
:::

## 1. Install the CLI

```bash
pip install cng-datasets
```

## 2. Generate a processing pipeline

Point the CLI at a source and describe how it should be indexed. This writes a set
of Kubernetes manifests to `--output-dir` — it does not move any data yet.

```bash
cng-datasets workflow \
  --dataset my-dataset \
  --source-url https://example.com/data.gdb \
  --bucket public-mydata \
  --layer MyLayer \
  --output-dir catalog/mydata/k8s/mylayer
```

## 3. Apply the workflow to the cluster

```bash
# One-time RBAC setup (per cluster/namespace; often already done)
kubectl apply -f catalog/mydata/k8s/mylayer/workflow-rbac.yaml

# Run the workflow
kubectl apply \
  -f catalog/mydata/k8s/mylayer/configmap.yaml \
  -f catalog/mydata/k8s/mylayer/workflow.yaml
```

## 4. Monitor

```bash
kubectl get jobs | grep my-dataset
kubectl logs job/my-dataset-workflow
```

The cluster converts the source, writes the cloud-native outputs to the object
store, and the catalog entry is published alongside them. When it finishes, the
dataset is ready to query at scale — and ready for agents to discover via its STAC
metadata.

:::{seealso} Full documentation
The complete operator's guide — parameter tuning, memory and chunking, multi-layer
and raster sources, troubleshooting — lives in the repository's
[`AGENTS.md`](https://github.com/boettiger-lab/data-workflows/blob/main/AGENTS.md).
:::
