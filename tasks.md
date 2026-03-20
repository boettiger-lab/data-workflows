# Upstream Fixes Needed (cng-datasets)

## 1. Point geometry support in `geom_to_h3_cells` (`vector/h3_tiling.py`)

`h3_polygon_wkt_to_cells` silently returns NULL for non-polygon geometries. For POINT inputs, use `h3_latlng_to_cell(ST_Y(geom), ST_X(geom), resolution)` instead. The fix should detect geometry type and branch accordingly.

## 2. DuckDB `httpfs` extension signature failure (`vector/h3_tiling.py`)

`setup_duckdb_connection()` relies on DuckDB auto-installing `httpfs` at runtime, which fails with a signature validation error in the cluster environment. Pre-install and pre-load the extension in the Docker image (or handle the install explicitly before setting http params).

## 3. Silent empty-output in hex jobs produces misleading "success"

When a chunk produces 0 rows (e.g. due to #1 or invalid geometry), the job exits 0 and writes an empty parquet file. Add a warning or non-zero exit when a chunk that should have data writes 0 rows, so failures surface in the job status rather than in a downstream step.

## 4. Repartition fails ungracefully on empty chunk directory

`repartition_by_h0` crashes with a DuckDB IO error when `/tmp/hex/` has no files after writing. Add an explicit check after `result.to_parquet(local_dir)` and raise a clear error (or skip upload) if the output directory is empty, rather than letting DuckDB throw an opaque glob error.
