# Natural Capital Project Layers

("Nature's Contributions to People")

This workflow processes Natural Capital Project's raster datasets from Cloud Optimized GeoTIFF (COG) format to globally partitioned H3 hexagon-based datasets.

## Overview

The pipeline transforms global NCP raster layers into partitioned Parquet datasets organized by H3 hexagons, enabling efficient spatial queries and analysis at multiple resolutions.

**Input:** Cloud Optimized GeoTIFF rasters
- `NCP_biod_nathab_cog.tif` - NCP with biodiversity and natural habitat considerations
- `NCP_only_cog.tif` - NCP values only
- Format: Raster with integer values (-128 to 19+ scale)
- NoData values: Handled as "nan" strings

**Output:** Partitioned Parquet datasets
- Location: `s3://public-ncp/hex/` (initial) → `s3://public-ncp/rehex/` (rescaled)
- Partitioning: By H3 level 0 hex (`h0=<hex_id>/`)
- Schema: 
  - Initial: `Z` (integer value), `h{zoom}` (H3 cell ID), `h0` (H3 level 0 cell ID)
  - Rescaled: `ncp` (float, normalized), `h{zoom}`, `h0`
- Default resolution: H3 level 8

## Workflow Steps

### 1. Spatial Partitioning Strategy

The workflow uses the global H3 grid system at resolution 0 (122 hexagons covering Earth) to partition processing:

- Load reference grid: `s3://public-grids/hex/h0-valid.parquet`
- Contains geometry and identifiers for each h0 hexagon
- Each h0 hex is processed independently in parallel

### 2. Per-Hexagon Processing (`raster.py`)

For each h0 hexagon (indexed 0-121):

1. **Extract hex geometry** from h0-valid.parquet based on index `i`
2. **Crop raster** using GDAL Warp:
   - Clips input COG to hex boundary (cutlineWKT)
   - Reprojects to EPSG:4326 if needed
   - Outputs to temporary XYZ point format (`/tmp/vec.xyz`)
3. **Convert to H3 cells**:
   - Load XYZ data (X, Y, value)
   - Filter null values (handles "nan" strings)
   - Compute H3 cell IDs at target resolution (default zoom=8)
   - Compute H3 level 0 cell for partitioning
4. **Write output**:
   - Save as Parquet partitioned by h0
   - Path: `{output_url}/h0={h0}/data_0.parquet`

### 3. Kubernetes Job Array Execution (`raster_job.yaml`)

The workflow uses Kubernetes indexed Jobs for parallelization:

```yaml
completions: 122        # One job per h0 hex
parallelism: 61         # Process 61 hexes concurrently
completionMode: Indexed # Each job gets unique index 0-121
```

**Job configuration:**
- Image: `ghcr.io/rocker-org/ml-spatial`
- Resources: 4 CPU cores, 34 GiB RAM per task
- Priority: Opportunistic (can be pre-empted)
- Init container clones GitHub repo with processing scripts
- AWS credentials mounted via Kubernetes secrets
- Uses internal S3 endpoint for efficiency

**Command execution (processes both layers):**
```bash
python -u ncp/raster.py --i $INDEX --zoom 8 \
  --input-url https://minio.carlboettiger.info/public-ncp/NCP_biod_nathab_cog.tif \
  --output-url s3://public-ncp/hex/ncp_biod_nathab

python -u ncp/raster.py --i $INDEX --zoom 8 \
  --input-url https://minio.carlboettiger.info/public-ncp/NCP_only_cog.tif \
  --output-url s3://public-ncp/hex/ncp_only
```

### 4. Post-Processing (`post-process.ipynb`)

After the initial hexagon processing, data is rescaled and repartitioned:

1. **Load initial partitioned data**:
   ```python
   con.read_parquet("s3://public-ncp/hex/ncp_only/**")
   ```

2. **Rescale values**:
   - Filter out NoData values (e.g., -128 for ncp_only)
   - Normalize to [0,1] scale: `ncp = Z / 19`

3. **Repartition**:
   ```python
   .mutate(ncp = _.Z / 19)
   .drop("Z")
   .to_parquet("s3://public-ncp/rehex/ncp_only/", partition_by="h0")
   ```

4. **Quality control**:
   - View distributions: `.group_by(_.Z).count()`
   - Visual inspection via leafmap with TiTiler

## Usage

### Production Run

Deploy to Kubernetes cluster:
```bash
kubectl apply -f ncp/raster_job.yaml
```

Monitor progress:
```bash
kubectl get jobs -l k8s-app=wetlands
kubectl logs -l k8s-app=wetlands -f
```

### Single Hex Processing

Process a specific hex locally:
```bash
python raster.py --i 42 --zoom 8 \
  --input-url https://minio.carlboettiger.info/public-ncp/NCP_biod_nathab_cog.tif \
  --output-url s3://public-ncp/hex/ncp_biod_nathab
```

Parameters:
- `--i`: Hex index (0-121, required)
- `--zoom`: H3 resolution (default: 8)
- `--input-url`: Input raster URL
- `--output-url`: Output parquet location
- `--profile`: Enable memory/runtime profiling

### Post-Processing

Run rescaling and repartitioning:
```python
# In Jupyter notebook or Python script
con.read_parquet("s3://public-ncp/hex/ncp_only/**") \
   .filter(_.Z != -128) \
   .mutate(ncp = _.Z / 19) \
   .drop("Z") \
   .to_parquet("s3://public-ncp/rehex/ncp_only/", partition_by="h0")
```

## Data Flow

```
COG Raster (Global NCP)
    ↓
[GDAL Warp] → Crop to h0 hex → XYZ points
    ↓
[DuckDB + H3 extension]
    ↓
Compute H3 cells at target resolution
    ↓
Filter null/NoData values
    ↓
Parquet (partitioned by h0)
    ↓
[Post-processing]
    ↓
Rescale & repartition
    ↓
Final Parquet (normalized values)
```

## Dependencies

- Python with GDAL bindings (`osgeo.gdal`)
- DuckDB with spatial and H3 extensions
- Ibis with DuckDB backend
- Custom utilities: `cng.utils`, `cng.h3`
- AWS S3 access (credentials via environment)
- Optional: leafmap for visualization

## Output Structure

### Initial Output
```
s3://public-ncp/hex/
├── ncp_only/
│   ├── h0=8009fffffffffff/
│   │   └── data_0.parquet
│   └── ...
└── ncp_biod_nathab/
    ├── h0=8009fffffffffff/
    │   └── data_0.parquet
    └── ...
```

### Rescaled Output
```
s3://public-ncp/rehex/
├── ncp_only/
│   ├── h0=8009fffffffffff/
│   │   └── [partition files]
│   └── ...
└── ncp_biod_nathab/
    ├── h0=8009fffffffffff/
    │   └── [partition files]
    └── ...
```

Each partition contains:
- `ncp`: Float value (normalized 0-1 scale)
- `h8`: H3 cell ID at resolution 8 (or specified zoom)
- `h0`: H3 cell ID at resolution 0 (partitioning key)

## Data Layers

1. **NCP_biod_nathab**: Combines nature's contributions to people with biodiversity and natural habitat considerations
2. **NCP_only**: Pure NCP values without additional ecological factors

