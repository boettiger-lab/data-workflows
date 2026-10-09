# GBIF 2026-09 build

Port of `catalog/gbif/2026-06/` to the GBIF **2026-09-01** AWS Open Data snapshot
(data-workflows#662). Source: `s3://gbif-open-data-us-east-1/occurrence/2026-09-01/occurrence.parquet/`,
anonymous read, 9,898 files, 0.29 TB.

Output: `s3://public-gbif/2026-09/`. The live `2026-06` release stays in place until this one
passes the acceptance checks below.

## What changed from 2026-06

| Change | Why |
|---|---|
| Snapshot `2026-06-01` -> `2026-09-01`, prefixes `2026-06` -> `2026-09` | the refresh itself |
| `FILES_PER_CHUNK` 42 -> 50 | source grew 8,375 -> 9,898 files. `42*200 = 8,400` would silently drop the last 1,498 files; `50*200 = 10,000` covers them at the same 200 completions |
| `namespace: biodiversity` -> `geo-workflows` | AGENTS.md HARD BOUNDARY 3 |
| `priorityClassName: opportunistic` dropped from hex, consolidate, rechunk, taxonomy, sidecar | those pods run well over an hour and were a preemption target at -2000000000 (skill `pod-preemption`). Kept on the two registry-fetch jobs, which run in minutes |
| Parallelism: hex 100 -> 50, consolidate 30 -> 15, taxonomy 30 -> 20 | fair trade for the priority increase, keeps the node claim flat |
| `maxFailedIndexes` added to hex (10) and consolidate (25) | a partial fan-out surfaces as `Failed` instead of a quiet gap. Consolidate's is loose because the dense h0 partitions are expected to OOM at 120Gi and get picked up by the rechunk job |
| Rechunk `REMAP` reset to `FILL_ME` | the 2026-06 index list is specific to that build's sorted h0 order. An unedited apply now crashes the pod instead of rechunking the wrong partitions |

The Stage 1 and Stage 2 scripts are otherwise unchanged, including the `#244` dedup by `gbifid`,
the one-file-per-h0 write (`#279`) and the clean output path (`#240`).

## Run order

Scripts are mounted from the ConfigMap, never cloned from the `datasets` repo (HARD BOUNDARY 2),
so apply the ConfigMap first and re-apply it after any edit to the two `.py` files.

```bash
NS=geo-workflows
kubectl apply -n $NS -f configmap.yaml

# Stage 1: H3 index + h0 partition -> 2026-09/chunks/   (200 completions)
kubectl apply -n $NS -f gbif-2026-09-hex.yaml
kubectl wait -n $NS job/gbif-2026-09-hex --for=condition=complete --timeout=86400s

# Stage 2: dedup + consolidate -> 2026-09/hex/h0=<int>/data_0.parquet   (122 completions)
kubectl apply -n $NS -f gbif-2026-09-consolidate.yaml

# Dense partitions that OOM at 120Gi: read the failed indices, fill REMAP, then apply
kubectl -n $NS get job gbif-2026-09-consolidate -o jsonpath='{.status.failedIndexes}{"\n"}'
kubectl apply -n $NS -f gbif-2026-09-consolidate-rechunk.yaml

# Sidecars (after the hex is complete)
kubectl apply -n $NS -f gbif-2026-09-taxonomy.yaml
kubectl apply -n $NS -f gbif-2026-09-sidecar.yaml
kubectl apply -n $NS -f gbif-2026-09-publishers.yaml
kubectl apply -n $NS -f gbif-2026-09-obis-datasets.yaml
```

Check the preemption gap on every long job, not just failing ones:

```bash
kubectl -n geo-workflows get job <name> \
  -o jsonpath='succeeded={.status.succeeded} failed={.status.failed} failedIndexes={.status.failedIndexes}{"\n"}'
```

`failed` far above `len(failedIndexes)` means pods are dying and retrying underneath a job that
still reports `Complete`.

## Acceptance checks

Run these through the `duckdb-geo` MCP, not locally (HARD BOUNDARY 0). Full list in #662.

```sql
-- per h0: no duplicates, exact count (approx_count_distinct is unreliable at this scale, #244)
SELECT COUNT(*) AS n, COUNT(DISTINCT gbifid) AS distinct_gbifid
FROM read_parquet('s3://public-gbif/2026-09/hex/h0=*/data_0.parquet', hive_partitioning=true);

-- 122 partitions, exactly one file each (#332)
SELECT COUNT(*) FROM glob('s3://public-gbif/2026-09/hex/h0=*/*.parquet');
```

Also verify: no `//` keys under `2026-09/`, `2026-09/chunks/` purged after consolidate (the
`rclone purge` no-ops under load, #240), and the total distinct `gbifid` against the source
record count. That total goes into the STAC asset description.

STAC and README for the release are written to `/tmp/` and uploaded with `rclone`, never
committed here (HARD BOUNDARY 1).
