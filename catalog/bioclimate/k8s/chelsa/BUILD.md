# CHELSA v2.1 future bioclimate — build notes

Evidence for the CHELSA CMIP6 future ingest (data-workflows #564). Everything below is
**measured** from the source rasters on the cluster, not taken from upstream documentation.
Record measurements here so the next reader inherits evidence rather than assumption.

## Source

```
https://os.zhdk.cloud.switch.ch/chelsav2/GLOBAL/climatologies/{period}/{GCM}/{ssp}/bio/CHELSA_bio{N}_{period}_{gcm-lowercase}_{ssp}_V.2.1.tif
```

322 files verified HTTP 200 (7 variables x 5 GCMs x 3 SSPs x 3 periods, plus 7 baseline),
92.5 GB total, staged to `s3://public-bioclimate/raw/chelsa-2-1/`.

- **GCMs (5, ISIMIP3b):** GFDL-ESM4, IPSL-CM6A-LR, MPI-ESM1-2-HR, MRI-ESM2-0, UKESM1-0-LL
- **SSPs (3):** ssp126, ssp370, ssp585
- **Periods (3):** 2011-2040, 2041-2070, 2071-2100
- **License:** CC0-1.0

## Grid

| | |
|---|---|
| Size | 43200 x 20880, EPSG:4326 |
| Pixel | 0.008333333 deg (30 arc-sec, ~0.93 km) |
| Footprint | **84N to 90S** — excludes 84-90N |
| Type | UInt16, DEFLATE/PREDICTOR=2, block 43200x1 (stripped, not tiled) |
| Valid | `STATISTICS_VALID_PERCENT = 99.999` on every variable |

**CHELSA is a full-globe surface including ocean**, not a land product. Ocean probes return
plausible values, not fill (bio1 Pacific 26.7 C, Atlantic 22.25 C, Southern Ocean -1.45 C,
Antarctica -42.85 C; bio12 Pacific 985 mm, Atlantic 724 mm). The build therefore applies a land
mask; without one a global res-8 hex is ~670 M rows per raster instead of ~195 M.

## Per-variable metadata — MEASURED, and inconsistent across variables

Measured with `gdalinfo -stats` on the 2041-2070 / GFDL-ESM4 / ssp370 member:

| var | quantity | NoData | Scale | Offset | raw min | raw max | physical range | units |
|---|---|---:|---:|---:|---:|---:|---|---|
| bio1 | annual mean temperature | **0** | 0.1 | -273.15 | 2216 | 3096 | -51.55 .. 36.45 | degC |
| bio4 | temperature seasonality | **0** | 0.1 | 0 | 28 | 23048 | 2.8 .. 2304.8 | degC x 100 |
| bio5 | max temp of warmest month | **0** | 0.1 | -273.15 | 2413 | 3235 | -31.85 .. 50.35 | degC |
| bio6 | min temp of coldest month | **0** | 0.1 | -273.15 | 2091 | 3011 | -64.05 .. 27.95 | degC |
| bio12 | annual precipitation | **0** | 0.1 | 0 | 4 | **65535** | 0.4 .. **6553.5** | mm |
| bio15 | precipitation seasonality | **65535** | 0.1 | 0 | 0 | 2660 | 0 .. 266 | % (CV) |
| bio17 | precipitation of driest quarter | **65535** | 0.1 | 0 | 0 | 42195 | 0 .. 4219.5 | mm |

### ⛔ Two traps in this table

1. **NoData is not constant across the product.** bio1/bio4/bio5/bio6/bio12 use `0`;
   **bio15 and bio17 use `65535`**. A single batch-wide `--nodata` would corrupt some
   variables. The build reads the sentinel from each file at runtime
   (`chelsa_read_meta.py`) rather than carrying this table into code.

2. **`65535` means opposite things in different variables.** In bio15 and bio17 it is the
   declared NoData. In **bio12 it is real data**: bio12's NoData is `0`, and its maximum is
   exactly `65535`, the UInt16 ceiling — 6553.5 mm, below the world record of ~11 900 mm, so
   the encoding **clips** rather than measures in the wettest places. Those cells are a lower
   bound, not a measurement, and must be documented as such rather than averaged silently.

## Units are applied by the tool, not by us

`cng-datasets raster` hands the raster **path** to `exactextract`, whose GDAL source applies the
band scale/offset — so **hex values arrive already in physical units**. Grepping
`cng_datasets/raster/cog.py` for `GetScale` finds nothing and is misleading; the conversion
happens a layer down.

Verified: one member hexed at res 5 over the Amazon h0 returns `min=1.51 max=30.15 mean=27.32`
degC. Applying the transform a second time produced `-273.5 .. -269.9`.

**A double-scaled column passes every structural check** — row counts, mask retention, NULL
counts and `median BETWEEN min AND max` all stay consistent, because a linear transform applied
twice preserves ordering and cardinality. Only a physical plausibility bound catches it.

Note the contrast: `chelsa_ensemble.py` reads via `gdal.Band.ReadAsArray`, which does **not**
apply scale/offset, so its explicit transform is correct. The two scripts differ legitimately.

## Resolution

Native **h8**, parents **5, 4, 0**. h8 is a measured match to the ~0.93 km pixel, not a
convention: pixel area is 0.861 km2 at the equator and 0.745 km2 at 30 deg latitude against an
h8 cell of 0.7373 km2 — a **0.99:1** correspondence at mid-latitude.

| lat | pixel area | pixels per cell @ h8 | pixels per cell @ h7 | cells per pixel @ h9 |
|---:|---:|---:|---:|---:|
| 0 | 0.861 km2 | 0.86 | 6.00 | 8.17 |
| 30 | 0.745 | 0.99 | 6.93 | 7.08 |
| 45 | 0.609 | 1.21 | 8.48 | 5.78 |
| 70 | 0.294 | 2.51 | 17.54 | 2.79 |

`cng-datasets` auto-detection suggests **h6** here (it targets an H3 edge of ~3x the pixel
width). h6 carries no `h8` and would not join the catalog — always pass `--h3-resolution`
explicitly. Upstream: boettiger-lab/datasets#182.

## Land mask

**WWF Terrestrial Ecoregions of the World 2017**, `s3://public-ecoregion/ecoregion/hex/`
(already native h8). **195,048,994** cells across **108** h0 partitions, ~143.8 M km2.

Rejected: Overture countries. It is a *sovereignty* boundary including territorial and
archipelagic waters (Indonesia 4.99 M km2 against ~1.9 M km2 of land; Canada 11.9 M against
9.98 M) and omits Antarctica entirely. Set arithmetic between the two: 176.0 M cells in both,
19.0 M ecoregion-only (**11.59 M km2 Antarctic + 2.19 M km2 Arctic**), 20.9 M Overture-only.
Their union exceeds Earth's land area.

**Zero** ecoregion land cells fall above the CHELSA northern edge of 84N, so the mask loses
nothing to the source footprint.

Rollups on the masked footprint: **h5 = 595,155**, **h4 = 90,027**, **h0 = 108**.

## Pilot result (bio1, ssp370, 2041-2070)

Job `Complete=True`, `failedIndexes` empty, 122/122 indices.

| check | result |
|---|---|
| rows | 195,048,994 — equals the land-mask cell count exactly |
| distinct h8 | 195,048,994 — one row per cell, no duplicates |
| partitions | 108, matching the ecoregion land h0 set, 0 missing |
| h5 / h4 | 595,155 / 90,027 — exact match to the mask rollup |
| median range | -51.55 .. 36.75 degC, mean 11.89 |
| NULLs | 0 |
| median outside [min, max] | 0 |
| mean model spread | 2.02 degC |
| max model spread | 10.45 degC |

**End-to-end cross-check.** The coldest median cell is `-51.55` degC, which equals the GFDL
source raster's `STATISTICS_MINIMUM` of 2216 converted (`2216 * 0.1 - 273.15`) to the cent. An
independent `gdallocationinfo` probe of the raw source at (-60, -3) gives 29.35 degC; the
pipeline gives 29.309 degC for the h8 cell containing that point — the residual is the
difference between one pixel and an area-weighted cell mean.

## Timing

~3 min per member per h0, so ~15 min per pod for five members. 122 pods at parallelism 24
completed in **139 minutes**.

## Gotchas hit during the build

- **`rclone copyto` exits 0 when the source does not exist.** An all-ocean skip guard written as
  `if ! rclone copyto ...` never fired; those pods hexed five members and then died at the join.
  Test for the file (`[ ! -s ... ]`), not the exit code.
- **ConfigMap volumes expose keys as symlinks** into `..data/`, and rclone does not follow them
  ("not a directory"). `cp -L` into a real directory before uploading.
- **Do not inline the `h3_cell_area()` recipe** into a STAC description — `verify-stac.py`
  HARD-fails it, because a baked copy drifts from the h3-guide.
