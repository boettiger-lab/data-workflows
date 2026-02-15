# Redlining / Mapping Inequality

## Source Data

Original geopackage: https://dsl.richmond.edu/panorama/redlining/static/mappinginequality.gpkg

Historical redlining maps showing discriminatory mortgage lending practices in US cities from the 1930s-1940s.

## Overview

This workflow processes historical redlining data into cloud-native formats:
1. **GeoParquet** - Optimized columnar format for analysis
2. **PMTiles** - Vector tiles for web mapping
3. **H3-indexed Parquet** - Hexagonal tiling at resolution 10 with parent hexes (h9, h8, h0)

All processing uses the `cng_datasets` Python package for standardized, reusable data processing. Jobs use the `ghcr.io/boettiger-lab/datasets` image with all dependencies pre-installed, and clone the repository via an initContainer for fast execution.

### H3 Resolution Configuration

The workflow generates H3 hexagons at **resolution 10** (h10) and includes parent hexagons at resolutions **h9, h8, and h0**. These resolutions can be configured during workflow generation:

```bash
cng-datasets workflow \
  --dataset mappinginequality \
  --source-url https://dsl.richmond.edu/panorama/redlining/static/mappinginequality.gpkg \
  --bucket public-mappinginequality \
  --h3-resolution 10 \
  --parent-resolutions "9,8,0"
```

**Resolution Guide:**
- **h10** (~15m hexagons) - Fine-grained analysis, optimal for urban features
- **h9** (~50m hexagons) - Intermediate scale
- **h8** (~175m hexagons) - Neighborhood scale  
- **h0** (continent scale) - Used for efficient partitioning

Other datasets may use different resolutions based on their spatial scale (e.g., h8 for regional data, h12 for detailed local data).

### Processing Workflow

The H3 hexagonal tiling follows a **two-pass approach** (matching wdpa/):
1. **Chunking** - Process data in parallel chunks, writing to `s3://public-mappinginequality/mappinginequality/chunks/`
2. **Repartitioning** - Consolidate all chunks into h0-partitioned format in `s3://public-mappinginequality/mappinginequality/hex/`, then delete temporary chunks/

This approach enables efficient parallel processing of large datasets while ensuring optimal query performance with h0 partitioning.

## Quick Start

### 1. Generate All Workflow Files

```bash
cng-datasets workflow \
  --dataset mappinginequality \
  --source-url https://dsl.richmond.edu/panorama/redlining/static/mappinginequality.gpkg \
  --bucket public-mappinginequality \
  --h3-resolution 10 \
  --parent-resolutions "9,8,0"
```

This generates all required Kubernetes job configurations:
- `convert-job.yaml` - GPKG → GeoParquet conversion
- `pmtiles-job.yaml` - PMTiles vector tile generation
- `hex-job.yaml` - H3 hexagonal tiling (automatic chunking based on dataset size)
- `repartition-job.yaml` - Consolidate chunks by h0 partition
- `workflow.yaml` - K8s Job orchestrator (runs jobs sequentially)
- `workflow-rbac.yaml` - Kubernetes RBAC permissions (generic, one per namespace)

### 2. Run the Workflow

```bash
# One-time RBAC setup
kubectl apply -f k8s/workflow-rbac.yaml

# Create ConfigMap from job YAMLs and run workflow
kubectl create configmap mappinginequality-yamls \
  --from-file=k8s/convert-job.yaml \
  --from-file=k8s/pmtiles-job.yaml \
  --from-file=k8s/hex-job.yaml \
  --from-file=k8s/repartition-job.yaml
kubectl apply -f k8s/workflow.yaml

# Monitor progress
kubectl logs -f job/mappinginequality-workflow
```

The workflow automatically orchestrates all steps in sequence. You can also run jobs individually:
```bash
kubectl apply -f convert-job.yaml
kubectl apply -f pmtiles-job.yaml
kubectl apply -f hex-job.yaml
kubectl apply -f repartition-job.yaml
```

The workflow automatically:
1. Creates bucket and sets public read access with CORS
2. Converts GPKG to GeoParquet and PMTiles (parallel)
3. Processes into H3 hexagons in chunks (50 chunks, 20 parallel workers → `mappinginequality/chunks/`)
4. Repartitions chunks by h0 for efficient querying (`mappinginequality/chunks/` → `mappinginequality/hex/`)
5. Cleans up temporary chunks directory
6. Runs entirely in K8s (laptop can disconnect)

## Data Structure

The final hex data contains:
- All original redlining polygon attributes
- `h10`: H3 hexagon ID at resolution 10 (UBIGINT)
- `h9`: Parent hex at resolution 9 (UBIGINT)
- `h8`: Parent hex at resolution 8 (UBIGINT)
- `h0`: Parent hex at resolution 0 (UBIGINT)

The h0 partitioning enables efficient spatial queries by limiting reads to relevant geographic regions.

## Output Locations

- `s3://public-mappinginequality/mappinginequality.parquet` - GeoParquet
- `s3://public-mappinginequality/mappinginequality.pmtiles` - PMTiles
- `s3://public-mappinginequality/mappinginequality/chunks/` - Temporary H3 processing chunks (deleted after repartitioning)
- `s3://public-mappinginequality/mappinginequality/hex/` - H3-indexed parquet (partitioned by h0)

## Cleanup and Reset

### Delete All Jobs
```bash
# Delete all redlining jobs and ConfigMap
kubectl delete job mappinginequality-convert mappinginequality-pmtiles mappinginequality-hex mappinginequality-repartition mappinginequality-workflow --ignore-not-found=true
kubectl delete configmap mappinginequality-yamls --ignore-not-found=true
```

### Delete Data from Bucket
```bash
# Delete all generated data (using rclone)
rclone purge nrp:public-mappinginequality

# Or delete specific outputs:
rclone delete nrp:public-mappinginequality/mappinginequality.parquet
rclone delete nrp:public-mappinginequality/mappinginequality.pmtiles
rclone purge nrp:public-mappinginequality/mappinginequality/hex/
rclone purge nrp:public-mappinginequality/mappinginequality/chunks/  # if workflow was interrupted
```

### Complete Reset
To completely reset and rerun from scratch:
```bash
# 1. Delete all jobs and ConfigMap
kubectl delete job mappinginequality-convert mappinginequality-pmtiles mappinginequality-hex mappinginequality-repartition mappinginequality-workflow --ignore-not-found=true
kubectl delete configmap mappinginequality-yamls --ignore-not-found=true

# 2. Delete all data
rclone purge nrp:public-mappinginequality

# 3. Rerun workflow
kubectl create configmap mappinginequality-yamls \
  --from-file=k8s/convert-job.yaml \
  --from-file=k8s/pmtiles-job.yaml \
  --from-file=k8s/hex-job.yaml \
  --from-file=k8s/repartition-job.yaml
kubectl apply -f k8s/workflow.yaml
```

### Check Job Status
```bash
# List all jobs
kubectl get jobs | grep mappinginequality

# Check specific job status
kubectl describe job mappinginequality-hex

# View logs
kubectl logs job/mappinginequality-convert
kubectl logs job/mappinginequality-hex-0-xxxxx  # specific pod

# List all pods for a job
kubectl get pods | grep mappinginequality-hex
```