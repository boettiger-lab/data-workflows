# deep-submergence-dives build notes

Collection: `s3://public-high-seas/deep-submergence-dives/` (issue #763)
Source: `DeepSubmergenceMetadata.geojson`, supplied by the authors of Bell et al. 2025,
*Science Advances* 11(19): eadp8602 (doi:10.1126/sciadv.adp8602), received 2026-10-08
(22,594,453 bytes, sha256 `11d11dae7e7a6be7069b7645fdfb711ddfeed728cf1a5cc192dba8303c6eb0cf`).
`CC-BY-4.0`. The Zenodo supplement (doi:10.5281/zenodo.13948032) is cited only; its points and
attributes differ from this file.

## Run order

```bash
# 1. stage the raw (from a machine holding the file)
rclone copyto DeepSubmergenceMetadata.geojson nrp:public-high-seas/raw/DeepSubmergenceMetadata.geojson

# 2. build: setup-bucket -> convert -> pmtiles + hex -> repartition
kubectl apply -n geo-workflows -f workflow-rbac.yaml
kubectl apply -n geo-workflows -f configmap.yaml -f workflow.yaml
kubectl -n geo-workflows get jobs | grep deep-submergence-dives

# 3. STAC: size and sha256 measured from the staged object
python3 gen_stac.py DeepSubmergenceMetadata.geojson /tmp/stac-collection.json <size> <sha256>
scripts/verify-stac.py --no-data /tmp/stac-collection.json
rclone copyto /tmp/stac-collection.json nrp:public-high-seas/deep-submergence-dives/stac-collection.json
scripts/verify-stac.py --bucket public-high-seas --dataset deep-submergence-dives   # must exit 0
```

Then add a `child` link to `public-high-seas/stac-collection.json` and upload the README.

After convert, check the flat's column list against `gen_stac.py`. GeoJSON conversion can add
an `OGC_FID` column (it did for `ebsa-2023`), which the STAC must then document.

## Resolution

Native h8, parent h0. Each point maps to one cell. h8 (about 0.74 km²) suits the positions,
whose reported precision ranges from whole degrees to 1e-6 degrees.

## Measured from the supplied file

| column | measured |
|---|---|
| rows | 43,422, all `Point`, `OBJECTID` 1 to 43,422 unique |
| distinct locations | 29,289 (one site holds 292 dives) |
| `Depth` | -10,936 to -200 m, no sentinel, all negative |
| `Year` | 1958 to 2024 |
| `Latitude` | -78.4833 to 81.56314; 1,986 whole-degree values, 1,448 rows whole-degree in both axes |
| `Longitude` | -180 to 180; equals the geometry x on every row |
| `Platform` | 119 distinct, 1 null |
| `Geomorphology_Description` | 26 values, 10 null |
| `Basin` | 9 values, 11 null |
| `Sovereign` | 120 values, null on all 8,176 `High Seas` rows |
| `Jurisdiction` | `EEZ` 35,246, `High Seas` 8,176 |
