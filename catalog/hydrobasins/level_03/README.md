# HydroBasins Level 3 Processing

This directory contains scripts and configurations for processing HydroBasins Level 3 watershed data into H3 hexagons and PMTiles, following the approach developed for the WDPA dataset.

## Source Data

**Input:** `s3://public-hydrobasins/level_03.parquet`  
**Resolution:** Pfafstetter Level 3 (major sub-continental watershed scale)

## Processing Pipeline

The workflow converts watershed polygons to:
1. **H3 Resolution 8 Hexagons** - For spatial analysis and querying
2. **PMTiles** - For web mapping visualization

### Quick Start

Run all processing steps:

```bash
# 1. Generate H3 hexagons in parallel chunks
kubectl apply -f hydrobasins/level_03/hex-job.yaml -n biodiversity

# Wait for hex job to complete, then:

# 2. Repartition hexagons by h0 cell
kubectl apply -f hydrobasins/level_03/repartition-job.yaml -n biodiversity

# 3. Generate PMTiles for visualization (can run in parallel with hex processing)
kubectl apply -f hydrobasins/level_03/pmtiles-job.yaml -n biodiversity
```

## Processing Steps

### 1. H3 Hex Processing

**Script:** `vec.py`  
**Job:** `hex-job.yaml`

Processes watershed polygons into H3 resolution 8 hexagons in parallel chunks:
- Reads from `s3://public-hydrobasins/level_03.parquet`
- Chunk size: 100 features per chunk
- Parallelism: 50 workers
- Preserves attributes: `HYBAS_ID` (as `id`), `PFAF_ID`, `UP_AREA`, `SUB_AREA`, `MAIN_BAS`

```bash
kubectl apply -f hydrobasins/level_03/hex-job.yaml -n biodiversity

# Monitor progress
kubectl get pods -n biodiversity -l k8s-app=hydrobasins-level3-hex
```

**Output:** `s3://public-hydrobasins/level_03/chunks/chunk_*.parquet`

### 2. Repartitioning by H3 Resolution 0

**Script:** `repartition.py`  
**Job:** `repartition-job.yaml`

Consolidates hex chunks into h0-partitioned format for efficient spatial queries:
- Reads all chunks from `s3://public-hydrobasins/level_03/chunks/`
- Repartitions by h0 (coarsest H3 resolution)
- Automatically removes temporary chunks directory on success

```bash
kubectl apply -f hydrobasins/level_03/repartition-job.yaml -n biodiversity

# Monitor progress
kubectl logs -f job/hydrobasins-level3-repartition -n biodiversity
```

**Output:** `s3://public-hydrobasins/level_03/hexes/` (hive-partitioned by h0)

### 3. PMTiles Generation

**Script:** `create_pmtiles.sh`  
**Job:** `pmtiles-job.yaml`

Creates vector tiles for web mapping:
- Converts parquet → GeoJSONSeq → PMTiles using tippecanoe
- Layer name: `hydrobasins_level_03`

```bash
kubectl apply -f hydrobasins/level_03/pmtiles-job.yaml -n biodiversity

# Monitor progress
kubectl logs -f job/hydrobasins-level3-pmtiles -n biodiversity
```

**Output:** `s3://public-hydrobasins/level_03/hydrobasins_level_03.pmtiles`

## Output Structure

```
s3://public-hydrobasins/level_03/
├── hydrobasins_level_03.pmtiles       # Vector tiles for web mapping
└── hexes/                             # H3 hexagons partitioned by h0
    ├── h0=0/
    ├── h0=1/
    └── ...
```

## Notes

- Level 3 represents major sub-continental watersheds in the Pfafstetter coding system
- Smaller polygons than Level 6, but covers finer watershed detail
- Uses same H3 resolution 8 for consistency across levels
