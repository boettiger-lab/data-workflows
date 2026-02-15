

# World Database of Protected Areas (WDPA)

## Source Data

Original geodatabase: `s3://public-wdpa/WDPA_Dec2025_Public.gdb`

We process the polygon data only, layer `WDPA_poly_Dec2025` (296,046 features).

## Automated Workflow

### Quick Start

Run the complete processing pipeline with a single command:

```bash
# First, set up RBAC (one-time setup)
kubectl apply -f wdpa/workflow-rbac.yaml

# Run the complete workflow
kubectl apply -f wdpa/workflow.yaml -n biodiversity

# Monitor progress
kubectl logs -f job/wdpa-workflow -n biodiversity
```

The workflow automatically orchestrates all processing steps:
1. **Parquet & PMTiles Generation** (parallel) - Convert GDB to parquet and PMTiles
2. **H3 Hex Processing** - Generate H3 resolution 8 hexagons in chunks
3. **Repartitioning** - Consolidate hex data by h0 partition
4. **Cleanup** - Remove temporary chunks directory (only on success)

### Workflow Components

The workflow job (`workflow.yaml`) runs inside Kubernetes and manages the entire pipeline without requiring an active laptop connection. It:
- Submits jobs in the correct order
- Waits for each step to complete before proceeding
- Handles failures appropriately
- Cleans up temporary data on success

## Manual Processing Steps

You can also run individual steps manually:

### 1. GeoParquet Conversion

Convert the GDB layer to GeoParquet format:

**Script:** `convert_gdb_to_parquet.sh`  
**Job:** `convert-job.yaml`

```bash
kubectl apply -f wdpa/convert-job.yaml -n biodiversity
```

**Output:** `s3://public-wdpa/WDPA_Dec2025.parquet` (5.1 GB)

### 2. PMTiles Generation

Create vector tiles for web mapping:

**Script:** `create_pmtiles.sh`  
**Job:** `pmtiles-job.yaml`

The script converts GDB → GeoJSONSeq → PMTiles using tippecanoe.

```bash
kubectl apply -f wdpa/pmtiles-job.yaml -n biodiversity
```

**Output:** `s3://public-wdpa/WDPA_Dec2025.pmtiles`

### 3. H3 Hexagon Processing

Process polygons into H3 resolution 8 hexagons:

**Script:** `vec.py`  
**Job:** `hex-job.yaml`

Processes the data in indexed chunks with parallel workers.

```bash
kubectl apply -f wdpa/hex-job.yaml -n biodiversity
```

**Output:** `s3://public-wdpa/chunks/chunk_*.parquet` (temporary chunks)

### 4. Repartitioning by H3 Resolution 0

Reorganize hex chunks into hive-partitioned format by h0 cell:

**Script:** `repartition.py`  
**Job:** `repartition-job.yaml`

Reads all chunks and writes with h0 partitioning for efficient spatial queries. On success, automatically removes the temporary `chunks/` directory.

```bash
kubectl apply -f wdpa/repartition-job.yaml -n biodiversity
```

**Output:** `s3://public-wdpa/hex/h0=*/` (hive-partitioned by h0)

## Final Outputs

- **GeoParquet:** `s3://public-wdpa/WDPA_Dec2025.parquet` - Full dataset with all attributes
- **PMTiles:** `s3://public-wdpa/WDPA_Dec2025.pmtiles` - Vector tiles for web mapping
- **H3 Hexagons:** `s3://public-wdpa/hex/` - Hive-partitioned by h0, resolution 8 hexagons

## Troubleshooting

### Check workflow status
```bash
kubectl get jobs -n biodiversity -l workflow=wdpa-workflow
kubectl logs -f job/wdpa-workflow -n biodiversity
```

### Clean up failed workflow
```bash
kubectl delete job wdpa-workflow -n biodiversity
kubectl delete jobs -n biodiversity -l workflow=wdpa-workflow
```

### Manual cleanup of chunks directory
```bash
mc rm --recursive --force s3/public-wdpa/chunks/
```

## Bucket Setup

```bash
mc anonymous set download nvme/public-wdpa
mc mb nrp/public-wdpa
mc anonymous set download nrp/public-wdpa
mc cp -r nvme/public-wdpa/ nrp/public-wdpa
```
