# `wrc-2` — build notes and measured evidence

Wildfire Risk to Communities, 2nd Edition (landscape-wide risk), ingested for #592 as part of the
`roadless` dataset set (#594). Counterpart to #586 (Wildfire Hazard Potential): WHP answers "could
this burn intensely", WRC answers "would that harm anyone". The 2026-08-18 Roadless Rule rescission
announcement talks about "neighboring communities" but cites only the hazard statistic; this is the
layer that measures the quantity the announcement claims to be about.

## Source

| | |
|---|---|
| Citation | Scott, Joe H.; Brough, April M.; Gilbertson-Day, Julie W.; Dillon, Gregory K.; Moran, Christopher. 2024. *Wildfire Risk to Communities: Spatial datasets of landscape-wide wildfire risk components for the United States*, 2nd Edition. Fort Collins, CO: Forest Service Research Data Archive. |
| Archive id | **RDS-2020-0016-2** (`https://doi.org/10.2737/RDS-2020-0016-2`) |
| Metadata date | 2024-04-23 |
| License | US Government work — public domain |
| Staged raw | `s3://public-fire/raw/wrc-2/` |

### Latest edition confirmed by grepping the body, not the status code

The RDS archive **soft-200s on invalid publication ids** — it returns HTTP 200 with an "Invalid
publication id" HTML body — so a status check proves nothing. Grepping the body:

| id | verdict |
|---|---|
| `RDS-2020-0016` (1st ed.) | VALID |
| **`RDS-2020-0016-2`** | **VALID — latest** |
| `RDS-2020-0016-3` | INVALID |
| `RDS-2020-0016-4` | INVALID |

## Two findings that corrected the issue's own scope

Both recorded on #592 before building.

### 1. This publication has no building-coverage layer

The issue asked for a "Building Coverage / building density" layer. The authoritative
`_fileindex_RDS-2020-0016-2.html` enumerates **exactly eight themes**, and none is a building layer:

`BP` · `CFL` · `cRPS` · `Exposure` · `FLEP4` · `FLEP8` · `RPS` · `WHP`

Building and housing-unit products are a **separate DOI** — `RDS-2020-0060-2`, *WRC: spatial
datasets of wildfire risk for populated areas* (confirmed latest; `-3` is INVALID). Split out as
**#611** rather than pulling one raster from a second publication into this collection set: that
publication has ten themes, and `HURisk`/`HUExposure` are arguably more on-point for "risk to
communities" than building cover. The question this issue actually poses — how much IRA acreage is
near a community — is already answerable from `silvis-wui-2020`.

### 2. Exposure Type is continuous, so its reducer is `mean`, not `mode`

The issue's reducer table listed Exposure Type as categorical. The source says otherwise:

> "**Continuous values** of exposure type… A value of 1 is 'direct' exposure. **Values between 0 and
> 1 represent 'indirect' exposure**, with higher values representing closer proximity to directly
> exposed areas… A value of 0 represents 'nonexposed' areas that have nonburnable land cover and are
> more than 1530 m from burnable wildland vegetation."

Confirmed on the raster itself (`AK/Exposure_AK.tif`, extracted and opened): `Float32`, **no color
table, no category names**, computed min/max `0.0 / 1.0`, mean `0.759`. There is nothing to take a
mode of. The categorical presentation belongs to the **web application**, which bins this continuum
for display; the published raster is a continuum.

## Layers and reducers

| `--dataset` | Source theme | Native | Parents | Reducer | Column | Source range |
|---|---|---|---|---|---|---|
| `wrc-2-rps-conus` / `-ak` | `RPS` | 10 | 9, 8, 0 | `mean` | `rps` | 0 – 13.2 |
| `wrc-2-bp-conus` / `-ak` | `BP` | 10 | 9, 8, 0 | `mean` | `bp` | 0 – 0.14 |
| `wrc-2-cfl-conus` / `-ak` | `CFL` | 10 | 9, 8, 0 | `mean` | `cfl` | 0 – 861.7 |
| `wrc-2-exposure-conus` / `-ak` | `Exposure` | 10 | 9, 8, 0 | `mean` | `exposure` | 0 – 1 |

**All four take `mean`.** Every one is an index, a probability, or a length — a per-area or
normalized quantity, never an amount already integrated over the pixel — so `sum` would produce a
meaningless sum of intensities, the error class that made the carbon layer ~7× low (#171/#202).
There is no meaningful "total RPS"; consumers compare means across land classes.

`cRPS`, `FLEP4`, `FLEP8` and this publication's own 30 m `WHP` are in scope of the source but not of
this issue. Note the 30 m `WHP` here is a **different product** from the 270 m
`RDS-2015-0047-4` WHP ingested in #586 — do not conflate them.

### Resolution: 10, and it is a join requirement not just a pixel match

The source is 30 m and `h10` (0.0150 km²) is the catalog's finest resolution, so 30 m is mildly
**under**-sampled — accepted per the raster-hexing anchor table. More important, native 10 with
parents 9, 8, 0 matches both join partners exactly, so this layer joins them cell-for-cell:

| Partner | Path | H3 |
|---|---|---|
| `roadless-areas-2001` (#584) | `s3://public-usfs/roadless-areas-2001/hex/h0=*/data_0.parquet` | 10 → [9, 8, 0] |
| `silvis-wui-2020` | `s3://public-wui/wui-2020/hex/h0=*/data_0.parquet` | 10 → [9, 8, 0] |

⚠️ Both partners are **vector-derived**, so their per-feature attributes repeat on every cell the
feature covers — dedup by `_cng_fid` before any `SUM`. WRC is raster-derived: one row per cell, no
dedup needed. Getting this asymmetry wrong is the main correctness hazard in the downstream joins.

## Grid facts — measured, not assumed

| | CONUS | Alaska |
|---|---|---|
| CRS | **EPSG:5070** (Albers, 29.5/45.5, −96, 23) | **EPSG:3338** (Alaska Albers, 55/65, −154, 50) |
| Pixels | 156,335 × 101,538 | 124,603 × 66,861 |
| Pixel size | 30 m | 30 m |
| Dtype | Float32 | Float32 |
| NoData | **−9999** | **−9999** |
| Compression | DEFLATE, **striped — 1 row per block** | same |
| Container | BigTIFF (`II+\0`) | BigTIFF |

CONUS CRS was read from the FGDC metadata's projection parameters; Alaska was confirmed by opening
`Exposure_AK.tif` directly (`NAD83 / Alaska Albers`, EPSG authority code 3338, nodata −9999,
approximate min/max/mean 0.0 / 1.0 / 0.759).

**Striped blocks matter:** with one row per block there is no tiling to support random access, so
`gdalwarp` reads are effectively sequential. Do not expect `/vsis3` to behave — and the
raster-hexing skill already forbids it for GDAL ("flaky/node-dependent"), so the COG job
rclone-localizes first.

### The COG step is mandatory and its absence fails silently

Both domains are projected, which is the #586 trap exactly: `cng-datasets raster` hands H3 cell
polygons in **degrees** to exactextract, so against an Albers raster in metres every cell lands
within ~100 m of the projection origin — EPSG:5070 (0,0) is lon −96 / lat 23, in the Gulf of Mexico
— and every cell reads nodata. Measured on #586: **zero rows written, Job exited 0.** Structural
checks all pass on an empty build; only the h0 coverage gate catches it.

### COGs stay Float32 — the integer scale/offset optimization is not available

RPS spans roughly `1e-23` to `13.2`, and the source's own percentile table puts the CONUS 1st
percentile at `2.4e-4`. A linear `Int16 + scale` encoding would annihilate the low end and break
agreement with that table, so the ~2× size win is refused. BP (0–0.14) and CFL (0–861.7) have the
same problem at the bottom of their ranges.

Resampling for the warp is **`near`**, deliberately: the warp is ~1:1 in ground resolution
(30 m → ~0.00034° at 40°N), so interpolation adds no accuracy, while `bilinear` would smear the
−9999 sentinel across every nodata boundary — the exact leak the plausibility bound exists to catch.
The real area weighting happens later, in exactextract.

## Distribution is awkward — why staging is a ranged Zip64 extraction

Three facts, all verified live:

1. **The data zips are Box-only.** The stable
   `https://www.fs.usda.gov/rds/archive/products/RDS-2020-0016-2/<name>.zip` path **404s** for every
   data archive; only `_Metadata_Fileindex.zip` and `_Supplements.zip` are served there. The data
   comes exclusively from opaque `usfs-public.box.com/shared/static/<hash>.zip` URLs that have to be
   scraped off the catalog HTML. (`RDS-2020-0060-2`, for #611, *is* on the stable path — this
   publication is the odd one.)
2. **~⅓ of every zip is `.tif.ovr` pyramid** we do not want. `RPS_CONUS.zip` is 36.3 GB, of which
   8.96 GB is a pyramid.
3. **All eight Alaska themes ship inside one 29 GB zip**, interleaved with their pyramids. A
   streaming `unzip -p` for `RPS_AK` — the 7th theme — would read ~24 GB of stream to reach it, and
   four times over for four layers.

So each pod reads the Zip64 end-of-central-directory, walks the central directory, seeks to the one
member's local header, and inflates only its compressed byte range. Verified byte-exact against
`AK/Exposure_AK.tif` (511,598,120 bytes, magic `II+\0`).

| Member | Box hash | zip | `.tif` uncompressed |
|---|---|---|---|
| `RPS_CONUS` | `88tv8byot0t22o9p1eqlrfqco3z5ouvf` | 36.3 GB | 27,368,546,444 |
| `BP_CONUS` | `7itw7p56vje2m0u3kqh91lt6kqq1i9l1` | 34.7 GB | 26,196,396,386 |
| `CFL_CONUS` | `7nb6hpw2rfc0zrhk1mv80fhbirajoqfd` | 31.3 GB | 23,587,116,646 |
| `Exposure_CONUS` | `nbmlha1iejzzjo9y3uoehln493o2c4ad` | 6.05 GB | 4,554,904,628 |
| Alaska, all 8 themes | `jh6l2x2blct82hbtmu4n6dvoe9bz25ap` | 29.0 GB | RPS 5,423,384,600 · BP 5,059,258,202 · CFL 3,347,670,548 · Exposure 511,598,120 |

All eight hash / member / size triples were checked against the live central directories before the
job was submitted. The expected uncompressed size is asserted in the pod, so a truncated or
soft-200'd download fails loudly instead of producing a short raster that hexes to garbage.

**If a pod 404s, re-scrape rather than assuming the file moved:**
```bash
curl -sL https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0016-2 \
  | grep -oE '<a[^>]+box\.com/shared/static/[^"]+"[^>]*>[^<]+'
```

## Independent validation target — better than a COG min/max

`RDS-2020-0016-2_Supplements.zip` (731 KB, stable URL) ships **`WRC_V2_DataPercentiles.xlsx`** with
sheets `RPS_percentiles`, `cRPS_percentiles`, `WHP_percentiles` — values at **1-percentile
increments for CONUS and for every state, Alaska included**. So the hex distribution can be checked
against published source percentiles rather than only against the COG's own range, which is the WRC
analogue of the class-share table that validated #586. The web application's RPS class breaks are
the **40th / 70th / 90th / 95th** percentiles; standard WHP breaks are the 44th / 67th / 84th /
95th.

Also shipped: `WRC_V2_Methods_Landscape-wideRisk.pdf`, `WRC_V2_Landscape-wideRisk_GISDataSymbology.pdf`.

## Provenance caveats to carry into STAC

- The FSim burn-probability and intensity inputs are natively **270 m** and were **upsampled to
  30 m** to match the LANDFIRE fuel and vegetation grid. So the 30 m grid overstates the independent
  information content of BP and CFL in particular — the same oversampling obligation #586
  discharged.
- The data "reflect landscape conditions as of the end of **2014**" (LANDFIRE 2020, version 2.2.0).
  That, not the 2024 publication date, is the basis for the temporal extent.
- Alaska is clipped to −180..−129 longitude in the COG step. The source EPSG:3338 grid spans the
  antimeridian and a naive warp to EPSG:4326 yields a ~360°-wide, almost entirely nodata raster on
  the dateline seam. The dropped far-western Aleutians (~157°E..180) hold **no** National Forest
  System land — the Alaska units are the Tongass and Chugach, far to the east — so nothing relevant
  to the roadless question is lost. Recorded in STAC.

## Contrast with #586 worth stating in STAC

WHP was published as four per-domain collections because its **classified breaks are
domain-relative** — an Alaska "Very High" starts at index 8,912 while a CONUS "Very High" starts at
1,985, so the two cannot be pooled. **WRC RPS has no such problem**: the source quotes a single
national range (0–13.2) and the same structure-response functions are applied everywhere, so CONUS
and Alaska values *are* comparable. The CONUS/Alaska split here is purely about grid and CRS.

## Pipeline

Run in `geo-workflows`, and **one hex Job at a time** (`AGENTS.md`).

```bash
# 1. stage the eight source rasters to s3://public-fire/raw/wrc-2/
kubectl apply -n geo-workflows -f wrc-2-stage-raw.yaml

# 2. build the eight WGS84 COGs (MANDATORY -- see above)
kubectl apply -n geo-workflows -f make-cogs.yaml

# 3. hex, sequentially, waiting for Complete between each
kubectl apply -n geo-workflows -f wrc-2-rps-conus-hex.yaml
kubectl apply -n geo-workflows -f wrc-2-rps-ak-hex.yaml
```

`setup-bucket` is **not** run: `public-fire` already exists, serves anonymously, is a child of the
root catalog, and already holds `calfire-2024`/`calfire-2025`/`usgs-fires-2021` and the four
`whp-2023-*` collections. Nothing about a new dataset changes bucket-level access. There is no
root-catalog or MinIO-backup registration step either — that tier was retired in #568; the only
obligation is a correct SPDX `license`, which is `public-domain` with a license link.

### Hex sizing, from measurement rather than guesswork

`nlcd` is the right precedent: same footprint (CONUS), same source pixel (30 m), same native
resolution (10). Measured live from its published hex:

| | rows | populated h0 | densest h0 |
|---|---:|---:|---:|
| `nlcd/hex/year=2024` | 520,932,773 | 6 | 226,732,560 (`577164439745200127`) |

So expect **~521 M rows per CONUS layer**, and — scaling the measured `whp-2023` Alaska res-9 count
(16,540,214 over 3 h0) by the ~7× cells-per-resolution step — **~116 M rows per Alaska layer**.

| Setting | Value | Why |
|---|---|---|
| `memory` (CONUS) | **192Gi** | measured peak on res-10 CONUS is 105–141Gi (#453). A 256Gi request barely fits a ~250Gi-allocatable node and causes chronic `FailedScheduling` |
| `memory` (Alaska) | 128Gi | densest Alaska h0 is roughly a quarter of CONUS's cell count |
| `ephemeral-storage` | **50Gi** | the pod rclone-localizes the COG, and ours is ~28 GB — unlike `nlcd`, whose COG is only 1.58 GB and fits in 40Gi |
| `parallelism` | 6 | 192Gi pods must spread across the cluster |
| `priorityClassName` | **omitted** | default priority 0. A dense res-10 h0 runs 1.5–2 h, and `opportunistic` (−2000000000) at that duration is near-certain preemption |
| node pinning | **none** | pinning a 192Gi/8cpu job serializes it — #307 turned a CONUS res-10 hex from hours into 30–50 h |
| `backoffLimitPerIndex` / `maxFailedIndexes` | 3 / 0 | a partial indexed run must surface as `Failed`, not publish as complete (#409) |
| `podFailurePolicy` | Ignore `DisruptionTarget` | a preemption is not a data error and should not spend the index's retry budget |

### The 116 near-no-op pods, and why they are not optimized away yet

Completions are fixed at 122 (one per h0 base cell) but only 6 intersect CONUS and 3 intersect the
Alaska COG, so ~116 pods per layer localize the ~28 GB COG and produce nothing. `nlcd` accepts the
same waste, but its COG is 1.58 GB, so for us the cost is ~20× worse.

It is deliberately **not** gated on a computed h0-index whitelist on this first build: the
index → h0 cell mapping belongs to `cng-datasets`, and guessing it risks silently skipping a
*populated* cell — a far worse failure than wasted bandwidth. Each pod echoes its index, so once
this job has run the real mapping can be read out of the pod logs and the remaining six layers can
use the established explicit `CHUNK_MAP=(...)` pattern (`catalog/rap`, `catalog/cwhr`). Upstream
two-tier proposal: `boettiger-lab/datasets#172`.

## Post-build verification

```bash
# h0 coverage gate -- per domain, against its own measured h0 set.
# ⚠️ NEVER gate these against a national reference such as roadless-areas-2001/hex/: each WRC
# collection is one domain, so a national reference is a guaranteed false FAIL (learned on #586).
scripts/check-hex-coverage.sh nrp:public-fire/wrc-2-rps-conus/hex/ --expect-h0 <6 measured>
scripts/check-hex-coverage.sh nrp:public-fire/wrc-2-rps-ak/hex/    --expect-h0 <3 measured>

# STAC, with data checks
python3 scripts/verify-stac.py --bucket public-fire
```

`check-hex-coverage.sh` communicates through its exit code — read `${PIPESTATUS[0]}` if piping. It
compares **populated** partitions (`--min-bytes`), which is what avoided the #409/#410 phantom-gap
false alarm.

Value checks, via the duckdb-geo MCP:

- rows == `COUNT(DISTINCT h10)`; zero NULL in the finest parent
- zero `-9999` leak; `MIN`/`MAX` inside the COG's measured range
- **percentile agreement** with `WRC_V2_DataPercentiles.xlsx` at the 40/70/90/95 breaks, for CONUS
  and for Alaska — this is the check worth trusting most, and it catches nodata leaks and any
  double-scaling at once
- the Alaska dateline h0 `576707042908045311` must be populated
- **cross-layer sanity**: join RPS to `whp-2023-continuous-conus` on `h8`. RPS should rise with the
  WHP index but **not** track it perfectly — that divergence is the hazard-vs-risk distinction, and
  perfect agreement would mean something is wrong

## Build results

_Pending — staging in progress. Row counts, populated h0 sets, measured footprints, value ranges,
percentile agreement and the headline IRA statistics are recorded here as each stage lands._
