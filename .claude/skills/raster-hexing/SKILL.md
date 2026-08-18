---
name: raster-hexing
description: >-
  Build and hex raster datasets: choosing the native H3 resolution from the source pixel, selecting the --hex-resampling reducer (sum, mean, mode, max, min), mosaicking a many-tile source into one COG, raster-workflow parameters, and the campaign checklist for re-hexing an existing raster. Use for any GeoTIFF or COG ingest, or any re-hex of published raster data.
---

# Raster Hexing

Raster ingest produces **COG + H3 hex only** — no GeoParquet, no PMTiles. Always create the WGS84 COG first, then hex from that COG on NRP S3 (never from the original source URL).

## Generating a raster workflow
```bash
cng-datasets raster-workflow \
  --dataset <name> --source-url <cog-url> --bucket <bucket> \
  --h3-resolution 8 --parent-resolutions "0" --value-column <band_name> \
  --hex-memory 32Gi --max-parallelism 61 \
  --output-dir catalog/<dataset>/k8s/<name>
```

Differences from vector:
- Command: `raster-workflow`
- Completions always 122 (one per h0 cell) — not configurable
- Defaults: `--h3-resolution` 8, `--parent-resolutions "0"`, `--hex-memory 32Gi`, `--max-parallelism 61`
- `--value-column` — raster band name in output (default `value`)
- `--nodata` — value to exclude (auto from metadata)
- `--hex-resampling` — **how pixels aggregate into each cell (`sum`/`mean`/`mode`/`max`/`min`, default `mean`). Picking the wrong one silently corrupts the data — see "Choosing the aggregation reducer" below. As important as `--value-column`.**
- Always creates a WGS84 COG on NRP S3 first; hex reads from that COG

**Multi-tile rasters** (e.g. multiple UTM zones): repeat `--source-url`. Adds `preprocess-cog` step that mosaics into one WGS84 COG:
```bash
cng-datasets raster-workflow --dataset wyoming/rap-arte \
  --source-url s3://.../rap_arte_zone12.tif \
  --source-url s3://.../rap_arte_zone13.tif \
  --bucket public-wyoming \
  --target-extent "-111.1,40.9,-104.0,45.0" --band 1 --value-column arte \
  --output-dir catalog/wyoming/k8s/rap-arte
```
Extra options: `--target-extent "xmin,ymin,xmax,ymax"` (EPSG:4326 clip), `--target-resolution <degrees>`, `--band <n>` (1-indexed), `--output-cog-name <key>`.

## ⚠️ Mosaicking a MANY-tile source (thousands of 1° tiles) into one global COG — two traps

For a source shipped as thousands of small tiles (Copernicus GLO-30/90 DEM = 26,475 tiles; many
global rasters), repeating `--source-url` is unusable and the naïve single-job mosaic fails two ways.
Both were hit and fixed on the DEM import (data-workflows #426; manifests at
`catalog/dem/k8s/copernicus-glo90/` are the working pattern):

1. **rook-cephfs metadata latency kills the file-opens, NOT bandwidth.** Localizing 26k tiles to the
   `rechunk-scratch` **cephfs** PVC and running `gdalbuildvrt` over them crawled — each file open pays
   a network-metadata RTT (~150 ms), so 26k opens = 60+ min *each* for the localize and the VRT build,
   at idle CPU. Local NVMe opens the same files in <1 s. **Fix: localize to LOCAL ephemeral (`/tmp`),
   not the PVC.** 66 GB > the 50Gi ephemeral cap, so split into N balanced **contiguous longitude
   bands** (integer-degree cuts → tile-aligned, seamless), one indexed pod per band on local NVMe →
   regional COGs, then a tiny merge job stitches the few regional COGs into the global COG (a handful
   of large-file opens is fine on cephfs). ~35 min total vs "never finished." Reserve the cephfs PVC
   for the *merge* (few big files), never the many-small-file localize.
2. **`gdalbuildvrt` default `-resolution average` silently downsamples.** Tiles whose pixel size in
   *degrees* varies (Copernicus DEM narrows column counts toward the poles to hold ~90 m ground
   spacing) get averaged to a bogus middle X-resolution — the equator was squished ~2.5× (Everest read
   8146 m instead of ~8700). **Always pass `-resolution highest`** (→ the uniform finest grid) for a
   lat/lon global mosaic. Sanity-check a known peak's pixel value against the raw source tile.

Also: `gdalinfo -stats` writes a `.tif.aux.xml` sidecar and **reads cached stats from it on a rerun** —
if you rebuild the COG in the same scratch dir, a stale `.aux.xml` reports the OLD min/max/mean. `rm`
the `.aux.xml` too, or verify values with a fresh `gdallocationinfo`/`ComputeStatistics`, not the sidecar.

## ⚠️ Choosing the aggregation reducer (`--hex-resampling`)

`--hex-resampling` controls how source pixels collapse into each H3 cell. **The right reducer depends entirely on what the pixel value *means*, and the wrong one silently produces nonsense** (summing land-cover class codes, averaging species counts). Decide this per dataset, every time. Supported: `sum`, `mean`, `mode`, `max`, `min` (default `mean`).

| Pixel value is… | Reducer | Examples |
|---|---|---|
| **Amount already integrated *per pixel*** — each pixel holds the whole-pixel total | `sum` | population *per pixel* (GHS-POP persons/cell), fishing-effort hours per cell, counts |
| **Density / intensity / rate / fraction** — a *per-area* or normalized quantity | `mean` | carbon **density** (Mg C **ha⁻¹** — Noon irrecoverable/vulnerable/manageable carbon), NDVI, % cover (RAP), depth (GEBCO), indices (NCP) |
| **Categorical** — discrete class codes | `mode` | land cover (CGLS-LC100, NLCD), wetland class (GLWD) |

**⛔ The density-vs-amount trap (the #1 way `sum` goes wrong) — check the source UNITS before choosing the reducer.** `sum` is correct *only* when each pixel value is an amount **already integrated over the pixel** (GHS-POP stores persons *per pixel*, so `sum` recovers the population total). If the value is a **density** — a per-area quantity like Mg C **ha⁻¹**, t km⁻², persons km⁻² — then `sum` produces a meaningless *sum of densities*, off from the true total by roughly the pixel area (carbon was ~7× low; data-workflows #171/#202). **A stock can be a density:** "carbon stock" is conceptually extensive, but the Noon et al. carbon rasters store Mg C **per hectare**, so they need area-integration, *not* `sum`. The reducer follows the **units**, not the conceptual quantity — read the source READMEs / band metadata / paper to confirm whether a value is per-pixel or per-area.

To get a **total from a density raster**: use `mean` (area-weighted mean density per cell), then multiply by the H3 cell ground area downstream — `total = mean_density × cell_area` (h3 `cell_area`; cells are ~equal-area per resolution). There is no one-step density→total reducer yet ([`boettiger-lab/datasets#105`](https://github.com/boettiger-lab/datasets/issues/105)). For an existing density-`sum` build, the equivalent correction is `value × pixel_area_ha` per cell (pixel area is latitude-dependent on a WGS84 grid, ≈ `9·cos(lat)` ha for a ~300 m grid).

**Correctness check:** for an amount-per-pixel `sum`, the catalog-wide `SUM(value)` over the hex parquet MUST equal the source COG's pixel sum within sub-pixel rounding (compute the COG sum with a GDAL block-sum job; query the hex sum via the MCP). **For a density layer, the COG pixel-sum is itself *not* a total — validate the area-corrected `SUM` against the published global total instead** (e.g. irrecoverable carbon 2018 ≈ 137 Gt vs Noon et al. 139.1 Gt). `mean`/`mode` have no global invariant — spot-check the hex against the COG over a known region.

**Species richness / "peak" quantities** (MOBI, IUCN richness): the correct reducer is `max` — **not** `sum` (double-counts species) and **not** `mean` (averages away hotspots). `max` (and `min`) are supported as of [`boettiger-lab/datasets#95`](https://github.com/boettiger-lab/datasets/issues/95) (closed 2026-06-01); MOBI and IUCN-richness were rebuilt with `max` at res 8/5 (data-workflows #194). Validate: hex `MAX(value)` == COG max, and every cell value within `[COG min, COG max]` (roll up to coarser resolutions with `GROUP BY h<parent> + MAX`, never `AVG`/`SUM`).

**`mode` keeps only the *dominant* class** per cell; the class mix is discarded. Fine for "dominant class" maps, but **inadequate for area-accounting** ("how much wetland?"), which then undercounts to plurality cells only. Per-class fractional coverage (one column per class) is not produced by the current pipeline — flag it if a use case needs class areas.

**Reducer choice is independent of geometry correctness.** The raster pipeline integrates each cell's true footprint, including the antimeridian/poles (fixed in `cng-datasets` #88/#92). But any **global** raster hexed before that fix is inflated at the ±180/pole seam and must be re-hexed regardless of reducer.

## Raster workflow parameters

| Param | Default | When to change |
|---|---|---|
| `--h3-resolution` | auto (from pixel size) | Override if auto is wrong |
| `--hex-memory` | 32Gi | Raise if OOM. **Res-8 hex of a 300 m global raster needs 64Gi** — `exact_extract` on the densest h0 cells (~5.76 M cells/h0) OOMs at 32Gi (`exit 137`); with `backoffLimit: 0` it silently retries forever, with `backoffLimitPerIndex` it can blow `maxFailedIndexes` and **fail the job** (observed on nci-frontiers `flii`/forestry). Use 64Gi for res-8 300 m layers; coarser res or coarser source can stay at 32Gi. |
| `--max-parallelism` | 61 | k8s only; reduce on quota hit; cap 122 |
| `--parent-resolutions` | "0" | Add intermediate (e.g. `"7,0"`) if needed |
| `--value-column` | "value" | Use meaningful name (`carbon`, `arte`, `nlcd`) |
| `--nodata` | auto | Override if metadata nodata is wrong/missing |

Raster completions are always **122** — not configurable.

## Re-hexing an existing raster (campaign-style reprocessing)

Most rework here comes from skipped pre-flight checks, not hard problems. Do, in order:

1. **Pre-flight the COG** with one GDAL job (rclone-localize → read; never `/vsis3` for GDAL — it's flaky/node-dependent). Report size, dtype, **real nodata** (published STAC nodata is often wrong), and the value summary that becomes your validation truth (class histogram for `mode`; pixel-SUM for `sum`; min/max/mean for `mean`). **Confirm the COG is non-empty** — published "total" COGs have shipped 100% nodata.
2. **Resolution = match the source pixel** (≈100 m → res 9; ≈500 m → res 8). Don't bump blindly; res finer than the pixel is 7× cost for no gain.
3. **Hex job musts:** mount the `rclone-config` secret (the tool localizes the COG via rclone first; generated YAML omits it → fails), `backoffLimitPerIndex: 2` + `maxFailedIndexes` (not `backoffLimit: 0`), output to a **staging** prefix. `:latest` has the seam fix — no runtime clone.
4. **Validate value AND coverage.** `sum`: hex `SUM` == COG pixel-SUM. Note `sum`/area layers are a **full h0 grid** (one row per cell, `value = 0` where the feature is absent) — same shape as carbon/ghs-pop; that's expected, not bloat. Check that the count of **nonzero** cells matches the feature extent, not the total. `mode`: sparse (cells with no valid pixel are dropped); only canonical codes + distribution tracks the histogram. **Seam (all reducers):** dateline h0 `576707042908045311` — fixed builds span ±180°, buggy ones are bloated and miss the dateline.
   **⛔ h0-partition COVERAGE gate (data-workflows #409).** An indexed 122-completion hex Job that dies/gets-preempted mid-run can leave a *subset* of h0 partitions on S3 and get published as if complete. Two defenses, both required: (a) never treat a hex build as done unless the k8s Job reports `Complete=True` with empty `failedIndexes` — a partial run must surface as `Failed`, so keep `backoffLimitPerIndex` + `maxFailedIndexes` (never `backoffLimit: 0`); and (b) after the job, run the cheap partition-set gate against a reference build from the same COG (e.g. the fractional-coverage layer) or an explicit expected h0 set:
   ```bash
   scripts/check-hex-coverage.sh nrp:<bucket>/<dataset>/hex/ \
       --reference nrp:<bucket>/<dataset>/hex-fractions/   # or --expect-count N / --expect-h0 h0a,h0b,...
   ```
   It is a metadata listing (rclone `lsf` sizes of `h0=*`), not a big-data scan — safe on a laptop. **⚠️ Compare POPULATED partitions, not directories.** A `mode` (sparse) reducer writes a partition only where valid pixels exist; a `sum`/coverage reducer writes a *full grid* — a `data_0.parquet` for every h0 it touches, including empty (0-row, ~214 B) partitions for all-nodata h0. So a raw `h0=*` directory count of a full-grid layer is a **superset** of its data extent, and a naive dir-vs-dir comparison across reducers reports **phantom gaps** — exactly what made NLCD mode look like "6 of 11" when its 6 populated h0 were complete and the fractions reference merely had 5 extra empty dirs (the #409/#410 false alarm). The gate therefore filters both sides to partitions whose bytes exceed `--min-bytes` (default 4096; a real partition is MB–GB). Exit non-zero + the missing h0 set means genuinely-missing populated partitions; re-run before publishing/validating values. The gate **also reports any empty partitions it finds under the target** as purge candidates (advisory by default; `--fail-on-empty` makes their presence a hard failure) — purge them (`rclone purge …/h0=<cell>/` then re-verify empty) so they don't pollute `**` globs or fake gaps for the next reader.
5. **Flip: purge-and-VERIFY-empty, then sync.** `cng-datasets raster` overwrites the partition for each h0 it produces, but does **not** remove partitions for h0s that now yield no data — so reprocessing to a smaller/different domain (e.g. all-land → wetland-only) leaves **stale partitions** behind that corrupt aggregates. And `rclone purge` can silently no-op under S3 load. So purge staging **and confirm it's empty** before any re-hex. `kubectl apply` on a completed Job is a no-op; `delete`+`apply` to rerun. Jobs TTL-GC 3 h after completion — validate before then.
