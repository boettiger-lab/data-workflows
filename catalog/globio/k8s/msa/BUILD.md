# GLOBIO 4 MSA — build notes

Raster import of the PBL GLOBIO 4 terrestrial **Mean Species Abundance (MSA)** release
(Schipper et al. 2020), issue [#463]. 12 layers = 4 time/scenario slices
(`2015`, `ssp1rcp26-2050`, `ssp3rcp60-2050`, `ssp5rcp85-2050`) × 3 taxonomic layers
(`overall`, `plants`, `wbvert`). Bucket `public-globio`.

Source encoding (pre-flight): Float32, EPSG:4326, 10 arc-sec (~300 m), **NoData `-999`**, MSA ∈ [0,1].
Hex reducer **`mean`** (MSA is a bounded intensity index — never `sum`), native **res 8**, parents `0`.

## Run order (NOT the generated `workflow.yaml` orchestrator — see deviations)

```bash
NS=geo-workflows
# 0. bucket (once)
kubectl -n $NS apply -f setup-bucket.yaml
# 1. stage all 12 raw tifs from PBL -> s3://public-globio/raw/<slice>/<layer>.tif
kubectl -n $NS apply -f stage-raw.yaml
# 2. build 12 WGS84 COGs (indexed job) -> s3://public-globio/globio-msa-<slice>-<layer>-cog.tif
kubectl -n $NS apply -f cog.yaml
# 3. hex each layer from its COG (one hex job at a time; 122 completions each)
kubectl -n $NS apply -f <slice>/<layer>/globio-msa-<slice>-<layer>-hex.yaml
```

## Deviations from `cng-datasets raster-workflow` output (intentional)

1. **Added a COG step (`cog.yaml`).** For a single already-WGS84 source, `raster-workflow`
   emits only setup-bucket → hex and produces **no COG asset**, hexing straight from the raw
   striped LZW tif. We add a `gdal_translate -of COG` step (Float32, ZSTD/PREDICTOR=3, AVERAGE
   overviews, nodata -999) — it is both the published raster asset and a tiled input for
   efficient windowed hex reads. Hex `--input` was repointed from `raw/…tif` to the COG.
2. **Backoff.** Generated hex used `backoffLimit: 0` (forbidden — hides partial coverage).
   Switched to `backoffLimitPerIndex: 2` + `maxFailedIndexes: 10` so a partial run surfaces
   as `Failed` (the #409 coverage gate). Validated: 2015/overall hex = 122/122, 105 populated
   h0, MSA ∈ [0.059, 0.922], 0 out-of-range; area-weighted mean 0.58 (vs pixel-mean 0.69),
   consistent with GLOBIO's published area-weighted global mean.
3. `cog.yaml` uses **local ephemeral** scratch, not the cephfs PVC (cephfs crawled at
   ~0.3 MB/s under node contention; COG peak disk ~20 GB fits the 50Gi ephemeral cap).
