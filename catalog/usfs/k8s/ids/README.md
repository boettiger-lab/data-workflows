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
- **Hex wants ~5 Gi, not 32 Gi.** Measured on the survey-extent hex (74 completions, chunk-size
  1000, res 10 + parents 9,8,0): pods ran at 328Mi-1.4Gi with a **peak of 5,243Mi**. The damage
  armada manifests therefore request **8Gi**, not the 32Gi first generated. On Armada this is not
  a tidiness point: memory is what decides how many placement slots exist, and the
  `armada-pipeline` skill measured a 32Gi request leaving 4,231 of 4,233 jobs unschedulable.
