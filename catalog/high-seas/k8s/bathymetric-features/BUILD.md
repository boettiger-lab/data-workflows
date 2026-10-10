# bathymetric-features build notes

Collection: `s3://public-high-seas/bathymetric-features/` (issue #766), layers `peaks` and `contours`.
Source: Souche, Hartz and Schmid (2026), PANGAEA doi:10.1594/PANGAEA.992546, `CC-BY-4.0`.
Accessed 2026-10-09.

| staged raw | bytes | sha256 |
|---|---|---|
| `raw/bathymetry_peaks_GEBCO2025_15s.gpkg` | 23,797,760 | `9dc975a25a4fc21945940338a193f1e3549520dc3621f65a87d1a55cb009896a` |
| `raw/bathymetry_features_GEBCO2025_15s.gpkg` | 2,683,092,992 | `e1837a7ded65ac1a9357e1cf74fff7f4626f663a12976222552a07502371c4f0` |

## Run order

```bash
kubectl apply -n geo-workflows -f bathymetric-features-stage-raw.yaml

# peaks: full workflow
kubectl apply -n geo-workflows -f peaks/workflow-rbac.yaml -f peaks/configmap.yaml -f peaks/workflow.yaml

# contours: step by step, the geometry fix runs between convert and hex/pmtiles
kubectl apply -n geo-workflows -f contours/bathymetric-features-contours-convert.yaml
kubectl apply -n geo-workflows -f contours/bathymetric-features-contours-fix-antimeridian.yaml
kubectl apply -n geo-workflows -f contours/bathymetric-features-contours-hex.yaml -f contours/bathymetric-features-contours-pmtiles.yaml
# chunk 0 (the 1,000 largest polygons) runs for hours: once the other 627 finish, delete the hex
# job, re-run chunk 0 as 40 slices, and merge them into chunks/
kubectl apply -n geo-workflows -f contours/bathymetric-features-contours-hex-c0.yaml
kubectl apply -n geo-workflows -f contours/bathymetric-features-contours-c0-merge.yaml
kubectl apply -n geo-workflows -f contours/bathymetric-features-contours-repartition.yaml

# STAC + README
python3 gen_stac.py /tmp/bf
scripts/verify-stac.py --no-data /tmp/bf/stac-collection.json
rclone copyto /tmp/bf/stac-collection.json nrp:public-high-seas/bathymetric-features/stac-collection.json
rclone copyto /tmp/bf/README.md nrp:public-high-seas/bathymetric-features/README.md
scripts/verify-stac.py --bucket public-high-seas --dataset bathymetric-features   # must exit 0
```

Then add a `child` link to `public-high-seas/stac-collection.json`.

## Why the contours need a fix step

Upstream publishes 429 contours (185 features near the date line) with longitudes out to
+/-190, and 2 contours as GeometryCollections of two polygons. The hex step drops the part of a
polygon beyond +/-180 (feature 34916: 796 cells instead of about 1,227). The fix job splits those
polygons at +/-180 and shifts the overflow by 360 degrees, and turns the two collections into
MultiPolygons. Attributes are untouched, so `centroid_lon` still lies outside +/-180 for 68 contours.

## Resolution and sizing

Native h8, parent h0, both layers. The contours have 627,471 rows, so the hex needs 628 chunks of
1,000. Rows are ordered largest first: about 289M h8 cells in total, median chunk about 70k cells,
chunk 0 about 77M. The largest single polygon is about 1.1M cells.

## Measured

| | peaks | contours |
|---|---|---|
| rows | 143,888 (`peak_id` unique, 1 to 145,190) | 627,471 (125,514 features) |
| quality control | 125,514 clean; `error_with_contours` 17,186; `error_no_contours` 1,188 | 25% level complete; 100% level missing for 57 features |
| depth | `depth` -9,460 to 0 (23 at 0) | `contour_depth` -9,406 to -79.25; `peak_depth` -9,070 to 0 |
| prominence | 300 to 5,435 | same |
| other | 604 peaks relocated; geometry within 0.0104 deg of lat/lon columns | `nested_on_feature_id` empty string for 63,335 features; `feature_id` = `peak_id` |

The expected contour count is not 125,514 x 5: some levels failed to generate (paper, Methods),
so `--expect-features` is the GeoPackage's own count, 627,471.
