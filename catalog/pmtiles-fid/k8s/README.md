# PMTiles `_cng_fid` rebuild (#735 group A)

21 PMTiles assets were built before their GeoParquet gained `_cng_fid` (the #372
backfill), so the tiles had no feature id. These jobs rebuild them from the final
GeoParquet over the internal endpoint and keep each asset's layer name, zoom range
and field set (SVI keeps its 3–4 field subset), adding `_cng_fid`.

| file | does |
|---|---|
| `assets.py` | the 20 small assets: source parquet, layer, tippecanoe flags, tile field → parquet column |
| `build.py` | one asset per index: DuckDB extract → GeoJSONSeq → tippecanoe → footer check → `staging/735-fid/<key>` |
| `configmap.yaml` / `pmtiles-fid.yaml` | indexed Job over `assets.py` (regenerate the ConfigMap after editing either `.py`) |
| `flood-hazard-pmtiles-fid.yaml` | the large one, on the `rechunk-scratch` PVC |
| `check_staged.py` | compares staged footers with the live/backup ones (layers, zooms, fields + `_cng_fid`) |
| `swap.sh` | backs up live → `staging/735-nofid-backup/<key>`, then staged → live |
| `stac_add_fid.py` | adds `{"name": "_cng_fid", "type": "int64"}` to the PMTiles assets' `table:columns` |

Deliberate field changes: `seafloor-geomorphology` drops the `_ogr_geometry__bbox.*`
fields (a GDAL bbox-covering artifact in the old tiles, also removed from its STAC).
The SVI 2000/2010 county tiles keep their old renames (`ST_ABBR`, `COUNTY`, and
`FIPS`, which is the 3-digit `CNTY_FIPS` for 2000).

Run order: apply `configmap.yaml` + `pmtiles-fid.yaml`, then `flood-hazard-pmtiles-fid.yaml`,
then `check_staged.py` → `swap.sh` → `stac_add_fid.py` + `scripts/verify-stac.py` + `rclone copyto`.
