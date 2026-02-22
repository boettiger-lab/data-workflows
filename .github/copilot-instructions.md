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

## Available Skills

Detailed reference guides are in `skills/`. **Do not read these proactively** — load a skill only when the task requires it:

| Skill file | When to load |
|---|---|
| `skills/nrp-k8s/SKILL.md` | Creating or debugging Kubernetes jobs on NRP Nautilus (priority classes, resource limits, GPU avoidance, namespace quotas) |
| `skills/nrp-s3/SKILL.md` | S3 bucket operations: endpoints, rclone, bucket policies, CORS, DuckDB S3 access, syncing to source.coop |
| `skills/gdal-remote/SKILL.md` | Reading remote geospatial files with GDAL/OGR virtual filesystems, DuckDB spatial, format conversions, Parquet driver availability |
