# Re-encoding STRING H3 Hex Parquet to INTEGER

Datasets processed before ~early 2026 stored H3 cell IDs as VARCHAR (hex string notation,
e.g. `"8001fffffffffff"`). Newer datasets use UBIGINT (decimal integer, e.g.
`576707042908045311`), which is faster to join.

This document explains how to re-encode existing STRING hex parquet in-place.

## Background

Two observable differences between old and new encoding:

| | STRING (old) | INTEGER (new) |
|---|---|---|
| Column type | `VARCHAR` | `UBIGINT` / `BIGINT` |
| Partition dir names | `h0=8001fffffffffff/` | `h0=576707042908045311/` |
| H3 function used | `h3_latlng_to_cell_string` | `h3_latlng_to_cell` |

The conversion function is `h3_string_to_h3(varchar) → UBIGINT` from the
[h3-duckdb](https://github.com/isaacbrodsky/h3-duckdb) community extension.

## Why not reprocess from scratch?

For **raster** datasets, reprocessing requires re-running GDAL warp + XYZ extraction
per h0 cell — slow, cluster-intensive, preemption-prone. The re-encode job is pure
parquet→parquet: read all hex files, cast two columns, write with new partition names.
This takes minutes instead of hours.

For **vector** datasets (WDPA, GBIF, iNat, etc.) reprocessing may be more appropriate
since the full pipeline is needed anyway to pick up any other improvements.

## Approach

Because you cannot overwrite a file you are streaming from, the job writes to a
temporary `hex-new/` path, then swaps:

```
1. DuckDB: read hex/**/*.parquet → cast h* columns → write to hex-new/ (PARTITION_BY h0)
2. rclone delete nrp:<bucket>/hex/
3. rclone move nrp:<bucket>/hex-new/ nrp:<bucket>/hex/
```

The new partition directory names are automatically created by DuckDB's `PARTITION_BY`
using the cast integer values.

## DuckDB SQL Template

```sql
INSTALL h3 FROM community; LOAD h3;
INSTALL httpfs; LOAD httpfs;
-- configure S3 credentials ...

COPY (
    SELECT
        -- all non-h3 columns unchanged, then cast each h* column:
        <value_columns>,
        h3_string_to_h3(<hN>) AS <hN>,   -- repeat for each h* column except h0
        h3_string_to_h3(h0) AS h0         -- h0 last — used as PARTITION_BY key
    FROM read_parquet('s3://<bucket>/<dataset>/hex/**/*.parquet')
) TO 's3://<bucket>/<dataset>/hex-new/'
(FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY (h0));
```

**Notes:**
- Do NOT use `hive_partitioning=true` when reading — h0 is already stored as a column
  inside the parquet files; hive partitioning would add a second VARCHAR h0 from the
  directory name.
- DuckDB writes files as `<partition>/data_0.parquet` (or `part-0.parquet` depending on
  version). Either is fine — all downstream queries use `hex/**/*.parquet` glob patterns.
- Put `h0` last in the SELECT so `PARTITION_BY (h0)` works on the cast integer value.

## Generating a k8s Job

Use this template, substituting parameters:

```bash
BUCKET=public-wyoming
DATASET=nlcd-2024
HEX_COLS="nlcd"          # non-h3 value columns (comma-separated)
H3_COLS="h8"             # h3 columns other than h0 (space-separated)
JOB_NAME="${DATASET}-reencode-hex"
```

See `catalog/wyoming/k8s/nlcd-2024/nlcd-2024-reencode-hex.yaml` as a worked example.

## Datasets to Re-encode (Issue #29)

| Dataset | Bucket | H3 cols | Status |
|---------|--------|---------|--------|
| `nlcd-2024` | `public-wyoming` | h8 | ⏳ in progress |
| `rap-pfg-biomass` | `public-wyoming` | h10 | pending |
| `rap-arte` | `public-wyoming` | h8 | pending (finish processing first) |
| `rap-iag` | `public-wyoming` | h8 | pending (finish processing first) |
| `sagebrush-design` | `public-wyoming` | h8 | pending (finish processing first) |
| WDPA | `public-wdpa` | h8 | pending (vector — consider reprocess) |
| IUCN | `public-iucn` | h8 | pending (vector — consider reprocess) |
| GBIF | `public-gbif` | h0–h9 | pending (vector) |
| iNaturalist | `public-inat` | h0–h4 | pending (vector) |
| NCP | `public-ncp` | h8 | pending (vector) |
| Carbon irrecoverable v1 | `public-carbon` | h8 | pending (raster) |
| Carbon vulnerable v1 | `public-carbon` | h0–h8 | pending (raster) |
| Overture Maps regions | `public-overturemaps` | h8 | pending (vector) |
| HydroBasins L3 | `public-hydrobasins` | h8 | pending (vector) |
