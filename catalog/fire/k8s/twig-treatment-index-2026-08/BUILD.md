# TWIG treatment index — build notes

Issue: [#603](https://github.com/boettiger-lab/data-workflows/issues/603) ·
Collection: `s3://public-fire/twig-treatment-index-2026-08/`

Everything below was **measured on the built artifacts**, not taken from upstream documentation.
Re-measure rather than reuse if you rebuild.

## Source

Live ArcGIS feature service, `Query` capability only, so it is paged:
`https://gis.reshapewildfire.org/arcgis/rest/services/Hosted/Treatment_Index_View/FeatureServer/0`

Paging is by **objectid range**, not `resultOffset`. `objectid` runs 1..1,491,072 contiguously
(max == count), so ranges are stable if upstream edits land mid-scrape; offset paging would silently
skip or duplicate rows.

| | |
|---|---|
| Access date | 2026-09-17 |
| Upstream last edit | 2026-09-02 (`editingInfo.lastEditDate`) |
| Staged raw | `s3://public-fire/raw/twig-treatment-index-2026-08.gpkg` |
| Size / sha256 | 5,785,997,312 B / `d0a4eb816db3217a6883a524f2e8996bc510a415377c8d0057695298b986cb11` |
| Licence | CC-BY-4.0, from the [publisher's data-resources page](https://reshapewildfire.org/resources/twig-data-resources/) (the service itself publishes none) |

Reconciled 1,491,072 paged rows against `returnCountOnly` at both the start and end of the fetch,
with 1,491,072 distinct `objectid`.

## Why GeoPackage, not FlatGeobuf

Exactly **one** record has NULL geometry, which forced the staging format:

- FlatGeobuf **rejects NULL geometry** while building a spatial index.
- FlatGeobuf with `SPATIAL_INDEX=NO` produced a file DuckDB's bundled GDAL **cannot open at all** —
  `Invalid Input Error: Skipping beyond end of binary data at position 1149`, deterministic across
  two attempts, at the offset where the index would begin.
- GeoPackage stores NULL geometry natively **and** keeps its index.

Do not switch this back to FlatGeobuf.

GeoPackage has one cost: it is SQLite, so reading it over `/vsicurl` turns every page into a small
random HTTP range read. `cng-convert-to-parquet` rewrites an `s3://` source to the **public**
endpoint, which measured **14 minutes at 76m CPU** — essentially idle. The convert job therefore
`rclone`-pulls the file over the **internal** endpoint first and hands GDAL a local path, after which
the same work runs at **1900-2000m CPU**. This mirrors what the tool already does for `.gdb`.

## Resolution is a measurement

`--resolution-by-area "0.032:10,0.22:9,8"` with `--parent-resolutions 9,8,0`.

Geometry area in planar deg², measured on the built GeoParquet:

| statistic | deg² | approx. cells at res 10 |
|---|---|---|
| median | 1.09e-05 | ~7 |
| p99.9 | 0.00326 | ~2.2M |
| p99.99 | 0.0188 | ~12.5M |
| **max** | **2.1376** | **~1.4 billion** |

A flat res 10 is therefore impossible: one polygon would generate roughly 1.4 billion cells and OOM
at any memory. Resulting tiers, which match the measured thresholds exactly:

| native_res | features | hex rows |
|---|---:|---:|
| 10 | 1,490,993 | 39,426,573 |
| 9 | 71 | 305,009 |
| 8 | 7 | 113,961 |

**The catch-all tier is 8, never coarser**, so every feature still carries `h8`, the catalog's
universal join key. Verified: `h8` NULL rows = **0**. `h10` is NULL for the 78 features held coarser,
which is documented in the hex asset description (`verify-stac` HARD-fails it otherwise).

## Why k8s and not Armada

The k8s hex hardcodes `--chunk-size 1000`, so `max-completions × 1000` is a silent coverage cap: the
default 200 would have hexed the first 200,000 of 1,491,072 features and still looked complete.
Passing `--expect-features` makes the generator derive `--chunk-size 7456`, so 200 × 7,456 =
1,491,200 covers everything. Both hex runs completed 200/200 with zero failures, so Armada was not
needed.

## Measured resource usage

Size from these, not from a neighbouring job. NRP's admission webhook scores the account on
requested-vs-used and then **refuses every new job on the account regardless of size**, so an
over-request blocks unrelated work, not just its own.

| job | requested | measured |
|---|---|---|
| stage-raw | 1 cpu / 4 Gi | 1.4-1.6 Gi steady |
| convert | 2 cpu / 12 Gi | ~1 Gi, 1900-2000m cpu once localized |
| hex (per pod) | 4 cpu / 8 Gi | peak 1.05 Gi, mean 0.65 Gi (tail sample of 4 pods) |

Two sizing traps hit during this build:

- **8 Gi for 1.5 Gi of work tripped the webhook** and blocked the convert step behind it.
- **2 Gi was then too tight**: a 45-second sampler read 1.53 Gi steady but missed the early spike
  while the first batches are all in flight, and the pod was OOMKilled 48 seconds in. The scrape
  submits ranges in bounded batches of 12 to cap that spike; 4 Gi is the headroom.

The hex request of 8 Gi is roughly 8x the measured peak and could come down, but the sample is the
tail of the run, so measure the dense chunks before cutting it.

## Data quirks found by measurement

- **Whitespace.** 70,516 rows in `activity` and 96,713 in `equipment` carried trailing spaces, which
  silently break equality filters. `--trim-strings` collapses `activity` from 236 distinct values to
  **234**, exactly matching its 234 `activity_code` values, which is the proof the variants were
  duplicates rather than real categories. 10 rows in the free-text `name` column keep theirs.
- **`error` is multi-valued**, semicolon-separated. Equality-matching under-counts: parsed,
  `MODIFIED_SHAPE` is 2,694 not 1,797 and `BUFFERED_LINE` is 15,561 not 14,711. 85,997 rows carry at
  least one flag. `LARGE_AREA` (4 rows) was added upstream after #603 was written.
- **The service's advertised extent is wrong.** It reports −151.6→−51.8 lon, but the real data spans
  −164.67→144.86. The eastern edge is 2 legitimate NPS treatments on **Guam**; the `xmax` of −51.81
  and `ymin` of 8.57 in the service metadata are both set by **one mislocated polygon** — a 1.9-acre
  Virginia treatment mapped into the Atlantic off South America, which the publisher already flags
  `SPATIAL`. The collection publishes sub-bounding-boxes for the two real clusters.
- **`SHAPE__Area` / `SHAPE__Length` are square degrees and degrees**, not m², because the service
  computes them in the requested output SR (EPSG:4326). The publisher's own metadata table says
  square metres, which is true of their file geodatabase but not of a 4326 service query. Use `acres`.
- **Dates.** `treatment_date` spans 1202-02-10 to 2926-10-03. 1,429,746 rows fall 1980→access date,
  61,314 are future-dated and 12 predate 1980. Nothing dropped. The issue's "62,519 future" was
  correct when written; "future" moves with the current date.

## Verification

```
rows                       1,491,072
distinct _cng_fid          1,491,072
distinct unique_id         1,491,072   <- unique_id is a valid dedup key
NULL geometry                      1
hex features               1,491,071   <- the NULL-geometry row polyfills to zero cells
hex h8 NULL rows                   0
hex h0 partitions                 14
hex rows                  39,845,543
scripts/audit-feature-dup.py --key unique_id   CLEAN
scripts/verify-stac.py --bucket public-fire    0 hard
```
