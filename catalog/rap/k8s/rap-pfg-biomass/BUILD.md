# RAP perennial forb & grass biomass — issue #677

Publishing a COG that was built on 2026-06-10 and then orphaned: no STAC collection, no hex, and
no reference anywhere in this repo. It read as abandoned. It was not — the data is correct.

## What it is, measured rather than assumed

RAP **Vegetation Biomass v3**, 2024, **band 2** (perennial forb & grass), lbs/acre. uint16, ~30 m,
EPSG:4326, CONUS, nodata 65535.

This is a *different upstream product* from the vegetation **cover** stack behind `rap-afg-cover`
and `rap-pfg-cover` — same publisher, different variable, different units, different nodata.

Band identity was verified against the upstream raster rather than inferred from the filename,
because #666 defect 3 established that a filename is not evidence:

| point | this COG | upstream band 1 (annual) | upstream band 2 (perennial) |
|---|---:|---:|---:|
| Kansas (−99.5, 38.5) | **1647** | 408 | **1647** ✅ |
| Boise ID (−116.2, 43.6) | **234** | 4 | **234** ✅ |
| Cheyenne WY | 0 | 0 | 0 |

Licence **CC0-1.0**, confirmed in the biomass product's own README — a separate document from the
cover README, checked independently rather than carried across.

## Two settings that differ from the cover collections

Both silently corrupt the output if copied from a cover manifest:

- **`--nodata 65535`**, not 255. The raster is uint16 because lbs/acre exceeds a byte, and 255 is
  a live data value here.
- **`--hex-resampling mean`**, because lbs/acre is a **density** — mass per unit area. The reducer
  follows the source units, not the conceptual quantity: biomass *sounds* like something to sum,
  but summing a per-acre density across cells is meaningless. A consumer wanting a regional total
  weights by cell area.

## Edition: 2024, deliberately

Upstream publishes 2025 (released 2026-02-24) and the four cover collections here are 2025. This
one stays 2024 because that is the data that exists and has been verified; building 2025 means
re-staging a ~37 GB source, which is new work rather than publication of existing work. The STAC
says 2024 plainly. A 2025 build is a reasonable follow-up and should be its own task.

## Run order

```bash
kubectl apply -n geo-workflows -f rap-pfg-biomass-rename-cog.yaml   # to the bucket's convention
kubectl apply -n geo-workflows -f rap-pfg-biomass-hex.yaml          # 6 CONUS partitions
```

The rename copies server-side, compares byte counts, and only then deletes the old key. The hex
asserts its input is single-band before running — the guard the cover collection lacked.

`--h0-index` values are 12, 14, 20, 50, 71, 78 (the full CONUS set), resolved from the `i` column
of `s3://public-grids/hex/h0-valid.parquet`. These are **not** H3 base cell numbers: the two
0–121 numberings do not coincide, and index 20 is base cell 19. See #666.
