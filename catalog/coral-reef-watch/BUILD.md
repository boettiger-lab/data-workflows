# NOAA Coral Reef Watch 5 km: build notes (#802)

Scope (products, tiers, window, resolution, reducers, naming) is in #802. This file covers how it is built.

## Daily tier (`crw-5km-daily/<product>`)

| file | what it is |
|---|---|
| `k8s/crw-setup-bucket.yaml` | creates `public-coral-reef-watch` (generated; run once) |
| `k8s/daily/update-daily.sh` | the whole daily pipeline for a date range |
| `k8s/daily/crw-5km-daily-script.yaml` | that script as a ConfigMap (regenerate after editing the script) |
| `k8s/daily/crw-5km-daily-cronjob.yaml` | 18:00 UTC daily: last 10 days + prune beyond 13 months |
| `k8s/daily/crw-5km-daily-backfill.yaml` | one-off fill of the window, one week per index |

For each day and product, `update-daily.sh` does the following:

1. Download the upstream netCDF.
2. Stage it to `raw/daily/<product>/` with a `.json` sidecar (URL, access time, upstream Last-Modified, bytes, sha256).
3. Hex it with `cng-datasets mdim --fan-out time --unit-index YYYYMMDD`.
4. For `ssta` only, write the NE Pacific blob summary.
5. Upload the COG.

The COG goes up last and doubles as the completion marker. A failed day is redone on the next run, and a finished day is skipped.

### Layout

```
public-coral-reef-watch/
  raw/daily/<product>/<upstream name>.nc{,.json}
  crw-5km-daily/<product>/cog/<product>-YYYYMMDD.tif
  crw-5km-daily/<product>/hex/h0=<cell>/part-tYYYYMMDD-0.parquet     # columns: h6, h0, time, <variable>
  crw-5km-daily/<product>/hex/_manifest/chunk-YYYYMMDD.parquet
  crw-5km-daily/ne-pacific-blob/date=YYYY-MM-DD/data_0.parquet
```

The hex is **one file per day per h0**, not the catalog's usual `data_0.parquet`. A rolling series cannot be merged into a single file without rewriting the whole window every day. Read it with the glob `hex/h0=*/*.parquet`, and filter on `time`.

### Why `mdim` and not `raster-workflow`

`raster-workflow` fans out 122 pods to hex one static raster. Each CRW day is one global 7200 × 3600 grid of about 11 MB. `mdim --fan-out time` reads the whole grid once in one pod and writes every h0 partition. It applies the CF scale and nodata itself, and stamps a `time` column. A local test of one h0 cell took 11 s.

The generator cannot emit a CronJob or add one day to a rolling series, so these manifests are hand-rolled. Their pod shape, env and resources are copied from `cng-datasets mdim-workflow` output.

### Deploy

```bash
kubectl apply -f k8s/crw-setup-bucket.yaml                     # once
kubectl apply -f k8s/daily/crw-5km-daily-script.yaml
kubectl apply -f k8s/daily/crw-5km-daily-backfill.yaml          # once
kubectl apply -f k8s/daily/crw-5km-daily-cronjob.yaml
```

After editing `update-daily.sh`:

```bash
kubectl create configmap crw-5km-daily-script -n geo-workflows \
  --from-file=update-daily.sh --dry-run=client -o yaml   # paste below the header in crw-5km-daily-script.yaml
```

### ⚠️ Out-of-range pixels are masked before `mdim`

Upstream ships pixels outside each variable's declared `valid_min`/`valid_max`, all at Arctic and sub-Arctic ice edges. On 2026-10-24 there were 2,413 DHW pixels above 100 °C-weeks (up to 162.27) and 793 HotSpot pixels below −15 °C.

CF treats values outside the valid range as missing:
- GDAL's classic netCDF driver honours that, so the COGs are correct.
- The multidim reader that `mdim` uses does not, so those pixels used to reach the hex. The cells came out as 158.67 °C-weeks where every in-range pixel was nodata.

`update-daily.sh` therefore masks those pixels to nodata on its working copy before hexing. The staged raw stays byte-identical to upstream. SST, SSTA and both BAA products had no out-of-range pixels.

### Resources

One pod with 2 CPU and 16Gi memory (DuckDB limit 13GiB). A 6Gi/4GiB pod ran out of memory during the global hex, even though 15-second samples peaked at 2.3 GiB. One day of all six products takes about 6–8 minutes, and the two hex-heavy products produce about 9–10M rows per day.

## Monthly and annual tiers

Not built yet (#802).
