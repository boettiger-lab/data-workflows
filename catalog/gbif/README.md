# Accessing the processed data

```r
library(duckdbfs)
duckdb_secrets("", "", "s3-west.nrp-nautilus.io")
open_dataset("s3://public-gbif/2025-06/hex/**")

```



# GBIF H3 Processing Pipeline

This directory contains a two-stage pipeline for processing GBIF occurrence data with H3 geospatial indexes and optimizing it for efficient remote access.

## Overview

The pipeline transforms the raw GBIF parquet dataset (~4,600 files, ~2.5B records) into H3-indexed, spatially-partitioned, optimized parquet files that enable efficient spatial queries.

### Why H3 Indexing?

H3 is a hierarchical hexagonal grid system that provides:
- **Spatial locality**: nearby locations have similar H3 indexes
- **Multi-resolution**: h0 (coarse) to h15 (fine) resolutions
- **Efficient spatial queries**: range queries, point lookups, and spatial joins

## Pipeline Stages

### Stage 1: H3 Indexing and Partitioning (`process_gbif_h3.py`)

**Job**: `hex-job.yaml`
**Completions**: 200 (each processes 25 source files)

#### What it does:
1. Lists all source parquet files from `s3://gbif-open-data-us-east-1/occurrence/2025-06-01/occurrence.parquet/` using boto3
2. Divides files into 200 chunks of ~25 files each
3. For each chunk:
   - Reads the 25 parquet files in parallel
   - Adds H3 index columns (h0 through h10) based on lat/lon coordinates
   - Filters invalid coordinates
   - Partitions by h0 (122 global partitions at coarsest resolution)
   - Writes output to `s3://public-gbif/2025-06/chunks/h0=<hex>/`

#### Output:
- ~200 files per h0 partition (one from each processing job)
- Files named: `job####_h0<hex>.parquet`
- Deterministic filenames prevent duplicates across restarts

#### Performance:
- Processes 25 files at once in DuckDB for I/O efficiency
- No parallelism concerns - each job has disjoint input files
- Target: ~23 source files per job completion

### Stage 2: Consolidation and Optimization (`consolidate_h0_partitions.py`)

**Job**: `consolidate-job.yaml`
**Completions**: 122 (one per h0 partition)

#### What it does:
1. Lists all h0 partitions from chunks/
2. For each h0 partition:
   - Reads all ~200 fragmented files in that partition from chunks/
   - Sorts by h1, h2, h3, h4, h5 for spatial locality
   - Writes optimized files to hex/ subdirectory with proper row groups
   - Deletes original fragmented files from chunks/

#### Optimization Strategy:

**Target File Size: 256 MB**
- Balances cloud storage efficiency with query granularity
- Allows S3 range requests to fetch relevant data without reading entire file
- Each file contains ~10M rows (varies by partition density)

**Row Group Size: 1M rows**
- Enables fine-grained predicate pushdown
- DuckDB/Arrow can skip row groups that don't match query predicates
- Smaller than file size allows multiple "chunks" per file for parallel processing

**Compression: ZSTD**
- Better compression ratio than Snappy (20-30% size reduction)
- Fast decompression for cloud reads
- Industry standard for parquet in cloud environments

**Spatial Sorting: ORDER BY h1, h2, h3, h4, h5**
- Creates spatial clustering within each h0 partition
- Nearby locations are stored together in the same row groups
- Dramatically improves queries like "find all records in hex X" or "within distance Y"
- Enables efficient Z-order curve traversal

#### Why This Matters for Remote Reads:

1. **Predicate Pushdown**: Row-level statistics let query engines skip irrelevant data
2. **Spatial Locality**: Sorted data means spatial queries read contiguous blocks
3. **Optimal I/O**: 256MB files balance latency (fewer requests) with throughput (parallel reads)
4. **Columnar Storage**: Only fetch columns needed for query
5. **Partition Pruning**: h0 partitioning eliminates entire directories from query

## Running the Pipeline

### Step 1: Initial Processing

```bash
# Delete any previous runs
kubectl delete job gbif-h3-process
mc rm -r --force nrp/public-gbif/2025-06/chunks

# Start processing
kubectl apply -f gbif/hex-job.yaml

# Monitor progress
kubectl get jobs
watch kubectl get pods -l k8s-app=gbif-h3-process

# Check logs for specific pod
kubectl logs gbif-h3-process-0-xxxxx
```

Wait for all 200 completions to finish.

### Step 2: Consolidation

```bash
# Delete consolidation job if exists
kubectl delete job gbif-h3-consolidate

# Start consolidation
kubectl apply -f gbif/consolidate-job.yaml

# Monitor progress
watch kubectl get pods -l k8s-app=gbif-h3-consolidate
```

Wait for all 122 completions (one per h0 partition).

## Final Output Structure

```
s3://public-gbif/2025-06/hex/
├── h0=8001fffffffffff/
│   ├── optimized_8001fffffffffff_0.parquet
│   ├── optimized_8001fffffffffff_1.parquet
│   └── ...
├── h0=8003fffffffffff/
│   └── optimized_8003fffffffffff_0.parquet
└── ...
```

## Querying the Data

### Example with DuckDB:

```python
import duckdb

con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs;")

# Query specific h0 partition(s)
result = con.execute("""
    SELECT species, COUNT(*) as count
    FROM read_parquet('s3://public-gbif/2025-06/hex/h0=8001fffffffffff/*.parquet')
    WHERE h3 = 633564256014688256  -- specific h3 cell at resolution 3
    GROUP BY species
    ORDER BY count DESC
    LIMIT 10
""").fetchall()
```

### Example with Polars:

```python
import polars as pl

# Spatial query leveraging partitioning and sorting
df = pl.scan_parquet('s3://public-gbif/2025-06/hex/h0=80*/optimized_*.parquet')
result = (df
    .filter(pl.col('h2') == 592370033168572416)
    .select(['species', 'decimallatitude', 'decimallongitude', 'h3'])
    .collect()
)
```

## Performance Characteristics

### Without Optimization:
- 4,600 source files → 4,600 random seeks for global query
- No spatial locality → read entire dataset for spatial queries
- Poor compression → higher bandwidth costs

### With Optimization:
- 122 partitions × ~10 files each = ~1,220 files (vs 4,600)
- Spatial sorting → queries read 10-100x less data
- ZSTD compression → 30% smaller files
- Row group pruning → skip 90%+ of irrelevant data

## Resource Requirements

### Stage 1 (Processing):
- Memory: 64 GB per pod (handles reading 25 files + H3 computation)
- CPU: 4 cores (I/O bound)
- Duration: ~30-60 min per pod
- Total: ~200 pod-hours

### Stage 2 (Consolidation):
- Memory: 64 GB per pod (reads ~200 files, sorts in memory)
- CPU: 4 cores (compression bound)
- Duration: ~10-30 min per pod
- Total: ~60 pod-hours

## Future Enhancements

1. **GeoParquet Metadata**: Add WGS84 geometry column for full GeoParquet compliance
2. **Additional Sorting**: Consider compound sort keys (h1, h2, h3, species, eventDate)
3. **Statistics**: Pre-compute partition-level statistics (species counts, date ranges)
4. **Delta Lake**: Use Delta Lake format for ACID properties and time travel
5. **Higher Resolution Partitioning**: Partition by h1 or h2 for very large datasets

## Troubleshooting

### Job fails to list files:
- Check S3 credentials in kubernetes secret `aws`
- Verify network connectivity to S3 endpoint

### Out of memory errors:
- Reduce `files_per_chunk` in `process_gbif_h3.py`
- Increase memory request in job YAML

### Consolidation hangs:
- Check if partition has too many rows (>100M)
- Increase memory or split partition manually

### Duplicate files after restart:
- This is now prevented by deterministic filenames
- Safe to restart jobs - they will overwrite their own outputs
