# USFS administrative / proclaimed / surface-ownership layers — build notes

Four layers ingested together under issue
[boettiger-lab/data-workflows#585](https://github.com/boettiger-lab/data-workflows/issues/585):
`nfs-surface-ownership`, `administrative-forest`, `proclaimed-forest`, `ranger-district`.
They are the **denominator** for the Roadless Rule rescission audit whose numerator is
`roadless-areas-2001` (#584). This file covers all four; the per-layer directories hold only
manifests.

Second dataset group in the `public-usfs` bucket, which #584 created and registered.

## Sources

All under `https://data.fs.usda.gov/geodata/edw/edw_resources/shp/`, staged to
`s3://public-usfs/raw/` by `catalog/usfs/k8s/admin-forest/usfs-admin-stage-raw.yaml`
(job `usfs-admin-stage-raw`, run 2026-08-25). Every file matched the byte size recorded on
#585 on 2026-08-19, so upstream has **not** republished in place.

| Archive | Bytes | Ingested as |
|---|---:|---|
| `S_USA.SurfaceOwnership.zip` | 130,767,416 | `nfs-surface-ownership` |
| `S_USA.AdministrativeForest.zip` | 45,012,944 | `administrative-forest` |
| `S_USA.ProclaimedForest.zip` | 44,085,531 | `proclaimed-forest` |
| `S_USA.RangerDistrict.zip` | 58,498,963 | `ranger-district` |
| `S_USA.BasicOwnership.zip` | 107,609,121 | **not ingested** — see below |

`S_USA.OwnershipBasic` and `S_USA.ProclaimedForest_ProclaimedGrassland` return 404; they do
not exist.

## Measured schema (from the staging job's probe, 2026-08-25)

All four layers are **EPSG:4269 (NAD83)** and are reprojected to EPSG:4326 by
`cng-convert-to-parquet`, per house convention. Every layer carries `GIS_ACRES`, `SHAPE_AREA`
and `SHAPE_LEN` as **per-feature totals**.

| Layer | Features | `SUM(GIS_ACRES)` | Fields |
|---|---:|---:|---|
| `SurfaceOwnership` | 117,190 | 204,298,788 | 26 fields; `OWNERCLASS`, `NFSLANDUNI`, `REGION`, `LANDSTATUS`, … |
| `AdministrativeForest` | 112 | 236,835,251 | `ADMINFORES`, `REGION`, `FORESTNUMB`, `FORESTORGC`, `FORESTNAME`, `GIS_ACRES`, `SHAPE_AREA`, `SHAPE_LEN` |
| `ProclaimedForest` | 154 | 225,145,181 | `PROCLAIMED`, `FORESTNAME`, `GIS_ACRES`, `SHAPE_AREA`, `SHAPE_LEN` |
| `RangerDistrict` | 503 | 237,098,674 | `RANGERDIST`, `REGION`, `FORESTNUMB`, `DISTRICTNU`, `DISTRICTOR`, `FORESTNAME`, `DISTRICTNA`, `GIS_ACRES`, `SHAPE_AREA`, `SHAPE_LEN` |
| `BasicOwnership` | 327 | 240,162,289 | `BASICOWNER`, `OWNERCLASS`, `GIS_ACRES`, `REGION`, `FORESTNAME`, … |

### ⚠️ No layer carries a state attribute

Checked every field of all four layers: **none has a STATE column**, and none has any other
state discriminator. This matters because #585's acceptance criteria are stated per-state
(Montana). Unlike `roadless-areas-2001`, where the Idaho/Colorado split is a `STATE` predicate,
**Montana here can only be obtained spatially.**

Method adopted: derive MT by H3 join against census state polygons on the shared `h8` key,
staying in hex space, and cross-check the result against `pad-us-4-1/fee` filtered to
`Mang_Name='USFS'`, `State_Nm='MT'` (independently measured at 17,254,331 ac). Acreage is taken
from the H3 footprint over DISTINCT cells, **not** by summing `GIS_ACRES`, which is a
per-feature total.

## The ownership decision — settled on measurement

`SurfaceOwnership` filtered to `OWNERCLASS = 'USDA FOREST SERVICE'` is the NFS denominator.

| Source | USFS acres |
|---|---:|
| `S_USA.SurfaceOwnership`, `OWNERCLASS='USDA FOREST SERVICE'` | **193,174,461** |
| `pad-us-4-1/fee`, `Mang_Name='USFS'` (already in the catalog) | 193,275,732 |
| 2026-08-18 announcement | "193 million" |

Two unrelated publishers agree to **0.05%** (101,271 ac apart), and both land on the
announcement's figure. `OWNERCLASS` is a clean three-value vocabulary:

| `OWNERCLASS` | Acres |
|---|---:|
| `USDA FOREST SERVICE` | 193,174,461 |
| `NON-FS` | 10,993,819 |
| `UNPARTITIONED RIPARIAN INTEREST` | 130,508 |

### The envelope layers are not ownership, and the gap is enormous

| Layer | Features | `SUM(GIS_ACRES)` | vs ownership |
|---|---:|---:|---:|
| Surface ownership (USFS only) | 117,190 total | 193,174,461 | — |
| `ProclaimedForest` | 154 | 225,145,181 | **+31,970,720** |
| `AdministrativeForest` | 112 | 236,835,251 | **+43,660,790** |
| `RangerDistrict` | 503 | 237,098,674 | +43,924,213 |
| `BasicOwnership` (all classes) | 327 | 240,162,289 | +46,987,828 |

Using `AdministrativeForest` as the NFS denominator inflates it by 43.7M acres (+22.6%), which
deflates any "share of NFS land" percentage by ~18% relative. That is the specific error #585
was opened to prevent, and it is why the envelopes are ingested **alongside** ownership rather
than instead of it: a reader will mistake them for ownership, so the STAC has to say plainly
which is which.

### Why `BasicOwnership` is not ingested

Rejected on resolution, not on vocabulary. **Correcting the record on #585:** the issue comment
stated `BasicOwnership` "cannot be filtered to NFS without a lookup we do not have" because
`BASICOWNER` holds opaque numeric ids (98, 107, 32, …). The probe shows it *also* carries an
`OWNERCLASS` field, so that particular objection does not hold. The decisive objection stands
untouched: it is a **327-feature dissolve** against `SurfaceOwnership`'s 117,190 features.
Inholdings are the entire analytical point of preferring ownership over an envelope, and a
327-feature dissolve cannot represent them.

## Pipeline

| Setting | Value | Why |
|---|---|---|
| H3 native | `10`, parents `9,8,0` | matches #584 so IRA and NFS join cell-for-cell; `h8` is the catalog join key |
| CRS | EPSG:4269 → 4326 | house convention |
| bucket | `public-usfs` | created + root-registered by #584; `setup-bucket` and `workflow-rbac` are **not** re-run |
| namespace | `geo-workflows` | passed explicitly; the generator defaults to the legacy `biodiversity` |
| extent | national, incl. AK and PR | not clipped |
| ownership filtering | none at ingest | all `OWNERCLASS` values retained; NON-FS inholdings are the reason this layer was chosen. Filter in SQL. |

### ⚠️ `--chunk-size` must be patched after generation

`cng-datasets workflow` **hardcodes `--chunk-size 1000`** in the hex step. It is not derived
from `--max-completions` and no CLI flag exposes it, although `cng-datasets vector` itself
accepts `--chunk-size`. `AGENTS.md:263` states armada "allows `--chunk-size 1`", but the
generator provides no way to request it.

Left as generated, the three envelope layers would be silently broken: with 112 features and
chunk-size 1000, chunk-id 0 hexes **all 112 features in one pod** (~64M res-10 cells) while
chunk-ids 1–111 address rows 1000–111,999 and do nothing — 111 no-op pods and one pod carrying
an entire national layer.

The envelope layers are therefore patched to `--chunk-size 1` (one feature per pod, the reason
for using armada at all), applied to all three copies per layer — standalone job, armada job,
and the configmap-embedded copy — so no route picks up a stale value.

| Layer | completions × chunk-size | features | coverage |
|---|---|---:|---|
| `administrative-forest` | 112 × 1 | 112 | 112 ≥ 112 ✓ |
| `proclaimed-forest` | 154 × 1 | 154 | 154 ≥ 154 ✓ |
| `ranger-district` | 503 × 1 | 503 | 503 ≥ 503 ✓ |
| `nfs-surface-ownership` | 118 × 1000 | 117,190 | 118,000 ≥ 117,190 ✓ |

`nfs-surface-ownership` keeps chunk-size 1000, where it is correct. Its 118 completions are set
explicitly against the **#494 silent-coverage-cap** trap — features hexed = `max-completions ×
chunk-size`, and the default 200 caps a build with no error and no failed job. Post-build,
`COUNT(DISTINCT _cng_fid)` on hex must equal the flat feature count for every layer.

### Backend

`ranger-district` (503 completions) exceeds the k8s 200-completion cap and requires armada.
`administrative-forest` (112) and `proclaimed-forest` (154) fit within the cap. Memory starts at
16Gi for the envelope layers and 8Gi for `nfs-surface-ownership`; per the `hex-tuning` skill,
over-asking is the standard failure mode here, and with one feature per pod an OOM costs a
single feature and is a tuning signal, not a failure. On OOM, lower `--intermediate-chunk-size`
before raising `--hex-memory`.

## Hex caveats

One hex row = one (feature, cell) pair. `GIS_ACRES`, `SHAPE_AREA` and `SHAPE_LEN` are
per-feature totals **repeated on every cell the feature covers**; dedup key is `_cng_fid`.
Derive area from the H3 footprint over DISTINCT cells instead of summing `GIS_ACRES`. This is
flagged at the hex asset description level in each collection's STAC.

**Dateline — checked, not inherited.** Measured bounding boxes are `-150.008 .. -64.734`
(ownership) and `-150.008 .. -65.700` (the three envelopes), western limit identical to #584.
**These layers do not reach the Aleutians**, so the antimeridian is never crossed. An earlier
note in this file predicted Aleutian coverage and a live seam risk; the data refutes it.

h0 `576707042908045311` — the cell AGENTS.md flags for dateline problems — **is** populated in
`nfs-surface-ownership`, but legitimately: 661 features / 2,002,031 hex rows spanning longitudes
-150.008 to -133.022, entirely in the western hemisphere with no wrap to +180. Same verdict as
#584, reached by measurement on this layer rather than carried over from it.

## Acceptance criteria — measured against the ingested data

### Method for state attribution

**No layer carries a state attribute**, so Montana is obtained spatially. Nothing about this is
Montana-specific — any state needs the same step; Montana is simply the state the claim is about.

The units are **NFS `h10` cells**. `h8` is the shared join key against
`census-2024/state` (native res 8), so a state mask is applied at `h8` and area is then summed
over the `h10` footprint. Measuring in `h10` matters: an `h8` cell is ~0.74 km² and is counted
whole if a feature merely clips it, and that bias is **not uniform** — it scales with how
fragmented the set is:

| Set | `h8`-implied acres | true acres | `h8` bias |
|---|---:|---:|---:|
| MT NFS (contiguous) | 20,370,770 | 17,345,447 | +17.4% |
| MT IRA (fragmented) | 8,450,865 | 6,448,465 | **+31.1%** |

Computing the ratio at `h8` therefore inflates it (41.5% vs the correct 37.0%). All figures below
are `h10` footprints. Designated wilderness is the one component only available at `h8`
(`pad-us-4-1/combined` is native res 8) — it is applied as an `h8` parent mask **restricted to NFS
`h10` cells**, which validates well: 3,435,932 ac against PAD-US's own `GIS_Acres` of 3,441,403,
a **-0.16%** difference.

### 1. National reconciliation against the 193M-acre figure ✅

| Source | USFS acres | vs announcement |
|---|---:|---:|
| `SurfaceOwnership`, `OWNERCLASS='USDA FOREST SERVICE'` (`GIS_ACRES`) | **193,174,461** | +0.09% |
| `pad-us-4-1/fee`, `Mang_Name='USFS'` (independent publisher) | 193,275,732 | +0.14% |
| This layer's H3 res-10 footprint | 192,895,244 | -0.05% |
| Announcement | "193 million" | — |

**Residual documented:** the two publishers differ by **101,271 acres (0.05%)**. The H3 footprint
sits 279,217 ac (-0.14%) below the `GIS_ACRES` total, the same small negative bias #584 measured
(-0.25%) — cells are dropped where a polygon covers less than one res-10 cell.

### 2. MT NFS acreage under both definitions ✅

| Definition | MT acres |
|---|---:|
| **Surface ownership** (`OWNERCLASS='USDA FOREST SERVICE'`) | **17,345,447** |
| `pad-us-4-1/fee` USFS, `State_Nm='MT'` (cross-check) | 17,254,331 (+0.53%) |
| **Proclaimed boundary** (`proclaimed-forest`) | _pending build_ |

Two unrelated sources agree to **0.53%**, computed differently — PAD-US pre-splits features by
state; this is a cell-wise mask. Agreement is evidence, not tautology.

### 3. MT IRA ÷ MT NFS — the "nearly 60 percent" claim ❌ REFUTED as stated

| Quantity | Acres | Share of MT NFS |
|---|---:|---:|
| MT NFS (surface ownership) | 17,345,447 | 100% |
| MT IRA on NFS | 6,416,470 | **36.99%** |

**36.99%, not "nearly 60 percent."** For 60% to hold, the denominator would have to be 10,659,001
ac — 6.7M acres below Montana's actual NFS surface ownership. And no USFS denominator rescues the
claim *in the direction attempted*: the proclaimed and administrative envelopes are **larger** than
surface ownership, so substituting them pushes the share **down**, not up.

### 4. The wilderness hypothesis ✅ CONFIRMED

#585 flagged this as the first thing to test and explicitly declined to assert it. It holds.

| Quantity | Acres | Share of MT NFS |
|---|---:|---:|
| MT IRA on NFS | 6,416,470 | 36.99% |
| MT USFS designated wilderness on NFS | 3,435,932 | 19.81% |
| less overlap (IRA ∩ wilderness) | -103,611 | -0.60% |
| **IRA ∪ wilderness** | **9,748,791** | **56.20%** |

**56.20%** is fairly described as "nearly 60 percent"; #585 predicted ≈57%. So the claim is
reconcilable **only** if "Forest Service land" is read as *roadless areas plus designated
wilderness*, not as roadless areas alone. The union is computed over **DISTINCT cells**, never by
adding acreages — IRA and wilderness overlap by 103,611 ac and summing would double-count.

### 5. Roaded-NFS comparison stratum ✅ DERIVABLE

NFS minus IRA (#584) minus designated wilderness (`pad-us-4.1`), as a DISTINCT-cell set difference:

| Stratum | Acres | Share of NFS |
|---|---:|---:|
| NFS surface ownership (h10 footprint) | 192,895,244 | 100% |
| less inventoried roadless on NFS | -57,793,130 | 29.96% |
| less designated wilderness on NFS | -36,277,809 | 18.81% |
| **Roaded NFS (the counterfactual)** | **100,720,169** | **52.21%** |
| _MT roaded NFS_ | _7,596,656_ | _43.80%_ |

This is the missing comparison group for every hazard/treatment claim in the `roadless` set: a
"40% of IRAs are high hazard" figure is uninterpretable without the same figure for this stratum.
57,793,130 of the 58,419,694 published IRA acres fall on NFS surface ownership (98.9%), the
remainder being IRA over inholdings and other ownership inside the envelope.

### 6. Build-integrity gates

| Gate | `nfs-surface-ownership` |
|---|---|
| Feature count, flat | 117,190 ✅ |
| `SUM(GIS_ACRES)` flat | 204,298,788 ✅ |
| `COUNT(DISTINCT _cng_fid)` on hex | 117,190 — equals flat, no #494 silent cap ✅ |
| Hex/flat agreement, deduped `SUM(GIS_ACRES)` | 204,298,788 — exact ✅ |
| Hex job | `Complete`, `failedIndexes: []`, 118/118 ✅ |
| h0 partition gate | PASS, 9 == 9 populated, no empty partitions ✅ |
| NULL finest-parent (`h10`) cells | 0, so no #311 note required ✅ |
| Dateline seam | no wrap; see above ✅ |
| Per-feature duplication | all attributes REPEATED; raw `SUM(GIS_ACRES)` inflates **161,918x** ✅ |

`SURFACEOWN` has 117,190 distinct values — exactly the row count — so each input row is one
logical feature and **axis-2 (upstream) duplication does not apply**; `_cng_fid` is a sufficient
dedup key.

_Envelope-layer gates pending their builds._
