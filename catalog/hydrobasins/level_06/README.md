# HydroBasins Level 6 Processing

This directory contains scripts and configurations for processing HydroBasins Level 6 watershed data into H3 hexagons and PMTiles, following the approach developed for the WDPA dataset.

## Source Data

**Input:** `s3://public-hydrobasins/level_06.parquet`  
**Features:** ~16,397 major watersheds globally  
**Resolution:** Pfafstetter Level 6 (major watershed scale)

## Processing Pipeline

The workflow converts watershed polygons to:
1. **H3 Resolution 8 Hexagons** - For spatial analysis and querying
2. **PMTiles** - For web mapping visualization

### Quick Start

Run all processing steps:

```bash
# 1. Generate H3 hexagons in parallel chunks
kubectl apply -f hydrobasins/level_06/hex-job.yaml -n biodiversity

# Wait for hex job to complete, then:

# 2. Repartition hexagons by h0 cell
kubectl apply -f hydrobasins/level_06/repartition-job.yaml -n biodiversity

# 3. Generate PMTiles for visualization (can run in parallel with hex processing)
kubectl apply -f hydrobasins/level_06/pmtiles-job.yaml -n biodiversity
```

## Processing Steps

### 1. H3 Hex Processing

**Script:** `vec.py`  
**Job:** `hex-job.yaml`

Processes watershed polygons into H3 resolution 8 hexagons in parallel chunks:
- Reads from `s3://public-hydrobasins/level_06.parquet`
- Chunk size: 1,000 features per chunk (17 chunks total for ~16,397 features)
- Parallelism: 10 workers
- Preserves attributes: `HYBAS_ID` (as `id`), `PFAF_ID`, `UP_AREA`, `SUB_AREA`, `MAIN_BAS`

```bash
kubectl apply -f hydrobasins/level_06/hex-job.yaml -n biodiversity

# Monitor progress
kubectl get pods -n biodiversity -l k8s-app=hydrobasins-level6-hex
```

**Output:** `s3://public-hydrobasins/level_06/chunks/chunk_*.parquet`

### 2. Repartitioning by H3 Resolution 0

**Script:** `repartition.py`  
**Job:** `repartition-job.yaml`

Consolidates hex chunks into h0-partitioned format for efficient spatial queries:
- Reads all chunks from `s3://public-hydrobasins/level_06/chunks/`
- Repartitions by h0 (coarsest H3 resolution)
- Automatically removes temporary chunks directory on success

```bash
kubectl apply -f hydrobasins/level_06/repartition-job.yaml -n biodiversity

# Monitor progress
kubectl logs -f job/hydrobasins-level6-repartition -n biodiversity
```

**Output:** `s3://public-hydrobasins/level_06/hexes/` (hive-partitioned by h0)

### 3. PMTiles Generation

**Script:** `create_pmtiles.sh`  
**Job:** `pmtiles-job.yaml`

Creates vector tiles for web mapping:
- Converts parquet → GeoJSONSeq → PMTiles using tippecanoe
- Layer name: `hydrobasins_level_06`

```bash
kubectl apply -f hydrobasins/level_06/pmtiles-job.yaml -n biodiversity

# Monitor progress
kubectl logs -f job/hydrobasins-level6-pmtiles -n biodiversity
```

**Output:** `s3://public-hydrobasins/level_06/hydrobasins_level_06.pmtiles`

## Output Structure

```
s3://public-hydrobasins/level_06/
├── hydrobasins_level_06.pmtiles       # Vector tiles for web mapping
└── hexes/                             # H3 hexagons partitioned by h0
    ├── h0=0/
    ├── h0=1/
    ├── ...
    └── h0=121/
```

## Data Schema

### Hex Parquet Schema

| Column    | Type   | Description                           |
|-----------|--------|---------------------------------------|
| id        | int64  | HYBAS_ID - Unique basin identifier    |
| PFAF_ID   | string | Pfafstetter code                      |
| UP_AREA   | double | Upstream drainage area (km²)          |
| SUB_AREA  | double | Sub-basin area (km²)                  |
| MAIN_BAS  | int64  | Main basin identifier                 |
| h8        | string | H3 cell ID at resolution 8            |
| h0        | string | H3 cell ID at resolution 0 (partition)|

## Resource Requirements

- **Hex Processing:** 2 CPU, 8 GB RAM per worker
- **Repartitioning:** 4 CPU, 64 GB RAM
- **PMTiles:** 4 CPU, 64 GB RAM

## Monitoring

Check job status:
```bash
# List all level 6 jobs
kubectl get jobs -n biodiversity | grep hydrobasins-level6

# View logs for specific job
kubectl logs -f job/hydrobasins-level6-hex -n biodiversity
kubectl logs -f job/hydrobasins-level6-repartition -n biodiversity
kubectl logs -f job/hydrobasins-level6-pmtiles -n biodiversity

# Check pod status
kubectl get pods -n biodiversity -l k8s-app=hydrobasins-level6-hex
```

## Cleanup

Remove completed jobs:
```bash
kubectl delete job hydrobasins-level6-hex -n biodiversity
kubectl delete job hydrobasins-level6-repartition -n biodiversity
kubectl delete job hydrobasins-level6-pmtiles -n biodiversity
```

## Notes

- The hex processing uses indexed jobs (0-16) for parallel execution
- Chunk size can be adjusted via `--chunk-size` parameter in `vec.py`
- H3 resolution can be changed via `--zoom` parameter (default: 8)
- The repartitioning job automatically cleans up the temporary chunks directory
- All processing preserves important HydroBasins attributes for watershed analysis
