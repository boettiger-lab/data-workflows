---
name: hex-tuning
description: >-
  Tune H3 hex generation for vector datasets: the memory and chunking mental model (peak RAM is driven by the largest single feature, not dataset size), H3 native and parent resolution conventions for join compatibility across the catalog, vector workflow parameters, and reprocessing failed chunks. Use when a hex job OOMs, when choosing resolutions, or when sizing chunks and completions.
---

# Hex Tuning

How to size a vector hex job, and how to choose resolutions that stay joinable to the rest of the catalog.

## Memory and Chunking Mental Model

**RAM is driven by the H3 cell count of the single largest feature in a chunk — not dataset size or bounding box.**

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
