# `wrc-2-pa` — build notes and measured evidence

Wildfire Risk to Communities, 2nd Edition — **populated areas** (`RDS-2020-0060-2`), ingested for
**#611** as part of the `roadless` dataset set (#594).

> ⚠️ **This is a different DOI from `catalog/fire/k8s/wrc-2/`.**
> `RDS-2020-0016-2` (that directory, #592 and #627) is the **landscape-wide** publication: `BP`,
> `CFL`, `cRPS`, `Exposure`, `FLEP4`, `FLEP8`, `RPS`, `WHP`. It has **no** building or housing-unit
> layer — that was the finding that split this issue out of #592. `RDS-2020-0060-2` is where the
> building, population and housing-unit products live. Every dataset id here carries `-pa-` so the
> two publications never blur in the catalog.

## Source

| | |
|---|---|
| Citation | Scott, Joe H.; Brough, April M.; Gilbertson-Day, Julie W.; Dillon, Gregory K.; Moran, Christopher. 2024. *Wildfire Risk to Communities: Spatial datasets of wildfire risk for populated areas in the United States*, 2nd Edition. Fort Collins, CO: Forest Service Research Data Archive. |
| Archive id | **RDS-2020-0060-2** (`https://doi.org/10.2737/RDS-2020-0060-2`) |
| Landing page | `https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0060-2` |
| Access date | **2026-09-16** |
| License | US Government work — public domain |
| Staged raw | `s3://public-fire/raw/wrc-2-pa/` |
| Bucket | `public-fire` (decided on #611, 2026-09-16) |

### Latest edition confirmed by grepping the body, not the status code

The RDS archive **soft-200s on invalid publication ids** — it returns HTTP 200 with an "Invalid
publication id" HTML body — so a status check proves nothing. Grepping the body on 2026-09-16:

| id | verdict |
|---|---|
| `RDS-2020-0060` (1st ed.) | VALID |
| **`RDS-2020-0060-2`** | **VALID — latest** |
| `RDS-2020-0060-3` | INVALID |

### Why `public-fire` and not a bucket of its own

Six of the ten themes — `BuildingCount`, `BuildingDensity`, `BuildingCover`, `PopCount`, `PopDen`,
`HUCount`, `HUDen` — carry no fire content at all. They are built-environment denominators that
happen to ship inside a wildfire publication, and there is a real argument that they belong
somewhere other than a bucket titled "Wildfire: hazard potential, observed burn severity, and fire
perimeters".

They are here anyway, because splitting one DOI across two buckets fragments provenance and the
STAC tree worse than the mismatch it fixes: half a publication would sit beside its sibling
publication (`wrc-2-rps-*`, same authors, same web application) and half somewhere else, with no
single place a reader could see the ten themes together. The `public-fire` collection description is
widened instead, to say it also carries populated-areas exposure layers.

## Layers, reducers, and the units they were read from

The reducer for each theme is taken from the **authoritative file index**
(`_fileindex_RDS-2020-0060-2.html`), which states units per theme. It is not inferred from the theme
name, and that matters here more than anywhere else in the catalog: `BuildingCount`,
`BuildingDensity` and `BuildingCover` differ only in a suffix and take **three different**
treatments.

| Theme | File-index wording | Reducer | Warp resampler |
|---|---|---|---|
| `HURisk` | "unitless index… all four primary elements of wildfire risk… on 30-m pixels where housing unit density is greater than zero", 0–7,556,012 | `mean` | `near` |
| `HUExposure` | "expected number of housing units **within a 30-m pixel** potentially exposed to wildfire in a year", 0–0.13 | **`sum`** | **`sum`** |
| `BuildingCount` | "count of buildings located **within each 30-m pixel**", 0–50 | **`sum`** | **`sum`** |
| `PopCount` | "residential population count (persons) **in each 30-m pixel**", 0–7,571 | **`sum`** | **`sum`** |
| `HUCount` | "number of housing units **in each 30-m pixel**", 0–3,030.4 | **`sum`** | **`sum`** |
| `BuildingDensity` | "density of buildings… (**buildings per square kilometer**)", 0–8,054 | `mean` | `near` |
| `BuildingCover` | "**percentage** of habitable land area covered by buildings", 0–100 | `mean` | `near` |
| `PopDen` | "residential population density (**people/km²**)", 0–109,512 | `mean` | `near` |
| `HUDen` | "housing-unit density… (**housing units/km²**)", 0–62,264 | `mean` | `near` |
| `HUImpact` | "relative potential impact of fire to housing units **at any 30-m pixel**… unitless index", 0–1,952,625,152 | `mean` | `near` |

The four `sum` themes all say *within / in each pixel* and name a countable thing, so the value is an
amount already integrated over the pixel. The six `mean` themes name a per-km² denominator, a
percentage, or an explicitly unitless index. Applying one reducer across the publication is the
density-vs-amount error that made the carbon layer ~7× low (#171/#202); here it would be wrong for
four layers whichever way it was applied.

### Scope of this pass

**`HURisk` and `HUExposure`, CONUS and Alaska — four datasets.** The pair #611 names under "if
built partially", and deliberately one `mean` layer and one `sum` layer, so both reducer paths and
the mass-conservation invariant are exercised and validated here rather than deferred.

All twenty raw rasters are staged regardless, so **the remaining eight themes — #692 — start at the
COG step** and never touch the upstream Box URLs again.

| Dataset id | Theme | Domain | Native | Parents | Reducer | Column |
|---|---|---|---|---|---|---|
| `wrc-2-pa-hurisk-conus` | `HURisk` | CONUS | 10 | 9, 8, 0 | `mean` | `hurisk` |
| `wrc-2-pa-hurisk-ak` | `HURisk` | Alaska | 10 | 9, 8, 0 | `mean` | `hurisk` |
| `wrc-2-pa-huexposure-conus` | `HUExposure` | CONUS | 10 | 9, 8, 0 | `sum` | `huexposure` |
| `wrc-2-pa-huexposure-ak` | `HUExposure` | Alaska | 10 | 9, 8, 0 | `sum` | `huexposure` |

### Resolution 10, and it is a join requirement not just a pixel match

The source is 30 m and `h10` (0.0150 km²) is the catalog's finest resolution, so 30 m is mildly
**under**-sampled — accepted per the raster-hexing anchor table. More important, native 10 with
parents 9, 8, 0 matches the join partners exactly:

| Partner | Path | H3 |
|---|---|---|
| `roadless-areas-2001` (#584) | `s3://public-usfs/roadless-areas-2001/hex/h0=*/data_0.parquet` | 10 → [9, 8, 0] |
| `silvis-wui-2020` | `s3://public-wui/wui-2020/hex/h0=*/data_0.parquet` | 10 → [9, 8, 0] |
| `wrc-2-rps-{conus,ak}` (#592) | `s3://public-fire/wrc-2-rps-*/hex/h0=*/data_0.parquet` | 10 → [9, 8, 0] |

⚠️ The first two partners are **vector-derived**, so their per-feature attributes repeat on every
cell the feature covers — dedup by `_cng_fid` before any `SUM`. These layers are raster-derived: one
row per cell, no dedup needed. Getting that asymmetry wrong is the main correctness hazard in the
downstream joins.

## Grid facts — measured, not assumed

Every raster was opened in the staging pod (`grid_facts.py`) before upload.

| # | raster | dtype | nodata | declared max |
|---:|---|---|---:|---:|
| 0 | `HURisk_CONUS` | `Int32` | −2147483648 | 7,294,316 |
| 1 | `HURisk_AK` | `Int32` | −2147483648 | 512,290 |
| 2 | `HUExposure_CONUS` | `Float32` | −3.4028230607370965e+38 | 0.12658333778381 |
| 3 | `HUExposure_AK` | `Float32` | −3.4028230607370965e+38 | 0.017185440286994 |
| 4 | `BuildingCount_CONUS` | **`UInt16`** | **255** | — |
| 5 | `BuildingCount_AK` | **`Int16`** | **255** | 8.0 |
| 6 | `PopCount_CONUS` | `Float32` | −3.4028230607370965e+38 | 7571.0122070312 |
| 7 | `PopCount_AK` | `Float32` | −3.4028230607370965e+38 | 194.59623718262 |
| 8 | `HUCount_CONUS` | `Float32` | −3.4028230607370965e+38 | 3030.3999023438 |
| 9 | `HUCount_AK` | `Float32` | −3.4028230607370965e+38 | 354.0 |
| 10 | `BuildingDensity_CONUS` | **`UInt16`** | **65535** | 8,054 |
| 11 | `BuildingDensity_AK` | **`Int16`** | **−1** | 2,514 |
| 12 | `BuildingCover_CONUS` | `Int16` | −128 | 100 |
| 13 | `BuildingCover_AK` | `Int16` | −128 | 100 |
| 14 | `PopDen_CONUS` | `Int32` | **−2147483647** | 109,512 |
| 15 | `PopDen_AK` | `Int16` | −32768 | 11,167 |
| 16 | `HUDen_CONUS` | `Int32` | **−32768** | 62,264 |
| 17 | `HUDen_AK` | `Int16` | −32768 | 4,692 |
| 18 | `HUImpact_CONUS` | `Int32` | −2147483648 | **1,952,625,152** |
| 19 | `HUImpact_AK` | `Int32` | −2147483648 | 155,192,256 |

Common to all twenty: CONUS **EPSG:5070** at 156,335 × 101,538, Alaska **EPSG:3338** at
124,603 × 66,861, 30 m pixels, **tiled 128×128**, no internal overviews, no colour table, no
category names. The `.ovr` pyramids ship as separate files and are never transferred.

### ⛔ Eight different nodata sentinels, two of them positive

The landscape publication is uniformly `Float32` / −9999, and carrying that assumption across would
have been silently destructive. This publication uses **255, 65535, −1, −128, −32768, −2147483647,
−2147483648 and −FLT_MAX**, and:

- **`BuildingCount` has a positive sentinel, 255, in a band whose valid range is 0–50.** Read as
  data it is 255 buildings in a 900 m² pixel.
- **The same theme changes dtype *and* sentinel between domains.** `BuildingDensity` is
  `UInt16`/65535 for CONUS and `Int16`/−1 for Alaska; `PopDen` is `Int32`/−2147483647 for CONUS and
  `Int16`/−32768 for Alaska. Any per-theme constant is wrong for one domain of each.
- **`PopDen_CONUS` is −2147483647, one off from the −2147483648 that `HURisk` and `HUImpact` use.**
- **`HUDen_CONUS` is an `Int32` band carrying an `Int16` sentinel** (−32768).

So `make-cogs.yaml` **reads the nodata from each source at run time** and asserts it against the
value recorded in the manifest. That removes the transcription risk from the warp command while
keeping a tripwire for an upstream re-release. Every sentinel is then collapsed to a uniform
**−9999** in the COG: all ten themes are non-negative, so −9999 cannot collide with a real value,
and the hex step's `--nodata` is then identical for all twenty datasets. Where the source dtype
cannot hold −9999 (`UInt16`, for `BuildingCount_CONUS` and `BuildingDensity_CONUS`) the COG is
promoted rather than the sentinel changed.

### `HUImpact`'s 1,952,625,152 maximum is a value, not a sentinel

#611 asked. The band is `Int32`, its sentinel is −2147483648, and 1,952,625,152 is the band's own
declared maximum and matches the maximum the file index publishes for the theme. It is real.

## ⛔ The COG step is mandatory, and `-r near` would corrupt the `sum` layers

Two separate hazards live in this one step.

### 1. Skipping it writes zero rows and exits 0

`cng-datasets raster` hands H3 cell polygons in **degrees** to exactextract, so against an Albers
raster in metres every cell lands within ~100 m of the projection origin — EPSG:5070 (0,0) is
lon −96 / lat 23, in the Gulf of Mexico — and every cell reads nodata. Measured on #586: **zero rows
written, Job exited 0.** Structural checks all pass on an empty build; only the h0 coverage gate
catches it. Both domains here are projected, so both need the warp.

### 2. `-r near` does not conserve an amount, and the error grows with latitude

The density-vs-amount trap has a second half that #171/#202 did not cover: **choosing the right
reducer is not enough if the reprojection itself does not conserve the amount.** `gdalwarp -r near`
resamples by nearest pixel centre, and EPSG:5070 → EPSG:4326 changes both the pixel count and the
per-pixel ground area, so a per-pixel *amount* is silently rescaled.

Measured on synthetic 400×400 EPSG:5070 `Int32` count rasters, source pixel sum vs warped pixel sum:

| Patch latitude | `-r near` | `-r bilinear` | `-r average` | `-r sum` |
|---|---:|---:|---:|---:|
| ~25°N | −1.06% | | | **+0.000%** |
| ~40°N | −7.31% | −7.35% | −6.89% | **+0.000%** |
| ~48°N | −11.87% | | | **+0.000%** |

`-r sum` (GDAL ≥ 3.1) takes the overlap-weighted sum of contributing source pixels and is exact at
every latitude, and it does not smear the sentinel — the minimum valid output was `0.0`. The `near`
error is **not** a constant that could be divided out afterwards: it grows with latitude and
reverses sign about the standard parallels.

So the resampler follows the same amount-vs-density split as the reducer: **`-r sum` for the four
amount themes, `-r near` for the six density/index themes.** A `sum` warp produces fractional
contributions, so those COGs are written `Float32` even where the source is an integer type.

`cng-datasets`' exact-extract `sum` is itself coverage-weighted and mass-conserving by construction
(`cng_datasets/raster/cog.py`, boettiger-lab/datasets#84), so pairing the two makes the whole chain
mass-conserving and makes #611's `SUM` invariant testable end to end. Each COG pod prints the exact
source pixel sum and the exact COG pixel sum so the conservation is evidence rather than assertion.

`-r near` is kept for the index and density layers for the reason wrc-2 gives: the warp is ~1:1 in
ground resolution, so interpolation buys no accuracy, while `bilinear` would smear the sentinel
across every nodata boundary.

### Statistics are exact here, not `approx_ok`

wrc-2's COG gate used `ComputeStatistics(True)`, which GDAL answers from the **AVERAGE-resampled
overviews**: it biased the reported max low by 28% (CONUS) and 53% (Alaska) and the mean by 3% and
11%, and those figures were fed into the published `raster:bands` before being caught. It also
cannot produce a SUM at all, and the SUM is the whole point for an amount layer. These rasters are
an order of magnitude smaller than the landscape ones, so a full blockwise pass costs minutes:
`raster_stats.py` reads the full-resolution band, accumulates in `float64` with Kahan compensation,
and everything it prints is publishable as-is.

## Alaska is clipped to −180..−129 longitude

Its EPSG:3338 grid spans the antimeridian, and a naive warp to EPSG:4326 yields a ~360°-wide,
almost entirely nodata raster sitting on the dateline seam. The clip drops the far-western Aleutians
(~157°E..180), which hold **no** National Forest System land — the Alaska units are the Tongass and
Chugach, far to the east — so nothing relevant to the roadless question is lost. For the `sum`
layers the clip necessarily drops that area's mass as well, so the COG pod reports both sums and
their difference; that number is evidence, not an error. Recorded in STAC.

## Distribution is awkward in three different ways

All verified live on 2026-09-16.

### 1. The source is split between the stable product path and Box

Four CONUS themes and the whole Alaska archive are served from the stable
`https://www.fs.usda.gov/rds/archive/products/RDS-2020-0060-2/<name>.zip` path. The other six CONUS
themes are served **only** from opaque `usfs-public.box.com/shared/static/<hash>.zip` URLs scraped
off the catalog HTML. (This is the reverse of wrc-2, where *every* data archive was Box-only.)

| Theme | Served from | zip bytes | member `.tif` | uncompressed bytes | zip method |
|---|---|---:|---|---:|---:|
| `BuildingCount` | product path | 237,683,558 | `BuildingCount_CONUS.tif` | 489,285,478 | 8 |
| `BuildingCover` | product path | 803,424,522 | `BuildingCover_CONUS.tif` | 887,640,016 | 8 |
| `HUCount` | product path | 488,102,647 | `HUCount_CONUS.tif` | 1,267,733,949 | 8 |
| `PopCount` | product path | 527,070,072 | `PopCount_CONUS.tif` | 1,291,805,345 | 8 |
| `BuildingDensity` | Box `slkg4dyrfdg83q2rvvhonf9r7ymtn7y3` | 1,761,357,480 | `BuildingDensity_CONUS.tif` | 1,633,170,834 | **9** |
| `HUDen` | Box `g9v52r7m228jw3ue741hf9qa539vf738` | 2,592,166,773 | `HUDen_CONUS.tif` | 2,825,789,724 | **9** |
| `HUExposure` | Box `9daudw45srposnbypere2k99ti2pisky` | 8,073,773,087 | `HUExposure_CONUS.tif` | 7,466,094,445 | **9** |
| `HUImpact` | Box `qzp8w75ofug7k143fzuort1dkmk2izrv` | 6,149,862,056 | `HUImpact_CONUS.tif` | 5,783,361,566 | 8 |
| `HURisk` | Box `ojr4i72a7gyzpfqvwbzf2pvmit6h7q9z` | 3,891,216,236 | `HURisk_CONUS.tif` | 3,930,077,598 | 8 |
| `PopDen` | Box `3xwr6uozu3iflob9r0qtyl792lydb1fi` | 2,907,646,939 | `PopDen_CONUS.tif` | 3,094,454,526 | **9** |

Alaska ships all ten themes in one 187,604,524-byte zip on the product path, members
`AK/<Theme>_AK.tif`, all method 8: BuildingCount 243,345,790 · BuildingCover 244,330,510 ·
BuildingDensity 186,230,848 · HUCount 414,931,855 · HUDen 255,173,556 · HUExposure 492,258,415 ·
HUImpact 486,918,970 · HURisk 483,203,658 · PopCount 414,967,801 · PopDen 231,003,574.

**If a pod 404s, re-scrape rather than assuming the file moved:**
```bash
curl -sL https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0060-2 \
  | grep -oE '<a[^>]+box\.com/shared/static/[^"]+"[^>]*>[^<]+'
```

### 2. ⛔ Four members are Deflate64, and `zlib` cannot read them

`BuildingDensity_CONUS`, `HUDen_CONUS`, `HUExposure_CONUS` and `PopDen_CONUS` — four of the six
Box-hosted archives, and only those four — use zip compression **method 9 (enhanced deflate)**:
a 64 KiB window and 64 KiB maximum match length, against deflate's 32 KiB / 258 B. `zlib` cannot
decode it and Info-ZIP `unzip` as commonly built cannot either.

The first revision of the extractor treated "not method 8" as **stored** and copied the compressed
bytes straight through, producing a file of exactly the compressed length full of garbage. Nothing
about that file is obviously wrong — it is the right kind of object in the right place — and the
**only** thing that caught it was the uncompressed-size assertion. That is the argument for the
assertion, and the reason the extractor now dispatches on the method explicitly and **refuses**
anything it does not recognise instead of falling through to stored.

Method 9 is handled with the `inflate64` wheel, pip-installed in the pod (the image does not ship
it). Verified in-cluster, and verified before use that successive `.inflate()` calls on 8 MiB slices
reproduce the single-shot output byte for byte. The chunk is 8 MiB rather than the 256 MiB used for
deflate because a Deflate64 range is decompressed in one shot, so the chunk bounds peak RSS: an
8 MiB compressed slice of `HUExposure_CONUS` expands to ~220 MB, and the format's worst case is far
higher.

### 3. Every archive carries a pyramid, and Alaska interleaves ten themes

Each zip ships a `.tif.ovr` next to its `.tif` — ~7.8 GB across the CONUS archives, and for
`BuildingCover` and `BuildingDensity` the pyramid is roughly a third of the payload. Alaska's single
187 MB zip interleaves ten themes with their pyramids and value-attribute tables, so a streaming
`unzip -p` for one theme would read most of the archive, ten times over.

So each pod reads the end-of-central-directory, walks the central directory, seeks to one member's
local header, and inflates only that member's compressed byte range. **Staged total 32,121,778,458
bytes (29.9 GiB)** across all twenty rasters — about a third of what the landscape publication
needed (#592 staged 89.5 GiB).

## Provenance caveats to carry into STAC

- The data "reflect landscape conditions as of the end of **2014**" (LANDFIRE 2020, version 2.2.0).
  That, not the 2024 publication date, is the basis for the temporal extent.
- The FSim burn-probability and intensity inputs are natively **270 m** and were **upsampled to
  30 m** to match the LANDFIRE grid, so the 30 m grid overstates the independent information
  content of the fire-conditioned layers. The same oversampling obligation #586 discharged.
- Access date **2026-09-16**, staged path `s3://public-fire/raw/wrc-2-pa/`, with the per-member
  uncompressed sizes above as the fingerprint.
- `RDS-2020-0060-2_Supplements.zip` (565.71 KB, stable path) ships
  `WRC_V2_Methods_PopulatedAreas.pdf` and `WRC_V2_Populated Areas_GISDataSymbology.pdf`.

## Hazard, risk, and what this publication adds

`whp-2023-*` (#586) answers *could this burn intensely* — hazard. `wrc-2-rps-*` (#592) answers
*would that harm a home that stood here* — risk to potential structures, which is defined
everywhere, whether or not anyone lives there. **This publication is the one that knows where people
actually are**: `HURisk` is defined only on pixels with housing-unit density greater than zero, and
`HUExposure` counts actual expected housing units. State the distinction on all three collections,
pointing at each other.

## Pipeline

Run in `geo-workflows`, and **one hex Job at a time** (`AGENTS.md`).

```bash
# 1. stage all twenty source rasters to s3://public-fire/raw/wrc-2-pa/
kubectl apply -n geo-workflows -f wrc-2-pa-stage-raw.yaml

# 2. build the WGS84 COGs (MANDATORY -- see above). completions: 4 builds #611's scope.
kubectl apply -n geo-workflows -f make-cogs.yaml

# 3. hex, sequentially, waiting for Complete between each
kubectl apply -n geo-workflows -f wrc-2-pa-hurisk-conus-hex.yaml
kubectl apply -n geo-workflows -f wrc-2-pa-hurisk-ak-hex.yaml
kubectl apply -n geo-workflows -f wrc-2-pa-huexposure-conus-hex.yaml
kubectl apply -n geo-workflows -f wrc-2-pa-huexposure-ak-hex.yaml
```

`setup-bucket` is **not** run: `public-fire` already exists, serves anonymously, is a child of the
root catalog, and already holds the `whp-2023-*`, `wrc-2-rps-*`, `mtbs-*`, `calfire-*`,
`usgs-fires-2021`, `fired-events-*`, `fpa-fod-*` and `ics-209-plus-*` collections. Nothing about a
new dataset changes bucket-level access. There is no root-catalog or MinIO-backup registration step
either — that tier was retired in #568; the only obligation is a correct SPDX `license`, which is
`public-domain` with a license link.

### The 122-completion fan-out is replaced by an explicit h0 list, without guessing

wrc-2 ran all 122 h0 completions per layer although only 6 (CONUS) or 5 (Alaska) hold data, and
declined to trim on the grounds that the index → h0 mapping is `cng-datasets`' own and guessing it
risks silently skipping a populated cell.

It does not have to be guessed. `cng-datasets` resolves `--h0-index` with
`WHERE i = <h0-index>` against `s3://public-grids/hex/h0-valid.parquet`
(`cng_datasets/raster/cog.py`) — a published table anyone can query. So the hex jobs carry
`H0S=(...)`, every index whose h0 geometry intersects that domain's COG footprint, read from that
same table:

| Domain | Completions | h0 indexes |
|---|---:|---|
| CONUS | 12 | 9, 12, 14, 20, 42, 50, 71, 78, 89, 100, 104, 120 |
| Alaska | 7 | 12, 28, 50, 59, 98, 104, 105 |

This is a **superset** of the cells that will hold data — the intersection is against the h0 cell
geometry, and a cell that does not actually overlap the raster is skipped by the tool in seconds —
so it cannot drop a populated cell. It removes 110 of 122 pods per CONUS layer and 115 per Alaska
layer.

For reference, the measured populated sets from the sibling `wrc-2-rps-*` build are CONUS
{12, 14, 20, 50, 71, 78} and Alaska {12, 59, 98, 104, 105}; both are contained in the lists above,
as they must be.

### Hex sizing, from measurement rather than guesswork

| Setting | Value | Why |
|---|---|---|
| `memory` | **192Gi** | Memory at res 10 is set by the ENUMERATION, not the output: every surviving h0 enumerates the same 282,475,249 res-10 children. Measured on the sibling wrc-2 CONUS run, four pods spanning 47.8 M to 226.7 M cells all sat at 132–134 GiB — a 4.7× range in cells giving 1.8% in memory. 128Gi sits *below* that steady state. |
| `ephemeral-storage` | 50Gi | the pod rclone-localizes the COG |
| `parallelism` | 4 | 192Gi pods must spread across the cluster |
| `priorityClassName` | **omitted** | default priority 0. A dense res-10 h0 runs for hours, and `opportunistic` (−2000000000) at that duration is near-certain preemption (skill `pod-preemption`) |
| node pinning | **none** | pinning a 192Gi/8cpu job serializes it — #307 turned a CONUS res-10 hex from hours into 30–50 h |
| `backoffLimitPerIndex` / `maxFailedIndexes` | 3 / 0 | a partial indexed run must surface as `Failed`, not publish as complete (#409) |
| `podFailurePolicy` | Ignore `DisruptionTarget` | a preemption is not a data error and should not spend the index's retry budget |

### `cog-facts.yaml` — exact facts for the *published* COGs

`make-cogs.yaml` prints exact statistics, but it measures the local file **before** upload, and
three of its four pods have since been reaped. `cog-facts.yaml` re-measures all four COGs as they
are actually published on S3, reusing `raster_stats.py` verbatim from the `wrc-2-pa-make-cogs-src`
ConfigMap so the numbers come from the same gated code path. It emits one `FACTS <json>` line per
dataset — statistics plus the bbox derived from the geotransform — so `facts.json` is transcribed
from machine output rather than by eye, and a truncated or mis-uploaded COG would surface here and
nowhere else.

```bash
kubectl apply -n geo-workflows -f cog-facts.yaml
kubectl -n geo-workflows logs job/wrc-2-pa-cog-facts | grep '^FACTS '
```

## Post-build verification

```bash
# h0 coverage gate -- per domain, against its own measured h0 set.
# ⚠️ NEVER gate these against a national reference such as roadless-areas-2001/hex/: each
# collection is one domain, so a national reference is a guaranteed false FAIL (learned on #586).
scripts/check-hex-coverage.sh nrp:public-fire/wrc-2-pa-hurisk-conus/hex/ --expect-h0 <measured>
scripts/check-hex-coverage.sh nrp:public-fire/wrc-2-pa-hurisk-ak/hex/   --expect-h0 <measured>

python3 scripts/verify-stac.py --bucket public-fire
```

Value checks, via the duckdb-geo MCP:

- rows == `COUNT(DISTINCT h10)`; zero NULL in the finest parent
- zero sentinel leak; `MIN` ≥ 0 on every layer, since every theme is non-negative
- **`mean` layers** (`HURisk`): hex mean inside the COG's exact min/max, and a physical
  plausibility bound
- **`sum` layers** (`HUExposure`): hex `SUM(huexposure)` equals the COG pixel sum within rounding —
  the invariant the `-r sum` warp exists to make true
- the Alaska dateline h0 `576707042908045311` must be populated
- **cross-layer sanity**: join `HURisk` to `wrc-2-rps-conus` on `h8`. HURisk should rise with RPS
  but not track it perfectly — RPS is defined everywhere, HURisk only where housing-unit density is
  greater than zero, and that divergence is the whole difference between the two publications.

## Build results

### Stage raw (2026-09-16) — 20/20, every member byte-exact

Job `wrc-2-pa-stage-raw`: `Complete=True`, `succeeded=20`, `failedIndexes` empty. Each pod asserted
the member's uncompressed size from the live central directory before uploading, and every one
matched. Verified again from S3 afterwards:

| Raster | Staged bytes | S3 ETag |
|---|---:|---|
| `HURisk_CONUS` | 3,930,077,598 | `4f0ca4d2536cb36c67f6f16e405bd70b-59` |
| `HURisk_AK` | 483,203,658 | `b06df1953c2f989261148414b67520d3-8` |
| `HUExposure_CONUS` | 7,466,094,445 | `8558fb54268f6dea7ae16718e6f4d966-112` |
| `HUExposure_AK` | 492,258,415 | `7a08c73c2f48443e985a28d46801c8ad-8` |
| `BuildingCount_CONUS` | 489,285,478 | `870ed959ad217edcd06c28edde3414a0-8` |
| `BuildingCount_AK` | 243,345,790 | `a65ad269da2996290f61eb0847bd7987-4` |
| `PopCount_CONUS` | 1,291,805,345 | `7fc8a75c583f8cf0930d711f08ba5927-20` |
| `PopCount_AK` | 414,967,801 | `e2f653351fa3c867ae4a78d726d0afd5-7` |
| `HUCount_CONUS` | 1,267,733,949 | `92afe430e704544e374ec6263eb14dc0-19` |
| `HUCount_AK` | 414,931,855 | `9ba959eda128f834fccf0e0fc4ac675a-7` |
| `BuildingDensity_CONUS` | 1,633,170,834 | `8feab075bef86edc4a65060c45d283e2-25` |
| `BuildingDensity_AK` | 186,230,848 | `1e00ac19dcf3756699300ef1cec77fad` |
| `BuildingCover_CONUS` | 887,640,016 | `0f68d00864849da28e01046ae9dd5a52-14` |
| `BuildingCover_AK` | 244,330,510 | `f77e908e4399a1fb07eb7eb4acce082c-4` |
| `PopDen_CONUS` | 3,094,454,526 | `63069530b4cbb9e10be5a5859aaaa1b2-47` |
| `PopDen_AK` | 231,003,574 | `820b672e5ef4a5ebcc619bf6bbf692d5-4` |
| `HUDen_CONUS` | 2,825,789,724 | `6c085a25ccc257fefaf96f68e6d31c35-43` |
| `HUDen_AK` | 255,173,556 | `e04f496f88fd49b457f13e6ae7cff4f6-4` |
| `HUImpact_CONUS` | 5,783,361,566 | `9d3599c62f10e397977bceb17e6f8d0a-87` |
| `HUImpact_AK` | 486,918,970 | `f359b7520f4e6d0226587ea0d012202d-8` |

**32,121,778,458 bytes (29.92 GiB) staged, zero size drift.** The `.ovr` pyramids were never
transferred — roughly 8 GB the ranged extraction skipped.

Most of the twenty finished in under two minutes; the whole Alaska archive's ten members are
small and deflate. The four Deflate64 members dominated the wall clock, and
`HUExposure_CONUS` — 6.29 GB compressed, read in 8 MiB slices — took about 75 minutes on its own,
with zero range retries. The 8 MiB chunk is a memory bound, not a throughput choice; if this ever
needs to be faster, raise it and raise the pod's memory with it.

**The failure worth remembering:** the first three attempts at each of the four Deflate64 members
produced a file of exactly the *compressed* length, because the extractor treated "not method 8" as
stored. Nothing about such a file looks wrong from the outside. The uncompressed-size assertion is
the only thing that caught it, and that is the argument for keeping the assertion.

### COGs (2026-09-16/17)

**4/4 built.** Three on the first pass; `HUExposure_CONUS` needed a memory fix (below) and built
in 38 minutes on the retry, of which the warp itself was 30m17s.

| | `hurisk-conus` | `hurisk-ak` | `huexposure-conus` | `huexposure-ak` |
|---|---|---|---|---|
| Warped size | 197,514 × 92,269 | 150,764 × 67,401 | 197,514 × 92,269 | 150,764 × 67,401 |
| Pixel (deg) | 0.0003257129231020243 | 0.00033827704226473165 | 0.0003257129231020243 | 0.00033827704226473165 |
| Dtype / nodata | Int32 / −9999 | Int32 / −9999 | Float32 / −9999 | Float32 / −9999 |
| Overviews | 9, `BLOCKSIZE=512` | 9 | 9 | 9 |
| Resampler | `near` | `near` | **`sum`** | **`sum`** |

The Alaska warps match the sibling `wrc-2-rps-ak` grid exactly (150,764 × 67,401), as they must —
same source grid, same clip.

#### The reprojection numbers, measured on the real rasters

This is the evidence for the resampler split, and it is stronger than the synthetic test.

| | source valid px | source SUM | COG valid px | COG SUM | SUM drift |
|---|---:|---:|---:|---:|---:|
| `hurisk-conus` (`near`) | 1,586,774,801 | 1,659,303,050,581 | 1,396,313,753 | 1,419,524,640,175 | **−14.4%** |
| `hurisk-ak` (`near`) | 3,926,732 | 12,498,413,361 | 5,275,836 | 17,776,728,265 | **+42.2%** |
| `huexposure-conus` (**`sum`**) | 1,586,774,801 | 50484.404891164275 | 1,536,046,263 | 50484.37529216313 | **−5.9e-7** |
| `huexposure-ak` (**`sum`**) | 3,926,732 | 325.4611482655238 | 5,793,024 | 325.46115222398214 | **+1.2e-8** |

Three things to take from this.

**The `near` drift reverses sign between the two domains** — CONUS loses 14.4% of the pixel total
while Alaska gains 42.2%. It is not a scale factor anyone could divide out, and pooling two domains
warped that way would be meaningless. HURisk is a `mean` layer, so this costs it nothing; had it
been an amount it would have been a silent 14–42% error.

**`-r sum` conserved the total on both domains** — to seven significant figures over 1.5 billion
CONUS pixels and to twelve over Alaska, under the same warp that moved `near` by −14.4% and +42.2%.
That is the invariant #611 asks for, established at the COG step so the hex step can be checked
against it.

Note the direction of the pixel-count change differs between the two `sum` domains — CONUS
1,586,774,801 → 1,536,046,263 (fewer, larger output pixels) and Alaska 3,926,732 → 5,793,024 (more,
smaller ones) — and the total held either way. That is the point of an overlap-weighted resampler.

**The Alaska dateline clip dropped no mass.** `huexposure-ak`'s source and COG sums agree, so the
far-western Aleutians excluded by the −180..−129 clip contain no exposed housing units at all. That
is now measured rather than argued.

Also worth noting: **both `near` warps preserved the maximum exactly** (7,294,316 and 512,290), and
the minimum is 0.0 with no sentinel leak on any of the three. the two `sum` COGs' maxima move in
opposite directions from their sources, and both are correct. `huexposure-ak` falls from
0.01718544028699398 to 0.011197708547115326 and `huexposure-conus` rises from 0.12658333778381348 to
0.14124265313148499. Each output pixel holds the amount within its own footprint, and the
reprojected pixels are smaller than 30 m at Alaskan latitudes and larger at CONUS ones. The
published `raster:bands` statistics describe the COG, so those are the numbers recorded, with the
reason stated in the asset description. **A `sum` COG's per-pixel maximum is not the source's
per-pixel maximum, and it is not supposed to be** — the total is what is conserved.

The `gdalwarp` datum warning — *Several coordinate operations are going to be used* — appears on
every warp here, as it did on wrc-2. Both source CRSs are NAD83 and the target is WGS84, PROJ has
more than one candidate transform, and the disagreement between candidates is 1–2 m against a 30 m
pixel. Left at PROJ's default rather than pinned with `-to ONLY_BEST=YES`, which can fail outright
when the best transform needs a grid file the image does not ship.

#### ⛔ `-r sum` OOMKilled at 24Gi where `-r near` did not, and the cause is arithmetic

`HUExposure_CONUS` was OOMKilled three times at 24Gi, always at 40–50% of the warp, while
`HURisk_CONUS` — the same 197,514 × 92,269 output grid, the same job, the same settings — warped
fine. Reproducible three times over, so not a flaky node.

`gdalwarp` chunks the output by the `-wm` budget, and with `-multi` it processes chunks across
`NUM_THREADS` in parallel, so peak RSS is roughly **NUM_THREADS × wm + GDAL_CACHEMAX**. At the
original `-wm 2048` with 8 threads and a 4096 MB cache that is ~20 GB before Python and GDAL
overhead — right at the limit. `-r near` survived it because nearest neighbour needs one source
pixel per output pixel, so its source buffer stays small; `-r sum` must hold the whole overlapping
source window for each chunk, so it actually spends the budget it is given.

Fixed by making the budget match the arithmetic rather than by raising the wall: `-wm 512`,
`GDAL_CACHEMAX 1024` (~5 GB expected), with the request raised to 32Gi as headroom. Smaller chunks
mean more of them, which costs wall clock against a tiled source and nothing in correctness.

**Generalise this to the follow-up:** the other three `sum` themes (`BuildingCount`, `PopCount`,
`HUCount`) are all CONUS-scale and will hit the same wall if the `-wm` is raised back.

`make-cogs.yaml` grew an `INDEX_OFFSET` knob for exactly this case, so one index can be rebuilt
without redoing the other three: `completions: 1` with `INDEX_OFFSET: '2'`.

#### Re-measured from the published objects (2026-09-17)

`wrc-2-pa-cog-facts` read all four COGs back off S3 and re-ran the gate. **4/4 gate OK**, and every
figure reproduces what `make-cogs` measured locally before upload — so the published objects are
the objects that were gated, and `huexposure-ak`'s mean, never transcribed at build time, is
recovered.

| | `hurisk-conus` | `hurisk-ak` | `huexposure-conus` | `huexposure-ak` |
|---|---:|---:|---:|---:|
| valid px | 1,396,313,753 | 5,275,836 | 1,536,046,263 | 5,793,024 |
| min | 0.0 | 0.0 | 0.0 | 0.0 |
| max | 7,294,316 | 512,290 | 0.14124265313148499 | 0.011197708547115326 |
| mean | 1016.6229739735293 | 3369.4618758050856 | 3.286644192184929e-05 | 5.6181564623930804e-05 |
| std | 7370.024526278766 | 9114.890034386981 | 0.00019670021630628932 | 0.00013640385482651098 |
| SUM | 1,419,524,640,175 | 17,776,728,265 | 50484.37529216313 | 325.46115222398214 |

#### ⚠️ The COG grid extent is NOT the collection bbox

The geotransform gives the reprojected **grid** extent, and an Albers → WGS84 warp bulges it well
past the data — CONUS reaches `[-128.387, 22.428, -64.054, 52.482]`, hundreds of kilometres into
the Gulf of Mexico and the Pacific, where these layers have no pixels at all. Alaska's is exactly
the `-te -180 48.8 -129.0 71.6` clip window. Every sibling in this bucket publishes a **data**
extent instead (`wrc-2-rps-conus` is `[-124.862, 24.395, -66.885, 49.385]`), and HURisk's is
narrower still, since it exists only where housing-unit density is greater than zero.

So `extent.spatial` is measured from the **hex output**, and the grid extent is kept in
`facts.json` as `cog_grid_bbox` for the record only.

### Hex

Run **one job at a time** (`AGENTS.md`), in this order. Recorded as each completes.

| job | state |
|---|---|
| `wrc-2-pa-hurisk-conus-hex` | running since 2026-09-17, 5/12 at 3h23m |
| `wrc-2-pa-hurisk-ak-hex` | not started |
| `wrc-2-pa-huexposure-conus-hex` | not started |
| `wrc-2-pa-huexposure-ak-hex` | not started |

The three are submitted by a chain that applies the next job **only** when the previous reaches
`Complete`, and stops on `Failed` — `maxFailedIndexes: 0` means a `Failed` job is a partial build
that must not be published (#409).

#### The explicit h0 fan-out is behaving exactly as designed, measured mid-run

After 5 of 12 completions — h0 indexes 9, 12, 14, 20 and 42 — **three** partitions exist, at cells
`576812596024311807`, `577164439745200127` and `577692205326532607`. Resolved against
`s3://public-grids/hex/h0-valid.parquet` those are indexes **12, 14 and 20**; indexes **9 and 42
completed and wrote nothing**, which is the superset design working as intended rather than a
fault. The remaining seven indexes are 50, 71, 78, 89, 100, 104 and 120, of which 50, 71 and 78 are
expected to populate, for **6 populated h0** — the same set `wrc-2-rps-conus` measured.

⚠️ That equality is the *expectation*, not a gate. `HURisk` exists only where housing-unit density
is greater than zero, so it may legitimately populate a subset of RPS's h0. A populated set that is
a strict subset of {12, 14, 20, 50, 71, 78} is fine; one containing an index outside it is not, and
would mean the fan-out list is wrong.

#### Mid-run value checks on the three completed partitions

| h0 | rows | distinct h10 | min | max | mean |
|---|---:|---:|---:|---:|---:|
| `576812596024311807` (i=12) | 665,493 | 665,493 | 0 | 208,932.03 | 1,480.69 |
| `577164439745200127` (i=20) | 52,576,076 | 52,576,076 | 0 | 1,157,180.74 | 419.07 |
| `577692205326532607` (i=14) | 26,064,832 | 26,064,832 | 0 | 5,334,818.96 | 1,069.15 |

`rows == COUNT(DISTINCT h10)` on every partition, zero NULL in the value column and in `h9`, and
`MIN` is 0 everywhere — so no `-9999` leaked. Every maximum sits below the COG's exact maximum of
7,294,316, as an area-weighted mean of pixels must.

Schema as published: `hurisk DOUBLE`, `h10/h9/h8 UBIGINT`, `h0 BIGINT` — matching the
`table:columns` that `gen_stac.py` declares.

**The h0 index → cell lookup is confirmed correct against the running job.** Completion 0 of
`wrc-2-pa-hurisk-conus-hex` took h0-index 9 and reported cell `577903311559065599`, which is exactly
what `s3://public-grids/hex/h0-valid.parquet` gives for `i = 9`. The explicit `H0S=(...)` fan-out is
therefore reading the same mapping `cng-datasets` uses.

#### The `sum` targets the hex must reproduce

These are the COG pixel sums measured above. Hex `SUM(huexposure)` must equal them within rounding:

| dataset | target |
|---|---:|
| `wrc-2-pa-huexposure-conus` | **50484.37529216313** |
| `wrc-2-pa-huexposure-ak` | **325.46115222398214** |

For the `mean` layers there is no such invariant; check instead that the hex mean sits inside the
COG's exact range, that `MIN` is ≥ 0, and that no `-9999` leaked.
