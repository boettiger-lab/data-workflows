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

### ⚠️ `-1` is a VALID class, not fill

The FGDC domain for `integrated-binary-*` is `rdommin` **−1** to `rdommax` 3, and −1 occupies
**25.2%** of the *Cenchrus ciliaris* `integrated-binary-fifth` raster — 342 322 727 px, third
largest bin after NoData and class 0. A sign test ("negatives are fill") would delete it. The
FGDC gives no `edomvd` label for the codes, so the semantics of −1 must be read out of Jarnevich et
al. 2024 before the collection description names the classes. **Open item — do not describe the
class set until this is resolved.**

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
normalised to the per-species total. **A per-model-type breakdown (occurrence-only) is still owed**
before the road gradient is reported — the gradient leans on the occurrence models specifically.

Consequence for #588's distance-to-road gradient: **cheatgrass is the cleanest of the 12 (1.2%) and
the gradient is defensible there; tamarisk is the second-most gHM-dependent (16.4%) and its
gradient is substantially the model reproducing its own predictor.** Report tamarisk, Russian
olive, jointed goatgrass and buffelgrass as suitability-only, with the circularity stated.

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
   **Phase-1 subset running 2026-08-26** (`k8s/inhabit-v4/cog.yaml`, hand-authored — see the
   resampling trap above). Output grid, identical for every layer: **57745 x 25711 @
   0.001096100359 deg**, origin (−128.386308874497, 51.268044444672). Two gates run per layer and
   both pass so far: the warped class set is exactly `{-1, 0, 1, 2, 3}` (nearest-neighbour held),
   and the grid matches the pinned constant.
5. Hex res 10 / parents 9,8,0, reducer per product class, 4 CONUS h0 indices.
6. STAC collection `inhabit-v4-2024`, one item per (species × product); `scripts/verify-stac.py`.

**Hex queue: #610 yields to #588 (`ira-road-proximity`) and #590 (`landfire-2024-hex`)** by the
user's instruction on 2026-08-26. Steps 1–4 are staging/COG/metadata only and do not take the hex
lock.
