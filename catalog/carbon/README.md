# Conservation International - Irrecoverable Carbon

This workflow processes Conservation International's irrecoverable carbon dataset from Cloud Optimized GeoTIFF (COG) format to a globally partitioned H3 hexagon-based dataset.

## Overview

The pipeline transforms a global raster dataset of irrecoverable carbon stocks into a partitioned Parquet dataset organized by H3 hexagons, enabling efficient spatial queries and analysis at multiple resolutions.

**Input:** Cloud Optimized GeoTIFF raster
- Source: `s3://public-carbon/cogs/irrecoverable_c_total_2018.tif`
- Public URL: `https://s3-west.nrp-nautilus.io/public-carbon/cogs/irrecoverable_c_total_2018.tif`
- Format: Raster with carbon values (integer)
- NoData value: 65535 (auto-detected)

**Output:** Partitioned Parquet dataset
- Location: `s3://public-carbon/irrecoverable-carbon/hex/`
- Partitioning: By H3 level 0 hex (`h0=<hex_id>/`)
- Schema: `carbon` (integer), `h{zoom}` (H3 cell ID at target resolution), `h0` (H3 level 0 cell ID)
- Default resolution: H3 level 8

## Workflow Steps

### 1. Spatial Partitioning Strategy

The workflow uses the global H3 grid system at resolution 0 (122 hexagons covering Earth) to partition processing:

- Load reference grid: `s3://public-grids/hex/h0-valid.parquet`
- Contains geometry and identifiers for each h0 hexagon
- Each h0 hex is processed independently in parallel

### 2. Per-Hexagon Processing

The workflow uses the `cng-datasets` CLI to process each h0 hexagon (indexed 0-121). The processing logic is handled by the `RasterProcessor` class in the package.

1. **Extract hex geometry** from h0-valid.parquet based on index `i`
2. **Crop raster** using GDAL Warp:
   - Clips input COG to hex boundary (cutlineWKT)
   - Reprojects to EPSG:4326 if needed
   - Outputs to temporary XYZ point format
3. **Convert to H3 cells**:
   - Load XYZ data (X, Y, carbon value)
   - Filter out NoData values (65535, auto-detected from raster metadata)
   - Compute H3 cell IDs at target resolution (default zoom=8)
   - Compute H3 level 0 cell for partitioning
4. **Write output**:
   - Save as Parquet partitioned by h0
   - Path: `s3://public-carbon/irrecoverable-carbon/hex/h0={h0}/data_0.parquet`

### 3. Running the Workflow

#### Local Testing (Single h0 region)

Test processing a single h0 region locally using the CLI:

```bash
# Install the package in development mode
pip install -e .

# Process a single h0 region (e.g., index 0)
# Uses public HTTPS access (no credentials needed)
cng-datasets raster \
  --input https://s3-west.nrp-nautilus.io/public-carbon/cogs/irrecoverable_c_total_2018.tif \
  --output-parquet s3://public-carbon/irrecoverable-carbon/hex/ \
  --resolution 8 \
  --parent-resolutions 0 \
  --h0-index 0 \
  --value-column carbon
```

#### Kubernetes Workflow (All regions)

Generate and run the full workflow on Kubernetes:

```bash
# Generate workflow files
cng-datasets raster-workflow \
  --dataset irrecoverable-carbon \
  --source-url s3://public-carbon/cogs/irrecoverable_c_total_2018.tif \
  --bucket public-carbon \
  --output-dir k8s \
  --h3-resolution 8 \
  --parent-resolutions 0 \
  --value-column carbon

# Apply the workflow
kubectl apply -f carbon/k8s/workflow-rbac.yaml
kubectl apply -f carbon/k8s/configmap.yaml
kubectl apply -f carbon/k8s/workflow.yaml

# Monitor progress
kubectl logs -f job/irrecoverable-carbon-workflow
```

The workflow will:
1. Setup the bucket (CORS, public access)
2. Launch 122 parallel jobs to process each h0 region

### 4. Output Schema

The output parquet files have the following schema:

```
carbon: int32       # Carbon value from raster
h8: string          # H3 cell ID at resolution 8 (default)
h0: string          # H3 cell ID at resolution 0 (for partitioning)
```

### 6. NoData Handling

The workflow automatically detects and excludes NoData values:

1. **Auto-detection**: Reads NoData value from raster metadata (65535 for this dataset)
2. **Manual override**: Use `--nodata` argument to specify a different value
3. **No NoData**: If no value is specified or detected, all values are included

This keeps output files efficient by excluding cells with missing data.

## Data Source

**Dataset**: Conservation International - Irrecoverable Carbon (2018)

Irrecoverable carbon represents carbon stocks that would be lost if ecosystems are converted and could not be recovered by 2050. This is a critical metric for conservation planning and climate mitigation.

**Citation**: 
Noon, M. L., Goldstein, A., Ledezma, J. C., Roehrdanz, P. R., Cook-Patton, S. C., Spawn-Lee, S. A., Wright, T. M., Gonzalez-Roglich, M., Hole, D. G., Rockström, J., & Turner, W. R. (2022). Mapping the irrecoverable carbon in Earth's ecosystems. *Nature Sustainability*, 5(1), 37-46.

## Technology Stack

- **GDAL**: Raster processing and warping
- **DuckDB**: Fast analytical queries with spatial and H3 extensions
- **H3**: Uber's hexagonal hierarchical geospatial indexing system
- **Parquet**: Columnar storage format for efficient querying
- **Kubernetes**: Parallel processing across 122 h0 regions

## Notes

- The workflow is designed for memory efficiency by processing one h0 region at a time
- NoData filtering reduces storage by excluding cells with no carbon data
- H3 level 8 (~531m average edge) provides good balance of detail and file size
- Output is partitioned by h0 for efficient spatial queries

### S3 Access Patterns

**Local execution**: 
- Reads from public HTTPS endpoint (`https://s3-west.nrp-nautilus.io`)
- Uses `/vsicurl/` for GDAL access (no credentials needed)
- No AWS environment variables required for reading public data

**Kubernetes jobs**:
- Use internal S3 endpoint (`rook-ceph-rgw-nautiluss3.rook`)
- Access via `/vsis3/` with credentials from cluster secrets
- Much faster access due to internal network
- Path-style addressing with HTTP (no SSL)

