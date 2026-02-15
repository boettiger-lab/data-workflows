# Agent Instructions: Dataset Processing

You are working in a repository that uses `cng-datasets` to process geospatial data into cloud-native formats on a Kubernetes cluster. This document tells you everything you need to know.

## What You Are Doing

You are taking source geospatial data and producing three outputs per dataset:

| Format | File | Use |
|--------|------|-----|
| GeoParquet | `dataset.parquet` | Analytical queries with DuckDB/Polars |
| PMTiles | `dataset.pmtiles` | Web map visualization |
| H3 Hex Parquet | `dataset/hex/h0={cell}/data_0.parquet` | Spatial joins and aggregation |

You do **not** process data locally. You generate Kubernetes jobs that do the processing on the cluster.

## How To Process a Dataset

### Step 1: Identify the source data

Find the public URL to the source data. If it's already uploaded to S3, it will be at:
```
https://s3-west.nrp-nautilus.io/<bucket>/raw/<filename>
```

For multi-layer files (GDB, GPKG), inspect the layers:
```bash
ogrinfo /vsicurl/<source-url>
```

### Step 2: Generate the pipeline

Run `cng-datasets workflow` locally — this only generates YAML files, it does not process data:

```bash
cng-datasets workflow \
  --dataset <name> \
  --source-url <url> \
  --bucket <bucket> \
  --h3-resolution 10 \
  --parent-resolutions "9,8,0" \
  --hex-memory 32Gi \
  --max-completions 200 \
  --max-parallelism 50 \
  --output-dir catalog/<dataset>/k8s/<name>
```

Add `--layer <LayerName>` for multi-layer sources.

**For multi-layer sources**, run one workflow command per spatial layer:
```bash
cng-datasets workflow --dataset mydata/fee --layer FeeLayer ...
cng-datasets workflow --dataset mydata/easement --layer EasementLayer ...
```

The `/` in `--dataset` creates hierarchical S3 paths while using `-` in k8s job names.

### Step 3: Apply to the cluster

```bash
kubectl apply -f catalog/<dataset>/k8s/<name>/<name>-setup-bucket.yaml \
              -f catalog/<dataset>/k8s/<name>/<name>-convert.yaml \
              -f catalog/<dataset>/k8s/<name>/workflow.yaml
```

The workflow orchestrator handles the rest: setup-bucket → convert → pmtiles + hex (parallel) → repartition.

### Step 4: Monitor

```bash
kubectl get jobs | grep <name>       # Job status
kubectl logs job/<name>-convert      # Check conversion
kubectl logs job/<name>-workflow     # Orchestrator log
```

A complete run for a ~300K feature dataset typically takes 1-2 hours.

### Step 5: Document

After processing completes, create:
- `catalog/<dataset>/stac/README.md` — data dictionary, usage examples, citation
- `catalog/<dataset>/stac/stac-collection.json` — STAC metadata

Upload to the bucket:
```bash
rclone copy catalog/<dataset>/stac/README.md nrp:<bucket>/
rclone copy catalog/<dataset>/stac/stac-collection.json nrp:<bucket>/
```

## Common Parameters

| Parameter | Default | When to change |
|-----------|---------|----------------|
| `--h3-resolution` | 10 | Lower (8, 6) for coarser data or very large features |
| `--hex-memory` | 8Gi | Increase to 32Gi or 64Gi for large/complex geometries |
| `--max-completions` | 200 | Keep at 200 for datasets > 50K features |
| `--max-parallelism` | 50 | Reduce if cluster is already busy |
| `--parent-resolutions` | "9,8,0" | Almost never change this |
| `--intermediate-chunk-size` | auto | Decrease if hex pods OOM during unnest step |

## S3 Bucket Layout

```
bucket/
├── raw/                         # Source data
├── dataset.parquet              # GeoParquet
├── dataset.pmtiles              # PMTiles
├── dataset/
│   └── hex/
│       └── h0={cell}/data_0.parquet
├── README.md
└── stac-collection.json
```

## Troubleshooting

**Convert fails → check logs:**
```bash
kubectl logs job/<name>-convert
```

**Hex pods OOM → increase memory or chunks:**
Regenerate with `--hex-memory 64Gi` or `--max-completions 200`, delete failed job, reapply.

**S3 throttling (503 SlowDown):** Transient. Wait a few minutes and retry.

**Workflow stuck → check what step it's on:**
```bash
kubectl logs job/<name>-workflow
kubectl get jobs | grep <name>
```

## What NOT To Do

- **Do not process data locally.** The CLI generates k8s jobs. You apply them. The cluster does the work.
- **Do not modify `cng_datasets/` source code** unless fixing a bug in the tool itself. User workflows only touch `catalog/` and generated YAML.
- **Do not hardcode S3 endpoints or credentials.** The generated jobs handle S3 configuration (internal endpoints, secrets) automatically.
- **Do not exceed 200 completions per job.** This is a hard limit to avoid overwhelming the cluster's etcd.

## Reference: Complete PAD-US Example

PAD-US is a multi-layer GDB with 5 spatial layers. Each was processed with a separate workflow:

```bash
# Upload raw data first (one-time)
rclone copy PADUS4_1Geodatabase.gdb nrp:public-padus/raw/PADUS4_1Geodatabase.gdb -P

# Generate and apply each layer
for args in \
  "padus-4-1/fee PADUS4_1Fee" \
  "padus-4-1/easement PADUS4_1Easement" \
  "padus-4-1/proclamation PADUS4_1Proclamation" \
  "padus-4-1/marine PADUS4_1Marine" \
  "padus-4-1/combined PADUS4_1Combined_Proclamation_Marine_Fee_Designation_Easement"; do
  set -- $args
  cng-datasets workflow \
    --dataset "$1" \
    --source-url https://s3-west.nrp-nautilus.io/public-padus/raw/PADUS4_1Geodatabase.gdb \
    --bucket public-padus \
    --layer "$2" \
    --h3-resolution 10 --hex-memory 32Gi --max-completions 200 --max-parallelism 50 \
    --parent-resolutions "9,8,0" \
    --output-dir "catalog/pad-us/k8s/$(echo $1 | cut -d/ -f2)"
done

# Apply all workflows
for layer in fee easement proclamation marine combined; do
  kubectl apply \
    -f catalog/pad-us/k8s/$layer/*-setup-bucket.yaml \
    -f catalog/pad-us/k8s/$layer/*-convert.yaml \
    -f catalog/pad-us/k8s/$layer/workflow.yaml
done
```

Non-spatial lookup tables in the GDB were converted locally:
```bash
for table in Public_Access Category DesignationType ManagerType; do
  ogr2ogr -f Parquet "$table.parquet" /vsicurl/<source-url>.gdb "$table"
done
rclone copy *.parquet nrp:public-padus/padus-4-1/lookup/ -P
```
