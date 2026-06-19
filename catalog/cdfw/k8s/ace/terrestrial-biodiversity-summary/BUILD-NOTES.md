# Build notes — ACE v3.0 Terrestrial Biodiversity Summary (ds2739)

Issue: boettiger-lab/data-workflows#228. Locked scope lives in that issue.

Dataset: `ace/terrestrial-biodiversity-summary` → `s3://public-cdfw/ace/terrestrial-biodiversity-summary`
(new bucket `public-cdfw`). Vector, **63,890** statewide ACE hexagons. H3 native res **8**, parent **0**.
License **CC-BY-4.0** (confirmed from the ArcGIS Hub dataset record; see issue comment).

## Run order (this is what actually built the dataset)

```bash
D=catalog/cdfw/k8s/ace/terrestrial-biodiversity-summary
kubectl apply -f $D/workflow-rbac.yaml                                            # once
kubectl apply -f $D/ace-terrestrial-biodiversity-summary-setup-bucket.yaml        # create bucket
kubectl apply -f $D/ace-terrestrial-biodiversity-summary-stage-raw.yaml           # curl zip -> s3 raw/
kubectl apply -f $D/ace-terrestrial-biodiversity-summary-convert.yaml             # raw zip -> GeoParquet
kubectl apply -f $D/ace-terrestrial-biodiversity-summary-clean-columns.yaml       # drop OBJECTID, OGC_FID
kubectl apply -f $D/ace-terrestrial-biodiversity-summary-pmtiles.yaml             # PMTiles
kubectl apply -f $D/ace-terrestrial-biodiversity-summary-hex.yaml                 # H3 hex (chunk-size 320)
# wait for hex, then repartition merges chunks/ -> hex/
kubectl apply -f $D/ace-terrestrial-biodiversity-summary-repartition.yaml
```

## Deviations from the vanilla `cng-datasets workflow` output

1. **`stage-raw` step (added).** The locked source URL contains `&` query params; the
   generated `convert` command emitted it **unquoted**, so bash split it into background
   jobs. Per AGENTS Step 1b we stage the raw zip to `s3://public-cdfw/raw/ds2739.zip`
   first, then `convert` localizes it from internal S3, unzips, and passes the `.shp`.
   The orchestrator `configmap.yaml` convert step was patched to do the same — but the
   orchestrator DAG does **not** include `stage-raw`, so run `stage-raw` before using the
   orchestrator.

2. **`clean-columns` step (added).** `cng-convert-to-parquet` keeps the source `OBJECTID`
   (excluded by issue scope) plus a GDAL `OGC_FID`. This DuckDB job rewrites the parquet
   dropping both, leaving the 43 documented columns + `_cng_fid` + `geom`.

3. **Hex `--chunk-size` 50 → 320.** The generated default (50) × 200 completions covers
   only 10,000 of 63,890 features. ACE hexagons are tiny uniform polygons (~9 res-8 cells
   each), so memory is not a concern; 320 × 200 = 64,000 ≥ 63,890 and every chunk has data.
   8Gi hex memory was ample (no OOMs).

4. **`hex-chunk29` recovery job (added).** One hex pod (index 29) wedged in
   `ContainerCreating` then `Terminating` on an unhealthy node (`prp-gpu-2`). The other 199
   chunks had already written to `chunks/`. We deleted the job and reran only chunk 29 with
   a node anti-affinity excluding the bad node, then repartitioned.

## Validation (via duckdb-geo MCP)

- GeoParquet: 63,890 features, 63,890 distinct `Hex_ID`, `geom GEOMETRY('OGC:CRS84')`,
  Polygon/MultiPolygon, DuckDB-native (no geopandas creator). Columns: 43 + `_cng_fid` + `geom`.
- Hex: 519,971 rows, all 63,890 `Hex_ID` present, `h8` (uint64) + `h0` (int64, 2 cells),
  no geometry column. Native res 8, parent res 0.

## STAC / docs (on NRP S3, not in this repo)

- `s3://public-cdfw/stac-collection.json` — bucket collection `cdfw-datasets`
- `s3://public-cdfw/ace/terrestrial-biodiversity-summary/stac-collection.json` — `ace-terrestrial-biodiversity-summary`
- `s3://public-cdfw/README.md`
- Registered as a child of the root catalog (`public-data/stac/catalog.json`).
- MinIO mirror: `catalog/sync/k8s/sync-public-cdfw.yaml`.
