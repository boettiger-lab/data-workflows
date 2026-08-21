# `whp-2023` — build notes and measured evidence

Wildfire Hazard Potential v2023 (270 m), ingested for #586 as part of the `roadless` dataset
set (#594). The claim under audit is the 2026-08-18 announcement's ">40% of roadless acres are
at high or very high wildfire risk", whose agency basis is DEIS Vol I Table 22.

## Source

| | |
|---|---|
| Citation | Dillon, G.K. 2023. *Wildfire Hazard Potential for the United States (270-m), version 2023.* 4th Edition. Fort Collins, CO: Forest Service Research Data Archive. |
| Archive id | **RDS-2015-0047-4** (`https://doi.org/10.2737/RDS-2015-0047-4`) |
| Package | `RDS-2015-0047-4_Data.zip` |
| License | US Government work — public domain |
| Staged raw | `s3://public-fire/raw/whp-2023/` |

Confirmed against #589/#602: this is the edition the DEIS used, classes counted are **high +
very high**, the denominator is **total** acres (not forested), and non-burnable pixels are
**not** excluded.

## Why four collections and not one

The source ships three domains — CONUS, Alaska, Hawaii — and **classifies each against its own
distribution of the continuous index.** The breaks are not the same numbers:

| Class | CONUS | Alaska |
|---|---|---|
| 1 Very Low | ≤ 61 | ≤ 83 |
| 2 Low | 62–178 | 84–624 |
| 3 Moderate | 179–489 | 625–2,922 |
| 4 High | 490–1,985 | 2,923–8,912 |
| 5 Very High | > 1,985 | > 8,912 |

An Alaska "Very High" is a WHP index above 8,912; a CONUS "Very High" is above 1,985 — **4.5×
apart.** A single mosaicked classified layer would silently invite a pooled `GROUP BY class`
across two incompatible scales, which is precisely the arithmetic that yields a wrong headline
number. Publishing the domains separately makes that mistake impossible to make by accident,
and every collection carries `h8`, so they still join to each other and to
`roadless-areas-2001` cell for cell.

Hawaii is skipped — it holds no inventoried roadless areas — but its raw rasters are staged.

| `--dataset` | Native | Parents | Reducer | Column |
|---|---|---|---|---|
| `whp-2023-classified-conus` | 9 | 8, 0 | `mode` | `whp_class` |
| `whp-2023-classified-ak` | 9 | 8, 0 | `mode` | `whp_class` |
| `whp-2023-continuous-conus` | 8 | 0 | `mean` | `whp_index` |
| `whp-2023-continuous-ak` | 8 | 0 | `mean` | `whp_index` |

### Resolution split, by product

Measured pixels per H3 cell after reprojection:

| | CONUS | Alaska |
|---|---:|---:|
| res 9 (0.1053 km² cell) | ~1.3 px/cell | ~1.9 px/cell |
| res 8 (0.7373 km² cell) | ~9 px/cell | ~13 px/cell |

`mode` at ~9 px/cell is winner-take-all: a cell that is 4/9 Very High and 5/9 Moderate becomes
entirely Moderate, biasing the class-*share* statistic that is this issue's whole deliverable.
So the classified products take res 9 even though that mildly oversamples the source. An
area-weighted `mean`, by contrast, *wants* several pixels per cell, so the continuous products
take res 8. The oversampling is a documentation obligation, discharged in the STAC: each
collection states its effective source pixel (~250 m × 324 m at 40°N; ~169 m × 337 m at 60°N).

### Official class labels — transcribed, not remembered (#294)

Read from the source value attribute tables (`whp2023_cls_{conus,ak}.tif.vat.dbf`, column
`class_desc`):

`1: Very Low` · `2: Low` · `3: Moderate` · `4: High` · `5: Very High` · `6: Non-burnable` ·
`7: Water`

**The source ships no color table** — neither the classified GeoTIFFs nor the file geodatabase
carry one — so the STAC asserts no palette. `classification:classes` carries value and
description only.

## The COG step is mandatory, and its absence fails silently

`cng-datasets raster` documents its input as an already-COG'd WGS84 raster, and the
`raster-hexing` skill says to build the WGS84 COG first. Pointing it at the raw Albers GeoTIFF
instead **wrote zero rows and exited 0**: EPSG:5070 `(0,0)` is lon −96 / lat 23, so
degree-valued H3 cell polygons land ~100 m from the projection origin — in the Gulf of Mexico —
and every cell reads nodata. The Job reported `Complete`.

**Only the h0 coverage gate catches this.** Structural checks all pass on an empty build.

`make-cogs.yaml` therefore runs first: four indexed pods, `gdalwarp -t_srs EPSG:4326 -r near`
(nearest for *both* products — the classified one is categorical, so anything else invents
classes), then `gdal_translate -of COG`, with a hard gate that fails rather than publishing an
all-nodata COG.

Alaska is clipped to `-te -180 48.8 -129.0 71.6`, dropping the far-western Aleutians
(~157°E–180°) where the source grid wraps the antimeridian. No National Forest System land lies
there — the Alaska units are the Tongass and Chugach, far east — so nothing relevant is lost.

## Area truth comes from the source grid, not the COG

The source Albers grid is equal-area; the reprojected COG is geographic and therefore is not.
Counting COG pixels is not an area measurement. H3 cells at a fixed resolution are
near-equal-area, so hex cell counts *are* a valid area proxy — and they reproduce the source's
equal-area class shares closely (table below). All validation runs against the source pixel
counts.

## Build results

### `whp-2023-classified-*` (2026-08-20)

| | CONUS | Alaska |
|---|---:|---:|
| Rows | 74,428,571 | 16,540,214 |
| Rows == `COUNT(DISTINCT h9)` | ✅ exact | ✅ exact |
| Populated h0 partitions | 6 | 3 |
| nodata (255) leak | 0 | 0 |
| Value range | 1–7 | 1–7 |
| Measured footprint | −124.864, 24.467, −66.940, 49.387 | −173.190, 54.653, −129.988, 71.370 |

#### Class shares vs the equal-area source — the real accuracy check

Source percentages are computed from the value attribute table's pixel counts on the **Albers**
grid (equal-area, so this is area truth): CONUS total 110,817,217 px, Alaska 22,337,483 px.
Hex percentages are cell shares.

| Class | CONUS source | CONUS hex | Δ pp | AK source | AK hex | Δ pp |
|---|---:|---:|---:|---:|---:|---:|
| 1 Very Low | 29.53 | 29.18 | −0.35 | 39.64 | 39.58 | −0.06 |
| 2 Low | 17.42 | 17.27 | −0.15 | 17.70 | 17.11 | −0.59 |
| 3 Moderate | 13.93 | 14.04 | +0.11 | 10.20 | 10.26 | +0.06 |
| 4 High | 8.89 | 9.18 | +0.29 | 6.07 | 6.01 | −0.06 |
| 5 Very High | 3.26 | 3.29 | +0.03 | 2.74 | 2.68 | −0.06 |
| 6 Non-burnable | 21.55 | 21.61 | +0.06 | 10.99 | 11.38 | +0.39 |
| 7 Water | 5.42 | 5.43 | +0.01 | 12.67 | 12.98 | +0.31 |
| **→ 4 + 5** | **12.15** | **12.47** | **+0.32** | **8.80** | **8.69** | **−0.11** |

Every class lands within 0.6 pp of the equal-area source, and the headline class 4+5 share
within ±0.32 pp. The residual is two-stage resampling drift (Albers → geographic nearest, then
`mode` into H3), not error — but it is **not zero**, so a published figure derived from the hex
should be quoted to no better than a tenth of a percentage point, and anything requiring exact
agreement with the agency should be computed from the source Albers grid.

### 🔴 The Alaska question, settled — and it is not what it first looked like

The published `WHP2023_ManagementJurisdiction_Summary.xlsx` compares its `CONUS` and
`all_50_states` sheets for US Forest Service land:

| | CONUS sheet | all_50_states | Δ |
|---|---:|---:|---:|
| Very High WHP | 26,023,000 | 26,023,000 | **0** |
| High WHP | 40,917,000 | 40,917,000 | **0** |
| **High + Very High** | **66,940,000** | **66,940,000** | **0** |
| Total acres | 170,691,000 | 192,282,000 | +21,591,000 |

**Alaska and Hawaii add 21.6M acres of USFS land and exactly zero acres of High or Very High
WHP.** Per-state confirms it: Alaska USFS = 21,591,094 acres, **0** high+very-high. That is
physically sensible — USFS land in Alaska is Tongass and Chugach coastal temperate rainforest,
which sits at the bottom of the *Alaska* hazard distribution, while interior boreal Alaska
(BLM, State) takes the high classes.

So DEIS Table 22 is **internally consistent**: its numerator is identical in the "Total" and
"Total excluding AK" rows precisely because Alaska contributes zero. The defensible criticism is
narrower than "the agency ignored available data": labelling the Alaska cell **"Not Available"**
rather than **"0"** obscures that Alaska's ~12.2M IRA acres are pure denominator, and that
dropping them is exactly what lifts 28.7% to 41.8%. The data existed; the entry was mislabelled.

Validation targets for anyone building on this, from the same supplement:

| Unit | High+VeryHigh | Total | Share |
|---|---:|---:|---:|
| USFS, CONUS | 66,940,000 | 170,691,000 | **39.2%** |
| USFS, all 50 states | 66,940,000 | 192,282,000 | **34.8%** |

The 192,282,000 also independently corroborates the "193-million-acre National Forest System"
figure in the press release. And for #585, free: **Montana USFS = 17,174,998 acres**; with
#584's Montana IRA of 6,395,401 that is **37.2%**, not the "nearly 60 percent" of the release —
a third independent source agreeing with #594's conclusion that the Montana line is a
governor's quote, not an agency figure.

## Pipeline

Run in `geo-workflows`, one hex Job at a time (`AGENTS.md`: never more than one concurrent k8s
hex workflow — 40 parallelism each would be 160 pods if all four ran together).

```bash
# 1. stage the source package to s3://public-fire/raw/whp-2023/
kubectl apply -n geo-workflows -f whp-2023-stage-raw.yaml

# 2. build the four WGS84 COGs (MANDATORY — see above)
kubectl apply -n geo-workflows -f make-cogs.yaml

# 3. hex, sequentially, waiting for Complete between each
for d in classified-conus classified-ak continuous-conus continuous-ak; do
  kubectl apply -n geo-workflows -f "$d/whp-2023-$d-hex.yaml"
done

# 4. STAC — four dataset collections + the patched bucket collection
python3 gen_stac.py
```

Job hardening on all four, replacing the generated `backoffLimit: 0`:
`backoffLimitPerIndex: 2` + `maxFailedIndexes: 0`, so a partial indexed run **fails** rather
than publishing as complete. `priorityClassName` is omitted — `opportunistic` gets preempted
here within ~20 s. The classified pair needs **120Gi** (a 64Gi attempt OOMed on the densest
CONUS cell); the continuous pair runs at 64Gi, since res 8 is ~7× fewer cells.

`setup-bucket` is **not** run: `public-fire` already exists, already serves anonymously, and
already holds `calfire-2024`/`calfire-2025`/`usgs-fires-2021`. Nothing about a new dataset
changes bucket-level access. There is also no root-catalog or MinIO-backup registration step —
that tier was retired from this repo in #568; the only obligation is a correct SPDX `license`,
which is `public-domain` with a license link.

## Post-build verification

```bash
# h0 coverage gate — per domain, NOT against a national reference
scripts/check-hex-coverage.sh nrp:public-fire/whp-2023-continuous-conus/hex/ \
  --expect-h0 576812596024311807,577164439745200127,577199624117288959,577234808489377791,577692205326532607,577762574070710271
scripts/check-hex-coverage.sh nrp:public-fire/whp-2023-continuous-ak/hex/ \
  --expect-h0 576707042908045311,576988517884755967,576812596024311807

# STAC, with data checks
python3 scripts/verify-stac.py --bucket public-fire
```

⚠️ **Do not gate these against `roadless-areas-2001/hex/` as a `--reference`.** That layer is
national; each WHP collection is one domain, so a national reference is a guaranteed false FAIL.
The two classified domains *together* populate 8 of that layer's 9 h0 partitions — the ninth,
`577832942814887935`, is **Puerto Rico** (El Yunque, 8,897 res-10 IRA cells), which WHP
CONUS+AK does not cover at all.

Also note `check-hex-coverage.sh` communicates through its exit code; if you pipe its output,
read `${PIPESTATUS[0]}` rather than `$?`.

### `whp-2023-continuous-*` (2026-08-21)

Both jobs `Complete=True`, 122/122, `failedIndexes: []`, no OOM at 64Gi.

| | CONUS | Alaska |
|---|---:|---:|
| Rows | 10,641,399 | 2,369,388 |
| Rows == `COUNT(DISTINCT h8)` | ✅ exact, 0 duplicates | ✅ exact, 0 duplicates |
| Populated h0 partitions | 6 (gate PASS) | 3 (gate PASS) |
| NULL `whp_index` | 0 | 0 |
| nodata (2147483647) leak | 0 | 0 |
| Index range | 0 – 93,924 | 0 – 48,140 |
| Mean index | 432.72 | 939.61 |
| Measured footprint | −124.868, 24.467, −66.940, 49.387 | −173.188, 54.654, −129.984, 71.371 |

The Alaska mean index being ~2.2× the CONUS mean is consistent rather than suspicious: the
Alaska class breaks sit far higher (Very High starts at 8,912 vs 1,985), so the same index scale
runs hotter there. This is the same fact that makes the classified products non-comparable across
domains, visible from the other side.

### Cross-product agreement — the check worth trusting most

The classified and continuous layers are built independently from different source rasters. Joined
on `h8` within one h0 partition (`577199624117288959`, California + interior West), the mean
continuous index per classified class is strictly monotonic across the hazard classes, and the two
non-fuel classes sit low where they should:

| Classified class | Break range (CONUS) | Mean continuous index |
|---|---|---:|
| 1 Very Low | ≤ 61 | 58 |
| 2 Low | 62–178 | 196.7 |
| 3 Moderate | 179–489 | 446.7 |
| 4 High | 490–1,985 | 1,222.4 |
| 5 Very High | > 1,985 | 7,641.1 |
| 6 Non-burnable | — | 150.8 |
| 7 Water | — | 59 |

Class 2's mean sitting just above its own 178 ceiling is expected from the join geometry, not a
defect: a res-9 classified cell is matched to the res-8 continuous cell containing it, and that
coarser cell also spans higher-class neighbours. Classes 3, 4 and 5 all land inside their ranges.

## Published

| Collection | Assets |
|---|---|
| `whp-2023-classified-conus` | COG + hex (res 9, parents 8/0) |
| `whp-2023-classified-ak` | COG + hex (res 9, parents 8/0) |
| `whp-2023-continuous-conus` | COG + hex (res 8, parent 0) |
| `whp-2023-continuous-ak` | COG + hex (res 8, parent 0) |

`verify-stac.py` PASS with data checks on all four dataset collections and on the patched bucket
collection (0 hard findings; the bucket's 18 advisories are all pre-existing on the CAL FIRE and
USGS assets and were not introduced here).

### Bucket-level changes, and why they were necessary

Adding a modelled hazard raster to `public-fire` made three published statements false, so the
bucket collection and README were **patched** (fetched, edited, re-uploaded — not regenerated, so
unmodelled fields survive; all 15 pre-existing assets verified preserved):

1. **`title`** — "Fire Perimeters: CAL FIRE (2024, 2025) and USGS Combined (2021)" → "Wildfire:
   hazard potential and fire perimeters". WHP is not a perimeter dataset.
2. **`license`: `CC-BY-4.0` → `various`**, and the bucket-level CC-BY license *link* dropped. The
   perimeter children are CC-BY-4.0; the Forest Service hazard products are public domain. No
   single bucket term is honest, and leaving the CC-BY link in place would assert CC-BY over
   public-domain children. A meta-collection with `child` links may use `various` with no license
   link — the real licenses live on and are gated per child (stac-authoring SKILL.md;
   `verify-stac.py check_license`).
3. **README intro** — it claimed the bucket holds fire *perimeter* datasets and that *all*
   datasets are polygon geometries. Both rewritten; per-dataset sections untouched.

**`id` was deliberately left as `fire-perimeters`.** It no longer describes the bucket well, but it
is consumer-visible and renaming it is out of scope for #586. Worth a follow-up issue.

Backups of both pre-patch files were taken before upload.

## Notes for the downstream issues

- **The `>40%` claim needs the Alaska caveat to be reproduced honestly.** 11,479,564 acres of high
  or very high WHP is 41.8% of the potentially affected environment **excluding** Alaska and 28.7%
  **including** it. Both figures are correct; only the first supports ">40%". Publish both.
- **The denominator is ~40.0M acres, not 44.7M** (#589/#602). Four bases are now in play —
  58.4M all-IRA / 44.7M rule-affected / 44.3M on NFS / 40.0M potentially affected. Every
  tabulation must name which it uses.
- **Use the continuous collections for any CONUS-vs-Alaska comparison.** The classified breaks are
  domain-relative and cannot be pooled.
- **#590 (LANDFIRE)** should know the DEIS's forest-area figures disagree with each other: the
  "16 percent of forested areas" claim implies ~30.0M forested acres, while the DEIS publishes
  20.9M (NLCD), ~21M (narrative) and 25.5M (FIA type groups).
