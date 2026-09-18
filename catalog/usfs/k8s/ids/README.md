# USFS Insect & Disease Detection Survey (IDS) build notes

Issue: [#591](https://github.com/boettiger-lab/data-workflows/issues/591) ·
Bucket: `public-usfs` · Raw: `s3://public-usfs/raw/ids/`

Two datasets come out of one staging, because all three layers ship inside every regional GDB:

| Dataset | Source layer | Features | Years |
|---|---|---|---|
| `ids-damage-1997-2025` | `DAMAGE_AREAS_FLAT_AllYears_*` | 4,533,015 | 1997-2025 (29) |
| `ids-survey-extent-1999-2025` | `SURVEYED_AREAS_FLAT_AllYears_*` | 73,730 | 1996-2025 (30) |

`DAMAGE_POINTS_FLAT_Allyears_*` (1,293,977 points) is **out of scope** for this ingest.
Note the lowercase `y` in `Allyears` on that layer and nowhere else: any code splitting a layer
name on `_AllYears` silently fails to match it.

## The ids are asymmetric on purpose

Damage genuinely starts in 1997 and holds **131,013 polygons in 1997-1998**, in all nine regions.
Survey extent's 1996/1997/1998 rows are **one row each, all in Region 6**, so 1996 is a stray value
rather than a start date and substantive coverage begins in 1999. See the census comment on #591.

**1997 and 1998 damage therefore has no usable denominator.** Damage rates are not computable for
those two years, and that has to be stated in the collection description.

## Step order

`convert` is **superseded by the merge jobs** and must not be applied.

`cng-convert-to-parquet` applies one `--layer` to every source, but IDS layer names carry a
per-region suffix, so no single `--layer` addresses all nine GDBs. The merge jobs normalize the
nine layers into one GPKG under a uniform name (which also resolves the CONUS ESRI:102039 vs
Alaska CRS split) and convert from there. Applying the generated orchestrator `workflow.yaml`
would re-run `convert` against the public endpoint and undo that.

```bash
# 1. stage raw + provenance manifest (once)
kubectl apply -n geo-workflows -f ids-stage-raw.yaml

# 2. optional: re-derive the layer/year census used for scoping
kubectl apply -n geo-workflows -f ids-year-census.yaml

# 3. merge 9 regions -> national GeoParquet (replaces `convert`)
kubectl apply -n geo-workflows -f ids-survey-extent-merge.yaml
kubectl apply -n geo-workflows -f ids-damage-merge.yaml

# 4. remaining steps, applied individually -- NOT via workflow.yaml
kubectl apply -n geo-workflows -f survey-extent/ids-survey-extent-1999-2025-pmtiles.yaml
kubectl apply -n geo-workflows -f survey-extent/ids-survey-extent-1999-2025-hex.yaml
kubectl apply -n geo-workflows -f survey-extent/ids-survey-extent-1999-2025-repartition.yaml

# damage, after the survey-extent hex finishes (one k8s hex workflow at a time)
kubectl apply -n geo-workflows -f damage/configmap.yaml
kubectl apply -n geo-workflows -f damage/ids-damage-1997-2025-pmtiles.yaml
kubectl apply -n geo-workflows -f damage/ids-damage-1997-2025-hex.yaml
kubectl apply -n geo-workflows -f damage/ids-damage-1997-2025-repartition.yaml
```

## Damage does not need Armada, because feature count is not the workload

The obvious reading is that 4,533,015 damage polygons need Armada while 73,730 survey footprints
fit k8s. Measured, it is the other way round. What drives hex cost is **covered area**, not feature
count:

| | features | total area | H3 r10 cells | cells per chunk |
|---|---|---|---|---|
| `ids-survey-extent-1999-2025` | 73,730 | 95.1M km2 | ~6.3B | ~86M at 74 chunks |
| `ids-damage-1997-2025` | 4,533,015 | 2.39M km2 | ~0.16B | ~0.8M at 200 chunks |

Damage carries 61x the features and about **1/40th the hex work**: they are small sketch polygons,
while a survey footprint is a whole flight area. At 200 completions a damage chunk is roughly 100x
lighter than a survey-extent chunk that k8s already runs at a 5.2Gi peak. So damage runs on the
plain k8s backend at 200 completions x 22,666, and the 200-completion cap is not a constraint here.

⚠️ **Do not measure this with `h3_polygon_wkt_to_cells_string`.** It returns **0 cells for
MULTIPOLYGON** without erroring, and these datasets are 99.05% and 89.5% MULTIPOLYGON, so a naive
per-feature cell count silently reports only the POLYGON remainder. The table above comes from
`SUM(ST_Area(...))` converted at the mean latitude. (`ST_Area_Spheroid` returns `nan` on these
geometries, which is a separate trap.)

## Gotchas already paid for

- **The origin rate-limits.** `www.fs.usda.gov` returns 429 on plain sequential HEADs from one
  host. Staging downloads at concurrency 3 and reruns pull from S3, never the origin.
- **Do not unpack a FileGDB on the `rechunk-scratch` PVC.** It is thousands of small files and
  CephFS charges per-file overhead: ~13 min/region. Unpacking on the node's local disk, and
  building the GPKG there with `OGR_SQLITE_SYNCHRONOUS OFF` (GPKG is SQLite, whose small
  synchronous writes are pathological on CephFS), gives ~30s/region.
- **`_cng_fid` is the dedup key for both datasets.** The natural ids are not unique:
  `SURVEYED_AREA_ID` has 57,575 distinct values over 73,730 rows, `DAMAGE_AREA_ID` 4,338,867 over
  4,533,015.
- **The geometry column is `Shape`**, not `geom`, inherited from the FileGDB.
- **Size hex memory from the LARGEST SINGLE FEATURE, not the chunk and not a short sample.**
  Sampling the survey-extent hex over its first 5 minutes showed a 5.2Gi peak; the true peak was
  **11.9Gi**, reached much later when a pod picked up one of the enormous footprints. A short
  sample understates this badly, because the heavy features are rare and arrive late.

  The scaling that does hold is per-feature area. Largest single feature, by `MAX(ST_Area(...))`:

  | | largest feature | approx r10 cells | observed peak RSS |
  |---|---|---|---|
  | survey extent | 77.8 deg2 (~700,000 km2) | ~47M | 11.9Gi (at a 32Gi limit) |
  | damage | 4.06 deg2 (~36,500 km2) | ~2.4M | ~2Gi expected |

  Damage's worst feature is ~19x smaller than survey extent's, so its hex requests **8Gi** and
  survey extent needs its 32Gi. Per AGENTS.md, start there and tune up from OOM signals rather
  than starting high.

## Damage does not need Armada, because feature count is not the workload

The obvious reading is that 4,533,015 damage polygons need Armada while 73,730 survey footprints
fit k8s. Measured, it is the other way round. What drives hex cost is **covered area**, not feature
count:

| | features | total area | H3 r10 cells | cells per chunk |
|---|---|---|---|---|
| `ids-survey-extent-1999-2025` | 73,730 | 95.1M km2 | ~6.3B | ~86M at 74 chunks |
| `ids-damage-1997-2025` | 4,533,015 | 2.39M km2 | ~0.16B | ~0.8M at 200 chunks |

Damage carries 61x the features and about **1/40th the hex work**: they are small sketch polygons,
while a survey footprint is a whole flight area. At 200 completions a damage chunk is roughly 100x
lighter than a survey-extent chunk that k8s already runs at a 5.2Gi peak. So damage runs on the
plain k8s backend at 200 completions x 22,666, and the 200-completion cap is not a constraint here.

⚠️ **Do not measure this with `h3_polygon_wkt_to_cells_string`.** It returns **0 cells for
MULTIPOLYGON** without erroring, and these datasets are 99.05% and 89.5% MULTIPOLYGON, so a naive
per-feature cell count silently reports only the POLYGON remainder. The table above comes from
`SUM(ST_Area(...))` converted at the mean latitude. (`ST_Area_Spheroid` returns `nan` on these
geometries, which is a separate trap.)

## Gotchas already paid for

- **The origin rate-limits.** `www.fs.usda.gov` returns 429 on plain sequential HEADs from one
  host. Staging downloads at concurrency 3 and reruns pull from S3, never the origin.
- **Do not unpack a FileGDB on the `rechunk-scratch` PVC.** It is thousands of small files and
  CephFS charges per-file overhead: ~13 min/region. Unpacking on the node's local disk, and
  building the GPKG there with `OGR_SQLITE_SYNCHRONOUS OFF` (GPKG is SQLite, whose small
  synchronous writes are pathological on CephFS), gives ~30s/region.
- **`_cng_fid` is the dedup key for both datasets.** The natural ids are not unique:
  `SURVEYED_AREA_ID` has 57,575 distinct values over 73,730 rows, `DAMAGE_AREA_ID` 4,338,867 over
  4,533,015.
- **The geometry column is `Shape`**, not `geom`, inherited from the FileGDB.
- **Hex wants ~5 Gi, not 32 Gi.** Measured on the survey-extent hex (74 completions, chunk-size
  1000, res 10 + parents 9,8,0): pods ran at 328Mi-1.4Gi with a **peak of 5,243Mi**. The damage
  armada manifests therefore request **8Gi**, not the 32Gi first generated. On Armada this is not
  a tidiness point: memory is what decides how many placement slots exist, and the
  `armada-pipeline` skill measured a 32Gi request leaving 4,231 of 4,233 jobs unschedulable.

## The survey-extent hex failure, and what actually fixed it

The first survey-extent hex run stranded **68 of 74 chunks**. Two things combined:

- `maxFailedIndexes: 1` with `backoffLimitPerIndex: 2` aborts the whole job once **two** indexes
  exhaust their 3 attempts, killing the in-flight ones;
- `backoffLimitPerIndex` implies `podReplacementPolicy: Failed`, which deletes a failed pod before
  its replacement, so **no logs survived** to say why.

Chunks 4, 18, 24, 25, 35 and 73 were the failures. Raising `--hex-memory` 32Gi -> 64Gi did nothing,
because it was never an OOM. Re-running with `backoffLimit: 0` kept a pod alive and showed the real
error:

```
INTERNAL Error: Parquet writer: 2210203080 uncompressed page size out of range for type integer
```

A single **uncompressed parquet page** of the H3 cell column overflowing the int32 limit: the write
side of the same family as the `stoi` cliff in AGENTS.md. `cng-datasets vector` exposes no
row-group or page-size option, so the only available lever is fewer rows per output file.

**Fix: `--chunk-size 1000` -> `100` for those 6 chunks only** (`ids-survey-extent-1999-2025-hex-subsplit.yaml`),
which cuts rows per file ~10x and takes the page back under the limit. Sub-chunk id `m*10+k` covers
exactly the feature range of original chunk `m`, so coverage is identical with no gaps or overlap.
All 60 sub-chunks succeeded. Two of them (738, 739) write no file and that is correct: they address
features 73800-74000, past the dataset's 73,730.

⚠️ **Sub-splitting must not write into `chunks/`.** Output is named from the chunk id alone, so at
`--chunk-size 100` sub-chunk 40 writes `chunk_000040.parquet` — the filename of the *good* chunk 40
from the 1000-sized run. The sub-split writes to `rechunk-tmp/` and
`ids-survey-extent-1999-2025-merge-subchunks.yaml` moves the files in as `chunk_1NNNNN`, which
cannot collide with the originals' `chunk_000000..chunk_000073`.

`--cleanup` is also removed from both repartition jobs: it deletes `chunks/` on success, and these
chunks cost 9+ hours to rebuild. Remove them deliberately after the coverage gate passes.

## Coverage gate results

`COUNT(DISTINCT _cng_fid)` on the hex must equal the flat parquet's feature count (hex-tuning skill
— a build can look complete while silently short).

| dataset | hex rows | distinct features | flat parquet | match |
|---|---|---|---|---|
| `ids-damage-1997-2025` | 159,415,254 | 4,533,015 | 4,533,015 | yes |

Hex carries `h10` (native) plus `h9`, `h8`, `h0`.

