# Dataset Documentation Workflow

This document outlines the standard process for documenting geospatial datasets in this repository. The goal is to ensure every dataset on the S3 bucket has a comprehensive `README.md` and a STAC collection text file (`stac-collection.json`) with full column/field definitions.

## 1. Verify Dataset on S3

First, confirm the dataset exists and understand its structure (Parquet, PMTiles, COG, etc.).

```bash
# List files in the bucket
rclone ls nrp:public-<dataset>/
```

## 2. Inspect Schema

For Parquet files, use DuckDB to inspect the schema and understand the columns/fields.

```bash
# Install duckdb and httpfs extension if needed
duckdb -c "
INSTALL httpfs; LOAD httpfs;
SET s3_endpoint='s3-west.nrp-nautilus.io';
SET s3_url_style='path';
DESCRIBE SELECT * FROM read_parquet('s3://public-<dataset>/<file>.parquet') LIMIT 1;
"
```

**REQUIRED: Query categorical columns for unique values.** The `table:columns` in the STAC and data dictionary in the README must document all distinct values for categorical/coded columns — do not guess or omit them. Use DuckDB to discover them:

```bash
duckdb -c "
INSTALL httpfs; LOAD httpfs;
SET s3_endpoint='s3-west.nrp-nautilus.io';
SET s3_url_style='path';
-- Get row count + distinct counts for key categorical fields
SELECT
  COUNT(*) as total,
  COUNT(DISTINCT my_category_col) as n_categories
FROM read_parquet('s3://public-<dataset>/<file>.parquet');

-- Get all unique values with counts for a categorical column
SELECT my_category_col, COUNT(*) as n
FROM read_parquet('s3://public-<dataset>/<file>.parquet')
GROUP BY 1 ORDER BY n DESC;
"
```

Include the actual unique values in both the README data dictionary and the `summaries` block of `stac-collection.json`.

For PMTiles, confirm the `source-layer` name. This is always the **last path segment** of the `--dataset` flag used during processing (e.g., `--dataset padus-4-1/fee` → source-layer is `fee`). You do NOT need to inspect the file — derive it from the `--dataset` flag.

For COG rasters, inspect band count, data type, and nodata value:

```bash
# Inspect raster metadata (band count, type, nodata, spatial info)
gdalinfo /vsicurl/https://s3-west.nrp-nautilus.io/public-<dataset>/<file>-cog.tif
```

## 3. Research Metadata & Citations

Find the official source of the data to get:
- **Citation**: Proper attribution for the data provider.
- **License**: Terms of use.
- **Column Dictionary**: Definitions for every column/field.
- **Methodology**: How the data was created.

**Common Sources:**
- Official data portals (e.g., Protected Planet, CDC, IUCN).
- Peer-reviewed papers (DOI).
- Technical manuals or user guides.

## 4. Create Documentation (Version Controlled)

Create a `stac/` subdirectory for the dataset to store version-controlled documentation.

```bash
mkdir -p catalog/<dataset>/stac/
```

### A. Create `README.md`

Create `catalog/<dataset>/stac/README.md` with:
- **Overview**: What the dataset is.
- **Source & Attribution**: Citation, source URL, license.
- **Data Format**: Description of files (H3 parquet, PMTiles, COG).
- **Data Dictionary**: detailed table of all columns/fields with types and descriptions.
- **MapLibre GL JS example** with the correct `source-layer` name (= last segment of `--dataset`).
- **DuckDB example** with the full public URL to the parquet file.
- **Usage Notes**: any specific caveats (e.g., "use DISTINCT for overlapping polygons").

### B. Create `stac-collection.json`

Create `catalog/<dataset>/stac/stac-collection.json` following the STAC standard.

**Extensions** — choose based on dataset type:
- **Vector/Tabular** (GeoParquet, hex parquet): `https://stac-extensions.github.io/table/v1.2.0/schema.json`
- **Raster COG**: also add `https://stac-extensions.github.io/eo/v1.1.0/schema.json` and document bands in `summaries.eo:bands`

**Links**:
- `"rel": "root"` -> `https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json`
- `"rel": "parent"` -> `https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json`
- `"rel": "self"` -> `https://s3-west.nrp-nautilus.io/public-<dataset>/stac-collection.json`
- `"rel": "describedby"` -> `https://s3-west.nrp-nautilus.io/public-<dataset>/README.md`

**Assets**: Define the data files (parquet, pmtiles, cog, etc.).

**Asset key naming — CRITICAL**: The JSON key for each asset MUST be the **dataset name** (last segment of `--dataset`), not the format name. Do NOT use generic keys like `"pmtiles"`, `"geoparquet"`, or `"h3-parquet"`. Use descriptive, dataset-specific keys:

```json
"assets": {
    "cd": {                          ← dataset name, NOT "pmtiles"
        "href": "...cd.pmtiles",
        "type": "application/vnd.pmtiles",
        "vector:layers": ["cd"],
        "roles": ["visual"]
    },
    "cd-parquet": {                  ← dataset name + format suffix, NOT "geoparquet"
        "href": "...cd.parquet",
        "type": "application/vnd.apache.parquet",
        "roles": ["data"]
    },
    "cd-hex": {                      ← dataset name + suffix, NOT "h3-parquet"
        "href": ".../cd/hex/",
        "type": "application/vnd.apache.parquet",
        "roles": ["data"]
    }
}
```

Generic keys like `"pmtiles"` are unusable when a collection has multiple PMTiles assets, and cause layer ID collisions in downstream apps. Always use the dataset name.

- **Vector layer assets**: Any asset with named layers (PMTiles, GDB, GPKG) MUST include `"vector:layers": ["<name>"]`. For PMTiles, the layer name = last segment of `--dataset`.
- **COG assets**: Use `"type": "image/tiff; application=geotiff; profile=cloud-optimized"` and list `"roles": ["data", "visual"]`.

**Table Columns**: Use the `table:columns` array to formally define the schema (name, type, description). **Always query the actual data** for types and categorical values — do not guess.

**Summaries**: Document key categorical column values (from real queries) and, for rasters, band metadata:
```json
"summaries": {
  "eo:bands": [
    {
      "name": "band_name",
      "description": "Human-readable description of what the band measures",
      "data_type": "uint8",
      "nodata": 255
    }
  ]
}
```

## 5. Upload to S3

Upload the documentation to the public bucket. This makes it the "official" documentation.

```bash
rclone copy catalog/<dataset>/stac/README.md nrp:public-<dataset>/
rclone copy catalog/<dataset>/stac/stac-collection.json nrp:public-<dataset>/
```

## 6. Update Main STAC Catalog

For new datasets, add links to the central catalog at `nrp:public-data/stac/catalog.json`:

```bash
# Download current catalog
curl -s https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json > /tmp/catalog.json

# Edit to add new child links in the "links" array:
# {
#   "rel": "child",
#   "href": "https://s3-west.nrp-nautilus.io/<bucket>/<dataset>/stac-collection.json",
#   "type": "application/json",
#   "title": "Your Dataset Title"
# }

# Upload updated catalog
rclone copyto /tmp/catalog.json nrp:public-data/stac/catalog.json
```

Verify at: https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json

## 7. Commit to Git

Commit the `stac/` directory to the repository to track valid changes to metadata.
