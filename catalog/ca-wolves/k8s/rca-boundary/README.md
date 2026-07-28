# rca-boundary — build recipe

Northern California Regional Conservation Assessment (RCA) study-area boundary →
`public-ca-wolves/rca-boundary` (GeoParquet + PMTiles + H3 hex res 8). Issue: #496.

Source: `RCA_FINALFINAL.shp` (23 polygons; EPA Level III ecoregions × 13 NorCal counties),
staged to `s3://public-ca-wolves/rca-boundary/raw/`.

Generated with:

```bash
cng-datasets workflow \
  --dataset rca-boundary \
  --source-url s3://public-ca-wolves/rca-boundary/raw/RCA_FINALFINAL.shp \
  --bucket public-ca-wolves --namespace geo-workflows \
  --h3-resolution 8 --parent-resolutions "0" \
  --hex-memory 8Gi --max-completions 200 --max-parallelism 50 \
  --output-dir catalog/ca-wolves/k8s/rca-boundary
```

## ⚠️ Manual run order — the source has a junk `GEOMETRY` attribute column

The shapefile carries a **non-geometry attribute column literally named `GEOMETRY`** (a DOUBLE
= `Shape_Area/10000`). The hex step's geometry-column autodetection collides with it, so
`ST_GeometryType(geom)` binds to that DOUBLE and the hex job fails with
`Binder Error: No function matches ... 'ST_GeometryType(DOUBLE)'`. Reported upstream:
boettiger-lab/datasets#171.

Because of that, the orchestrator (`workflow.yaml`) is **not** run end-to-end here. Run the
steps manually, inserting a one-off clean step between convert and hex:

```bash
kubectl apply -n geo-workflows -f rca-boundary-setup-bucket.yaml     # no-op; bucket exists
kubectl apply -n geo-workflows -f rca-boundary-convert.yaml          # -> rca-boundary.parquet
kubectl apply -n geo-workflows -f rca-boundary-clean-parquet.yaml    # drop the junk GEOMETRY col
# then swap the cleaned file into place:
#   rclone moveto nrp:public-ca-wolves/rca-boundary-clean.parquet nrp:public-ca-wolves/rca-boundary.parquet
kubectl apply -n geo-workflows -f rca-boundary-pmtiles.yaml          # -> rca-boundary.pmtiles
kubectl apply -n geo-workflows -f rca-boundary-hex.yaml              # completions:1 (23 features < 1000)
kubectl apply -n geo-workflows -f rca-boundary-repartition.yaml      # chunks/ -> hex/h0=*/data_0.parquet
```

`rca-boundary-hex.yaml` has `completions: 1` (not the generated 200) because 23 features fit in
one chunk of 1000 — 199 empty pods would otherwise be pure waste.

STAC + README are published to `s3://public-ca-wolves/rca-boundary/` (not stored in this repo).
