# Reproducing "11.3 million acres are already near existing roads"

Issue: boettiger-lab/data-workflows#588. Inputs: `public-usfs/roadless-areas-2001` (#584),
`public-usfs/roadcore-fs` (#588), `public-census/census-2025/roads` (#588),
`public-padus/padus-4-1`, `public-usfs/nfs-surface-ownership` (#585).

## The claim, and what it actually says

The 2026-08-18 rescission announcement:

> "more than a quarter of these lands — **11.3 million acres** — are already near existing roads."

Three things had to be pinned down before this could be checked, and #589/#602 recovered all
three from the agency's own documents:

| Question | Agency answer | Source |
|---|---|---|
| What is "near"? | **0.5 miles**, either side of the road line | DEIS Vol I p. 41 |
| Which roads? | NFS roads from the NRM database (Sept-2025 snapshot) **plus other authorized public roads** | DEIS Vol I fn. 10, fn. 20 |
| Against what base? | The **potentially affected environment**, 40,049,537 ac | DEIS / #589 / #594 |

**The Economic Analysis reports a different number for the same buffer**: 13.3M acres (30.8%)
against the 44.7M rule-affected base with no wilderness deduction, and 22.3M (51.5%) within
1 mile. Both are "more than a quarter", so the press release is not wrong either way — but a
reproduction has to pick a base, and the ~2.0M gap between 11.3M and 13.3M is roughly the
wilderness/WSA/wild-river deduction. Reproducing **both** therefore tests the pipeline twice
and explains the gap rather than assuming it.

## Method

**True geometry, not hex.** Every acreage is

```sql
ST_Area(ST_Intersection(ira_polygon, ST_Buffer(ST_Union_Agg(roads), d)))
```

computed in an equal-area projection. Roads are unioned **before** buffering, so overlapping
buffers are never double-counted. The issue is explicit that this must not run on H3
adjacency: a resolution-8 cell is ~0.7 km², far coarser than the 805 m buffer the question
turns on. The res-10 hex is used only as an independent cross-check and as the #587 join
product.

**Projections, gated before use.** EPSG:5070 (conterminous), EPSG:3338 (Alaska), EPSG:32161
(Puerto Rico). The gate reconciles computed polygon area against the Forest Service's
published `ACRES` column and hard-fails on drift:

| Region | CRS | Computed | Published | Deviation |
|---|---|---:|---:|---:|
| CONUS | EPSG:5070 | 43,617,280 | 43,617,280 | −0.000% |
| AK | EPSG:3338 | 14,778,681 | 14,778,681 | −0.000% |
| PR | EPSG:32161 | 23,734 | 23,734 | −0.001% |

**Distance ladder** (m): 50, 100, 200, 400, **804.672 (0.5 mi)**, 1000, **1609.344 (1 mi)**,
2414.016, 3218.688. The ladder brackets both published distances so the result does not hinge
on one reverse-engineered number, and doubles as the #587 distance bands.

**Six road strata.** `roadcore-all` · `roadcore-ml2to5` (closed ML1 roads excluded) ·
`roadcore-ml1only` · `tiger-drivable` (pedestrian MTFCC S1710/S1720/S1820/S1830 excluded) ·
**`union-deis`** = roadcore-all ∪ tiger-drivable, the reproducible equivalent of the road set
the DEIS buffered · `tiger-all` (informational).

**Three denominators**, all reported: all-IRA 58,419,694 · rule-affected 44,701,002
(`STATE NOT IN ('ID','CO')`) · PAE.

### The PAE reconstruction

The DEIS states 40,049,537 ac = 44.7M − 0.4M non-NFS − 1.3M wilderness − 2.8M wilderness
study areas − 85k wild river segments. Rebuilt independently as rule-affected IRA ∩ NFS
surface ownership (`OWNERCLASS = 'USDA FOREST SERVICE'`, #585), minus PAD-US 4.1
`Des_Tp IN ('WA','WSA','WSR')`:

> **39,962,728 acres — −0.22% against the agency's stated 40,049,537.**

Close enough to use as a denominator, and reported with that error rather than snapped to the
agency figure.

## ⚠️ What this reproduction cannot cover

1. **The regulatory definition is broader than the layer the DEIS buffered.** 36 CFR 294.11
   defines a road as *"a motor vehicle travelway over 50 inches wide"*, including
   **unclassified** roads ("unplanned roads, abandoned travelways, and off-road vehicle
   tracks") and **temporary** roads. The DEIS buffered a narrower operational set. A buffer
   built from the regulatory definition would cover **more** than 11.3M acres.
2. **Temporary roads are not reproducible by anyone.** The Forest Service maintains no
   national database of them (DEIS fn. 20) — they are tracked only locally during project
   implementation. This is a limit on the agency's own analysis as much as on ours.
3. **8,204 RoadCore records have no geometry** (4,745 official miles, 1.3% of the system),
   every one flagged by the source's own `LOC_ERROR` column, 7,430 as `ROUTE NOT FOUND`. They
   cannot be buffered by anyone. Every proximity figure here — and the agency's — is missing
   them.
4. **TIGER is a cartographic product**, not a survey; rural centrelines can sit tens of metres
   off the true roadway. That is comparable to the finest bands in the ladder.

## Results

<!-- filled from ira-road-consolidate; see the job log and ira-road-proximity.parquet -->

## Reproducing

```bash
kubectl apply -n geo-workflows -f analysis-workingset.yaml    # clips + gates projections + PAE
kubectl apply -n geo-workflows -f analysis-proximity.yaml     # 60 shards, the buffer ladder
kubectl apply -n geo-workflows -f analysis-consolidate.yaml   # fact table + solve
kubectl apply -n geo-workflows -f analysis-distance-hex.yaml  # res-10 hex for #587
```

Sharded on `hash(_cng_fid)` and checkpointed per (stratum, region, shard), so a failure or
preemption resumes rather than restarting.

### Geometry simplification, and why it does not change the answer

Road centrelines are digitised far finer than this analysis can use, and `ST_Buffer`'s output
complexity follows its input's. A single roadless area's road union can carry millions of
vertices, and buffering one OOM-killed a 48Gi-class pod on **RoadCore alone** even after the
per-distance loop had cut peak memory ~9x. Centrelines are therefore simplified with
`ST_Simplify(geom, 5.0)` — in metres, in the equal-area projection — before the union.

**5 m is below the positional accuracy of both inputs**, so it cannot be the limiting error:

| | Accuracy | vs 5 m |
|---|---|---|
| RoadCore (EDW, ~1:24,000 source scales) | ~12 m | 2.4x coarser |
| TIGER/Line rural centrelines | tens of metres | far coarser |
| Finest ladder band | 50 m | 10x coarser |
| The 0.5-mile headline distance | 804.672 m | 160x coarser |

It is applied **uniformly to every stratum, region and distance**, so no two reported figures
are computed by different methods. When the simplification was introduced mid-run, the 27
checkpoints already computed without it were discarded rather than merged.

**Validation.** Re-run one shard with `SIMPLIFY_M = 0.0` and compare acreages against the
simplified run; the deviation is recorded in the Results section. If it were ever to exceed a
small fraction of a percent, the tolerance is wrong and the figures should not be published.

### Two performance findings worth keeping

- **The ladder must not be a `CROSS JOIN` over the nine distances.** Doing so keeps nine
  buffered road unions alive per row-vector and OOM-killed a 28Gi pod (exit 137). GEOS
  allocations are invisible to DuckDB's `memory_limit`, so it cannot spill its way out — the
  only lever is how many large geometries are in flight. Looping one distance at a time cut
  peak memory from >28Gi to **2–8Gi**.
- **Idle CPU alongside high memory is the signature of a few enormous geometries**, not many
  small ones. The single-pod version sat at ~1.9 of 16 cores while allocating; that is what
  identified skew and pointed at sharding rather than at more RAM.
