---
name: hex-tuning
description: >-
  Tune H3 hex generation for vector datasets: the memory and chunking mental model (peak RAM is driven by the largest single feature, not dataset size), H3 native and parent resolution conventions for join compatibility across the catalog, vector workflow parameters, and reprocessing failed chunks. Use when a hex job OOMs, when choosing resolutions, or when sizing chunks and completions.
---

# Hex Tuning

How to size a vector hex job, and how to choose resolutions that stay joinable to the rest of the catalog.

## Memory and Chunking Mental Model

**RAM is driven by the H3 cell count of the single largest feature in a chunk — not dataset size or bounding box.**

### ⛔ MEASURE the request — never inherit it from a neighbouring job

```bash
kubectl -n geo-workflows top pod --no-headers | grep '^<prefix>' | awk '{
  v=$3; if(v~/Gi$/){gsub(/Gi/,"",v); v=v*1024} else gsub(/Mi/,"",v);
  if(v+0>m)m=v+0; s+=v; n++} END {printf "n=%d peak=%.2fGi mean=%.2fGi\n", n, m/1024, s/n/1024}'
```

(Handle both `Mi` and `Gi` — `kubectl top` mixes them, and a naive `gsub(/Mi/,"")` silently
reports a peak *below* the mean.)

Measured on the CHELSA hex (one raster per job): **peak 5.2 Gi, mean 3.5 Gi** against an initial
**32 Gi** request — inherited by halving a 64 Gi figure that had itself been sized for a
35-raster chain rather than the one raster a job actually runs.

**An over-request throttles your own throughput**, because the request decides how many pods a
shared cluster can hold. At 32 Gi the Armada scheduler reported *"4,231 jobs do not fit on any
node"*. Aim for measured peak + ~50%, then re-measure.

### But check WHICH resource is binding before celebrating

Right-sizing 32 Gi → 8 Gi on that workload moved concurrency only from ~28 to ~31 pods, because
**CPU was the binding constraint, not memory**: 8 cores x 30 pods ≈ 240 cores, and the scheduler's
`Total allocated resources after scheduling` line had already shown `cpu=224`. Read that line —
it tells you which dimension you are actually up against:

```bash
armadactl get queue-report <queue>   # or: kubectl describe node | grep -A5 'Allocated resources'
```

Halving cores to fit twice the pods is usually a wash, since the per-job runtime roughly doubles.
When CPU is the cap, more throughput means more cluster share, not a different slicing.

### The profile is bimodal — size for the common case, handle the few

Most chunks are cheap and a handful cost everything: for a global raster ~116 of 122 h0 cells are
ocean and finish in seconds while a few land cells dominate. A flat request sized for the worst
chunk oversizes every other one, and at fine resolutions the worst chunk can be so large the
request barely places (boettiger-lab/datasets#173: a res-10 CONUS h0 peaked at ~140 GiB, and
256 Gi requests chronically hit `FailedScheduling`).

Prefer, in order:
1. **finer chunks**, so the worst case shrinks (sub-h0 chunking, datasets#173);
2. **two tiers** — the common size for most, a larger request for the known-dense few;
3. a flat worst-case request only when neither is available, knowing it costs concurrency.

Hex generation is two passes:
1. For each feature polygon, compute covering H3 cells (large array per feature)
2. Unnest arrays row-by-row; **peak RAM = size of the largest single feature's cell array**

Counterintuitive result: 10,000 small features at 8Gi can be fine, while a single continent-scale polygon OOMs at 32Gi. What drives RAM:
- H3 resolution (exponential: res 8 ≈ 1/170th the cells of res 10 for the same area)
- Area of the largest single feature in the chunk
- Geometry complexity affects Pass 1 runtime, not Pass 2 RAM

**Right approach:** start with default (8Gi vector), then tune from OOM signals.
1. Use Armada with `--chunk-size 1` for variable feature sizes (each feature its own pod)
2. On OOM: identify the large polygon(s) and either lower resolution, raise `--hex-memory`, or re-run that chunk alone (see Reprocessing Failed Chunks)
3. OOMs are expected — a tuning signal, not failure.

**Resolution guidance:**

| Dataset type | Resolution | Rationale |
|---|---|---|
| Countries, continents | 8 | Continent-scale features |
| States, provinces | 8 | Still very large |
| Counties, districts | 8–10 | Mostly OK at 10; watch outliers |
| Census tracts, parcels | 10 | Small features |
| Points | 10 | Each point → one cell; coarser = aggregation |
| Lines | 8 | Buffered by H3 circumradius; default 8 auto-detected |

#### ⭐ H3 resolution & parent convention (join compatibility — pick native res AND parents deliberately)

Native resolution alone is not the whole decision — the **parent-resolution set** is what
makes a dataset joinable to the rest of the catalog. Two datasets join cheaply only at a
resolution they **both physically carry** (`h<N> = h<N>`); otherwise a consumer must
`h3_cell_to_parent()` on the fly, which LLM agents do unreliably (wrong direction, skipped,
empty joins). So encode the joins into the data, don't hope the model derives them.

- **`h8` is the catalog's universal join key. Default native resolution is 8**, and **every
  dataset finer than 8 (native `h9`/`h10`) MUST carry `h8`** as a parent. Rationale: raster
  hexes (carbon, GHS-POP, richness) are native `h8`, and vector hexes (native `h10`) carry
  `h8` — so nearly everything meets at `h8`. A one-off native `h7` (e.g. the gHM 1 km raster
  before this rule) is an **outlier with no `h8`** and silently breaks those joins — don't do it.
- **`h0` always** — it is the hive partition key and the coarsest common join; every hex asset
  carries it (it must be in `--parent-resolutions`).
- **`h10` is currently our finest.** Small features (parcels, tracts, points) → native `h10`,
  parents `9,8,0` (the generator default) so they carry `h8`.
- **Coarser than 8 only when features are genuinely huge** — continent- or ocean-scale polygons
  (e.g. large marine areas hexed at `h5`) to keep hex cell-count/RAM sane. Such a dataset
  *cannot* carry `h8` (finer than native); consumers roll finer data **up** to `h5` to join it.
  Use a coarse native res because the feature size forces it, never as a cost shortcut on data
  that should be `h8`. **For rasters the same applies but the driver is the source pixel, not
  feature size** — see skill `raster-hexing`.
- **A dataset may declare a *set* of parents** (e.g. native `h8` with `--parent-resolutions
  "5,4,0"` → columns `h8,h5,h4,h0`) so it joins at several standard resolutions at once. Pick the
  parent set from the resolutions of the datasets it will be joined against.
- Always record the chosen native + parents in the issue (scope) and in the hex asset's
  `h3:native_resolution` / `h3:parent_resolutions` (STAC).

### Vector workflow parameters

| Param | Default | When to change |
|---|---|---|
| `--h3-resolution` | 10 | Lower (8, 6) for large polygons. Halving res ≈ 6× fewer cells. |
| `--hex-memory` | 8Gi | Tune from OOM signals. Start low. |
| `--max-completions` | 200 | Number of hex chunks. With armada: set to feature count for chunk-size 1. **⛔ Not a hard cap — a silent coverage limit (data-workflows #494):** the k8s hex uses a FIXED `--chunk-size 1000`, so total features hexed = `max-completions × 1000`. The default 200 silently caps a build at **200,000 features** — anything beyond that is never hexed and the repartition/STAC look "complete." For any dataset **>200k features**, set `--max-completions ≥ ceil(feature_count / 1000)` (e.g. 711,583 → 720). The generator can't count features in a zip/parquet source, so it can't warn you. **Always** confirm coverage post-build: `COUNT(DISTINCT _cng_fid)` on the hex must equal the flat parquet's feature count (not just that h0 partitions exist). |
| `--max-parallelism` | 50 | k8s only — capped by pod quota. Unused with armada. |
| `--parent-resolutions` | "9,8,0" | Use `"0"` when `--h3-resolution 8` (9/8 would duplicate target). |
| `--intermediate-chunk-size` | 10 | Decrease if hex OOMs during unnest — try this before raising memory. |

## Reprocessing Failed Chunks

For chunks that fail (e.g. DuckDB parquet page-size limits on complex geometries), reprocess at coarser H3:
1. Identify failed IDs: `kubectl get pods | grep <name>-hex | grep -E "Error|Failed"`
2. Copy `<name>-hex.yaml` → `<name>-hex-rechunk.yaml`, rename the job, set `completions: <N-failed>`, and replace the command with a CHUNK_MAP:
   ```yaml
   args:
   - |
     set -e
     CHUNK_MAP=(0 1 2 94)
     CHUNK_ID=${CHUNK_MAP[$JOB_COMPLETION_INDEX]}
     cng-datasets vector \
       --input s3://<bucket>/<dataset>.parquet \
       --output s3://<bucket>/<dataset>/chunks \
       --chunk-id $CHUNK_ID --chunk-size <same> --intermediate-chunk-size <same> \
       --resolution 8 --parent-resolutions 9,8,0
   ```
3. Apply, then run `<name>-repartition.yaml`. Repartition merges both resolutions from `chunks/` → `hex/` by h0.
