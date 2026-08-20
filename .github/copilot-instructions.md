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

Detailed reference guides are in `.claude/skills/`. **Do not read these proactively** — load a skill only when the task requires it:

| Skill file | When to load |
|---|---|
| `.claude/skills/stac-authoring/SKILL.md` | Writing or editing any `stac-collection.json` or dataset README |
| `.claude/skills/raster-hexing/SKILL.md` | Ingesting or re-hexing a GeoTIFF/COG — resolution, reducer, mosaicking |
| `.claude/skills/hex-tuning/SKILL.md` | A hex job OOMs, or choosing native/parent H3 resolutions and chunk sizes |
| `.claude/skills/job-troubleshooting/SKILL.md` | A job fails, hangs, or a published parquet will not read |
| `.claude/skills/dataset-recipes/SKILL.md` | Starting an ingest that resembles a worked example |
