# HydroBasins Level 4 Processing

This directory contains scripts and configurations for processing HydroBasins Level 4 watershed data into H3 hexagons and PMTiles, following the approach developed for the WDPA dataset.

## Source Data

**Input:** `s3://public-hydrobasins/level_04.parquet`  
**Resolution:** Pfafstetter Level 4 (intermediate watershed scale)

## Processing Pipeline

The workflow converts watershed polygons to:
1. **H3 Resolution 8 Hexagons** - For spatial analysis and querying
2. **PMTiles** - For web mapping visualization

### Quick Start

Run all processing steps:

```bash
# 1. Generate H3 hexagons in parallel chunks
kubectl apply -f hydrobasins/level_04/hex-job.yaml -n biodiversity

# Wait for hex job to complete, then:

# 2. Repartition hexagons by h0 cell
kubectl apply -f hydrobasins/level_04/repartition-job.yaml -n biodiversity

# 3. Generate PMTiles for visualization (can run in parallel with hex processing)
kubectl apply -f hydrobasins/level_04/pmtiles-job.yaml -n biodiversity
```

## Processing Steps

### 1. H3 Hex Processing

**Script:** `vec.py`  
**Job:** `hex-job.yaml`

Processes watershed polygons into H3 resolution 8 hexagons in parallel chunks:
- Reads from `s3://public-hydrobasins/level_04.parquet`
- Chunk size: 100 features per chunk
- Parallelism: 50 workers
- Preserves attributes: `HYBAS_ID` (as `id`), `PFAF_ID`, `UP_AREA`, `SUB_AREA`, `MAIN_BAS`

```bash
kubectl apply -f hydrobasins/level_04/hex-job.yaml -n biodiversity

# Monitor progress
kubectl get pods -n biodiversity -l k8s-app=hydrobasins-level4-hex
```

**Output:** `s3://public-hydrobasins/level_04/chunks/chunk_*.parquet`

### 2. Repartitioning by H3 Resolution 0

**Script:** `repartition.py`  
**Job:** `repartition-job.yaml`

Consolidates hex chunks into h0-partitioned format for efficient spatial queries:
- Reads all chunks from `s3://public-hydrobasins/level_04/chunks/`
- Repartitions by h0 (coarsest H3 resolution)
- Automatically removes temporary chunks directory on success

```bash
kubectl apply -f hydrobasins/level_04/repartition-job.yaml -n biodiversity

# Monitor progress
kubectl logs -f job/hydrobasins-level4-repartition -n biodiversity
```

**Output:** `s3://public-hydrobasins/level_04/hexes/` (hive-partitioned by h0)

### 3. PMTiles Generation

**Script:** `create_pmtiles.sh`  
**Job:** `pmtiles-job.yaml`

Creates vector tiles for web mapping:
- Converts parquet → GeoJSONSeq → PMTiles using tippecanoe
- Layer name: `hydrobasins_level_04`

```bash
kubectl apply -f hydrobasins/level_04/pmtiles-job.yaml -n biodiversity

# Monitor progress
kubectl logs -f job/hydrobasins-level4-pmtiles -n biodiversity
```

**Output:** `s3://public-hydrobasins/level_04/hydrobasins_level_04.pmtiles`

## Output Structure

```
s3://public-hydrobasins/level_04/
├── hydrobasins_level_04.pmtiles       # Vector tiles for web mapping
└── hexes/                             # H3 hexagons partitioned by h0
    ├── h0=0/
    ├── h0=1/
    └── ...
```

## Notes

- Level 4 represents intermediate watersheds in the Pfafstetter coding system
- Balance between Level 3 (larger) and Level 6 (smaller) watersheds
- Uses same H3 resolution 8 for consistency across levels
