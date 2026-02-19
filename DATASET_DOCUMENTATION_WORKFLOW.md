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
duckdb -c "INSTALL httpfs; LOAD httpfs; DESCRIBE SELECT * FROM 'https://s3-west.nrp-nautilus.io/public-<dataset>/<file>.parquet' LIMIT 1;"
```

For PMTiles, confirm the `source-layer` name. This is always the **last path segment** of the `--dataset` flag used during processing (e.g., `--dataset padus-4-1/fee` → source-layer is `fee`). You do NOT need to inspect the file — derive it from the `--dataset` flag.

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
- **Extensions**: Use `https://stac-extensions.github.io/table/v1.2.0/schema.json` for tabular data.
- **Links**:
    - `"rel": "root"` -> `https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json`
    - `"rel": "parent"` -> `https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json`
    - `"rel": "self"` -> `https://s3-west.nrp-nautilus.io/public-<dataset>/stac-collection.json`
    - `"rel": "describedby"` -> `https://s3-west.nrp-nautilus.io/public-<dataset>/README.md`
- **Assets**: Define the data files (parquet, pmtiles, cog, etc.).
- **PMTiles asset description**: MUST include `source-layer: "<name>"` so users know the MapLibre layer name without inspecting the file. The name = last segment of `--dataset`.
- **Table Columns**: Use the `table:columns` array to formally define the schema (name, type, description).

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
