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

For PMTiles, you can inspect the metadata using `pmtiles` CLI or by creating a temporary inspection script.

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
mkdir -p datasets/<dataset>/stac/
```

### A. Create `README.md`

Create `datasets/<dataset>/stac/README.md` with:
- **Overview**: What the dataset is.
- **Source & Attribution**: Citation, source URL, license.
- **Data Format**: Description of files (H3 parquet, PMTiles, COG).
- **Data Dictionary**: detailed table of all columns/fields with types and descriptions.
- **Usage Notes**: any specific caveats (e.g., "use DISTINCT for overlapping polygons").

### B. Create `stac-collection.json`

Create `datasets/<dataset>/stac/stac-collection.json` following the STAC standard.
- **Extensions**: Use `https://stac-extensions.github.io/table/v1.2.0/schema.json` for tabular data.
- **Links**:
    - `"rel": "root"` -> `https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json`
    - `"rel": "parent"` -> `https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json`
    - `"rel": "self"` -> `https://s3-west.nrp-nautilus.io/public-<dataset>/stac-collection.json`
    - `"rel": "describedby"` -> `https://s3-west.nrp-nautilus.io/public-<dataset>/README.md`
- **Assets**: Define the data files (parquet, cog, etc.).
- **Table Columns**: Use the `table:columns` array to formally define the schema (name, type, description).

## 5. Upload to S3

Upload the documentation to the public bucket. This makes it the "official" documentation.

```bash
rclone copy datasets/<dataset>/stac/README.md nrp:public-<dataset>/
rclone copy datasets/<dataset>/stac/stac-collection.json nrp:public-<dataset>/
```

## 6. Update Catalog (Optional)

If this is a new dataset, ensure it is linked in the central catalog: `nrp:public-data/stac/catalog.json`.

## 7. Commit to Git

Commit the `stac/` directory to the repository to track valid changes to metadata.
