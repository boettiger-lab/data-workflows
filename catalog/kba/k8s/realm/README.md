# KBA 2026-03: marine / coastal / terrestrial realm (#748)

Adds `marine_frac` and `realm` to all three `public-kba/kba-2026-03/sites` assets (GeoParquet, PMTiles, H3 hex).

**Method.** `marine_frac` is the share of a site's distinct H3 resolution-8 cells (from the KBA hex) that fall in the ocean mask:
the IHO EEZ hex (`public-high-seas/iho/eez/hex`, native res 8) together with the IHO high-seas hex
(`public-high-seas/iho/high-seas/hex`, native res 4, matched via `h3_cell_to_parent(h8, 4)`).
`realm` = `marine` (>= 0.9), `coastal` (0.1 to < 0.9), `terrestrial` (< 0.1).

**Steps used (2026-10-05).**
1. Back up the live files: `rclone copy` of `sites.parquet`, `sites.pmtiles` and `sites/hex/` to `s3://public-kba/staging/kba-realm-backup/` (STAC too).
2. `kubectl apply -f kba-realm-build.yaml` (namespace `geo-workflows`). This writes `sites.parquet` (row groups of 2000),
   `sites.pmtiles` (the same ogr2ogr + tippecanoe command as `../sites/kba-2026-03-sites-pmtiles.yaml`) and one
   `data_0.parquet` per `h0` into `s3://public-kba/staging/kba-realm/`.
3. Verify through the duckdb-geo MCP: 16,509 rows, hex `COUNT(DISTINCT SitRecID)` = 16,509, hex rows unchanged (28,429,517),
   existing attributes and geometry identical by `_cng_fid`, PMTiles footer with the same zooms and layer plus the two new fields.
4. Swap: the `h0` partition sets are identical, so `rclone copy` staging onto `kba-2026-03/`, then `rclone check --one-way`.
5. Add the columns to the STAC parquet + hex (identical text) and PMTiles (lean form); `verify-stac.py --bucket public-kba --dataset kba-2026-03/sites` exits 0.

Result: marine 1,668, coastal 2,071, terrestrial 12,770.

A `PARTITION_BY` COPY split three large partitions into `data_0` + `data_1`, which a `data_0.parquet` glob silently misses.
The job therefore writes each `h0` partition with its own COPY.
