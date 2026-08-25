# `roadcore-fs` — build notes and measured evidence

Every existing road under USDA Forest Service jurisdiction (RoadCore), from the Natural
Resource Manager (NRM) database via the Enterprise Data Warehouse. Issue:
boettiger-lab/data-workflows#588. Second dataset in `public-usfs` after #584's
`roadless-areas-2001`.

## Source

```
https://data.fs.usda.gov/geodata/edw/edw_resources/shp/S_USA.RoadCore_FS.zip
```

Verified 2026-08-25: HTTP 200, `application/zip`, **432,024,035 bytes**,
`Last-Modified: Sun, 11 May 2025 17:11:42 GMT`. Zip contents read from the central
directory over HTTP range requests:

| Member | Raw bytes | Zipped |
|---|---:|---:|
| `S_USA.RoadCore_FS.shp` | 556,398,584 | 388,347,026 |
| `S_USA.RoadCore_FS.dbf` | 423,184,592 | 40,624,242 |
| `S_USA.RoadCore_FS.shx` | 2,941,428 | 1,787,059 |
| `S_USA.RoadCore_FS.shp.xml` (FGDC) | 87,335 | 23,682 |

`(shx − 100) / 8` = **367,666 features**, confirmed exactly by the ingested parquet.

FGDC metadata also fetched separately from
`edw_resources/meta/S_USA.RoadCore_FS.xml` for the attribute domains.

### Sibling layers probed

`S_USA.RoadCore.zip` and `S_USA.RoadCore_NonFS.zip` both **404** — RoadCore_FS is the only
core road layer EDW publishes. `S_USA.Road_MVUM.zip` exists (Motor Vehicle Use Map) but is
the public-motorized subset, out of scope for #588.

### ⚠️ Do not use `EDW_RoadBasic_01` as a reference

The ArcGIS REST service `apps.fs.usda.gov/arcx/rest/services/EDW/EDW_RoadBasic_01` reports
**174,044 features / 226,861 miles** and returns **zero ML1 rows**. It is a filtered
publication view, not the core layer. Anyone sizing this dataset from the REST service will
be short by more than half the road system.

## Measured schema

367,666 **Polyline** features. Source CRS **EPSG:4269 (NAD83)** → EPSG:4326 by
`cng-convert-to-parquet`. Bounding box `(-149.981, 18.268) … (-65.730, 61.029)` — national,
Alaska through Puerto Rico, no antimeridian crossing.

### ⚠️ Shapefile 10-character column truncation — and why we undid it

The EDW distribution is an ESRI Shapefile, whose DBF attribute table caps field names at 10
characters. So the raw conversion produced `OPER_MAINT`, `FUNCTIONAL`, `SURFACE_TY`,
`PFSR_CLASS`, `OBJECTIVE_` and so on. The truncation is an artifact of the transport format:
the FGDC metadata and the EDW REST service both publish the full names, and #588 asks
specifically to *"Preserve `OPER_MAINT_LEVEL` and `SYSTEM`"*.

`roadcore-fs-derive.yaml` restores the 16 truncated names between `convert` and `hex`, so
every downstream artifact (parquet, hex, PMTiles, STAC) carries the FGDC names. It is a pure
rename — the job asserts the row count is unchanged and that the four load-bearing columns
exist before swapping the file into place.

| Shapefile (10 char) | Published | | Shapefile | Published |
|---|---|---|---|---|
| `CONGRESSIO` | `CONGRESSIONAL_DISTRICT` | | `PFSR_CLASS` | `PFSR_CLASSIFICATION` |
| `FUNCTIONAL` | `FUNCTIONAL_CLASS` | | `PRIMARY_MA` | `PRIMARY_MAINTAINER` |
| `JURISDICTI` | `JURISDICTION` | | `ROUTE_STAT` | `ROUTE_STATUS` |
| `LEVEL_OF_S` | `LEVEL_OF_SERVICE` | | `SECURITY_I` | `SECURITY_ID` |
| `MANAGING_O` | `MANAGING_ORG` | | `SERVICE_LI` | `SERVICE_LIFE` |
| `OBJECTIVE_` | `OBJECTIVE_MAINT_LEVEL` | | `SURFACE_TY` | `SURFACE_TYPE` |
| `OPENFORUSE` | `OPENFORUSETO` | | `SYMBOL_COD` | `SYMBOL_CODE` |
| `OPER_MAINT` | `OPER_MAINT_LEVEL` | | `SYMBOL_NAM` | `SYMBOL_NAME` |

Unchanged (already ≤10 chars): `ADMIN_ORG`, `BMP`, `COUNTY`, `EMP`, `GIS_MILES`,
`GLOBALID`, `ID`, `IVM_SYMBOL`, `LANES`, `LOC_ERROR`, `NAME`, `RTE_CN`, `SEG_LENGTH`,
`SHAPE_LEN`, `SYSTEM`.

### Single-valued columns — the layer's defining limit

| Column | Sole value |
|---|---|
| `SYSTEM` | `NFSR - NATIONAL FOREST SYSTEM ROAD` |
| `JURISDICTION` | `FS - FOREST SERVICE` |
| `ROUTE_STATUS` | `EX - EXISTING` |

FGDC purpose, verbatim: *"Only roads under the jurisdiction of the Forest Service are
included."* State, county and private roads are absent **by construction**. This is why #588
also ingests Census TIGER roads — the DEIS buffered *"National Forest System roads and other
authorized public roads"* (Vol I fn. 10), and this layer is only the first half.

### Codes present in the data but NOT in the FGDC domain

Measured against the ingested parquet, so the STAC `values` arrays are data-backed rather
than metadata-backed (`verify-stac.py` checks declared vs `DISTINCT`):

- `OPER_MAINT_LEVEL` — FGDC documents 1–5; the data also has `0 - NOT MAINTAINED` (39 rows)
  and `NA - NOT APPLICABLE` (40 rows), plus 276 NULLs.
- `FUNCTIONAL_CLASS` — FGDC documents A/C/L; the data also has `L - LOCAL IMPORTANT`.
- `OPENFORUSETO` — FGDC documents `All`/`Admin`; the data has `ALL`, `ADMIN` **and** `PUBLIC`.
- `LANES` — single-lane roads appear three ways: `1 - SINGLE`, `1 - SINGLE LANE`, `SINGLE`.
- `SERVICE_LIFE` — `C- LONG TERM SERVICE` and `C - LONG TERM SERVICE` differ by one space.
- `SURFACE_TYPE` — three distinct descriptions share the `AGG` prefix (`CRUSHED AGGREGATE OR
  GRAVEL`, `LIMESTONE`, `SCORIA`), and grass is coded both `SOD - GRASS` and `GRA - GRASS (NAT)`.

Match on the full string, not the code prefix, and normalise before grouping.

## The maintenance-level breakdown — the point of the dataset

`SEG_LENGTH` is the official on-record length in miles (derived from field measurements as
`EMP − BMP`). `GIS_MILES` is computed from the drawn geometry and sums ~5% higher.

| `OPER_MAINT_LEVEL` | Segments | Official miles | Share |
|---|---:|---:|---:|
| `2 - HIGH CLEARANCE VEHICLES` | 183,849 | 199,311 | 54.1% |
| **`1 - BASIC CUSTODIAL CARE (CLOSED)`** | **148,694** | **103,945** | **28.2%** |
| `3 - SUITABLE FOR PASSENGER CARS` | 24,631 | 49,919 | 13.6% |
| `4 - MODERATE DEGREE OF USER COMFORT` | 6,825 | 11,351 | 3.1% |
| `5 - HIGH DEGREE OF USER COMFORT` | 3,312 | 3,226 | 0.9% |
| (NULL) | 276 | 305 | 0.1% |
| `NA - NOT APPLICABLE` | 40 | 29 | 0.0% |
| `0 - NOT MAINTAINED` | 39 | 18 | 0.0% |
| **Total** | **367,666** | **368,103** | |

**Three published Forest Service figures reproduced exactly**, which is the strongest
available evidence that this is the right layer and that it is complete:

| Published claim | Source | Computed here | ✓ |
|---|---|---|---|
| NFS road system ≈ **368,000 miles** | DEIS / preamble | `SUM(SEG_LENGTH)` = **368,103** | ✓ |
| ≈ **65,000 mi (18%)** accommodate standard passenger cars | DEIS | ML3+4+5 = **64,496 mi (17.5%)** | ✓ |
| ≈ **200,000 mi (54%)** high-clearance | DEIS | ML2 = **199,311 mi (54.1%)** | ✓ |

**ML1 is 28.2% of the system.** Level 1 roads are closed to motor vehicles and placed in
storage between intermittent uses; they are frequently impassable and often revegetated.
Counting them as "existing roads" in a proximity claim inflates accessibility, which is
exactly the check #588 exists to run — hence the ML1/ML2-5 strata in the analysis.

## ⚠️ 8,204 records have no geometry — and the source says why

| | Count | Official miles |
|---|---:|---:|
| Total records | 367,666 | 368,103 |
| With geometry | 359,462 | 363,358 |
| **Without geometry** | **8,204** | **4,745** |

These are not a conversion failure. Every one of them carries a failing value in the
source's own `LOC_ERROR` column — the diagnostic from the Forest Service's linear-referencing
step, which places each road record onto the route centerline network:

| `LOC_ERROR` | Records | Of which no geometry | Official miles |
|---|---:|---:|---:|
| `NO ERROR` | 328,420 | 0 | 335,581 |
| `PARTIAL MATCH FOR THE TO-MEASURE` | 15,368 | 257 | 16,050 |
| `PARTIAL MATCH FOR THE FROM-MEASURE` | 14,151 | 49 | 10,699 |
| `PARTIAL MATCH FOR THE FROM-MEASURE AND TO-MEASURE` | 1,837 | 8 | 1,294 |
| **`ROUTE NOT FOUND`** | **7,430** | **7,430** | 4,127 |
| `MEASURE EXTENT OUT OF ROUTE MEASURE RANGE` | 232 | 232 | 194 |
| `ROUTE WITHOUT MEASURE` | 164 | 164 | 123 |
| `EMPTY ROUTE SHAPE` | 45 | 45 | 33 |
| `ZERO LENGTH EXTENT` | 19 | 19 | 2 |

They appear in the GeoParquet with attributes intact, but cannot appear in the hex or the
PMTiles, and **cannot be buffered in a distance analysis by anyone, including the agency**.
The 4,745 miles they represent (1.3% of the system) are therefore missing from every
road-proximity figure computed from this layer — ours and the DEIS's alike.

`_cng_fid` is unique per row (367,666 distinct over 367,666 rows), so there is no upstream
row duplication (axis 2). `NAME` (161,472 distinct) and `ID` (249,414) are *not* feature
keys — one road is stored as many segments. Use `RTE_CN` to reassemble whole routes.

## Pipeline

| Setting | Value | Why |
|---|---|---|
| dataset | `roadcore-fs` | PMTiles `source-layer` = `roadcore-fs` |
| bucket | `public-usfs` | alongside #584/#585 |
| H3 native | `8`, parents `0` | line default (`AGENTS.md:221`); res 8 is the catalog join key |
| `--chunk-size` | **2000** | 367,666 features ÷ 200 completions = 1,839. **The generator default of 1000 caps at 200,000 features and would have silently dropped 45% of the layer** — hand-set in both `roadcore-fs-hex.yaml` and `configmap.yaml` |
| `--hex-memory` | `16Gi` | line features at res 8; comfortable |
| `--row-group-size` | 100000 (default) | ~1.5 KB geometry/feature ⇒ ~150 MB column chunks, far under the ~2.8 GB httpfs `stoi` cliff |
| namespace | `geo-workflows` | |

Run order — `derive` sits between `convert` and `hex`:

```bash
kubectl apply -n geo-workflows -f roadcore-fs-setup-bucket.yaml   # idempotent; bucket exists
kubectl apply -n geo-workflows -f roadcore-fs-stage-raw.yaml
kubectl apply -n geo-workflows -f roadcore-fs-convert.yaml
kubectl apply -n geo-workflows -f roadcore-fs-derive.yaml         # restore FGDC column names
kubectl apply -n geo-workflows -f roadcore-fs-hex.yaml -f roadcore-fs-pmtiles.yaml
kubectl apply -n geo-workflows -f roadcore-fs-repartition.yaml    # after hex completes
```

`configmap.yaml` + `workflow.yaml` drive the same DAG via the orchestrator, but **do not
include `derive`** — run it manually between convert and hex, or the published columns stay
truncated.

`stage-raw` asserts the exact 432,024,035-byte length and the `PK` zip magic before upload,
so an HTML error page served with HTTP 200 fails the job rather than poisoning the build.

## Post-build verification

```sql
-- source fidelity: feature count and the published 368,000-mile system total
SELECT COUNT(*), COUNT(DISTINCT _cng_fid), ROUND(SUM(SEG_LENGTH))
FROM read_parquet('s3://public-usfs/roadcore-fs.parquet');
-- expect 367666 | 367666 | 368103

-- hex coverage: every feature WITH GEOMETRY must survive hexing
SELECT COUNT(DISTINCT _cng_fid)
FROM read_parquet('s3://public-usfs/roadcore-fs/hex/h0=*/data_0.parquet');
-- expect 359462 (= 367666 - 8204 null-geometry records)
```

```bash
scripts/check-hex-coverage.sh nrp:public-usfs/roadcore-fs/hex/
scripts/audit-feature-dup.py <stac-url> --asset roadcore-fs-hex --key _cng_fid
scripts/verify-stac.py --bucket public-usfs --dataset roadcore-fs
```

## Notes

- License: US Forest Service work. FGDC `useconst` is a no-warranty disclaimer only;
  `accconst` is `None` → `public-domain`, with a `rel: license` link to usa.gov/government-works.
- The FGDC disclaimer is worth carrying into STAC: these data are not legal documents and
  may not be used to determine title, ownership, legal descriptions, boundaries or
  jurisdiction. Relevant to any road-proximity buffering.
- No backup/mirror registration happens in this repo — that tier is owned by geo-agent-ops
  (see #584's BUILD.md for the same note).
