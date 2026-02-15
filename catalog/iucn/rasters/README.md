# IUCN 2025 Species Range Maps - Richness Layers

This workflow processes IUCN Red List 2025 species richness rasters from GeoTIFF format to globally partitioned H3 hexagon-based datasets.

## Overview

The pipeline transforms 14 global IUCN species richness raster layers into partitioned Parquet datasets organized by H3 hexagons, enabling efficient spatial queries and biodiversity analysis at multiple resolutions.

**Input:** GeoTIFF rasters from IUCN 2025
- Location: `s3://public-iucn/raw/richness/`
- Format: Raster with integer richness counts
- 14 layers covering multiple taxonomic groups and threat categories
- NoData values: Handled as "nan" strings and negative values

**Output:** Partitioned Parquet datasets
- Location: `s3://public-iucn/hex/{layer_name}/`
- Partitioning: By H3 level 0 hex (`h0=<hex_id>/`)
- Schema: `{layer_name}` (integer richness count), `h{zoom}` (H3 cell ID), `h0` (H3 level 0 cell ID)
- Default resolution: H3 level 8

## Data Layers

The workflow processes 14 distinct richness layers:

### Species Richness (SR)
- `Amphibians_SR_2025.tif` → amphibians_sr
- `Birds_SR_2025.tif` → birds_sr
- `Mammals_SR_2025.tif` → mammals_sr
- `Reptiles_SR_2025.tif` → reptiles_sr
- `FW_Fish_SR_2025.tif` → fw_fish_sr (Freshwater Fish)
- `Combined_SR_2025.tif` → combined_sr (All taxonomic groups)

### Threatened Species Richness (THR_SR)
- `Amphibians_THR_SR_2025.tif` → amphibians_thr_sr
- `Birds_THR_SR_2025.tif` → birds_thr_sr
- `Mammals_THR_SR_2025.tif` → mammals_thr_sr
- `Reptiles_THR_SR_2025.tif` → reptiles_thr_sr
- `FW_Fish_THR_SR_2025.tif` → fw_fish_thr_sr
- `Combined_THR_SR_2025.tif` → combined_thr_sr

### Range-Weighted Richness (RWR)
- `Combined_RWR_2025.tif` → combined_rwr
- `Combined_THR_RWR_2025.tif` → combined_thr_rwr (Threatened species only)

## Workflow Steps

### 1. Spatial Partitioning Strategy

The workflow uses the global H3 grid system at resolution 0 (122 hexagons covering Earth) to partition processing:

- Load reference grid: `s3://public-grids/hex/h0-valid.parquet`
- Contains geometry and identifiers for each h0 hexagon
- Each h0 hex is processed independently in parallel

### 2. Per-Hexagon Processing (`raster.py`)

For each h0 hexagon (indexed 0-121) and each layer:

1. **Extract hex geometry** from h0-valid.parquet based on index `i`
2. **Crop raster** using GDAL Warp:
   - Clips input GeoTIFF to hex boundary (cutlineWKT)
   - Reprojects to EPSG:4326 if needed
   - Outputs to temporary XYZ point format (`/tmp/iucn.xyz`)
3. **Convert to H3 cells**:
   - Load XYZ data (X, Y, richness value)
   - Filter null values (handles "nan" strings)
   - Filter out negative values (invalid data)
   - Compute H3 cell IDs at target resolution (default zoom=8)
   - Compute H3 level 0 cell for partitioning
4. **Write output**:
   - Save as Parquet partitioned by h0
   - Column name matches layer identifier
   - Path: `{output_url}/h0={h0}/data_0.parquet`

### 3. Kubernetes Job Array Execution (`raster_job.yaml`)

The workflow uses Kubernetes indexed Jobs for parallelization:

```yaml
completions: 122        # One job per h0 hex
parallelism: 61         # Process 61 hexes concurrently
completionMode: Indexed # Each job gets unique index 0-121
```

**Job configuration:**
- Image: `ghcr.io/boettiger-lab/datasets`
- Resources: 4 CPU cores, 34 GiB RAM per task
- Priority: Opportunistic (can be pre-empted)
- Init container clones GitHub repo with processing scripts
- AWS credentials mounted via Kubernetes secrets
- Uses internal S3 endpoint for efficiency

**Command execution:**
Each job processes all 14 layers sequentially for its assigned hex:
```bash
python -u iucn/raster.py --i $INDEX --zoom 8 \
  --input-url https://minio.carlboettiger.info/public-iucn/raw/richness/Amphibians_SR_2025.tif \
  --output-url s3://public-iucn/hex/amphibians_sr \
  --layer-name amphibians_sr

# ... repeats for all 14 layers
```

## Usage

### Production Run

Deploy to Kubernetes cluster:
```bash
kubectl apply -f iucn/raster_job.yaml
```

Monitor progress:
```bash
kubectl get jobs -l k8s-app=iucn-richness
kubectl logs -l k8s-app=iucn-richness -f
```

### Single Hex Processing

Process a specific hex and layer locally:
```bash
python raster.py --i 42 --zoom 8 \
  --input-url https://minio.carlboettiger.info/public-iucn/raw/richness/Birds_SR_2025.tif \
  --output-url s3://public-iucn/hex/birds_sr \
  --layer-name birds_sr
```

Parameters:
- `--i`: Hex index (0-121, required)
- `--zoom`: H3 resolution (default: 8)
- `--input-url`: Input raster URL (required)
- `--output-url`: Output parquet location (required)
- `--layer-name`: Column name for the richness value (required)
- `--profile`: Enable memory/runtime profiling

### Processing a Single Layer

To process just one layer across all hexes, modify the job.yaml to include only the desired layer command.

## Data Flow

```
GeoTIFF Raster (Global IUCN Richness)
    ↓
[GDAL Warp] → Crop to h0 hex → XYZ points
    ↓
[DuckDB + H3 extension]
    ↓
Compute H3 cells at target resolution
    ↓
Filter null/negative values
    ↓
Parquet (partitioned by h0)
```

## Dependencies

- Python with GDAL bindings (`osgeo.gdal`)
- DuckDB with spatial and H3 extensions
- Ibis with DuckDB backend
- Custom utilities: `cng.utils`, `cng.h3`
- AWS S3 access (credentials via environment)

## Output Structure

```
s3://public-iucn/hex/
├── amphibians_sr/
│   ├── h0=8009fffffffffff/
│   │   └── data_0.parquet
│   └── ...
├── birds_sr/
│   ├── h0=8009fffffffffff/
│   │   └── data_0.parquet
│   └── ...
├── mammals_sr/
│   └── ...
├── reptiles_sr/
│   └── ...
├── fw_fish_sr/
│   └── ...
├── combined_sr/
│   └── ...
├── amphibians_thr_sr/
│   └── ...
├── birds_thr_sr/
│   └── ...
├── mammals_thr_sr/
│   └── ...
├── reptiles_thr_sr/
│   └── ...
├── fw_fish_thr_sr/
│   └── ...
├── combined_thr_sr/
│   └── ...
├── combined_rwr/
│   └── ...
└── combined_thr_rwr/
    └── ...
```

Each partition contains:
- `{layer_name}`: Integer richness count
- `h8`: H3 cell ID at resolution 8 (or specified zoom)
- `h0`: H3 cell ID at resolution 0 (partitioning key)

## Processing Notes

- **Sequential Layer Processing**: Each job processes all 14 layers for its assigned hex sequentially. This approach maximizes data locality and minimizes setup overhead.
- **Memory Efficient**: Using 4 cores and 34 GiB per task handles even the largest layers (Combined_RWR_2025.tif at 14 MiB)
- **Data Validation**: Filters out null values and negative values to ensure data quality
- **Flexible Layer Names**: Column names match the layer identifier for easy identification in downstream analysis

## Performance

- **Total jobs**: 122 (one per h0 hex)
- **Parallelism**: 61 concurrent jobs
- **Layers per job**: 14 richness layers
- **Total operations**: 122 × 14 = 1,708 layer-hex combinations
- **Estimated time**: ~1-2 hours with 61-way parallelism (depending on cluster resources)

## Post-Processing: Removing Zero Values

After the initial hexing process, many cells contain 0 richness values (areas with no species). These can be removed to reduce storage and improve query performance.

### Post-Processing Workflow

The `post_process.py` script filters out 0 values and writes cleaned datasets:

**Input:** `s3://public-iucn/hex/{layer_name}/**`
**Output:** `s3://public-iucn/richness/hex/{layer_name}/**` (partitioned by h0)

### Running Post-Processing

Deploy the post-processing job:
```bash
kubectl apply -f iucn/post_process_job.yaml
```

Monitor progress:
```bash
kubectl get jobs -l k8s-app=iucn-post-process
kubectl logs -l k8s-app=iucn-post-process -f
```

The job processes all 14 layers sequentially, removing cells where richness = 0.

### Single Layer Post-Processing

Process one layer locally:
```bash
python post_process.py \
  --layer-name reptiles_thr_sr \
  --value-column reptiles_thr_sr
```

**Job configuration:**
- Resources: 8 CPU cores, 64 GiB RAM
- Processing: Sequential (all layers in one job)
- Priority: Opportunistic

## Cloud-Optimized GeoTIFFs (COGs)

The original IUCN richness rasters are available as Cloud-Optimized GeoTIFFs for direct web-based visualization and analysis:

**Location:** `s3://public-iucn/raw/richness/`

**Public URL:** `https://minio.carlboettiger.info/public-iucn/raw/richness/`

These COGs can be accessed directly in QGIS, ArcGIS, web mapping applications, or any COG-compatible tool without downloading the entire file. The internal tiling and overviews enable efficient streaming and visualization at multiple zoom levels.

### COG Workflow

Original GeoTIFFs were converted to COGs using `cog_job.yaml`:

1. Downloads source TIFFs to local storage
2. Applies `gdal_translate` with COG driver and optimal settings:
   - Compression: LZW
   - Tiling: 512×512
   - Overviews: Generated automatically
   - Predictor: Horizontal differencing for better compression
3. Uploads COGs to S3 with public read access
4. Validates COG format using `rio cogeo validate`

Deploy COG conversion:
```bash
kubectl apply -f iucn/cog_job.yaml
```
