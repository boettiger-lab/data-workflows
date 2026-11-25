# Agent guide

This dataset's specifics are in the STAC JSON beside this file: read it first. `table:columns`
gives each column's type, meaning and coded `values`. Assets are typed by role (`data`, `visual`).
The README (`rel: describedby`) gives provenance and caveats. A catalog has no data of its own:
follow its child links, each of which has its own AGENTS.md.

## H3 hex assets

- A hex asset (`…/hex/h0=*/data_0.parquet`) holds the data indexed to H3 cells, one column
  `h<res>` per resolution in `h3:native_resolution` and `h3:parent_resolutions`.
- Cell ids are 64-bit integers, stored as `BIGINT` in some files and `UBIGINT` in others. Cast
  both sides to `UBIGINT` before joining.
- Join datasets on `h8` when both carry it. Otherwise use the finest resolution they share,
  coarsening with `h3_cell_to_parent`.
- Files are hive-partitioned by `h0`, sometimes under `year=` or `period=`. Filter on `h0` to
  read fewer files.
- A feature's attributes repeat on every cell it covers. Never sum a per-feature total (an area,
  a count) over cells; count features with `COUNT(DISTINCT _cng_fid)` where that column exists.

## Access

Query in place. Single files (GeoParquet, COG, PMTiles) read over HTTPS range requests. A hex
glob cannot be listed over HTTPS; read it over S3 from NRP, anonymously:

```sql
INSTALL httpfs; LOAD httpfs; INSTALL h3 FROM community; LOAD h3;
CREATE SECRET (TYPE s3, ENDPOINT 's3-west.nrp-nautilus.io', URL_STYLE 'path', REGION 'us-east-1');
SELECT * FROM read_parquet('s3://<bucket>/<dataset>/hex/**/*.parquet', hive_partitioning = true)
WHERE h0 = <cell>;
```
