# LANDFIRE 2024 CONUS — build record (#590)

Evidence for the four `landfire-2024-*` collections in `s3://public-landfire`. Numbers here are
**measured from the objects**, not transcribed from upstream documentation — the shipped FGDC XML is
demonstrably wrong about raster dimensions for three of the four layers, and the band NoData
declaration disagrees with the documented fill code.

## Why this dataset exists

The 2026-08-18 Roadless Rule rescission announcement claims "overgrown stands, insect outbreaks and
disease" have turned healthy landscapes into tinderboxes. "Overgrown" is a claim about departure
from reference conditions, which is what LANDFIRE's Vegetation Condition Class measures. The
testable form is comparative — *are Inventoried Roadless Areas more departed than roaded NFS land?*
— against the strata in `public-usfs` (`roadless-areas-2001`, `nfs-surface-ownership`, `roadcore-fs`).

## Version pin

**LF 2024 Update, version 2.5.0** — the newest vintage that still ships VCC. Per `README_LF.txt`,
shipped inside every product:

```
LF 2022 Update [LF 2022 2.3.0] - 3rd update to LF 2016 Remap
LF 2023 Update [LF 2023 2.4.0] - 4th update to LF 2016 Remap
LF 2024 Update [LF 2024 2.5.0] - 5th update to LF 2016 Remap
LF 2025 Update [LF 2025 2.6.0] - 6th update to LF 2016 Remap
```

**LF 2025 (2.6.0) does not ship VCC** (nor SClass or VDep) for CONUS or AK — verified against the
complete `FullExtentDownloads` listing. An unpinned "latest" would have silently dropped the one
layer this build exists to analyse.

**Vintage mismatch to record downstream:** WHP 2023 (#586) is built on LANDFIRE 2020 **v2.2.0**
fuels. This build is **2.5.0**, three updates newer. Do not mix them as same-vintage.

## Source

Landing page (stable): <https://landfire.gov/data/FullExtentDownloads>

| Layer | URL | Bytes | Last-Modified |
|---|---|---|---|
| VCC | `https://landfire.gov/data-downloads/CONUS_LF2024/LF2024_VCC_CONUS.zip` | 1,945,210,012 | Thu, 15 Jan 2026 20:59:04 GMT |
| EVT | `…/LF2024_EVT_CONUS.zip` | 3,827,119,176 | Thu, 15 Jan 2026 21:08:05 GMT |
| EVC | `…/LF2024_EVC_CONUS.zip` | 9,209,843,324 | Thu, 15 Jan 2026 20:51:57 GMT |
| FBFM40 | `…/LF2024_FBFM40_CONUS.zip` | 3,358,372,323 | Thu, 15 Jan 2026 15:07:41 GMT |

All HTTP 200, `Content-Type: application/zip`, verified 2026-08-25. ~18.3 GB total.

Archive layout:

```
LF2024_<PROD>_CONUS/
  README_LF.txt
  CSV_Data/LF2024_<PROD>.csv                 <- legend / attribute table
  General_Metadata/LF2024_<PROD>_CONUS.xml   <- FGDC (dimensions UNRELIABLE, see below)
  Spatial_Metadata/conus_0k.shp, conus_90k.shp
  Tif/LF2024_<PROD>_CONUS.tif  (+ .tfw, .tif.ovr, .tif.vat.dbf, .tif.aux.xml)
```

Staged raw: `s3://public-landfire/raw/LF2024_<PROD>_CONUS.zip` plus the CSV legend, FGDC XML,
README and `.tif.vat.dbf` palette under `s3://public-landfire/raw/landfire-2024/<PROD>/`.
Sizes, sha256 and access date: see *Measurements* below.

## Grid

30 m, NAD83 Albers Conical Equal Area (EPSG:5070; `stdparll` 29.5/45.5, `longcm` -96.0,
`latprjo` 23.0). Confirmed from the TIFF, not the XML.

⚠️ **The FGDC XML row/col counts are wrong for EVT, EVC and FBFM40.** They report
`rowcount` 20729 × `colcount` 24853 (5.15e8 px) while VCC reports 101,538 × 156,335 (1.587e10 px).
All four report an identical `STATISTICS_COUNT` of 15,038,630,766, so all four are on the same 30 m
grid and the three small figures are stale. Dimensions below come from the TIFF.

## Measurements

All four rasters are **Int16, LZW, 156,336 × 101,538 = 15,874,044,768 px**, EPSG:5070, 30 m,
128×128 blocks, with a **declared band NoData of `32767`**. Measured 2026-08-25 by a full-raster
`np.bincount` pass in `landfire-2024-stage-raw` (exact counts, not a sampled histogram).

⚠️ **Note the dimensions: 156,336 columns, not the 156,335 the LF2023 product carries.** And note
the declared NoData is `32767`, not the `-9999` the LANDFIRE documentation names.

### Fill codes — measured, and NOT what the documentation implies

| Layer | distinct values | `-9999` | `-1111` | `32767` | real code range | `--nodata` for the hex step |
|---|---|---|---|---|---|---|
| VCC | 14 | 33.0294% | 5.1454% | 5.2628% | 1 … 180 | `-9999,-1111,32767` |
| EVT | 832 | 33.0294% | — | 5.2628% | 7008 … 9994 | `-9999,32767` |
| EVC | 267 | 33.0294% | — | 5.2628% | 11 … 399 | `-9999,32767` |
| FBFM40 | 46 | 33.0294% | — | 5.2628% | 91 … 204 | `-9999,32767` |

`-9999` and `32767` occur at **identical pixel counts in all four layers** (5,243,100,438 and
835,414,002), so they mask the same regions — the out-of-CONUS Albers corners and an interior
unmapped class. `-1111` (Fill / Not Mapped) occurs in **VCC only**.

⛔ **`32767` was the trap.** The issue's scoping comment specified `--nodata "-9999,-1111"` for VCC
and `"-9999"` for the other three, from the product documentation. That misses `32767` in **all
four** layers — 835,414,002 px, 5.26% of every raster — which would have entered the hex as a real
class. In `mode` it would win cells outright; in `fractions` it would take a share away from real
classes while itself looking like a legitimate category. It passes every structural check: the
value sits inside the COG min/max, row counts and partition coverage are unaffected, no NULLs
appear. Only the measured histogram catches it. This is why `--nodata` is set from the pass above
and not from upstream docs.

The COG step declares the single primary `-9999` (a GDAL band carries only one NoData value, and a
space-separated `-srcnodata` list means *per-band*, not "any of these"). The secondary codes remain
real pixel values in the COG, documented in `classification:classes`, and are excluded at the hex
step, which accepts a comma list (`_parse_nodata_values`, `cng_datasets/raster/cog.py:292`).

### Real class codes, confirmed against the shipped legends

- **VCC** — exactly the documented domain: `1`–`6` condition classes plus `111` Water, `112`
  Snow/Ice, `120` Developed, `132` Barren, `180` Agriculture. Class 3 (Moderate-to-Low departure,
  9.00%) and class 5 (High, 9.84%) are the most common condition classes.
- **EVT** — **832 codes present in CONUS**, fewer than the ~1,068 in the shipped CSV: the legend is
  the national vocabulary, the ingest is what actually occurs. STAC `values` comes from the ingest;
  `classification:classes` comes from the authoritative CSV.
- **EVC** — `11`–`399`, consistent with the lifeform+percent encoding (see *Reducers* below).
- **FBFM40** — `91`–`99` non-burnable plus `101`–`204` Scott & Burgan fuel models.

### Staged raw — provenance fingerprints

Recomputed from the staged objects, not transcribed. Accessed 2026-08-25.

| Layer | Staged path | Bytes | sha256 |
|---|---|---|---|
| VCC | `s3://public-landfire/raw/LF2024_VCC_CONUS.zip` | 1,945,210,012 | `586bc8b114870442074d3fd48f53f029331db8f697dcdef9a788ed88bba640ee` |
| EVT | `s3://public-landfire/raw/LF2024_EVT_CONUS.zip` | 3,827,119,176 | `ce3663846aacc926862b002e9b65de3ca411534ac809480a5997995f3298190e` |
| EVC | `s3://public-landfire/raw/LF2024_EVC_CONUS.zip` | 9,209,843,324 | `7a537f853e2e3ccc6fb1b7adc14f86087be77c6d13726e61ca109596943a4ac8` |
| FBFM40 | `s3://public-landfire/raw/LF2024_FBFM40_CONUS.zip` | 3,358,372,323 | `bb770e8792cd15525f671fc50821c3f09c87952cf74797e0906edc1dc8ac13e2` |

## H3

Native **10**, parents **9, 8, 0**. A 30 m pixel is 0.0009 km² against a res-10 cell at 0.015 km²
(~16 pixels per cell) — res 10 is our finest, so a 30 m source is slightly *under*sampled, which is
the accepted anchor for NLCD and Hansen too.

Six h0 cells carry CONUS at res 10. Derived from `s3://public-grids/hex/h0-valid.parquet` against
the LANDFIRE bbox and confirmed identical to NLCD 2024's populated partitions and to the MTBS CONUS
set:

| `--h0-index` | 12 | 14 | 20 | 50 | 71 | 78 |
|---|---|---|---|---|---|---|
| h0 cell | 576812596024311807 | 577692205326532607 | 577164439745200127 | 577199624117288959 | 577762574070710271 | 577234808489377791 |

## Reducers — all four layers are categorical

| Layer | Reducer | Non-vegetated / special codes (real classes, **not** nodata) |
|---|---|---|
| VCC | `mode` + `fractions` | 111 Water, 112 Snow/Ice, 120 Developed, 132 Barren-or-Sparse, 180 Agriculture |
| EVT | `mode` + `fractions` | lifeform via `EVT_LF` / `EVT_PHYS` in the shipped CSV |
| EVC | `mode` + `fractions` | 11–32 water/snow/developed/barren/quarries; 61–82 agriculture; 100 Sparse |
| FBFM40 | `mode` + `fractions` | 91/92/93/98/99 = NB1/NB2/NB3/NB8/NB9 non-burnable |

**EVC is categorical, not continuous — `mean` would silently corrupt it.** EVC pixel values are
lifeform + percent composite codes: `110`–`199` tree cover = (v−100)%, `210`–`299` shrub,
`310`–`399` herb, `100` sparse (carries no percent), `11`–`32` water/snow/developed/barren,
`61`–`82` agriculture. Averaging those codes averages *across lifeforms*:
`mean(115 tree-15%, 215 shrub-15%) = 165`, which decodes as "Tree Cover 65%" — true of neither
input, and true of nothing at 65% cover. It passes every structural check (inside the COG min/max,
row counts and partition coverage unaffected, no NULLs); only knowing the encoding catches it. A
decoded continuous canopy-cover layer is a separate derived product, not a reducer flag.

VCC's own legend (`LF2024_VCC.csv`), confirming ordinal class codes 1–6:

```
1  Vegetation Condition Class I.A    Very Low,          Vegetation Departure 0-16%
2  Vegetation Condition Class I.B    Low,               Vegetation Departure 17-33%
3  Vegetation Condition Class II.A   Moderate to Low,   Vegetation Departure 34-50%
4  Vegetation Condition Class II.B   Moderate to High,  Vegetation Departure 51-66%
5  Vegetation Condition Class III.A  High,              Vegetation Departure 67-83%
6  Vegetation Condition Class III.B  Very High,         Vegetation Departure 84-100%
```

**Why `fractions` in addition to `mode`:** `mode` keeps only the plurality class per cell and
discards the mix, which cannot answer "what share of forest is departed". `fractions` emits one row
per (cell, class) with `frac` = the class's coverage-weighted share, and keeps nodata as an explicit
class so `frac` sums to ≤ 1 per cell and the unclassified share stays recoverable rather than
silently inflating the real classes:

```sql
-- ground area of one class
SELECT SUM(frac * h3_cell_area(h10, 'km^2')) FROM … WHERE vcc = 6
```

This also lets the non-vegetated / non-burnable codes above be **excluded from the denominator**
rather than merely documented.

## Jobs

| Job | Completions | What |
|---|---|---|
| `landfire-2024-stage-raw.yaml` | 4 | download → `raw/`, extract sidecars, measure the exact value histogram |
| `landfire-2024-cog.yaml` | 4 | unzip → WGS84 COG (`-r near`, NEAREST overviews) |
| `landfire-2024-hex.yaml` | 48 | both reducers × 4 layers × 6 h0, one wave |

The hex job carries **both reducers in one indexed Job** rather than two serialized ones: they are
independent per (layer, h0, reducer) and the namespace rule is one hex *workflow* at a time, so
folding the reducer into the index fans both out in a single wave.
