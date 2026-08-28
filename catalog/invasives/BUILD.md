# USGS INHABIT v4.0 — build notes

Evidence for the INHABIT invasive-plant habitat-suitability ingest (data-workflows #610).
Everything below is **measured** from the source rasters and the ScienceBase item API, not taken
from upstream documentation. Where a measurement contradicts the issue body or the FGDC metadata,
the measurement wins and the contradiction is recorded rather than quietly fixed.

## Source

USGS Invasive Species Habitat Tool (INHABIT) **v4.0, June 2024**, Fort Collins Science Center.
[doi:10.5066/P14HNEJF](https://doi.org/10.5066/P14HNEJF), ScienceBase parent
`663926f0d34e2537768ce951`, 259 species child items — of which **12** are in scope (the exotic
annual grasses that build continuous fine fuels, plus the two riparian woody invaders).

Method: Jarnevich et al. 2024, *NeoBiota* 96:261–278
([10.3897/neobiota.96.134842](https://doi.org/10.3897/neobiota.96.134842)); five algorithms (BRT,
GLM, MARS, Maxent, RF) in SAHM 2.2.2, ensembled by continuous Boyce index.

⚠️ **Fetch from ScienceBase, never from <https://gis.usgs.gov/inhabit/>** — the viewer 403s
non-browser agents.

⚠️ **v3.0 ([10.5066/P9V54H5K](https://doi.org/10.5066/P9V54H5K)) is not comparable.** v4 changed
the ensemble from *model agreement* to *continuous relative suitability*; pixel values do not mean
the same thing. Do not mix them.

## Inventory — measured 2026-08-26

Child-item ids pinned in `k8s/inhabit-v4/stage-raw.yaml`, re-verified against the parent listing on
2026-08-26.

| Species | common name | ScienceBase child item | rasters | in-scope GB |
|---|---|---|---:|---:|
| *Aegilops cylindrica* | jointed goatgrass | `669ee0dcd34eef99d5abbb3b` | 9 | 2.91 |
| *Bromus arvensis* | field brome | `669fd2e7d34eef99d5abc5eb` | 9 | 2.79 |
| *Agropyron cristatum* | crested wheatgrass | `669ee8e0d34eef99d5abbb50` | 9 | 2.73 |
| *Bromus japonicus* | Japanese brome | `66a14239d34ef32deb7ede9c` | 9 | 2.67 |
| *Elaeagnus angustifolia* | Russian olive | `66a68b88d34ea6469c870807` | 9 | 2.36 |
| *Taeniatherum caput-medusae* | medusahead | `66bb7a6ad34e033882814282` | 9 | 2.25 |
| *Salsola tragus* | Russian thistle | `66c3c389d34e03388287bba9` | 9 | 2.03 |
| *Tamarix chinensis_ramosissima* | tamarisk | `66bb7eccd34e033882814498` | 9 | 2.02 |
| *Bromus tectorum* | cheatgrass | `66a14c62d34ec831f2c2b1cc` | 9 | 1.96 |
| *Ventenata dubia* | ventenata | `66c3adebd34e03388287af28` | 9 | 1.93 |
| *Bromus rubens* | red brome | `66a14559d34ef32deb7ee1a2` | 9 | 1.34 |
| *Cenchrus ciliaris* | buffelgrass | `66a29430d34ec831f2c2d2d7` | 9 | 0.98 |
| **total** | | | **108** | **26.0** |

**Two corrections to the issue body** (recorded, not silently applied):

1. **26.0 GB, not "≈4 GB for the set."** The issue generalised one species' per-file size.
2. **No species is missing a model.** All 12 carry occurrence, abundance and high-abundance,
   both plain and `-masked`, plus all three `integrated-binary-*`. The acceptance criterion
   "species missing abundance or high-abundance models are recorded, not silently dropped" is a
   no-op for this set. `stage-raw.yaml` still asserts it at runtime (prints `MISSING\t…` to
   stderr) so a future re-run against a changed release cannot drop one silently.

## ⚠️ The inner tif name does not match the zip name

`occurrence-weighted-ensemble-masked.zip` contains **`occ-cbi-weighted-ensemble-masked.tif`**
(`cbi` = continuous Boyce index, the v4 ensemble weighting). Deriving the member name from the
archive name fails. `stage-raw.yaml` globs by *extension* and renames to the canonical product key,
which is what every S3 path and STAC id downstream uses:

    s3://public-invasives/raw/inhabit-v4-2024/<species>/<product>.{tif,xml}

Products: `occurrence`, `abundance`, `high-abundance`, each also `-masked`;
`integrated-binary-{first,fifth,tenth}`; sidecars `variableImportance.csv`, `assessmentMetrics.csv`.

## Grid — measured with rasterio on the source tifs

| | |
|---|---|
| Size | **44319 x 30671** = 1.359 Gpx |
| CRS | Albers Conical Equal Area, NAD83 / GRS 1980 (`latitude_of_center` 40, `longitude_of_center` −96, standard parallels 20 / 60) |
| Pixel | **98.4693338923368 m** exactly — matches the v4 FGDC `absres`/`ordres` |
| Bounds | −2 236 972.33, −1 691 433.34 → 2 127 090.08, 1 328 719.60 (m) |
| Layout | LZW, **tiled 256 x 256**, no overviews |

The papers round the pixel to "90 m"; use the metadata value. Record 98.4693338923368 in STAC.

**`is_cog()` returns False** on these (tiled but no overviews), so `raster-workflow` will add a
`preprocess-cog` step for every layer rather than hexing the source directly. That is the desired
behaviour — the source is Albers and must be warped to EPSG:4326 first — but see the resampling
trap below.

## Pixel type and value domain — measured, and NOT what the issue assumed

| product class | dtype | NoData | measured value set | FGDC domain |
|---|---|---:|---|---|
| continuous ensembles (6) | **uint8** | **255** | **0 – 98, all 99 values present** | `rdommin` 0, `rdommax` 98 |
| `integrated-binary-*` (3) | **int8** | **−128** | **−1, 0, 1, 2, 3 — exactly five** | `rdommin` −1, `rdommax` 3 |

Exact full-raster `bincount` (not decimated), *Cenchrus ciliaris*, 1 359 308 049 px each:

| | `occurrence-masked` (uint8) | `integrated-binary-fifth` (int8) |
|---|---|---|
| NoData | 255 → 914 288 271 px (**67.26%**) | −128 → 571 952 903 px (**42.08%**) |
| data | 0–98, 99 distinct values | −1: 342 322 727 · 0: 407 783 717 · 1: 5 649 165 · 2: 4 905 953 · 3: 26 693 584 |

**No undeclared sentinel in either product** — the declared NoData is present, and nothing outside
the FGDC domain appears. That is a measurement, and it is why the census runs across all 108 rather
than being inferred from these two.

The census costs **5–6 s per raster** (uint8/int8, 256 bins, one pass over LZW blocks), so the full
set is minutes, not hours.

Two consequences:

1. **The continuous ensembles are uint8, not float32.** Relative suitability is stored as an
   integer index (0–98), not a 0–1 float. So a "300 MB zip" expands to a ~1.36 GB *uncompressed*
   raster, not ~5.4 GB, and the staged tif stays ~zip size because the internal LZW survives the
   zip. **The 50Gi ephemeral cap does not bind for staging** (largest single product 451 MB) and no
   `rechunk-scratch` PVC is needed for it. An earlier estimate on the issue assumed float32 and
   ~440 GB of intermediates; that was wrong and is corrected here.
2. **NoData differs by product class** — 255 for the continuous ensembles, −128 for the class
   rasters. A single batch-wide `--nodata` would corrupt one or the other. Pass it per product.

### `-1` is a VALID class — RESOLVED 2026-08-27: it is the MESS extrapolation flag

The FGDC domain for `integrated-binary-*` is `rdommin` **−1** to `rdommax` 3, and −1 occupies
**25.2%** of the *Cenchrus ciliaris* `integrated-binary-fifth` raster — 342 322 727 px, third
largest bin after NoData and class 0. It reaches **48.5%** on *Bromus rubens*. A sign test
("negatives are fill") would delete up to half a raster. The FGDC gives **no `edomvd` label** for
any of the five codes, which is why this was carried as an open item rather than guessed.

**Resolved from the release's own documentation, then independently confirmed against the data.**

Two documentary statements, neither in the child-item FGDC:

1. `INHABIT_VersionHistory.txt` (parent item `663926f0d34e2537768ce951`), listing the v4 changes:
   *"addition of categorical map combining **unsuitable, occurrence suitable, abundance suitable,
   and high abundance suitable**"* → four named categories for codes 0, 1, 2, 3.
2. Jarnevich et al. 2024, Methods → *Spatial outputs*: *"Finally, we combined the binary maps to
   display information across all three model groups (occurrence, abundance, high abundance) for
   each of the three thresholds, **while highlighting any areas of environmental
   extrapolation**."* → the fifth code is that highlight.

The extrapolation surface is named in the same section: a **MESS** (multivariate environmental
similarity surface, Elith et al. 2010) whose negative values mark *novel environmental
conditions* — at least one predictor outside the range of the model training data. That is also
exactly what the `-masked` continuous variants suppress (*"only display areas where environmental
characteristics are inside the range of the values used to develop the model"*, FGDC `supplinf`).

**Data-backed confirmation.** If −1 is the MESS flag, its pixel count must match the area the
`-masked` occurrence product suppresses. Measured from the value census:

| species | −1 px in `integrated-binary-fifth` | px suppressed by `occurrence-masked` | agreement |
|---|---:|---:|---:|
| *Bromus rubens* | 381 452 798 | 381 839 137 | **0.10%** |
| *Cenchrus ciliaris* | 342 322 727 | 341 949 521 | **0.11%** |
| *Taeniatherum caput-medusae* | 275 370 039 | 276 316 597 | 0.34% |
| *Ventenata dubia* | 170 230 431 | 170 942 048 | 0.42% |
| *Bromus tectorum* | 38 329 816 | 38 352 579 | **0.06%** |

Agreement to 0.06–0.42% on the five species where −1 is largest. The residual is expected and not
a discrepancy: the MESS mask is computed per predictor set, and the integrated map highlights
extrapolation across all three model groups while `occurrence-masked` is masked on the occurrence
predictors alone, so the two areas are near-identical rather than identical.

**Consequences for STAC and for use.**

- Codes are `-1` novel environmental conditions · `0` unsuitable · `1` occurrence suitable ·
  `2` abundance suitable · `3` high abundance suitable. NoData is `-128`.
- **`-1` must be excluded from suitability accounting explicitly** — a `>= 0` predicate. Folding
  it into class 0 would count "we don't know" as "unsuitable", which for red brome is half the map.
- **The `integrated-binary-*` products already carry the restriction information**, as class −1
  rather than as NoData. So the "use `-masked` inside an IRA" rule maps onto the class raster as
  "filter `-1`", not "fetch a different file". There is no `integrated-binary-*-masked` variant
  and none is needed.

### ⚠️ The ranks are EXCLUSIVE in the raster and NESTED in the source's tabulations

Found while resolving the class set, and it is the kind of thing that silently halves an answer.
Jarnevich et al. 2024, on the management-area summaries: *"Values were nested such that summaries
of occurrence models included locations defined as suitable by any of the three model groups."*

In the **raster**, a pixel suitable for high abundance is coded `3` **only** — it does not also
appear as `1`. In the paper's **tables**, "occurrence suitable" area includes everything suitable
at any level. So:

    occurrence-suitable   = suitability_class >= 1     (classes 1 + 2 + 3)
    abundance-suitable    = suitability_class >= 2
    high-abundance        = suitability_class  = 3

`COUNT(*) WHERE suitability_class = 1` is **not** occurrence-suitable ground — it undercounts by
every cell that also clears a higher threshold. For cheatgrass that is 90 394 262 px counted
against 301 109 637 actually occurrence-suitable: a **3.3× undercount**. This must be in the STAC
column description, not only here.

### The 0–100 scale is the design, confirmed by the paper

The census measured continuous maxima of 95–100 across species against an FGDC `rdommax` of 98
(see below), and the paper settles which is right: *"we rescaled the mapped values for each model
between **0 and 100** to make the maps more comparable."* So `rdommax` 98 is a per-file artifact
and the family scale is 0–100. STAC carries the measured per-layer range.

### ⚠️ Run a full value histogram before trusting the declared NoData

Carried in from the #590 LANDFIRE build (peer session, 2026-08-26): **`32767` is fill in all four
LANDFIRE layers, is the band's declared NoData, and appears in none of the product documentation** —
5.26% of every raster. Trusting the docs and trusting the band metadata each gave a different,
incomplete answer. An undeclared sentinel survives every structural check, wins cells outright
under `mode`, and takes share from real classes.

So: before hexing, run an exact `bincount` over each *source* raster (cheap here — uint8/int8, 256
bins) and declare the measured value set in STAC. `verify-stac.py`'s `values-vs-distinct` check is
hard against that declared set, so an invented or leaked code fails the gate rather than shipping.

## Value census — all 108 rasters, exact `bincount` (2026-08-26)

Job `k8s/inhabit-v4/value-census.yaml`, 12 indexed pods, 9m30s wall. Records land at
`s3://public-invasives/raw/inhabit-v4-2024/_census/<species>/<product>.json`.

**No undeclared sentinel anywhere in the 108.** The declared NoData is present in every raster and
nothing outside the FGDC domain appears. The #590 failure shape does not occur here — but that is
now a measurement rather than an assumption, and it is what STAC declares.

### The 36 class rasters are uniform

Every `integrated-binary-*`, all 12 species, all three thresholds: dtype int8, NoData −128, data
values **exactly `{-1, 0, 1, 2, 3}`**. No species carries a code the others do not. The hexed class
set must be a subset of this; nearest-neighbour warping is what preserves it.

### The continuous index runs 0–100, not the FGDC's 0–98

`rdommax` = 98 is a **per-file** figure and understates the product family. Measured maxima:

| max | species |
|---:|---|
| 100 | *A. cristatum*, *B. arvensis*, *B. japonicus*, *B. rubens*, *B. tectorum*, *E. angustifolia*, *S. tragus*, *V. dubia* |
| 99 | *A. cylindrica* |
| 98 | *C. ciliaris* |
| 96 | *T. caput-medusae* |
| 95 | *Tamarix* |

32 of the 72 continuous rasters reach 100. So the scale is **relative suitability 0–100**, and STAC
carries the *measured* per-item min/max, never the FGDC domain.

18 rasters have a gap in their value set (e.g. *A. cristatum* `occurrence` runs 0–88 then a single
pixel at 94; *B. arvensis* skips 99 and has 497 px at 100). Every isolated value sits in the far
tail with counts of 1–65 272 against ~787 M data pixels — sparse extremes and integer-rounding
artifacts of the ensemble scaling, **not sentinels**. Recorded so a later reader does not
re-litigate them.

## ⚠️ The training-envelope restriction is not a light touch, and it varies 3× by species

`-masked` is the stated IRA default, for a good reason (roadless country is high-elevation,
undersampled terrain outside the training envelope). But the census shows how much surface that
choice actually removes, and it is species-dependent to a degree the issue does not anticipate —
data pixels retained by `-masked` against the plain product:

| species | occurrence | abundance | high-abundance |
|---|---:|---:|---:|
| *Cenchrus ciliaris* | **56.5%** | **33.6%** | **33.6%** |
| *Bromus rubens* | **51.5%** | 79.6% | 79.6% |
| *Taeniatherum caput-medusae* | 64.9% | 69.2% | 69.2% |
| *Ventenata dubia* | 78.3% | 78.6% | 78.6% |
| *Agropyron cristatum* | 87.1% | 87.7% | 87.4% |
| *Salsola tragus* | 93.9% | 90.6% | 92.0% |
| *Aegilops cylindrica* | 92.4% | **100.0%** | 96.4% |
| *Tamarix chinensis_ramosissima* | 92.8% | 93.9% | 93.9% |
| *Bromus arvensis* | 94.3% | 97.3% | 97.3% |
| *Bromus tectorum* | 95.1% | 95.1% | 95.1% |
| *Elaeagnus angustifolia* | 96.1% | 95.7% | 95.8% |
| *Bromus japonicus* | 97.2% | 98.2% | 98.2% |

Two consequences the collection description must carry:

1. **For buffelgrass, `-masked` discards two thirds of CONUS** (33.6% retained on abundance and
   high-abundance). A masked IRA tabulation for that species is a statement about a third of the
   country, and the masked-vs-plain choice changes the answer more than any threshold choice does.
   Red brome (51.5% on occurrence) and medusahead (64.9%) are the next most affected. Cheatgrass —
   the species most of the fire argument rests on — is barely touched at 95.1%.
2. **For *Aegilops cylindrica* `abundance`, the masked file is not a restriction at all**: its value
   histogram is byte-for-byte identical to the plain product (file sizes differ by 476 bytes of TIFF
   metadata), i.e. 100.0% retained. Its `high-abundance` counterpart *is* genuinely masked (96.4%),
   so this is specific to one species × product. It may be legitimate — a model whose predictors
   never extrapolate — but "`-masked` = restricted to the training envelope" implies a safeguard
   that, for this one product, did nothing. Record it; do not present it as protection.

## ⚠️ Reprojection resampling — the generator hardcodes bilinear

`cng_datasets/k8s/workflows.py:865` appends **`--resampling bilinear`** to the generated
`preprocess-cog` step, and `raster-workflow` exposes **no flag to change it** (only `raster` has
`--resampling`). Overview resampling *is* correctly switched to `mode` for a categorical
`--hex-resampling` (datasets #108), which makes the step look categorical-aware while the main warp
is not.

Bilinear on class codes invents codes that do not exist upstream. **The three
`integrated-binary-*` products must be warped nearest-neighbour**; the generated YAML is patched to
`--resampling near` by hand until upstream takes a flag. Continuous ensembles keep bilinear.

Verification (acceptance criterion): the hexed class set must be a **subset** of the measured
source class set, with no new codes.

## Reducer — splits by product type

| products | `--hex-resampling` | why |
|---|---|---|
| the 6 continuous ensembles | **`mean`** | relative suitability is a normalized index, not a per-pixel amount |
| the 3 `integrated-binary-*` | **`mode`** | class codes; `sum`/`mean` on class codes is nonsense |

**`mode` keeps only the dominant class per cell and discards the mix**, so it cannot answer "how
many roadless acres are high-abundance-suitable" without undercounting to plurality cells
(`AGENTS.md:550`). Per-class fractional coverage is not produced by this pipeline. This must appear
in each `integrated-binary-*` hex asset `description`.

## H3

Native **10**, parents **9, 8, 0**. Pixel area 98.4693338923368² = **9 696 m²** against a res-10
cell of **15 047 m²** = **1.55 px/cell** — the same correspondence WHP (270 m) has at res 9 in #594.
Carries `h8`, so it joins #584 / #585 / #586 directly (`AGENTS.md:735`).

### ⛔ CONUS h0 set: `12, 14, 20, 50, 71, 78` — do NOT copy the RAP precedent

`catalog/rap/k8s/rap-pfg-cover/rap-pfg-cover-conus-hex.yaml` hardcodes `CHUNK_MAP=(12 20 50 71)`
with the comment "CONUS-bounding h0 indices; tool skips ones the raster doesn't cover". **That list
is missing two of the h0 cells CONUS actually occupies**, and the comment is what makes it look
safe: the tool skips *supplied* indices that have no coverage, but it can never process an index
that was never supplied. Under-supplying is silent.

Resolved against `s3://public-grids/hex/h0-valid.parquet` by locating known cities (index = row
order in that file):

| h0 index | h0 | covers |
|---:|---:|---|
| 14 | 577692205326532607 | Nashville, Houston, Miami, Key West — **the Southeast** |
| 20 | 577164439745200127 | Denver, Chicago, Bismarck, Duluth — the northern plains |
| 50 | 577199624117288959 | Seattle, Los Angeles, San Diego, Salt Lake — the West |
| 71 | 577762574070710271 | Tucson, El Paso, Yuma, Brownsville — the Southwest border |
| 78 | 577234808489377791 | Boston, Detroit, Pittsburgh, Norfolk, northern Maine — **the Northeast** |
| 12 | 576812596024311807 | far northern border strip; included as a cheap no-op |

**14 and 78 are absent from the RAP list.** Six indices are passed here; an index with no data is a
fast no-op, so over-supplying costs a pod and under-supplying loses a third of the country.

### The same gap is present in the published `public-rap` hex

Not a hypothetical. Verified against the catalog, 2026-08-26:

- `s3://public-rap/rap-pfg-cover/hex/` contains **exactly 4 h0 partitions** — `12, 20, 50, 71` —
  matching its `CHUNK_MAP` and missing `14` and `78`.
- Its own source COG `s3://public-rap/rap-pfg-cover-cog.tif` spans the **full CONUS**:
  −124.77 .. **−66.87** lon, 24.52 .. 49.39 lat.
- The hexed cells stop at **−82.12** lon (2 M-row sample).

So ~15° of longitude present in the COG — Florida, Georgia, the Carolinas, Virginia, and the entire
Northeast — is missing from the published res-10 hex. The COG is fine; the hex is not. This is a
`public-rap` defect, not an INHABIT one, and is raised separately; it is recorded here because it is
the reason this build does not inherit that index list.

## ⚠️ Road-bias check — COMPLETE, and it fires on all 12

The issue assumed the predictor library is environmental (Engelstad et al. Table S1) "rather than
distance-to-road", and required per-species verification. **Verified, and the assumption does not
hold: `gHM` (Global Human Modification — built substantially from roads, and already in our catalog
as `global-human-modification`) is a predictor in all 12 models.**

| species | gHM share of importance | rank |
|---|---:|---|
| *Aegilops cylindrica* | **22.0%** | **1 / 25** |
| *Tamarix chinensis_ramosissima* | **16.4%** | **2 / 26** |
| *Cenchrus ciliaris* | 13.9% | 3 / 24 |
| *Elaeagnus angustifolia* | 11.3% | 3 / 28 |
| *Salsola tragus* | 6.1% | 3 / 25 |
| *Ventenata dubia* | 5.7% | 6 / 26 |
| *Agropyron cristatum* | 5.1% | 7 / 28 |
| *Bromus arvensis* | 5.0% | 7 / 29 |
| *Bromus japonicus* | 3.5% | 8 / 26 |
| *Taeniatherum caput-medusae* | 3.4% | 7 / 26 |
| *Bromus rubens* | 2.2% | 8 / 24 |
| *Bromus tectorum* | **1.2%** | 12 / 25 |

Method: mean `AUCdiff` per predictor from `variableImportance.csv`, pooled over the five algorithms
and all four model types (`occurrence_KDE`, `occurrence_target`, `abundance`, `high_abundance`),
normalised to the per-species total.

### Per-model-group breakdown — DONE 2026-08-27, and pooling was flattering the numbers

The owed breakdown is complete. **12.6–22.9% of `AUCdiff` rows are negative** (removing the
predictor *improves* AUC), which makes a raw share-of-total ill-conditioned, so the figures below
clip negative means to zero and take a share of the positive total. That changes the numbers by
≤0.1pp against the raw share — the metric is robust — and rank is unaffected either way.

**The occurrence models are where gHM concentrates, and the occurrence models are what the road
gradient leans on.** gHM's share RISES when the pooled average is dropped, for 10 of 12 species:

| species | pooled (4 groups) | **occurrence only** | occurrence backgrounds |
|---|---:|---:|---|
| *Aegilops cylindrica* (jointed goatgrass) | 22.0% (r1/25) | **25.0% (r1/24)** | KDE, target |
| *Cenchrus ciliaris* (buffelgrass) | 13.9% (r3/24) | **22.4% (r1/23)** | KDE, target |
| *Elaeagnus angustifolia* (Russian olive) | 11.3% (r3/28) | **17.6% (r3/27)** | KDE, target |
| *Tamarix chinensis_ramosissima* (tamarisk) | 16.4% (r2/26) | **17.1% (r3/25)** | KDE, target |
| *Salsola tragus* (Russian thistle) | 6.1% (r3/25) | **12.9% (r2/22)** | KDE, target |
| *Bromus arvensis* (field brome) | 5.0% (r7/29) | 8.0% (r4/27) | KDE, target |
| *Agropyron cristatum* (crested wheatgrass) | 5.0% (r7/28) | 7.2% (r3/26) | KDE, target |
| *Bromus japonicus* (Japanese brome) | 3.5% (r8/26) | 6.3% (r6/26) | KDE, target |
| *Ventenata dubia* (ventenata) | 5.7% (r6/26) | 6.0% (r7/26) | KDE, target |
| *Bromus rubens* (red brome) | 2.2% (r8/24) | 4.0% (r8/22) | KDE, target |
| *Taeniatherum caput-medusae* (medusahead) | 3.4% (r7/26) | 3.1% (**r10/26**) | KDE, target |
| *Bromus tectorum* (cheatgrass) | 1.2% (r12/25) | **2.0% (r6/23)** | **target only** |

Split further, by the two occurrence background designs and the two abundance groups — this is
where the mechanism shows:

| species | `occurrence_KDE` | `occurrence_target` | `abundance` | `high_abundance` |
|---|---:|---:|---:|---:|
| *A. cylindrica* | 27.0% (r1) | 24.0% (r1) | 25.2% (r1) | 23.1% (r1) |
| *C. ciliaris* | **38.4% (r1)** | 2.4% (r8) | 1.3% (r10) | 2.1% (r8) |
| *E. angustifolia* | **36.6% (r1)** | 2.4% (r4) | 6.0% (r4) | 2.7% (r6) |
| *S. tragus* | **23.9% (r1)** | 1.3% (r10) | 2.9% (r7) | 0.7% (r13) |
| *B. japonicus* | 12.2% (r2) | 0.9% (r14) | −0.1% (r23) | 1.0% (r11) |
| *Tamarix* | 5.4% (r7) | **46.7% (r1)** | 21.3% (r2) | 18.2% (r2) |
| *B. tectorum* | *(no model)* | 2.0% (r6) | 0.9% (r13) | 0.9% (r15) |
| *T. caput-medusae* | 2.2% (r9) | 4.6% (r7) | 3.8% (r7) | 3.9% (r7) |
| *B. rubens* | 6.6% (r6) | 2.3% (r7) | 1.6% (r8) | −0.8% (r23) |
| *A. cristatum* | 6.8% (r6) | 9.2% (r3) | 3.7% (r7) | 2.4% (r11) |
| *B. arvensis* | 8.1% (r3) | 9.2% (r5) | 0.4% (r16) | 3.2% (r11) |
| *V. dubia* | 8.2% (r6) | 4.7% (r6) | 8.6% (r4) | 7.5% (r5) |

Three findings that change the recommendation:

1. **Cheatgrass has NO `occurrence_KDE` model at all** — it carries only `occurrence_target`, the
   design the paper introduces *specifically* to mitigate sampling bias ("we randomly selected up
   to 10 000 locations of non-native vascular plant observations … restricted to the same 99%
   binary KDE"). So the species the fire argument rests on is not merely the lowest-gHM of the 12,
   its only occurrence model is the bias-mitigated one. That is a stronger clean bill than the
   pooled 1.2% suggested, and it is the opposite of what its *rank* movement (12/25 → 6/23) looks
   like in isolation.
2. **The target-background design demonstrably works — for most species.** For buffelgrass,
   Russian olive and Russian thistle, gHM is rank 1 at 24–38% under the KDE background and falls
   to 1–2% under the target background. That is the bias mitigation doing its job, visible in the
   data.
3. **It does not work for tamarisk, and tamarisk is one of the two species the issue names for the
   gradient.** Tamarisk is the one species where gHM is *higher* under the target background
   (46.7%, rank 1/25) than under KDE (5.4%, rank 7) — and it stays rank 2 at 18–21% in both
   abundance groups. A tamarisk distance-to-road gradient is substantially the model reproducing
   its own predictor. Jointed goatgrass is worse in a different way: gHM is rank 1 in **all four**
   model groups, so no variant of it is clean.

**Recommendation for #588's gradient**, superseding the issue's "cheatgrass and tamarisk at
minimum":

| verdict | species | occurrence-only gHM |
|---|---|---|
| **defensible** | cheatgrass, medusahead, red brome | 2.0%, 3.1%, 4.0% |
| caution — report with the caveat | ventenata, Japanese brome, crested wheatgrass, field brome | 6.0–8.0% |
| **circular — suitability-only, do not report as road evidence** | Russian thistle, tamarisk, Russian olive, buffelgrass, jointed goatgrass | 12.9–25.0% |

**Drop tamarisk from the gradient and substitute medusahead** (3.1%, rank 10/26 — the best *rank*
of the 12). Cheatgrass + medusahead gives one annual grass and one annual grass with independent
predictor sets, both clean. Report the five circular species as suitability-only.

This does **not** invalidate the suitability surfaces — gHM is a legitimate predictor of invasion.
It invalidates the specific inference "suitability rises near roads, therefore roads drive
invasion" for the high-gHM species.

## Framing constraints that must reach the collection description

1. **Potential habitat, not occurrence.** A high-suitability pixel inside an IRA is not an invaded
   pixel. Every result reads "suitable habitat for X", never "X is present".
2. **`-masked` is the default for IRA tabulation.** Unrestricted extrapolation is least trustworthy
   exactly where roadless country sits — high-elevation, undersampled terrain outside the training
   envelope. Both variants land; the description must name `-masked` as the IRA default and give
   the reason.
3. **`fifth` (0.05) is the canonical threshold**, with `first` / `tenth` retained as the sensitivity
   band. Naming it up front is what stops a later analysis picking whichever threshold supports the
   conclusion.
4. **CONUS only.** INHABIT v4 excludes Alaska, where the Tongass and Chugach are the largest
   roadless acreage in the system. Every national statement from this dataset is a CONUS statement;
   report covered IRA acreage against the 44,701,002-acre rule-affected base (#584).

## Licence

USGS data release; FGDC `useconst` = "None", `accconst` = "None" → **US federal work, public
domain**.

⚠️ **The issue's registration criterion is obsolete.** It asks for `public-invasives` to be added to
`BUCKETS` in `catalog/sync/minio/gen-minio-sync.sh` and `REPOS` in `gen-source-sync.sh`. **`catalog/sync/`
was deleted from this repo in `8951888` (#536, #550, PR #568)** — the backup and source.coop mirror
tiers moved to geo-agent-ops on 2026-07-31, and `license-inventory.md` went with them. Per the
current AGENTS.md Step 7, this repo **registers nothing**: the only obligation is an accurate SPDX
`license` plus a `{"rel": "license"}` link on the STAC collection, which is the advisory input the
mirror-scope auditor reads. Mirror scope is geo-agent-ops's call.

Carry `sci:doi` = `10.5066/P14HNEJF` (data release) and the *NeoBiota* method DOI
`10.3897/neobiota.96.134842` into `sci:citation`.

## Not taken

- **The 2026-02-11 integrated management summaries**
  ([10.5066/P14G2CHI](https://doi.org/10.5066/P14G2CHI), CC0-1.0, 344 species) are pre-summarized to
  118 433 administrative units across 30 management-area types — **none of which is the IRA
  boundary**, so they cannot be intersected with #584. Cite as the newest tabular product; do not
  build on it.
- **INHABIT Global V1** (`685ebd93d4be025490e9e6cf`,
  [10.5066/P13AJ46S](https://doi.org/10.5066/P13AJ46S)) could close the Alaska gap later —
  different grid, different models, not pixel-comparable with v4 CONUS.
- The other 247 v4 species. Extending is a follow-up issue, not a silent expansion of this one.

## Build order

1. `k8s/inhabit-v4/setup-bucket.yaml` — create `public-invasives`. **Done 2026-08-26.**
2. `k8s/inhabit-v4/stage-raw.yaml` — 12 indexed pods, 132 files, 26.0 GB → `raw/inhabit-v4-2024/`. **Done 2026-08-26: 12/12 in 23 min, 264 objects, 26.54 GB.**
3. Value census (bincount per source raster) → declared value sets for STAC. **Done 2026-08-26, 108/108.**
4. COG: warp to EPSG:4326, **`near` for the class rasters**, bilinear for the continuous.
   **Phase-1 subset DONE 2026-08-26 — 48/48 in 12 min.** (`k8s/inhabit-v4/cog.yaml`, hand-authored — see the
   resampling trap above). Output grid, identical for every layer: **57745 x 25711 @
   0.001096100359 deg**, origin (−128.386308874497, 51.268044444672). Two gates run per layer and
   both pass so far: the warped class set is exactly `{-1, 0, 1, 2, 3}` (nearest-neighbour held),
   and the grid matches the pinned constant. Independently re-verified across all 48 COGs afterwards
   (5 were built before the pinned check existed): **one distinct grid, 48/48**, with correct dtype
   (uint8 / int8), nodata (255 / −128) and overviews present on every layer.
5. Hex res 10 / parents 9,8,0, reducer per product class, **6** CONUS h0 indices.
   `k8s/inhabit-v4/hex.yaml` — 72 completions (12 species x 6 h0), each pod hexing that species'
   4 phase-1 products for one h0 so the COG localize amortizes 4x. **APPLIED 2026-08-27**, once
   the hex lock freed (`ira-road-proximity` 60/60 Complete, `landfire-2024-cog` 4/4 Complete, no
   Running or Pending pods in the namespace — confirmed with a listing that printed a header row,
   per the manifest's own warning).

   **Parallelism raised 12 → 24 after all 12 scheduled instantly.** 24 x 192Gi = 4.5 TiB against
   367 cluster nodes with ≥200Gi allocatable and 304 TiB total, i.e. ~1.5% of cluster memory and
   well under the 200-pod norm — the manifest's `parallelism: 12` was sized for a cluster that
   #588/#590 were still occupying. Halves the wall time to 3 waves.

   **Cost, measured rather than estimated.** The one pre-existing partition set
   (`bromus_tectorum` h0-index 20, written 2026-08-26 before the run was interrupted) gives the
   real per-product figures: **~1h27m per (species × product × h0)** and **215 525 636 rows /
   1.9 GB** for a single continuous product in one h0. So ~6 h per pod, ~12–18 h for the fan-out,
   and roughly 230 GB across the 48 phase-1 layers. That interrupted run had written 3 of its 4
   products; the re-run overwrites the same partitions, so it is idempotent, not additive.

   ⚠️ **That estimate was 2.3x optimistic — see the mid-run audit below.** The real figure across
   29 completed pods is a **14.1 h median**, not ~6 h. Idempotency, however, held exactly as
   claimed: no hex object in S3 predates the re-run's start.
6. STAC. `scripts/gen_stac.py` emits both files; `scripts/verify-stac.py --no-data` passes on both
   (0 findings). **Not yet published** — the data checks need the hex live, so publish and re-run
   the full gate after step 5 clears its coverage check.

**Hex queue: #610 yielded to #588 (`ira-road-proximity`) and #590 (`landfire-2024-hex`)** by the
user's instruction on 2026-08-26; both had cleared by 2026-08-27, which is when the hex was
applied. Steps 1–4 are staging/COG/metadata only and never took the hex lock.

## The `mode` reducer writes DOUBLE, not an integer — measured before it mattered

`cng-datasets raster --hex-resampling mode` emits its value column as **DOUBLE**, so the class
codes read back as `-1.0 .. 3.0`. The STAC initially declared `suitability_class` as `int64`.

This would only have surfaced at the end of the ~18 h hex fan-out, because the class raster is each
pod's *fourth* product. A res-5 probe job against an already-published `integrated-binary-fifth`
COG answered it in **50 seconds** instead:

    cng-datasets raster --input s3://…/bromus_tectorum/integrated-binary-fifth.tif \
      --output-parquet s3://public-invasives/_probe/mode-dtype/hex/ --h0-index 12 \
      --resolution 5 --parent-resolutions 0 --value-column suitability_class \
      --hex-resampling mode --nodata -128

    column_name        column_type
    suitability_class  DOUBLE          <- not int64
    h5                 UBIGINT
    h0                 BIGINT

Resolution 5 was deliberate: the question is the column *type*, which does not depend on
resolution, so the probe should be as cheap as possible. Output purged after reading.

**Resolution: declare `double` and say so in the column description.** Two independent
confirmations that this is right rather than a defect to fix:

- **Catalog precedent.** `ca-climate-zones-hex` (also a `mode` reduce) declares its `zone` column
  `float64` with an *integer* `values` array. Same shape.
- **`verify-stac.py` already anticipates it.** Its `values`-vs-`DISTINCT` gate carries the comment
  *"the cng-datasets raster `mode` reducer emits the value column as DOUBLE, so code 11 reads back
  as 11.0"* and normalises the trailing `.0` before comparing. So integer `values` are correct and
  the declared type is documentary.

The column description now states the codes are integers stored as double, so a consumer writes
`= 3` / `>= 1` and casts for an exact integer join rather than being surprised.

## First hex partition validated at 68 min, not at hour 18

`bromus_japonicus/occurrence-masked` h0-index 12 landed first (43 MB — h0=12 is the far-northern
border strip, against 1.9 GB for h0=20). Checked immediately rather than trusting the fan-out:

| check | result |
|---|---|
| rows / `COUNT(DISTINCT h10)` | 4 616 113 / 4 616 113 — **one row per cell**, no duplicates |
| `suitability` range | 0 – 90, none outside 0–100 |
| NULLs in `suitability`, `h9`, `h8` | 0 |
| distinct `h0` in the partition | 1 |
| declared vs actual types | `suitability` DOUBLE, `h10`/`h9`/`h8`/`h0` **all UBIGINT** — see the correction below |

**`min` is 0, so the `mean` reducer emits zero-suitability cells rather than dropping them.** Worth
recording because the one pre-existing partition (`bromus_tectorum` h0=20) has `min` 1, which looks
like zeros being filtered until you check a second partition. They are not; that partition simply
has no all-zero cell.

### ⚠️ Correction 2026-08-28 — `h0` is UBIGINT, and the res-5 probe was wrong about it

The row above originally read `h0 BIGINT`, carried over from the res-5 dtype probe's output
(line 556). Re-measured with **pyarrow against a landed phase-1 partition**, not duckdb's
rendering and not the probe:

    bromus_tectorum/integrated-binary-fifth/hex/h0=576812596024311807/data_0.parquet
      suitability_class  double
      h10 uint64   h9 uint64   h8 uint64   h0 uint64

So `h0` is `uint64` like the other three. `gen_stac.py` declared it `int64`; **fixed 2026-08-28.**

Why this had to be caught by hand: `verify-stac.py` HARD-checks the `values` array against the
ingested `DISTINCT`, but it does **not** compare a declared `table:columns` type against the data.
So a wrong type declaration passes every gate in the build. This is the same failure mode the
`suitability_class` DOUBLE finding hit, one column over — that one was caught only because the
probe happened to print the type. The probe printed `h0` too, and printed it wrong, because at
res 5 with `--parent-resolutions 0` the h0 column takes a different code path than it does as the
hive partition key of a res-10 write.

**Rule for the rest of this build: type declarations are measured against a landed partition, not
against a probe.**

## Mid-run audit 2026-08-28 — nothing broke, and the schedule is 2.3x over

Full health check at 29/72, ~21 h into the fan-out. Recorded because "the pods say Running" is not
evidence: a hung pod reports Running, and `rclone lsf` exits 0 on a path that does not exist.

**Job integrity.** 53 pods, 29 terminated, **all exit 0, zero restarts, zero abnormal events**,
`failedIndexes` empty. The job's `failed: 1` counter is a pod already garbage-collected; no index
has a duplicate pod, so nothing was lost.

**Idempotency held.** The claim in step 5 above was that the re-run overwrites the interrupted
2026-08-26 partitions rather than leaving stale ones beside them. Verified by timestamp: **no hex
object in the bucket predates 2026-08-27 22:40**, the run's own first write. `bromus_tectorum` —
the species that interrupted run touched — carries a complete, freshly written 6 x 4 = 24 files.

**Output shape.** 141 parquet objects, 70.5 GB, zero empty, every one named `data_0.parquet`. Every
incomplete (species x h0) maps to a pod still in flight, and its missing products are always the
*tail* of the manifest's `PRODUCTS` order — consistent with sequential writes, not dropped output.

**Data quality**, sampled on one class and one continuous partition:

| check | class | continuous |
|---|---|---|
| value set / range | exactly `{-1,0,1,2,3}`, all integral | 4 – 87.6, inside 0–100 |
| NoData leak (255 / −128) | none | none |
| NULLs, any column | 0 | 0 |
| rows vs `COUNT(DISTINCT h10)` | equal — no duplicate cells | equal |
| distinct `h0` in partition | 1 | 1 |

**COGs 108/108** — all 9 products x 12 species, none zero-byte.

**Three phase-2 COG pods (indices 0, 5, 8) had lost their logs to node rotation**, so their
class-set gate output was unreadable. The gate `sys.exit(1)`s under `set -euo pipefail`, so exit 0
already proved it passed — but the six COGs were read directly anyway rather than argued about:
grid `57745x25711 @ 0.001096100359`, `int8`, nodata −128, 7 overviews, class set a subset, 6/6.

**Published STAC** all resolves; root catalog 66 children with `public-invasives` registered;
`verify-stac.py` clean on both the live leaf and a fresh regeneration.

**The one defect found was a metadata one** — `h0` declared `int64` against `uint64` on disk. See
the correction above.

**The schedule, measured across the 29 completed pods:** median **14.1 h**, mean 13.8 h, range
4.1–20.4 h — against a ~6 h budget. Throughput ~1.7 pods/h at 24 slots, so phase 1 lands ~45 h
after start rather than 12–18 h. The original estimate came from a *single* partition set; the
spread here (5x fastest-to-slowest) is why one sample could not have priced it. **Cost estimates
for a fan-out need a distribution, not a sample.**

## Phase-2 COGs — the other 60 layers

`k8s/inhabit-v4/cog-phase2.yaml`, applied 2026-08-27, **concurrent with the hex fan-out**. Safe:
different product keys, reads `raw/` and writes keys phase 1 never touches, and 3 pods x 4cpu/16Gi
is noise beside the hex job's 24 x 192Gi. It does not take the hex lock.

Generated from `cog.yaml` so the two are structurally identical — the only non-comment differences
are the job name, the labels, and the product list (`occurrence`, `abundance`, `high-abundance`,
`integrated-binary-first`, `integrated-binary-tenth`). Both the grid assertion and the class-set
gate carry over unchanged; the value census confirms the class set is `{-1,0,1,2,3}` for all 36
class rasters (12 species x first/fifth/tenth), so `first` and `tenth` gate against the same
constant `fifth` did.

## Coverage gate — why `--expect-h0` alone is the wrong gate here

`scripts/check-hex-coverage.sh` gates one hex prefix. There are up to 108 here, which is exactly
where a silently-partial build (#409) gets missed, so `scripts/check-coverage.sh` wraps it across
every layer.

The subtlety is what to expect. **Demanding all six CONUS h0 partitions for every layer would cry
wolf.** The continuous products use `mean`, which writes a partition only where valid source pixels
exist, so a species legitimately has no partition in an h0 it does not reach — buffelgrass is a
southwest species whose masked product retains 34% of CONUS, so an absent h0=78 (Northeast) is
correct data, not a dead pod. A gate that fires on every range-limited species trains the reader to
ignore it.

So each species is gated against **its own class raster**: the `integrated-binary-*` products carry
a class across all of CONUS (0 unsuitable, or -1 extrapolation), so their h0 set is the maximal
extent for that species and grid. The class raster itself is gated against the six CONUS h0 cells.
A continuous product missing an h0 its own class raster has is reported as a GAP to check against
that species' MESS retention, not asserted as a failure.

**This is the second of two defenses and does not replace the first.** It cannot distinguish "no
data for this species here" from "this pod died", so the Job check comes first: Complete with an
empty `failedIndexes`. A build is done only when both are clean.

## Phase-2 hex — written, NOT applied

`k8s/inhabit-v4/hex-phase2.yaml`. Same 72 completions (12 species x 6 h0), 5 products per pod
instead of 4, same reducer split (`mean` on the 0-100 index, `mode` on the class codes — `first`
and `tenth` have the identical value domain to `fifth`, so identical treatment).

⛔ **Apply only once `inhabit-v4-hex` reports Complete 72/72.** One res-10 fan-out at a time: each
holds 24 x 192Gi, and two concurrently is antisocial on shared nodes even though `geo-workflows`
enforces no quota.

**Budget, re-priced 2026-08-28 against phase 1's *observed* rate rather than its single-partition
extrapolation.** The original figure here (~7.25 h per pod, ~22 h) scaled the ~6 h/pod estimate by
5/4 products. Phase 1's actual median is **14.1 h per pod**, so the same 5/4 scaling gives
**~17.6 h per pod, 3 waves, ~53 h** — not 22 h. Phase 2 is the `first`/`tenth` sensitivity band
plus the unmasked continuous set; none of it is the canonical layer, and none of it is on the
critical path for the IRA tabulation, which reads `-masked` + `fifth`. **Decide whether to spend
~53 h of 24 x 192Gi on it before applying** — that is a scheduling call for the user, not a
default.

## STAC

`scripts/gen_stac.py` writes both documents to /tmp; nothing STAC-shaped is committed to this repo
(AGENTS.md Hard Boundary 1). Publish with:

    python3 catalog/invasives/scripts/gen_stac.py
    rclone copyto /tmp/invasives-bucket-stac.json nrp:public-invasives/stac-collection.json
    rclone copyto /tmp/inhabit-v4-2024-stac.json  nrp:public-invasives/inhabit-v4-2024/stac-collection.json
    rclone copyto /tmp/invasives-README.md        nrp:public-invasives/README.md
    scripts/verify-stac.py --bucket public-invasives --dataset inhabit-v4-2024

Shape: a bucket-level meta-collection `public-invasives` (one `child`) over the leaf collection
`inhabit-v4-2024`, which carries one COG and one hex asset per (species × product), keyed
`<species>-<product>-{cog,hex}` — **216 assets at full extent** (12 species x 9 products x 2), or
96 for phase 1 alone. `MEASURED` covers all 108 layers, so no re-measurement is needed for phase 2. Two levels rather than one because `public-invasives` is a domain
bucket that will plausibly hold INHABIT Global V1 and the other 247 v4 species later; collapsing
the collection onto the bucket root would have to be undone then.

**Two env gates gate a truthful interim publish**, so the collection never advertises an asset
that 404s:

- `PHASE` — which products have a built COG. `1` the four phase-1 products, `2` the five phase-2
  products, `all` (default) all nine.
- `READY_LAYERS` — which of those have a landed hex. `NONE` for none, a comma-separated list of
  `<species>|<product>` keys for some, unset for all (use only once the fan-out is 72/72 and the
  h0 coverage gate has passed).

COG assets always emit for the selected phase, since they are built and grid-verified. This is how the collection gets published truthfully while the fan-out is still
running, instead of advertising 48 hex assets that partly 404. The description gains a bracketed
interim note automatically.

### Published 2026-08-27 — COG-only interim, and the bucket is registered

    READY_LAYERS=NONE python3 catalog/invasives/scripts/gen_stac.py   # 48 assets, 48 COG, 0 hex
    python3 catalog/invasives/scripts/gen_readme.py

- `s3://public-invasives/stac-collection.json` — bucket meta-collection (1740 B)
- `s3://public-invasives/inhabit-v4-2024/stac-collection.json` — leaf, 48 COG assets (147 949 B)
- `s3://public-invasives/README.md` (14 718 B)
- `s3://public-data/stac/catalog.json` — **`public-invasives` added as a new top-level
  sub-catalog**, 65 → 66 children. This is the one case AGENTS.md Step 6 sanctions touching the
  root. The edit was diffed against a saved copy of the pre-edit catalog before upload and is
  exactly one inserted `child` link, nothing else.

`scripts/verify-stac.py` passes with **0 findings on all three** — the leaf, the bucket
meta-collection, and the whole-bucket sweep — against the live S3 documents, not just the /tmp
files. The data-backed checks run clean at this stage because there are no hex assets yet to check;
**re-run the leaf gate after the fan-out completes**, when `values`-vs-`DISTINCT` on
`suitability_class` becomes a real test rather than a no-op.

Two things the post-hex gate must confirm that the COG-only pass cannot:

1. The hexed `suitability_class` set is exactly `{-1, 0, 1, 2, 3}` — a `mode` reduce cannot invent
   a code, but the declared `values` array is HARD-checked against the ingested `DISTINCT`, so a
   surprise there means something upstream moved.
2. The declared `table:columns` type for `suitability_class` (`int64`) matches what `mode` actually
   wrote. If cng-datasets emits it as a double, the declaration is wrong and must follow the data —
   see `scripts/check-hex-encoding.sh`.

**One canonical text per column name, deliberately.** `suitability` appears on 36 hex assets and
`suitability_class` on 12, and mcp-data-server#303 folds per-column descriptions to the first-seen
text per column name across a collection — so a per-species or per-product wording would be
silently dropped for 35 of 36 assets, and `verify-stac.py` HARD-fails the divergence. Everything
species-specific or product-specific therefore lives in the per-asset `description`, which is
always rendered: the model group, the measured masked-retention percentage, the class pixel counts
and that species' gHM road-bias verdict.

### What each asset carries that a reader could not otherwise get

- Measured per-layer value range and data-pixel fraction, from the census — not the FGDC `rdommax`,
  which is a per-file figure (98) and understates the family scale (0–100).
- The five class labels with `classification:classes` and `color_hint` (ColorBrewer YlOrRd for
  ranks 1–3, near-white for unsuitable, desaturated purple for the extrapolation flag so it can
  never read as "more suitable"). The source ships no palette; the choice is stated in the asset
  description as AGENTS.md requires.
- The exclusive-vs-nested rank warning, so `suitability_class = 1` is not mistaken for all
  occurrence-suitable ground.
- The `mode`-discards-the-mix caveat on every `integrated-binary-*` hex asset.
- That species' gHM figure and the resulting road-gradient verdict, so the circularity travels with
  the data rather than living only in this file.
