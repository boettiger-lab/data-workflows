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

At resolution 10 an h0 index that holds no data is **not** free: the tool prunes only h0 cells whose
envelope misses the raster, and every surviving cell enumerates all ~280 M of its resolution 10
children before finding them all nodata. Running the generated 122 per year would be 4,758 pod slots
at 192Gi per layer to do 234 cells' worth of work.

The restricted sets are data-derived, from `s3://public-grids/hex/h0-valid.parquet` (the same grid
`cng-datasets` indexes with):

| Domain | h0 indexes | Cells |
|---|---|---|
| CONUS | 12, 14, 20, 50, 71, 78 | 576812596024311807, 577692205326532607, 577164439745200127, 577199624117288959, 577762574070710271, 577234808489377791 |
| Alaska | 12, 59, 105 | 576812596024311807, 576988517884755967, 576707042908045311 |

Two independent cross-checks:

1. These are the **populated** sets measured on `whp-2023-classified-{conus,ak}` in this same
   bucket. WHP covers every land pixel of its domain (it carries explicit non-burnable and water
   classes), so its populated set is a strict superset of any MTBS burn footprint in that domain.
2. Reconciled against the measured h0 set of `mtbs-perimeters-1984-2024`, which marks exactly where
   MTBS fires are — see *Reconciliation* below.

A bbox intersection alone is **not** the right test and would have over-selected: 12 h0 cells clip
the CONUS bounding rectangle and 7 clip the Alaska one, but the extra ones meet the rectangle only
over ocean, Canada or Mexico. `check-hex-coverage.sh` then verifies per year that every expected
partition is populated, so a wrong list fails loudly instead of shipping a hole.

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

_Filled from the completed builds; every number here is read back off the published artifacts._

### Reconciliation of the severity h0 sets against the perimeters build

_Pending the perimeters hex._

### `mtbs-perimeters-1984-2024`

_Pending._

### `mtbs-severity-1984-2024-conus` / `-ak`

_Pending._

## Post-build verification

```bash
# h0 coverage gate, per domain per year; mode (sparse) against fractions (same COG) is the
# right pairing -- and it communicates through its exit code, so read ${PIPESTATUS[0]} if piped.
for Y in $(seq 1984 2024); do
  scripts/check-hex-coverage.sh nrp:public-fire/mtbs-severity-1984-2024-conus/hex/year=$Y/ \
    --reference nrp:public-fire/mtbs-severity-1984-2024-conus/hex-fractions/year=$Y/
done

# STAC, static then data-backed
python3 scripts/verify-stac.py --no-data /tmp/mtbs-perimeters-1984-2024-stac.json
python3 scripts/verify-stac.py --bucket public-fire
```

⚠️ Do **not** gate a per-domain severity build against a national layer such as
`roadless-areas-2001/hex/` as `--reference` — a national reference is a guaranteed false FAIL.

### Acceptance criteria

| # | Criterion | Status |
|---|---|---|
| 1 | Severity `mode` majority agrees with the COG majority on a sample; values within the valid code set | _pending_ |
| 2 | Classes 5/6 documented and excludable from severity denominators | ✅ `classification:classes` + `values` + the denominator SQL in both severity collections |
| 3 | Burned share and high-severity share for IRA vs roaded NFS vs wilderness | ⚠️ partly blocked — see below |
| 4 | Reburn handling documented; unique-ground and fire-years both reportable | ✅ both queries in the collection descriptions and the bucket README |
| 5 | MTBS size threshold (incomplete census) stated in the collection description | ✅ all three collections |
| 6 | `mode` is sparse — h0 partition gate with `--min-bytes` filtering | _pending_ |
| 7 | `verify-stac.py` clean | _pending the live data_ |

**Criterion 3 is only partly deliverable, and inventing the missing denominators would be worse
than saying so.** `roadless-areas-2001` (#584) exists, so IRA-versus-domain is computable now.
"Roaded NFS" needs the NFS surface-ownership layer from #585, which is **not started** — without it
there is no way to separate roaded National Forest System land from everything else. "Wilderness"
has no issue in the `roadless` set at all and needs one filed. This build delivers the IRA
comparison and records the blocker rather than substituting a denominator that would not mean what
the criterion says.

## Notes for the downstream issues

- **#587 (FPA-FOD) owns ignition counts.** MTBS is not a census; anything about how *often* fires
  start has to come from there, not from a `COUNT(*)` here.
- **A "total acres burned" figure from this data is ambiguous until it says which quantity it
  means.** Unique ground and fire-years differ substantially in the West over 41 years, and the
  reburn record is the interesting part rather than noise to be deduplicated away.
- **Any severity time series has six holes** (CONUS 2004 and 2017, Alaska 1987, 1995, 2001, 2013).
  A trend line drawn straight through them understates those years as zero.
