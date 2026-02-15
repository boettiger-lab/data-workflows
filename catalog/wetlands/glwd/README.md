# Global Lakes and Wetlands Database (GLWD) Processing

Processing pipeline for converting the GLWD raster dataset to H3-indexed parquet format.

## Overview

The GLWD dataset is a global raster of lakes and wetlands. This workflow:
1. Processes the raster by h0 hex regions (memory-efficient for global data)
2. Converts to H3-indexed parquet partitioned by h0
3. Optionally creates a Cloud-Optimized GeoTIFF (COG) for visualization

## Quick Start

### Process a single h0 region locally

```bash
python job.py \
  --i 42 \
  --zoom 8 \
  --parent-resolutions "0" \
  --input-url https://minio.carlboettiger.info/public-wetlands/GLWD_v2_0/GLWD_v2_0_combined_classes/GLWD_v2_0_main_class.tif \
  --output-url s3://public-wetlands/hex/ \
  --value-column wetland_class
```

### Kubernetes Parallel Processing

Submit the Kubernetes job to process all 122 h0 regions in parallel:

```bash
kubectl apply -f raster_job.yaml
```

Monitor progress:

```bash
kubectl get jobs wetlands
kubectl get pods -l k8s-app=wetlands
```

## Configuration

### Job Parameters

- `--i`: H0 hex index (0-121) - required for parallel processing
- `--zoom`: H3 resolution (default: auto-detect from raster resolution)
- `--parent-resolutions`: Comma-separated parent resolutions (default: "0")
- `--input-url`: Input raster URL
- `--output-url`: Output parquet base path (ends with `/`)
- `--value-column`: Name for raster value column (default: "value")
- `--nodata`: NoData value to exclude (e.g., 65535)
- `--profile`: Enable memory/runtime profiling

### H3 Resolution

The processor can auto-detect optimal H3 resolution from the raster's pixel size:

- GLWD (~1km pixels) → typically h8 or h9
- High-res imagery (~30m) → h10-h11
- Very high-res (~1m) → h14-h15

**Auto-detection (recommended):**
```bash
python job.py --i 42  # Omit --zoom to auto-detect
```

**Manual override:**
```bash
python job.py --i 42 --zoom 8  # Force h8
# Output: "ℹ Using h8 (user specified) instead of detected h9"
```

The tool provides helpful feedback when you choose a different resolution than detected, but never errors - your choice is always respected.

### Parent Resolutions

Include parent resolutions for easy aggregation later:

```bash
--parent-resolutions "9,8,0"  # h9, h8, and h0 (partitioning)
```

## Output Structure

```
s3://public-wetlands/hex/
├── h0=8009fffffffffff/
│   └── data_0.parquet
├── h0=801dfffffffffff/
│   └── data_0.parquet
└── ...
```

Each partition contains:
- `wetland_class` (or custom value column): Raster pixel values
- `h8`: H3 cell ID at resolution 8 (or specified zoom)
- `h0`: H3 cell ID at resolution 0 (partitioning key)

## Creating a COG

To create a Cloud-Optimized GeoTIFF for web visualization:

```bash
cng-datasets raster \
  --input https://minio.carlboettiger.info/public-wetlands/GLWD_v2_0/GLWD_v2_0_combined_classes/GLWD_v2_0_main_class.tif \
  --output-cog s3://public-wetlands/GLWD-cog.tif \
  --compression zstd
```

The COG is optimized for:
- Cloud rendering in titiler
- Progressive streaming
- Efficient spatial queries
- EPSG:4326 projection

## Kubernetes Job Details

The `raster_job.yaml` creates an indexed job with:

- **122 completions**: One per h0 region (global coverage)
- **61 parallelism**: Process half the regions concurrently
- **4 CPU / 34Gi memory**: Per pod (adjust based on raster size)
- **Opportunistic scheduling**: Can be preempted if needed

Each pod processes a single h0 region independently, making the workflow:
- Memory-efficient (only loads one region at a time)
- Fault-tolerant (failed regions can be retried individually)
- Scalable (add more parallelism for faster processing)

## Using the RasterProcessor Class

For custom workflows:

```python
from cng_datasets.raster import RasterProcessor

processor = RasterProcessor(
    input_path="wetlands.tif",
    output_parquet_path="s3://bucket/wetlands/hex/",
    h3_resolution=None,  # Auto-detect
    parent_resolutions=[8, 0],
    h0_index=42,  # Process specific region
    value_column="wetland_class",
    nodata_value=255,
)

# Process single h0 region
processor.process_h0_region()

# Or process all regions
processor.process_all_h0_regions()
```

## See Also

- Package documentation: [README_PACKAGE.md](../../README_PACKAGE.md)
- Vector processing example: [redlining/](../../redlining/)
- Raster source code: [cng_datasets/raster/cog.py](../../cng_datasets/raster/cog.py)
