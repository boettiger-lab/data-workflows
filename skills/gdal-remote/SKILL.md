---
name: gdal-remote
description: >
  Work with geospatial data using GDAL/OGR and DuckDB, especially reading remote files
  via virtual filesystems (/vsicurl/, /vsis3/), inspecting multi-layer sources, converting
  between formats, and handling geometry edge cases. Covers the relationship between
  GDAL, DuckDB spatial, and Parquet/GeoParquet — including which tool can read what and
  common pitfalls with driver availability. Use when working with geospatial file formats
  (GDB, GPKG, Shapefile, GeoParquet, GeoTIFF, PMTiles), converting between them, or
  reading remote geospatial data.
license: Apache-2.0
metadata:
  author: boettiger-lab
  version: "1.0"
---

# GDAL, OGR, and DuckDB for Remote Geospatial Data

GDAL/OGR is the foundational library for reading and writing geospatial formats. DuckDB with its spatial extension is often a better choice for analytical queries on Parquet. Understanding which tool to use when — and what each can and cannot do — is essential.

## Choosing the Right Tool

| Task | Best tool | Why |
|------|-----------|-----|
| Inspect layers in a remote GDB/GPKG | `ogrinfo` | Quick, no data download |
| Convert GDB/Shapefile → GeoParquet | `ogr2ogr` or DuckDB `ST_Read` | Both work; DuckDB allows transforms in SQL |
| Query/filter a GeoParquet file | DuckDB native `read_parquet()` | Columnar pushdown, much faster than GDAL |
| Spatial joins, aggregation on Parquet | DuckDB with spatial extension | SQL interface, fast |
| Convert GeoParquet → GeoJSON/GeoJSONSeq | `ogr2ogr` | Streaming, handles large files |
| Create COG from GeoTIFF | `gdal.Translate` / `gdal.Warp` | Python API or CLI |
| Reproject raster data | `gdalwarp` | Full control over resampling |

## GDAL Parquet Driver Availability

**GDAL is often not built with the Parquet (Arrow) driver.** This depends on whether the Arrow/Parquet C++ libraries were available at compile time. Always check first:

```bash
# Check if Parquet driver is available
ogrinfo --formats | grep -i parquet

# Check if Arrow driver is available
ogrinfo --formats | grep -i arrow
```

If you see no output, GDAL cannot read or write Parquet files. In that case, use DuckDB instead for Parquet operations.

The `ghcr.io/osgeo/gdal:ubuntu-full-latest` Docker image (used in this repo) **does** include the Parquet driver. Most system-installed GDAL packages (e.g., `apt install gdal-bin`) do **not**.

## DuckDB vs GDAL for Parquet

When working with GeoParquet files, **DuckDB is almost always the better choice**:

- Native columnar Parquet reader with predicate pushdown and column pruning
- Fast SQL-based filtering, joins, and aggregation
- Reads directly from S3 (`s3://`) or HTTPS URLs
- Handles hive-partitioned layouts natively (`read_parquet('s3://bucket/hex/**')`)

Use GDAL for Parquet only when you need format conversion (e.g., Parquet → GeoJSONSeq for tippecanoe).

## DuckDB Spatial and Its Vendored GDAL

DuckDB's `spatial` extension bundles its own internal copy of GDAL. This vendored GDAL has important limitations:

### What DuckDB spatial's `ST_Read()` CAN do

- Read most GDAL vector formats: Shapefile, GDB, GPKG, GeoJSON, FlatGeobuf, etc.
- Use VSI prefixes to read remote files: `/vsicurl/https://...`, `/vsis3/...`
- Apply spatial transforms: `ST_Transform()`, `ST_FlipCoordinates()`
- Select specific layers from multi-layer sources

```sql
INSTALL spatial;
LOAD spatial;

-- Read a remote GDB layer
SELECT * FROM ST_Read('/vsicurl/https://example.com/data.gdb', layer='MyLayer');

-- Read with reprojection
SELECT ST_Transform(geom, 'EPSG:4269', 'EPSG:4326') AS geom, *
FROM ST_Read('/vsicurl/https://example.com/data.gdb', layer='MyLayer');
```

### What DuckDB spatial's `ST_Read()` CANNOT do

- **Read GeoParquet** — the vendored GDAL is not built with Arrow libraries, so `ST_Read('file.parquet')` will fail
- **Write to `/vsis3/`** — the vendored GDAL cannot write directly to S3 buckets (a fully configured system GDAL can)

### Reading GeoParquet in DuckDB (the right way)

Use DuckDB's **native Parquet reader**, not `ST_Read()`. Load the spatial extension first so DuckDB recognizes the geometry blob column:

```sql
INSTALL spatial;
LOAD spatial;

-- DuckDB's native reader handles parquet; spatial extension detects geometry
SELECT * FROM read_parquet('s3://public-padus/padus-4-1/fee.parquet') LIMIT 10;

-- Also works with HTTPS
SELECT * FROM read_parquet('https://s3-west.nrp-nautilus.io/public-padus/padus-4-1/fee.parquet');

-- Hive-partitioned reads
SELECT * FROM read_parquet('s3://public-padus/padus-4-1/fee/hex/**');
```

Key distinction: DuckDB native `read_parquet()` uses `s3://` prefixes (configured via DuckDB secrets). DuckDB spatial's `ST_Read()` uses GDAL's `/vsicurl/` or `/vsis3/` prefixes. Don't mix them up.

## OGR: Inspecting Remote Data

### List layers in a multi-layer source

```bash
ogrinfo /vsicurl/https://s3-west.nrp-nautilus.io/public-padus/raw/PADUS4_1Geodatabase.gdb
```

Output shows layer names, geometry types, and feature counts.

### Get layer details (schema, feature count, extent)

```bash
# Specific layer — use -so for summary only (no feature dump)
ogrinfo -so /vsicurl/https://example.com/data.gdb LayerName

# All layers summary
ogrinfo -so -al /vsicurl/https://example.com/data.gdb
```

The `-so` (summary only) flag is essential for remote files — without it, ogrinfo tries to print every feature.

### Count features in a layer

Parse the `Feature Count:` line from ogrinfo output:

```bash
ogrinfo -so /vsicurl/https://example.com/data.gdb LayerName | grep "Feature Count"
```

## OGR: Format Conversion

### Basic conversion with layer selection

```bash
# GDB layer → GeoParquet
ogr2ogr -f Parquet output.parquet /vsicurl/https://example.com/data.gdb "LayerName"

# GDB layer → GeoJSONSeq (for tippecanoe, streaming)
ogr2ogr -f GeoJSONSeq output.geojsonl /vsicurl/https://example.com/data.gdb "LayerName" -progress
```

### Writing directly to S3 with `/vsis3/`

When GDAL is properly configured with S3 credentials and endpoints, you can write directly to S3:

```bash
ogr2ogr -f Parquet /vsis3/bucket/output.parquet /vsis3/bucket/raw/source.gdb "LayerName" -progress
```

This requires GDAL environment variables to be set:
```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_S3_ENDPOINT=rook-ceph-rgw-nautiluss3.rook   # internal endpoint inside k8s
export AWS_HTTPS=NO
export AWS_VIRTUAL_HOSTING=FALSE
```

### Pipe to tippecanoe for PMTiles

```bash
# Stream GeoJSONSeq directly to tippecanoe via /vsistdout/
ogr2ogr -f GeoJSONSeq /vsistdout/ /vsis3/bucket/data.gdb "LayerName" \
  | tippecanoe -o output.pmtiles -l layername \
    --drop-densest-as-needed --extend-zooms-if-still-dropping --force

# Or from GeoParquet
ogr2ogr -f GeoJSONSeq /vsistdout/ /vsicurl/https://example.com/data.parquet \
  | tippecanoe -o output.pmtiles -l layername \
    --drop-densest-as-needed --extend-zooms-if-still-dropping --force
```

## Geometry Edge Cases

### Curved geometries (MULTISURFACE, CURVEPOLYGON)

Some GDB files contain curved geometry types that many tools cannot handle. Linearize them during conversion:

```bash
ogr2ogr -f GPKG \
  -nlt CONVERT_TO_LINEAR \
  -nlt PROMOTE_TO_MULTI \
  output.gpkg input.gdb "LayerName"
```

- `-nlt CONVERT_TO_LINEAR` — converts CircularString, CompoundCurve, CurvePolygon, MultiSurface to linear equivalents
- `-nlt PROMOTE_TO_MULTI` — ensures consistent multi-geometry types (MULTIPOLYGON not mixed POLYGON/MULTIPOLYGON)

You can combine these in a two-step pipeline: linearize to GPKG first, then convert to Parquet.

### FID / row ID issues

Some formats (GDB especially) include an FID column that can cause Arrow type mapping issues. Use `-unsetFid` if you hit problems:

```bash
ogr2ogr -f Parquet output.parquet input.gdb "LayerName" -unsetFid
```

## VSI Virtual Filesystem Prefixes

| Prefix | Purpose | Example |
|--------|---------|---------|
| `/vsicurl/` | Read remote files over HTTP/HTTPS | `/vsicurl/https://example.com/data.gdb` |
| `/vsis3/` | Read/write S3 buckets (requires credentials) | `/vsis3/bucket/path/file.parquet` |
| `/vsistdout/` | Stream output to stdout (for piping) | `ogr2ogr -f GeoJSONSeq /vsistdout/ input.gdb` |
| `/vsicurl_streaming/` | Streaming HTTP read (less seeking) | For formats that support sequential access |
| `/vsizip/` | Read inside zip archives | `/vsizip//vsicurl/https://example.com/data.zip` |

### Converting between URL styles

When you have an `s3://` URL and need a VSI path:

```
s3://bucket/path/file.gdb
→ /vsis3/bucket/path/file.gdb           (for GDAL with S3 credentials)
→ /vsicurl/https://s3-west.nrp-nautilus.io/bucket/path/file.gdb   (for public HTTP access)
```

When you have an HTTPS URL:
```
https://s3-west.nrp-nautilus.io/bucket/path/file.gdb
→ /vsicurl/https://s3-west.nrp-nautilus.io/bucket/path/file.gdb
```

## GDAL Python API (Raster)

For raster operations, use the GDAL Python API:

```python
from osgeo import gdal, osr
gdal.UseExceptions()

# Open a remote raster
ds = gdal.Open('/vsicurl/https://example.com/raster.tif')

# Get metadata
gt = ds.GetGeoTransform()  # [origin_x, pixel_width, 0, origin_y, 0, -pixel_height]
srs = osr.SpatialReference(wkt=ds.GetProjection())
band = ds.GetRasterBand(1)
nodata = band.GetNoDataValue()

# Create a COG with reprojection
warp_options = gdal.WarpOptions(
    dstSRS='EPSG:4326',
    format='COG',
    creationOptions=['COMPRESS=DEFLATE', 'BLOCKSIZE=512', 'NUM_THREADS=ALL_CPUS'],
    resampleAlg='nearest',
    multithread=True,
)
gdal.Warp('output.tif', '/vsicurl/https://example.com/raster.tif', options=warp_options)

# Create COG without reprojection (just optimize)
gdal.Translate('output.tif', 'input.tif',
    format='COG',
    creationOptions=['COMPRESS=DEFLATE', 'BLOCKSIZE=512'])
```

## Common Pitfalls

1. **Assuming GDAL has Parquet support** — Check `ogrinfo --formats | grep -i parquet` first. Most system installs lack it. Use DuckDB for Parquet instead.
2. **Using `ST_Read()` for GeoParquet in DuckDB** — The vendored GDAL in DuckDB spatial can't read Parquet. Use `read_parquet()` with the spatial extension loaded.
3. **Mixing URL styles** — `s3://` is for DuckDB native reader; `/vsicurl/` and `/vsis3/` are for GDAL (including DuckDB's `ST_Read()`). Don't pass `s3://` to `ST_Read()` or `/vsicurl/` to `read_parquet()`.
4. **Forgetting `-so` with remote ogrinfo** — Without summary-only mode, ogrinfo dumps every feature over the network.
5. **Curved geometries silently breaking downstream** — Always linearize GDB sources with `-nlt CONVERT_TO_LINEAR` if the source contains MULTISURFACE, CURVEPOLYGON, or similar types.
6. **DuckDB spatial's vendored GDAL can't write to S3** — `ST_Read` can read `/vsis3/` paths but `COPY ... TO '/vsis3/...'` via the spatial extension's GDAL won't work. Use DuckDB's native `COPY ... TO 's3://...'` for Parquet output, or use system GDAL for other formats.
