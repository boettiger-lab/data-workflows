# `census-2025/roads` — build notes and measured evidence

Census TIGER/Line 2025 road network, national. Issue: boettiger-lab/data-workflows#588.

Ingested as the non-federal complement to `public-usfs/roadcore-fs`: the 2026 Roadless Rule
Draft EIS buffered *"National Forest System roads and other authorized public roads"*
(Vol I fn. 10), and RoadCore carries only the first half — `SYSTEM` is `NFSR` and
`JURISDICTION` is `FS` on every one of its records, so state, county and private roads are
absent from it by construction.

## Source

```
https://www2.census.gov/geo/tiger/TIGER2025/ROADS/
```

Verified 2026-08-25: **3,233 per-county zips**, ~3.6 GB compressed, posted 2025-09-22 —
contemporaneous with the September-2025 NRM snapshot the DEIS buffered.

`cng-convert-to-parquet` rejects multiple `.zip` URLs (AGENTS.md Step 1c), so the ingest is
a two-job preprocess: an Indexed Job fanning out one pod per state/territory FIPS (56), then
a DuckDB merge into the national parquet.

## Two source-side obstacles

### 1. Census burst rate limiting (HTTP 429)

Fanning out at 14 pods × 6 concurrent fetches drew sustained 429s within a minute. Throttling
all the way down to 3 pods × serial fetches still 429'd — but a later probe of 12 sequential
fetches with no pause returned 200 every time at ~1.2 s each. **The limiter is burst-based
and recovers**; it had simply been tripped and needed time, not permanent throttling. Final
settings are 8 pods × 3 concurrent with a long retry ladder
(`--retry 15 --retry-delay 20 --retry-all-errors`) and an index-derived start stagger.

A rate-limited fetch can also return a short or HTML body that `curl` exits 0 on, so every
download is PK-magic checked and any bad file is re-fetched individually (4 attempts) rather
than failing the whole state — a 250-county state is too expensive to redo for one bad file.

### 2. ⚠️ One object is blocked outright by the Census WAF — documented vintage substitution

`tl_2025_47103_roads.zip` (Lincoln County, TN) returns **HTTP 200 with a 247-byte
`Request Rejected` HTML body** — an F5 ASM block, complete with a support ID:

```
<html><head><title>Request Rejected</title></head><body>The requested URL was rejected.
Please consult with your administrator.<br><br>Your support ID is: 13427891560110751339
```

Reproduced from two independent networks and with both a `curl` and a browser User-Agent, so
it is not our client, not rate limiting, and not a missing file — the same county's
**TIGER2024 (877,565 B) and TIGER2023 (876,847 B) files download normally**, as does every
neighbouring 2025 county.

Rather than publish a layer with a county-shaped hole, the preprocess falls back to the most
recent working vintage for any object still blocked after retries, and **records every
substitution** to `s3://public-census/raw/roads-2025/_substitutions_<FIPS>.txt`, which the
STAC cites. Currently exactly one:

```
47103 TIGER2025 blocked -> substituted TIGER2024
```

The conversion loop is vintage-agnostic (`tl_*_${FIPS}[0-9][0-9][0-9]_roads.shp`, GEOID parsed
by regex) so a substituted file merges identically. Lincoln County TN holds no National Forest
System land, so this has **no effect on the #588 analysis**.

## ⚠️ `GEOID_COUNTY` is added by this ingest and is not in the source

TIGER road shapefiles carry only `LINEARID`, `FULLNAME`, `RTTYP`, `MTFCC` — **no state or
county FIPS**. County identity exists only in the filename and is gone forever once the 3,233
files are merged. It is injected at preprocess time:

```bash
ogr2ogr -f GPKG state.gpkg "${s}" -append -nln roads -t_srs EPSG:4326 \
  -dialect SQLITE -sql "SELECT *, '${CGEOID}' AS GEOID_COUNTY FROM \"${LAYER}\""
```

(GPKG is the intermediate because Parquet is write-once and cannot take `-append`; the state
GPKG is converted to Parquet once at the end.)

The #588 analysis relies on this column to cut the 16.5M national features down to the 524
counties that intersect an IRA envelope — a key filter instead of a 16.5M-row spatial scan.

## Measured

| Quantity | Value |
|---|---|
| Features | **16,490,899** |
| Counties | **3,233** (all) |
| `COUNT(DISTINCT _cng_fid)` | 16,490,899 — one row per feature, no upstream duplication |
| Null/empty geometries dropped at merge | **0** |
| Flat GeoParquet | 4.4 GB |
| MTFCC classes | 15 |
| `RTTYP` | C, I, M, O, S, U |
| Bounding box | `(-176.959, -14.367, 179.453, 71.386)` |
| Hex rows (res 8) | **32,309,245** |
| Hex `COUNT(DISTINCT _cng_fid)` | **16,490,899 — exact agreement with the flat** |
| Populated `h0` partitions | 16 |

MTFCC present: `S1100, S1200, S1400, S1500, S1630, S1640, S1710, S1720, S1730, S1740, S1750,
S1780, S1810, S1820, S1830`. Note **`S1810` (winter trail / ice road)** is present and is
absent from some published MTFCC summaries.

### Road vs not-a-road

Four MTFCC classes are **not motor vehicle travelways**: `S1710` walkway, `S1720` stairway,
`S1820` bike path, `S1830` bridle path. They are retained at ingest so the decision stays
visible and reversible, and excluded at analysis time — 36 CFR 294.11 defines a road as
*"a motor vehicle travelway over 50 inches wide"*.

`S1500` (4WD vehicular trail) and `S1810` (winter/ice road) **are** motor vehicle travelways
and are kept, but both are seasonally or conditionally passable and are worth separating in
any accessibility analysis.

## Antimeridian

The layer crosses ±180 (Aleutians) and reaches −14.367 (American Samoa), so the h0 dateline
cell is genuinely in play. **No seam inflation:** `h0=576707042908045311` holds 39,408
features at 2.28 cells/feature, squarely inside the 1.36–2.28 range of every other partition.
Across the layer the maximum is 419 cells for a single feature (a ~190 km highway at ~460 m
res-8 edge length) and the mean is 1.96 — a wrapped geometry would produce tens of thousands.

## Pipeline

| Setting | Value | Why |
|---|---|---|
| dataset | `census-2025/roads` | PMTiles `source-layer` = `roads`; S3 `public-census/census-2025/roads` |
| H3 native | `8`, parents `0` | line default (`AGENTS.md:221`) |
| `--chunk-size` | **86577** | `ceil(16,490,899 / 200) × 1.05`. **The generator default of 1000 caps at 200,000 features — it would have silently dropped 99% of the layer** (the #494 silent-cap class). Sized from the actual merged row count by the build chain, and patched into both the hex manifest and `configmap.yaml` |
| `--hex-memory` | `32Gi` | matches `usgs-nhd` at 30.2M lines |
| `--row-group-size` | 100000 | TIGER geometries are short (~200 B WKB) ⇒ ~20 MB column chunks, far under the ~2.8 GB httpfs `stoi` cliff |

Run order:

```bash
kubectl apply -n geo-workflows -f preprocess-roads.yaml      # 56 pods, one per state FIPS
kubectl apply -n geo-workflows -f merge-roads.yaml           # -> census-2025/roads.parquet
kubectl apply -n geo-workflows -f census-2025-roads-setup-bucket.yaml
kubectl apply -n geo-workflows -f census-2025-roads-convert.yaml
kubectl apply -n geo-workflows -f census-2025-roads-hex.yaml   # set --chunk-size from the count FIRST
kubectl apply -n geo-workflows -f census-2025-roads-repartition.yaml
kubectl apply -n geo-workflows -f census-2025-roads-pmtiles.yaml   # deferred; see below
```

Both preprocess and merge assert their expected counts (56 state parquets, 3,233 counties)
and fail rather than publish a short "national" layer.

## Build results (2026-08-25)

| Job | Duration |
|---|---|
| preprocess (56 indexed pods) | 3m15s |
| merge | 33s |
| convert | 3m33s |
| hex (200 indexed pods) | 15m — `Complete`, `failedIndexes` empty |
| repartition | 48s |

### Verification

```
hex COUNT(DISTINCT _cng_fid) = 16,490,899 = flat COUNT(*)          ✅ exact
32,309,245 hex rows, 0 NULL h8, 16 populated h0 partitions          ✅
check-hex-coverage.sh --expect-count 16 --min-bytes 500             ✅ PASS
verify-stac.py --bucket public-census --dataset census-2025/roads   ✅ PASS, 0 hard
```

⚠️ `check-hex-coverage.sh` at its **default `--min-bytes 4096` reports 14 of 16** and fails.
That threshold exists to discard ~214-byte footer-only empties, but two partitions here are
legitimately tiny — `h0=578501445884575743` is 1,039 B for **1 real row** and
`h0=576882964768489471` is 2,379 B for **167 real rows**. Both carry data. Pass
`--min-bytes 500` for this dataset; do not read the default-threshold failure as missing
coverage.

## PMTiles — deferred

Tiling 16.5M road lines through GeoJSONSeq → tippecanoe is a multi-hour job, and **no #588
acceptance criterion depends on it**, so it is queued after the analysis. The manifest routes
both intermediates onto the `rechunk-scratch` PVC rather than pod ephemeral storage (the 50Gi
namespace cap) and reads the source over the internal S3 endpoint (`/vsis3/`) rather than the
public one the generator emits.

Until it runs, `census-2025/roads.pmtiles` does not exist and the `roads-pmtiles` STAC asset
points at a key that 404s.

## Notes

- License: US Census Bureau work → `public-domain`, with a `rel: license` link.
- TIGER/Line road geometry is a **cartographic representation**, not a survey product;
  positional accuracy varies by county and vintage and centerlines can sit tens of metres off
  the true roadway in rural areas. Relevant to any buffer-distance result computed from it.
