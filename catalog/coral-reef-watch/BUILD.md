# NOAA Coral Reef Watch 5 km: build notes (#802)

Scope (products, tiers, window, resolution, reducers, naming) is in #802. This file covers how it is built.

## Daily tier (`crw-5km-daily/<product>`)

| file | what it is |
|---|---|
| `k8s/crw-setup-bucket.yaml` | creates `public-coral-reef-watch` (generated; run once) |
| `k8s/daily/update-daily.sh` | the whole daily pipeline for a date range |
| `k8s/daily/crw-5km-daily-script.yaml` | both scripts as a ConfigMap (regenerate after editing either) |
| `k8s/daily/crw-5km-daily-cronjob.yaml` | 18:00 UTC daily: last 10 days + prune beyond 13 months |
| `k8s/daily/crw-5km-daily-backfill.yaml` | one-off fill of the window, one week per index |
| `k8s/daily/migrate-date-partitions.sh`, `crw-5km-daily-migrate.yaml` | one-off move of the first layout's hex into `date=` partitions (2026-10-26) |

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
  crw-5km-daily/<product>/hex/date=YYYY-MM-DD/h0=<cell>/part-tYYYYMMDD-0.parquet   # columns: h6, h0, time, <variable>
  crw-5km-daily/<product>/hex/date=YYYY-MM-DD/_manifest/chunk-YYYYMMDD.parquet
  crw-5km-daily/ne-pacific-blob/date=YYYY-MM-DD/data_0.parquet
```

The hex is **one file per day per h0**, not the catalog's usual `data_0.parquet`. A rolling series cannot be merged into a single file without rewriting the whole window every day. Read it with the glob `hex/date=*/h0=*/*.parquet` and filter on `date` (or `time`, the same day as a column inside each file).

The date is a path partition because each product holds about 46,000 files over the window. With the date only inside the files (the first layout), a one-day global query had to open every file and took over 2 minutes; with `date=` in the path it opens about 117.

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

### Out-of-range pixels

Upstream ships pixels outside each variable's declared `valid_min`/`valid_max`, all at Arctic and sub-Arctic ice edges. On 2026-10-24 there were 2,413 DHW pixels above 100 °C-weeks (up to 162.27) and 793 HotSpot pixels below −15 °C. CF treats them as missing.

GDAL's classic netCDF driver (the COGs) always honoured that. `mdim` did not before cng-datasets 0.11.3 (boettiger-lab/datasets#278), so the script used to mask those pixels itself; the pinned 0.11.3 image now drops them, and the mask step is gone. SST, SSTA and both BAA products have no out-of-range pixels.

### Resources

Both the CronJob and the backfill run at `priorityClassName: opportunistic`. A daily run takes about 8 minutes and a backfill week 10–16 minutes. Preempted work is simply redone, because finished days are skipped, and opportunistic pods are exempt from NRP's usage check (#804). Under 8-batch hexing the pods sit at 0.2–0.55 GiB, which would be 7–18% of the 3Gi request and outside NRP's 20–150% range at default priority.

Each pod requests 2 CPU and 3Gi memory, with a 3.5Gi limit and a DuckDB cap of 1800MiB. Each product produces about 9–10M H3 cells per day.

Each product-day is hexed in eight `mdim --h0-subset` batches of 16 h0 grid positions (the last holds 10):
- A whole-grid call peaks above 4.5 GiB in DuckDB, even though the pod averages 0.9–2.5 GiB. It ran out of memory at caps of 4 and 4.5 GiB.
- Quarter-grid batches mostly fit under an 1800MiB cap (one measured 2.0 GiB peak RSS under 1500MiB), but the densest quarter did not.
- Each batch writes its own h0 partitions, so the output is the same.

NRP policy sets two further constraints:
- **Limit/request ratio:** must be ≤ 1.2 for both CPU and memory (`container-must-meet-memory-and-cpu-ratio`).
- **Low-utilization block:** pods that request far more than they use block every deployment change on the account. The first 16Gi backfill did this on 2026-10-26.

## Monthly and annual tiers

Not built yet (#802).
