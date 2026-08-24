# `mtbs` — build notes and measured evidence

Monitoring Trends in Burn Severity, 1984–2024, ingested for #593 as part of the `roadless` dataset
set (#594). The claim under audit is the 2026-08-18 announcement's image of national forests as
"tinderboxes." WHP (#586) is a *model* of hazard potential; MTBS is what actually burned, and at
what severity, over four decades. Where modelled hazard and observed outcome diverge, that
divergence is the finding.

## Source

| | |
|---|---|
| Program | Monitoring Trends in Burn Severity (MTBS), a joint USGS EROS / USFS GTAC program |
| Landing page | <https://www.mtbs.gov/> |
| Paper | Picotte et al. 2020, *Fire Ecology* 16:16 — <https://doi.org/10.1186/s42408-020-00076-y> |
| Perimeters | ScienceBase item `5e7229b8e4b01d509268afba` — **Burned Areas Boundaries, version 12.0, April 2025** |
| Severity | ScienceBase parent `5e91dee782ce172707f02cdd`, 41 annual child items — **version 9.0 (Aug 2024)** for 1984–2022, **version 12.0 (Apr 2025)** for 2023–2024 |
| Access date | **2026-08-21** |
| License | USGS/USFS joint program — US Government work, public domain |
| Staged raw | `s3://public-fire/raw/mtbs/` (`perims/`, `mosaics/`, `mosaic-manifest.tsv`) |

`mtbs_perims_DD.zip` is **374,092,911 bytes**, decimal degrees on NAD83 (read as EPSG:4326),
**30,730 G-polygons** per its FGDC metadata.

### The URLs cannot be hardcoded, and the checksums are worth having

ScienceBase file URLs carry a content hash (`?f=__disk__<path>`) and the `?name=<file>` form
returns 404, so `mtbs-stage-raw.yaml` enumerates the 41 year-items from the items API at run time:

```
https://www.sciencebase.gov/catalog/items?parentId=5e91dee782ce172707f02cdd&format=json&max=100&fields=title,files
```

One request returns every file's name, byte size, `pathOnDisk` **and MD5**. Verifying against a
published MD5 beats any hardcoded byte count and survives an upstream re-upload. `curl` must be
driven with `--get --data-urlencode "f=<path>"` — pasting the encoded query string directly gets
the parameter dropped and a 404.

A rolling copy of the perimeters also exists at
`edcintl.cr.usgs.gov/downloads/sciweb1/shared/MTBS_Fire/data/composite_data/burned_area_extent_shapefile/mtbs_perimeter_data.zip`
(389,921,186 bytes). It is **not** used: it is overwritten in place with no dated archive and no
version label, so it cannot be cited to an edition.

### 🔴 Six of the 101 mosaic objects are broken upstream

Probed 2026-08-21, all 101 objects, three retries each with backoff:

| File | Listed size | Status |
|---|---:|---|
| `mtbs_CONUS_2004.zip` | 2,977,514 | 404 |
| `mtbs_CONUS_2017.zip` | 8,773,079 | 404 |
| `mtbs_AK_1987.zip` | 311,667 | 404 |
| `mtbs_AK_1995.zip` | 166,289 | 404 |
| `mtbs_AK_2001.zip` | 225,667 | 404 |
| `mtbs_AK_2013.zip` | 1,622,941 | 404 |

The other 95 download cleanly and match both their published size and their published MD5. The
failure is ScienceBase's object store, not the request:

- the `?f=__disk__…` form works for every other file on the *same items* (`mtbs_HI_2017.zip`
  returns exactly 9,359 bytes);
- the whole-item bundle download returns `mtbs_CONUS_2017.zip` as a **0-byte member**;
- no URL variant, User-Agent or referer changes it.

There is no alternative direct-download route. `edcintl` publishes the perimeter file but no mosaic
path (every plausible directory name 404s), and `burnseverity.cr.usgs.gov/direct-download` builds
mosaic archives through an **email queue** (`POST /downloads/addQueue.php`), not a fetchable URL.

**Consequence:** severity covers **CONUS 39 years** and **AK 36 years**, not 41 and 40. Losing
CONUS 2017 matters — it is a major fire year — so the gap is stated in both severity collections,
and a missing year must never be read as "nothing burned." Perimeters cover all 41 years, so
whether a place burned in 2017 is still answerable; only the severity classes are gone.

Closing the gap needs a human: request the six through the Burn Severity Portal's email queue, or
report the broken objects at <https://www.mtbs.gov/contact>.

## Pre-flight, measured from the source rasters

`ImageWidth`/`ImageLength`/`Compression`/`ColorMap`/`GDAL_NODATA` read directly from the TIFF
headers, before any build:

| | CONUS | Alaska |
|---|---|---|
| Grid (1984) | 148,880 × 87,090 = **12.96 Gpx** | 28,843 × 22,562 = 0.65 Gpx |
| Pixel | 30 m | 30 m |
| Projection | `USA_Contiguous_Albers_Equal_Area_Conic_USGS_version`, NAD83 | Alaska Albers, NAD83 |
| Compression | PackBits, `RowsPerStrip=1` | PackBits, `RowsPerStrip=1` |
| nodata | **0** (declared in the file) | **0** |
| Colour table | present, 256 entries | present, identical for codes 0–6 |

`RowsPerStrip=1` on a 13-gigapixel PackBits raster is another reason the COG step is not optional:
the source is effectively sequential-access only.

### Class codes and palette — transcribed, not remembered

Codes from the FGDC attribute domain shipped with each mosaic; **colours from the GeoTIFF's own
colour table**, which is identical in the CONUS and Alaska rasters. MTBS does ship a palette, so
the STAC asserts one (unlike WHP, where the source ships none).

| Code | Label | `color_hint` |
|---|---|---|
| 0 | Background / No Data (dropped, not stored) | `000000` |
| 1 | Unburned to Low | `006400` |
| 2 | Low | `7FFFD4` |
| 3 | Moderate | `FFFF00` |
| 4 | High | `FF0000` |
| 5 | Increased Greenness | `7FFF00` |
| 6 | Non-Processing Area Mask | `FFFFFF` |

**Codes 5 and 6 are not severity levels** and are excluded from every severity denominator the
STAC recommends. They stay in the data — dropping them would hide the non-processing mask, which is
itself information about coverage.

## Design decisions, and why they depart from the issue as first written

### Severity is per domain, not one national mosaic

MTBS ships CONUS, Alaska and Hawaii on **different Albers grids**. A single mosaicked national
30 m raster is ~86 Gpx per year — four times the NLCD CONUS COG that already needs 32Gi — and 41 of
them is a bad bet. Publishing `…-conus` and `…-ak` separately also matches the WHP precedent in
this same bucket, and both carry `h8`, so they still join cell for cell to each other, to
`whp-2023-*` and to `roadless-areas-2001`.

Unlike WHP, the split is *not* because the classes mean different things per domain: MTBS severity
thresholds are set **per fire** (`Low_T`, `Mod_T`, `High_T` on each perimeter), so a class 4 in
Alaska and a class 4 in CONUS are the same statement about that fire. These two collections *are*
directly comparable — the split is purely a grid-size decision, and the STAC says so.

### Unified multi-year layout, keyed by `year`

Copied from the `nlcd` Annual build (#453), the catalog's precedent for many annual years of one
categorical raster:

```
mtbs-severity-1984-2024-<dom>/hex/year=<YEAR>/h0=<CELL>/data_0.parquet
mtbs-severity-1984-2024-<dom>/hex-fractions/year=<YEAR>/h0=<CELL>/data_0.parquet
```

`year` and `h0` are both partition columns, so one year is a filter and reburn is a self-join on
the cell. 41 separate per-year collections would have been unusable.

### A `fractions` layer alongside `mode`

The issue specifies `mode`, and `mode` alone cannot answer the issue's own question. `mode` keeps
each cell's dominant class and discards the mix, so a cell that is 40% high severity and 60%
moderate reads as entirely moderate — and "share burned at high severity" is exactly that
class-share statistic. `--hex-resampling fractions --resampling near` emits long-format per-class
coverage (`severity`, `frac`), which makes the share exact and makes codes 5/6 cleanly excludable.
Precedent: `nlcd`, `cgls-lc100`, `cwhr`.

### Native resolution 10

30 m source → resolution 10 per the `raster-hexing` anchor table; `h10` is the catalog's finest, so
a 30 m source is *under*sampled and that is accepted. A resolution 10 cell holds ~17 source pixels,
which is why `mode`'s winner-take-all behaviour is a real loss and the `fractions` layer is not
optional. Parents 9, 8, 0 — `h8` because it is the catalog join key, `h0` because it is the
partition key.

### The COG step is mandatory and its absence fails silently

`cng-datasets raster` hands H3 cell polygons in **degrees** to exactextract. Against a raster still
in Albers **metres** they land within ~100 m of the projection origin and every cell reads nodata.
Measured on WHP (#586): the hex Job wrote **zero rows and exited 0**, reporting `Complete`. Only the
h0 coverage gate catches it. `mtbs-severity-cog.yaml` therefore warps every year to EPSG:4326 with
`-r near` (nearest is non-negotiable on a class raster — anything else invents classes) and gates on
a non-empty result plus a code set within 0–6.

Alaska is clipped to `-te -180 48.8 -129.0 71.6`. A naive Alaska-Albers→EPSG:4326 warp yields a
359.9°-wide raster on the dateline seam. The clip drops the far-western Aleutians (~157°E–180°),
which hold no National Forest System land — the Alaska units are the Tongass and Chugach, far east.

### The h0 fan-out is restricted, and why that is safe

At resolution 10 an h0 index that holds no data is **not** free: `cng-datasets raster` prunes only
h0 cells whose envelope misses the raster, and every surviving cell enumerates all ~280 M of its
resolution 10 children before finding them all nodata. Running the generated 122 per year would be
4,758 pod slots at 192Gi (CONUS) to do 234 cells' worth of work.

The sets are **measured off the completed perimeters hex**, by taking each populated h0 partition's
actual cell **centroids** (`h3_cell_to_lat` / `h3_cell_to_lng`) rather than the partition's res-0
footprint. Severity pixels exist only inside MTBS perimeters, so the perimeter h0 set is a strict
superset of the severity h0 set per domain — and the perimeters cover all 41 years, including the
years whose severity mosaic is missing, so it is a superset in time as well.

Where MTBS actually burns, by h0 partition:

| h0 index | h0 cell | res-10 cells | longitude | latitude | domain |
|---:|---|---:|---|---|---|
| 50 | 577199624117288959 | 23,606,176 | −124.41 … −109.70 | 32.54 … 49.12 | CONUS |
| 105 | 576707042908045311 | 11,962,966 | −166.19 … −140.16 | 56.73 … 70.16 | **Alaska** |
| 20 | 577164439745200127 | 9,106,451 | −113.05 … −83.36 | 31.49 … 49.07 | CONUS |
| 14 | 577692205326532607 | 6,666,408 | −96.18 … −79.21 | 25.19 … 37.01 | CONUS |
| 71 | 577762574070710271 | 4,350,826 | −116.67 … −95.22 | 26.29 … 37.12 | CONUS |
| 78 | 577234808489377791 | 996,605 | −84.41 … −67.18 | 33.55 … 44.88 | CONUS |
| 12 | 576812596024311807 | 817,385 | −120.43 … −112.52 | 47.31 … 49.14 | CONUS |
| 0 | 578114417791598591 | 37,515 | −156.69 … −155.09 | 19.01 … 20.91 | Hawaii (not built) |
| 89 | 577832942814887935 | 4,821 | −67.05 … −65.34 | 17.95 … 18.15 | Puerto Rico (not built) |
| 120 | 577727389698621439 | 3,161 | −159.72 … −156.94 | 21.07 … 22.02 | Hawaii (not built) |

So **CONUS = {12, 14, 20, 50, 71, 78}** and **Alaska = {105}**, a single base cell.

**Two wider candidate sets were rejected, and the Alaska one is the point.** Both would have been
defensible-looking and both are wrong:

- **The populated set of `whp-2023-classified-{conus,ak}`** — the first thing to reach for, since
  it is the same bucket and the same domains. It gives CONUS `{12, 14, 20, 50, 71, 78}` (correct)
  but Alaska `{12, 59, 105}` — **three cells where MTBS burns in one.** WHP maps every land pixel
  of its domain, carrying explicit non-burnable and water classes; MTBS maps only ground that
  burned. MTBS's Alaska fires sit entirely between 56.7°N and 70.2°N and −166.2° to −140.2°, inside
  one base cell. Cells 12 and 59 would have been 72 guaranteed-empty resolution 10 indexes.
- **The domain bounding box** — wider still, and wrong in a second way. Intersecting the Alaska
  clip box with the h0 grid returns `{12, 50, 105}`, pulling in cell 50 because the clip box reaches
  about 2.4° south of any Alaska data, into open Pacific off Vancouver Island.

`check-hex-coverage.sh` then verifies per year that every expected partition is populated, so a
wrong list fails loudly rather than shipping a hole.

## Pipeline

Run in `geo-workflows`, one hex Job at a time (`AGENTS.md`: never more than one concurrent k8s hex
workflow).

```bash
# 1. stage the source packages + pre-flight
kubectl apply -n geo-workflows -f mtbs-stage-raw.yaml

# 2. perimeters, step by step (the orchestrator's setup-bucket step is NOT run -- public-fire
#    already exists, already serves anonymously, and nothing about a new dataset changes
#    bucket-level access)
kubectl apply -n geo-workflows -f perimeters/mtbs-perimeters-1984-2024-convert.yaml
kubectl apply -n geo-workflows -f perimeters/mtbs-perimeters-1984-2024-hex.yaml
kubectl apply -n geo-workflows -f perimeters/mtbs-perimeters-1984-2024-pmtiles.yaml
kubectl apply -n geo-workflows -f perimeters/mtbs-perimeters-1984-2024-repartition.yaml

# 3. the 75 WGS84 severity COGs (MANDATORY -- see above)
kubectl apply -n geo-workflows -f mtbs-severity-cog.yaml

# 4. severity hex, sequentially, waiting for Complete between each
for f in severity/mtbs-severity-conus-hex.yaml \
         severity/mtbs-severity-conus-hex-fractions.yaml \
         severity/mtbs-severity-ak-hex.yaml \
         severity/mtbs-severity-ak-hex-fractions.yaml; do
  kubectl apply -n geo-workflows -f "$f"
  kubectl wait -n geo-workflows --for=condition=complete --timeout=36000s job/$(basename "$f" .yaml)
done

# 5. STAC + README (fill MEASURED first)
python3 gen_stac.py
```

Hardening applied on top of the generated manifests: `backoffLimitPerIndex` + `maxFailedIndexes`
replacing `backoffLimit: 0`, so a partial indexed run **fails** rather than publishing as complete;
explicit `namespace: geo-workflows` on every standalone job; `priorityClassName` omitted on the
severity hex jobs (`opportunistic` was preempted within ~20 s during the WHP build, which wastes
the whole cell enumeration).

### Two things that bit during the build

- **`column` is not installed in `ghcr.io/boettiger-lab/datasets:latest`.** A cosmetic
  `column -t -s$'\t'` pretty-print of the manifest exited 127 and killed `mtbs-stage-raw` *after*
  all 95 files were staged. Same class of surprise as `file` being absent during the WHP build.
  Replaced with `cat`, and the download loop now skips any object already staged at the right size
  so a late failure does not re-pull 263 MB from USGS.
- **Do not override `PROJ_DATA`/`PROJ_LIB`** in the COG job. The image ships eight `proj.db` at
  differing layout versions and a `find | head -1` non-deterministically picks a stale one, which
  broke `-t_srs EPSG:4326` on ~10% of pods during the NLCD Annual build (#453). GDAL's own default
  resolves correctly.

## Build results

Every number here is read back off the published artifacts through the duckdb-geo MCP.

### `mtbs-perimeters-1984-2024` (2026-08-21)

| | |
|---|---:|
| Features (flat parquet) | 30,730 |
| `COUNT(DISTINCT Event_ID)` | 30,730 (0 blank) |
| `SUM(BurnBndAc)` | 215,921,856 |
| Ignition dates | 1984-01-26 … 2024-12-17 |
| Hex rows | 57,552,314 |
| `COUNT(DISTINCT h10)` | 45,128,351 |
| `COUNT(DISTINCT _cng_fid)` on hex | **30,730 — equals the flat count** |
| Populated h0 partitions | 10 |
| NULL `h10` / `h9` / `h8` | 0 / 0 / 0 |
| Measured footprint | −166.188, 17.947, −65.338, 70.159 |
| Artifacts | parquet 455,449,347 B · pmtiles 523,033,666 B · hex 407,850,803 B |

**Coverage confirmed, which is the check `--max-completions` demands.** The k8s hex uses a fixed
`--chunk-size 1000`, so total features hexed = `max-completions × 1000`; at 31 that is 31,000 ≥
30,730, and `COUNT(DISTINCT _cng_fid)` on the hex equals the flat parquet's 30,730 exactly. The
default 200 would have scheduled 169 no-op pods.

**Deduplicated acreage round-trips exactly.** `SUM(BurnBndAc)` over `SELECT DISTINCT _cng_fid,
BurnBndAc` on the hex is 215,921,856 — identical to the flat parquet, over 30,730 deduplicated
rows. A raw `SUM` over the 57.5 M hex rows does not.

**No NULL finest-parent cells**, so the collection needs no coarsest-shared-resolution caveat.

**The one GEOMETRYCOLLECTION survived.** The source is 27,378 POLYGON, 3,351 MULTIPOLYGON and one
GEOMETRYCOLLECTION (`_cng_fid` 7416, `NV4099711695019840830`, IZEN 1, 1984, 38,483 acres, two
parts, `ST_IsValid` true). It carries 9,962 hex cells, so it was not silently dropped. Worth
checking because a mixed-type geometry is exactly the thing a polyfill step can skip without
complaint. Note tippecanoe reports 30,731 features rather than 30,730 — it splits that collection
into its two parts.

**Reburn, measured:**

| | |
|---|---:|
| Cells that burned at least once (unique ground) | 45,128,351 |
| (fire, cell) pairs — fire-years | 57,552,314 |
| Cells that burned exactly once | 36,763,278 |
| Cells that burned more than once | 8,365,073 |
| Most times one cell burned | 19 |

Fire-years exceed unique ground by **27.5%**. That is the gap any "total acres burned" figure has
to declare, and it is large enough that quoting the wrong one is a materially different claim.

`Event_ID` is one row per fire on this release, so the two duplication axes coincide and
`_cng_fid` is a sufficient dedup key: `scripts/audit-feature-dup.py … --key Event_ID` reports
30,730 rows / 30,730 distinct / 0 blank / 0 extra.

`verify-stac.py --bucket public-fire --dataset mtbs-perimeters-1984-2024` (with data checks) passes
with zero findings, which is what confirms the corrected `Incid_Type` and `Asmnt_Type` domains
against the ingest.

### 🔴 Two source-documentation errors the ingest caught

The FGDC entity/attribute section shipped with the perimeters is wrong about its own data, in a way
that would have produced a `values` array no consumer query could match:

| Column | FGDC says | The data holds |
|---|---|---|
| `Incid_Type` | `WF`, `Rx`, `UNK` | `Wildfire` (16,960), `Prescribed Fire` (8,870), `Unknown` (4,689), **`Wildland Fire Use`** (211) |
| `Asmnt_Type` | 6 values incl. `Emergency`, `Emergency (SS)` | 4: `Initial` (16,591), `Initial (SS)` (8,144), `Extended` (5,861), `Extended (SS)` (134) |

`Wildland Fire Use` appears nowhere in the source documentation. `BurnBndLat` / `BurnBndLon` are
also **text**, not numeric, and stay text through conversion — documented with the cast a consumer
needs. This is the "coded domains come from the ingest, not the docs" rule earning its place.

### `mtbs-severity-1984-2024-ak` (2026-08-24)

`mode` layer complete and read back through the duckdb-geo MCP.

| | |
|---|---:|
| Hex rows (`mode`) | 12,270,403 |
| `COUNT(DISTINCT h10)` — unique ground | 11,429,727 |
| Years | 36 (1984–2023 less 1987, 1995, 2001, 2013) |
| Severity value set | {1,2,3,4,5,6} — no 0, no out-of-domain code |
| NULL `h10` / `h9` / `h8` | 0 / 0 / 0 |
| Populated h0 partitions | **1** per year, all 36 years |
| Measured footprint | −166.191, 56.730, −140.157, 70.159 |

The footprint sits wholly inside base cell `576707042908045311`, which is the direct confirmation
that the one-cell Alaska fan-out was right and the WHP-inherited three-cell set would have bought
72 guaranteed-empty resolution 10 indexes. Rows exceed unique cells by 7.4% — Alaska's reburn rate
over 36 years, far below CONUS's 27.5% across the perimeters.

`catalog/fire/k8s/mtbs/check-severity-coverage.sh ak hex` passes 36/36 in about 10 s.

### `mtbs-severity-1984-2024-conus`

_Pending — `mtbs-severity-conus-hex` and `-hex-fractions` are queued behind the Alaska fractions
job in `mtbs-severity-hex-workflow`._

### Criterion 1, measured: `mode` tracks the COG but understates high severity

`mtbs-severity-cog-histogram.yaml` re-derives the per-year class histogram of all 75 published
COGs to `raw/mtbs/cog-histograms/`. The original source histograms were printed by the
`mtbs-severity-cog` pods, whose logs are long gone; the COGs are permanent, **and they are the
better reference anyway** — the hex is built from the WGS84 COG, not the Albers source, so
comparing against the COG isolates the reducer from the warp.

⚠️ **The COG is EPSG:4326 and its pixel counts are therefore a geographic share, not an area
share** — a pixel's ground area falls as cos(latitude), while H3 cells are equal-area. The job
emits `area_weight` (each row band weighted by `sin(φ_top) − sin(φ_bot)`) beside the raw count,
and the area-weighted column is the one comparable to the hex. Measured, the correction turns out
to be small — at most 0.43 pp on any CONUS class, under 0.04 pp on any Alaska class, because the
class mix barely tracks latitude even though cos(lat) varies steeply. That is a result, not an
assumption: it is worth establishing rather than asserting, and the job is cheap.

**Alaska, 36 years, `mode` hex against the area-weighted COG:**

| Code | Label | COG area % | `mode` hex % | Δ pp |
|---:|---|---:|---:|---:|
| 1 | Unburned to Low | 13.807 | 15.720 | **+1.913** |
| 2 | Low | 24.937 | 24.205 | −0.732 |
| 3 | Moderate | 29.698 | 29.225 | −0.473 |
| 4 | High | 20.554 | 19.630 | **−0.924** |
| 5 | Increased Greenness | 0.622 | 0.516 | −0.106 |
| 6 | Non-Processing Area Mask | 10.383 | 10.704 | +0.321 |

Per year, high-severity share (code 4 over codes 1–4), all 36 years:

| | |
|---|---:|
| Pearson r, `mode` vs COG | **0.99699** |
| Mean Δ | **−1.123 pp** |
| Max abs Δ | 2.528 pp (1985) |
| Years where `mode` understates | 34 of 36 |

**Both halves of criterion 1 pass, and the residual is the expected one rather than an error.**
r = 0.997 across 36 independent years means no year is mis-assigned to the wrong partition — a
shuffled `year` key could not survive that correlation. The bias is one-directional and it is the
winner-take-all signature: a resolution 10 cell holds only ~17 source pixels, high-severity patches
are typically smaller than that, so they lose the majority vote to the surrounding moderate and low
classes and get absorbed into class 1. `mode` therefore **understates high severity by about
1.1 pp**, roughly 4% relative.

That is the argument for the `fractions` layer stated as a number instead of an assertion. Anyone
quoting a high-severity share off the `mode` asset is low by ~4%, which is why the STAC, the README
and the collection descriptions all route that question to `hex-fractions`. The equivalent
`fractions`-vs-COG check is the stronger invariant — `SUM(frac)` per class is area-proportional, so
it should reproduce the area-weighted COG share to well under a point — and is pending that layer.

## State of the build, and how to resume it

**Read this section first if you are picking the task up in a new session.** The scope decisions
live in issue #593; the measured evidence lives here. Neither is in anyone's session context.

| Stage | State |
|---|---|
| `mtbs-stage-raw` | ✅ complete — 95 mosaics + perimeters staged and MD5-verified; 6 objects broken upstream |
| `mtbs-perimeters-1984-2024` | ✅ **built, published, verified** — collection is live and `verify-stac.py --bucket public-fire --dataset mtbs-perimeters-1984-2024` passes with data checks |
| `mtbs-severity-cog` (75 COGs) | ✅ complete — all 39 CONUS + 36 AK published, values {0…6} |
| `mtbs-severity-ak-hex` (`mode`) | ✅ complete and validated — 36/36 years, coverage gate passes, criterion 1 measured |
| `mtbs-severity-cog-histogram` | ✅ complete — 75/75, `raw/mtbs/cog-histograms/`, the criterion 1 reference |
| `mtbs-severity-ak-hex-fractions` | ⏳ running (started 2026-08-24T18:31Z), 36 pods, driven by `mtbs-severity-hex-workflow` |
| `mtbs-severity-conus-hex` | ⏳ queued behind it |
| `mtbs-severity-conus-hex-fractions` | ⏳ queued behind it |
| `MEASURED` in `gen_stac.py` | ◐ Alaska `mode` values filled; `ak.frac_rows` + all four CONUS values open |
| STAC for the two severity collections + bucket patch + README | ❌ not published |
| PR | ◐ **open as a DRAFT: [#612](https://github.com/boettiger-lab/data-workflows/pull/612)**, branch `worktree-mtbs-593` pushed. Deliberately draft — the severity data is not built, so `verify-stac` is red and the acceptance table in the PR body is the merge gate. Mark ready only when that table is green. |

**Wall-clock still to run is the dominant fact here.** A res-10 index takes a median 2.2 h. Alaska
fractions is 36 indexes at parallelism 61, so one wave: 2–4 h. Each CONUS layer is 234 indexes at
parallelism 61, so four waves: 9–16 h each. The chain is strictly sequential (`AGENTS.md`: never
more than one concurrent k8s hex workflow, and 61 pods at 192Gi is already ~11.7 TB of RAM), so
budget **roughly 24–36 h from 2026-08-24T18:31Z** before the CONUS collection can be measured.
Raising parallelism is not the lever: 122 concurrent pods would be ~23 TB and would not schedule.

Check where the campaign is:

```bash
kubectl -n geo-workflows logs job/mtbs-severity-hex-workflow          # the orchestrator's own log
kubectl -n geo-workflows get jobs | grep mtbs
rclone lsf --dirs-only nrp:public-fire/mtbs-severity-1984-2024-conus/hex/ | wc -l    # /39
rclone lsf --dirs-only nrp:public-fire/mtbs-severity-1984-2024-conus/hex-fractions/ | wc -l
rclone lsf --dirs-only nrp:public-fire/mtbs-severity-1984-2024-ak/hex-fractions/ | wc -l   # /36
```

⚠️ **`kubectl` is not on `PATH` by default here** — it is at `~/bin/kubectl`.

**If the orchestrator Job is gone** (TTL is 7 days, or it aborted), re-apply it. It is idempotent
for jobs that already finished only in the sense that `kubectl apply` on a completed Job is a no-op —
so delete any job it still needs to run before re-applying, and drop already-finished names from the
ConfigMap's key list first:

```bash
kubectl apply -n geo-workflows -f catalog/fire/k8s/mtbs/severity-hex-workflow.yaml
```

### Remaining work, in order

1. **Wait for the three hex jobs.** Each must report `Complete=True` with empty `failedIndexes`;
   the orchestrator aborts the chain otherwise. A res-10 index runs a median 2.2 h, so CONUS
   (234 indexes, parallelism 61) is roughly 12–16 h per layer.
2. **Run the h0 coverage gate per year per domain** — see *Post-build verification* below.
3. **Fill `MEASURED` in `gen_stac.py`.** It prints every unfilled key when run and refuses to let you
   forget. Alaska's `mode` values are in; what remains is `ak.frac_rows` and all four CONUS keys.
   Query through the duckdb-geo MCP, never local duckdb. The queries are the ones in
   *`mtbs-severity-1984-2024-ak`* above — `COUNT(*)`, `COUNT(DISTINCT h10)`, and
   `h3_cell_to_lng`/`h3_cell_to_lat` extremes for the bbox.
4. **Validate the class shares.** Done for Alaska `mode` — see *Criterion 1, measured* above; the
   reference histograms are already built and permanent at `raw/mtbs/cog-histograms/`, so this is
   now just a comparison, not a rebuild. Repeat for CONUS `mode`, and run the stronger
   `fractions`-vs-COG invariant on both domains (`SUM(frac)` per class is area-proportional and
   should reproduce the area-weighted COG share to well under a point; a large gap there IS a
   defect, unlike the `mode` gap, which is expected and quantified).
5. **Publish**: `python3 gen_stac.py`, then `scripts/verify-stac.py --no-data` on each, then
   `rclone copyto` the two severity collections, the patched bucket collection and the patched
   README. The perimeters collection is already live and must not be clobbered.
6. **`scripts/verify-stac.py --bucket public-fire`** must exit 0.
7. **Finish the PR.** [#612](https://github.com/boettiger-lab/data-workflows/pull/612) is already
   open as a draft with the acceptance-criteria table as its merge gate. Update that table as
   criteria go green, re-fire CI's `verify-stac` once the STAC is published (Actions → Verify STAC
   → Run workflow; GitHub does not re-read S3 on its own), then `gh pr ready 612`.

### Things already learned — do not rediscover them

- `column` is not installed in `ghcr.io/boettiger-lab/datasets:latest`.
- Never override `PROJ_DATA`/`PROJ_LIB` in a GDAL job on this image.
- ScienceBase needs `curl --get --data-urlencode "f=<pathOnDisk>"`; a pasted encoded query string 404s.
- Six source mosaics are permanently missing upstream; that is recorded, not a bug to re-investigate.
- `mtbs_CONUS_2005.tif` has 23 out-of-domain pixels, clamped by a VRT LUT.
- The severity h0 sets are measured, not inherited from WHP — CONUS 6 cells, **Alaska 1**.
- `parallelism: 61`, not 12: every index in these jobs is real work.
- **`gen_stac.py` reproduces the live perimeters collection byte-identically** (verified
  2026-08-24 by diffing its output against the published S3 object). The generator is the single
  source of truth, so re-running and re-uploading it cannot clobber the live collection with drift.
- **`MEASURED["ak"]["h0_count"]` was 3 and is 1.** It had inherited the WHP three-cell set that
  this file already records as *rejected*. The published Alaska hex has exactly one partition per
  year across all 36 years.
- **Join severity to `roadless-areas-2001` on `h10`, not `h8`.** Both are native resolution 10.
  One res-8 parent holds 49 res-10 cells, so an `h8` join admits every cell whose parent merely
  touches an IRA: measured on Alaska, 4,555 burned roadless cells against the exact 3,928 — a 16%
  overcount, all boundary. `h8` is for reaching collections that are *not* native resolution 10.
- **The COG histograms are area-weighted for a reason, and the reason is verification, not size.**
  EPSG:4326 pixel counts are a geographic share; H3 cells are equal-area. The measured correction
  is small (≤0.43 pp CONUS, ≤0.04 pp Alaska) because the class mix does not track latitude — but
  that is a finding, not something to have assumed.

## Post-build verification

```bash
# h0 coverage gate -- all 150 year-layers (39 CONUS + 36 AK years x mode + fractions) in ~40 s.
# Exits 1 and names every incomplete prefix. Optionally narrow: `... ak hex`.
catalog/fire/k8s/mtbs/check-severity-coverage.sh

# STAC, static then data-backed
python3 scripts/verify-stac.py --no-data /tmp/mtbs-perimeters-1984-2024-stac.json
python3 scripts/verify-stac.py --bucket public-fire
```

`check-severity-coverage.sh` gates against the **explicit measured h0 sets**, not against
`--reference`. Pairing `mode` against `hex-fractions` is a reasonable cross-check but the two
layers come from the same fan-out over the same restricted h0 list — so an error in that list, or
an h0 lost in both runs, cancels out and the reference agrees with the target about a hole they
share. Comparing each layer against the build's ground truth removes that blind spot. It ships
with the check that matters most for this dataset already encoded: a *missing year* is expected
for the six broken-upstream mosaics, so those years are excluded from the expected set rather
than reported as failures.

⚠️ Do **not** gate a per-domain severity build against a national layer such as
`roadless-areas-2001/hex/` as `--reference` — a national reference is a guaranteed false FAIL.

### Acceptance criteria

| # | Criterion | Status |
|---|---|---|
| 1 | Severity `mode` majority agrees with the COG majority on a sample; values within the valid code set | ◐ **Alaska done** — value set {1…6}, r = 0.997 vs the COG across all 36 years, mean Δ −1.12 pp with the expected winner-take-all sign (see *Criterion 1, measured*). CONUS pending its hex. |
| 2 | Classes 5/6 documented and excludable from severity denominators | ✅ `classification:classes` + `values` + the denominator SQL in both severity collections |
| 3 | Burned share and high-severity share for IRA vs roaded NFS vs wilderness | ⚠️ partly blocked — see below |
| 4 | Reburn handling documented; unique-ground and fire-years both reportable | ✅ both queries in the collection descriptions and the bucket README |
| 5 | MTBS size threshold (incomplete census) stated in the collection description | ✅ all three collections |
| 6 | `mode` is sparse — h0 partition gate with `--min-bytes` filtering | ◐ gate written and exercised in both directions (`check-severity-coverage.sh`); **Alaska `mode` passes 36/36**, the rest pending their builds |
| 7 | `verify-stac.py` clean | _pending the live data_ |

**Criterion 3 is only partly deliverable, and inventing the missing denominators would be worse
than saying so.** `roadless-areas-2001` (#584) exists, so IRA-versus-domain is computable now.
"Roaded NFS" needs the NFS surface-ownership layer from #585, which is **not started** — without it
there is no way to separate roaded National Forest System land from everything else. "Wilderness"
has no issue in the `roadless` set at all and needs one filed. This build delivers the IRA
comparison and records the blocker rather than substituting a denominator that would not mean what
the criterion says.

**The Alaska half of criterion 3 is computable now, and it is nearly degenerate — which is itself
the answer.** Joined on `h10` (the exact key; see above), 3,928 of the 1,708,717 resolution 10
cells inside Alaska's inventoried roadless areas carry any burn severity at all across 36 years:
**0.23%**. Alaska's National Forest System units are the Tongass and the Chugach, coastal temperate
rainforest that essentially does not burn, while Alaska's fire is interior boreal and almost
entirely outside the NFS. So the Alaska IRA sample is too small to carry a severity comparison, and
the substantive IRA-versus-domain test is the CONUS one, pending that build. Reporting a
high-severity share off 3,928 cells as though it characterised "roadless areas" would be the kind
of number this file exists to prevent.

## Notes for the downstream issues

- **#587 (FPA-FOD) owns ignition counts.** MTBS is not a census; anything about how *often* fires
  start has to come from there, not from a `COUNT(*)` here.
- **A "total acres burned" figure from this data is ambiguous until it says which quantity it
  means.** Unique ground and fire-years differ substantially in the West over 41 years, and the
  reburn record is the interesting part rather than noise to be deduplicated away.
- **Any severity time series has six holes** (CONUS 2004 and 2017, Alaska 1987, 1995, 2001, 2013).
  A trend line drawn straight through them understates those years as zero.
