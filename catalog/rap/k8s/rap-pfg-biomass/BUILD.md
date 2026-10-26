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

All commands from this directory. Steps 1–2 build the data, 3 verifies it, 4 publishes the STAC.

### 1. Build

```bash
kubectl apply -n geo-workflows -f rap-pfg-biomass-rename-cog.yaml   # to the bucket's convention
kubectl apply -n geo-workflows -f rap-pfg-biomass-hex.yaml          # 6 CONUS partitions
```

The rename copies server-side, compares byte counts, and only then deletes the old key. The hex
asserts its input is single-band before running — the guard the cover collection lacked.

`--h0-index` values are 12, 14, 20, 50, 71, 78 (the full CONUS set), resolved from the `i` column
of `s3://public-grids/hex/h0-valid.parquet`. These are **not** H3 base cell numbers: the two
0–121 numberings do not coincide, and index 20 is base cell 19. See #666.

### 2. Raw checksum

```bash
kubectl apply -n geo-workflows -f rap-bio-raw-checksum.yaml
kubectl logs -n geo-workflows job/rap-bio-raw-checksum | grep -E 'SHA256|BYTES'
```

Streams the staged raw over the internal endpoint and prints its SHA-256 and byte count — the S3
ETag is multipart and unusable as a digest. `gen_stac.py` carries the result as `RAW_SHA` /
`RAW_BYTES`; if the log disagrees with those constants, the staged raw has changed and the
provenance block must be updated before publishing.

### 3. Verify, before publishing anything

```bash
./verify-biomass-build.sh
```

See "Verification" below for what it checks and the expected output.

### 4. Publish

```bash
./gen_stac.py                                                   # -> /tmp/rap-bio-stac/ (never the repo)

kubectl create configmap rap-bio-stac -n geo-workflows \
  --from-file=/tmp/rap-bio-stac/ --dry-run=client -o yaml | kubectl apply -n geo-workflows -f -

kubectl apply -n geo-workflows -f rap-bio-publish-stac.yaml     # -> s3://public-rap/
```

`gen_stac.py` writes two files into `/tmp/rap-bio-stac/` (override with `RAP_BIO_STAC_OUT`),
measuring the bbox, sizes and timestamps off the live objects:

- `rap-pfg-biomass-stac-collection.json` — this collection.
- `parent-stac-collection.json` — the bucket collection `s3://public-rap/stac-collection.json`.
  It is **read from the live bucket** and given a child link to `rap-pfg-biomass` if it does not
  already have one; every other field and child link is kept as published. The four cover
  collections are owned by `rap-bands/gen_stac.py`, so this generator must not rebuild the parent
  from scratch or it would drop them.

Nothing it produces is committed — AGENTS.md HARD BOUNDARY 1 keeps STAC out of this repo.
`rap-bio-publish-stac.yaml` publishes exactly the ConfigMap's contents, so re-create the ConfigMap
after any re-run of `gen_stac.py`.

Pre-publish gate on the generated file, then the post-publish data-backed check:

```bash
python3 ../../../../scripts/verify-stac.py --no-data /tmp/rap-bio-stac/rap-pfg-biomass-stac-collection.json
python3 ../../../../scripts/verify-stac.py --bucket public-rap --dataset rap-pfg-biomass
```

## Verification (run after the hex completes)

`verify-biomass-build.sh` checks the #677 acceptance criteria against the **source**, not against
the collection's own metadata. Section 3 takes TiTiler zonal means of upstream bands 1 and 2 (and
of our COG) over two 1°×1° windows; section 4 queries the published hex over the same windows
through the duckdb-geo MCP (mean of the resolution-10 cells whose centres fall in the window,
reading only the one h0 partition the window sits in). Result:

| window | hex (section 4) | cells | upstream band 1 (annual) | upstream band 2 (perennial) |
|---|---:|---:|---:|---:|
| Kansas (−99…−98, 39…40) | **880.1** | 601,883 | 184.4 | **879.1** ✅ |
| Nevada (−118…−117, 40…41) | **132.3** | 599,965 | 458.2 | **132.2** ✅ |

The two windows **disagree in opposite directions** — Kansas holds 4.8× more perennial than annual
biomass, Nevada 3.5× more *annual* than perennial, the Great Basin's cheatgrass signature. Matching
band 2 in both is therefore conclusive: a band-1 build would read 184 in Kansas and 458 in Nevada.

⚠️ **Compare over windows that sit wholly inside one h0 cell.** An earlier check straddled two and
sampled only the completed partition's sliver — 33,946 cells of an expected ~600,000 — which made a
correct build look 2.3× off. The cell count is what exposes this; check it before trusting a mean.

Continental gradient, as a coherence check (a one-off hex query at build time, not part of the
script): Pacific west 266.5 < northern Rockies 313.6 < Great Plains 678.9 < humid southeast
799.3 lbs/acre. Tracks precipitation and growing season, and is not
something a mis-banded or mis-scaled build reproduces by accident.

Published extent is **−124.736, 25.045, −67.041, 49.389**, measured from the hex.
