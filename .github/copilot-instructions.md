## Start Here

Read `AGENTS.md` before doing anything. It explains the workflow for processing datasets.

This repo has **no source code**. Do not look for Python modules to study. The `cng-datasets` CLI is installed via pip and used as a black box — see its [README](https://github.com/boettiger-lab/datasets#readme) for CLI docs.

## Repository Structure

- `AGENTS.md` — complete instructions for processing datasets
- `DATASET_DOCUMENTATION_WORKFLOW.md` — how to create STAC metadata after processing
- `todo.md` — dataset completion tracker
- `catalog/` — per-dataset configs: k8s YAML, STAC metadata, processing notes

## Local Environment

The `cng-datasets` CLI is used to generate k8s job YAML files (not for processing data locally).

**Setup:**
```bash
uv venv
source .venv/bin/activate
uv pip install git+https://github.com/boettiger-lab/datasets.git
```

Do not run data processing commands (vector, raster, repartition) locally — those run inside k8s pods.

## Kubernetes

- `kubectl` is pre-configured for the NRP Nautilus cluster, namespace `biodiversity`
- Secrets `aws` and `rclone-config` are already set up in the namespace
- All jobs use `priorityClassName: opportunistic` (preemptible)
- The generated YAML handles all k8s configuration — you just apply it

## S3 Storage

This cluster uses Ceph S3 (not AWS). The `cng-datasets` tool handles all S3 configuration automatically in the generated k8s jobs.

For **local read-only access** to public data:
```
https://s3-west.nrp-nautilus.io/<bucket>/<path>
```
Use path-style URLs, not virtual-hosted-style. No credentials needed for public buckets.

For `rclone`, the remote name is `nrp`:
```
rclone ls nrp:<bucket>/
```

You do not need to know about internal S3 endpoints — the generated jobs handle this.

## GDAL

For inspecting remote files locally, use VSI-style paths:
```bash
ogrinfo /vsicurl/https://s3-west.nrp-nautilus.io/<bucket>/raw/<file>.gdb
```
