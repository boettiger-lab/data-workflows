# NOAA Coral Reef Watch 5 km: build notes (#802)

Scope (products, tiers, window, resolution, reducers, naming) is in #802. This file covers how it is built.

## Daily tier (`crw-5km-daily/<product>`)

| file | what it is |
|---|---|
| `k8s/crw-setup-bucket.yaml` | creates `public-coral-reef-watch` (generated; run once) |
| `k8s/daily/update-daily.sh` | the whole daily pipeline for a date range |
| `k8s/daily/crw-5km-daily-script.yaml` | the script as a ConfigMap (regenerate after editing it) |
| `k8s/daily/crw-5km-daily-cronjob.yaml` | 18:00 UTC daily: last 10 days, monthly compaction, prune beyond 13 months |
| `k8s/daily/crw-5km-daily-backfill.yaml` | one-off fill of the window, one week per index (`COMPACT=0`) |
| `k8s/daily/crw-5km-daily-compact.yaml` | one-off first compaction after the backfill, 8 cell shards per product |

For each day and product, `update-daily.sh` does the following:

1. Download the upstream netCDF.
2. Stage it to `raw/daily/<product>/` with a `.json` sidecar (URL, access time, upstream Last-Modified, bytes, sha256).
3. Hex it with `cng-datasets mdim --fan-out time --unit-index YYYYMMDD`.
4. For `ssta` only, write the NE Pacific blob summary.
5. Upload the COG.

The COG goes up last and doubles as the completion marker. A failed day is redone on the next run, and a finished day is skipped.

After the days, `update-daily.sh` compacts (unless `COMPACT=0`). Any daily hex file from a month that has closed is folded into its cell's `data_0.parquet`, sorted by `time` then `h6`, and deleted. A day present in both (posted late or reprocessed) takes the daily file's values. Compaction also keeps one row per cell per day: mdim splits a cell's day into `part-t<day>-0`, `-1`, ... files as it sees fit, so before 2026-10-27, when a rerun of a day did not first delete that day's files, a split left from an earlier run repeated rows (601,131 on ssta 2026-01-09 alone). `update-daily.sh` now deletes a day's daily files before hexing it, and `REWRITE_ALL=1` rewrites every compacted cell. With `PRUNE=1`, the same rewrite drops months older than the window, so the hex, COGs and raw are all pruned to the first of a month.

### Layout

```
public-coral-reef-watch/
  raw/daily/<product>/<upstream name>.nc{,.json}
  crw-5km-daily/<product>/cog/<product>-YYYYMMDD.tif
  crw-5km-daily/<product>/hex/h0=<cell>/data_0.parquet              # closed months; columns: h6, h0, time, <variable>
  crw-5km-daily/<product>/hex/h0=<cell>/part-tYYYYMMDD-0.parquet    # current month, one file a day until compacted
  crw-5km-daily/<product>/hex/_manifest/chunk-YYYYMMDD.parquet      # mdim's, deleted at compaction
  crw-5km-daily/ne-pacific-blob/data_0.parquet                     # one row a day; each run's part-YYYYMMDD.parquet is folded in at the end
```

The hex is one file per h0 cell, about 46 MB for 13 months of a dense cell, with row groups of 100,000 rows in time order. Read it with `hex/h0=*/*.parquet`, which picks up the current month's daily files too, and filter on `time`: the row-group statistics let a one-day query skip the rest of each file.

One file per cell per day, the layout as mdim writes it, came to about 46,000 files of 70-220 KB per product over the window; a one-day global query had to open every footer and took over 2 minutes. Partitioning by `date=` above `h0` was considered and rejected: it keeps files that small and still opens thousands of footers for any query across time. Rewriting every cell daily would cost about 36 GB of writes a day, so compaction is monthly, and the current month stays as daily files.

The first compaction reads about 370 small files per cell, several minutes a cell, so it runs as a one-off job sharded eight ways per product by H3 base cell (`CELL_SHARD`); one pod per product got through only 14-34 of about 117 cells in 4 hours. A monthly pass with one month of daily files took 33 s for one cell. DuckDB's memory limit must be set explicitly in the pod: left unset, it sizes itself to the node and the 3.5 GiB pod is OOM-killed.

### Why `mdim` and not `raster-workflow`

`raster-workflow` fans out 122 pods to hex one static raster. Each CRW day is one global 7200 × 3600 grid of about 11 MB. `mdim --fan-out time` reads the whole grid once in one pod and writes every h0 partition. It applies the CF scale and nodata itself, and stamps a `time` column. A local test of one h0 cell took 11 s.

The generator cannot emit a CronJob or add one day to a rolling series, so these manifests are hand-rolled. Their pod shape, env and resources are copied from `cng-datasets mdim-workflow` output.

### Deploy

```bash
kubectl apply -f k8s/crw-setup-bucket.yaml                     # once
kubectl apply -f k8s/daily/crw-5km-daily-script.yaml
kubectl apply -f k8s/daily/crw-5km-daily-backfill.yaml          # once
kubectl apply -f k8s/daily/crw-5km-daily-compact.yaml           # once, after the backfill
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

## Monthly tier (`crw-5km-monthly/<product>`)

| file | what it is |
|---|---|
| `k8s/monthly/update-monthly.sh` | the whole monthly pipeline for a month range |
| `k8s/monthly/crw-5km-monthly-script.yaml` | the script as a ConfigMap (regenerate after editing it) |
| `k8s/monthly/crw-5km-monthly-cronjob.yaml` | 19:00 UTC on the 2nd and 5th: last 3 months, yearly compaction |
| `k8s/monthly/crw-5km-monthly-backfill.yaml` | one-off fill from 1985-01, one product-year per index, 420 indexes (`COMPACT=0`) |
| `k8s/monthly/crw-5km-monthly-compact.yaml` | one-off first compaction after the backfill, 8 cell shards per product |

The steps match the daily tier, with these differences:
- The ten products are upstream's own monthly composites. A res-6 cell takes its pixels' min, mean or max to match the composite.
- The min and max composites also carry `date`, the day the extreme was first reached. The hex keeps it as `extreme_date` (DATE); the COG goes to `cog/<product>-YYYYMM-date.tif` beside the value COG, since one GeoTIFF cannot mix the value's Int16 and the date's UInt32. In a cell holding two pixels, the date is the extreme of the pixels' dates (latest for max, earliest for min), so it can come from a different pixel than the value.
- `time` is upstream's reference time, the last day of the month.
- mdim writes to local disk; the script converts `date` and uploads only the per-h0 files.
- DHW and both BAA products start in 1985-04, after twelve weeks of HotSpot accumulate; the other six start in 1985-01.
- Nothing is pruned. Compaction is yearly: the current year's monthly files stay beside `data_0.parquet` until January.

```
public-coral-reef-watch/
  raw/monthly/<product>/ct5km_<product>_v3.1_YYYYMM.nc{,.json}
  crw-5km-monthly/<product>/cog/<product>-YYYYMM.tif
  crw-5km-monthly/<product>/cog/<product>-YYYYMM-date.tif            # min and max products only
  crw-5km-monthly/<product>/hex/h0=<cell>/data_0.parquet             # closed years; columns: h6, h0, time, <variable>[, extreme_date]
  crw-5km-monthly/<product>/hex/h0=<cell>/part-tYYYYMM-0.parquet     # current year, one file a month until compacted
```

### Deploy

```bash
kubectl apply -f k8s/monthly/crw-5km-monthly-script.yaml
kubectl apply -f k8s/monthly/crw-5km-monthly-backfill.yaml      # once
kubectl apply -f k8s/monthly/crw-5km-monthly-compact.yaml       # once, after the backfill
kubectl apply -f k8s/monthly/crw-5km-monthly-cronjob.yaml
```

## Annual tier

Not built yet (#802).
