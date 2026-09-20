# GBIF import: compute cost and single-box benchmark

Reference numbers for "what does one full GBIF import actually cost, and could we run
it off-cluster." Captured 2026-09-20. **Not a scoping document** — build scope lives in
the GitHub issue (#662 for the 2026-09 refresh).

## Provenance of each number

| tag | meaning |
|---|---|
| **MEASURED** | from the real 2026-09 run — issue #662 build comment, plus the live `gbif-2026-09-consolidate` Job object in `geo-workflows` |
| *estimate* | never recorded; my assumption, flagged inline |

The **rechunk stage duration is the dominant uncertainty in every total below.** It has
never been timed. Everything else is either measured or small. If you run it again,
**record the wall clock** — it collapses a 3x spread to a point.

## Workload shape

| | |
|---|---|
| Upstream 2026-09-01 snapshot | 9,898 files / 285.3 GB (`gbif-open-data-us-east-1`) |
| Upstream 2026-06-01 snapshot | 8,375 files / 277.8 GB |
| Stage-1 intermediate `chunks/` | 50,384 files / 224.9 GB (deleted after consolidate) |
| Published `2026-06/` output | 154.9 GiB / 166.3 GB, 247 objects |
| h0 partitions | 122; **top 11 hold 83% of output bytes** |
| Densest h0 (`577023702256844799`) | **540.4 M rows, 61 cols (35 VARCHAR), 25.9 GB compressed / 58.5 GB uncompressed, 540 row groups** |

## Measured cluster timings (2026-09 run)

| stage | shape | wall | CPU-hours |
|---|---|---|---|
| Stage 1 hex | 200 x 8 vCPU / 48Gi, par 50 | **22 min** (MEASURED, `succeeded=200 failed=0`) | 147 vCPU-h |
| Stage 2 consolidate | 122 x 4 vCPU / 120Gi, par 15 | **79.7 min** (MEASURED: start 2026-09-09T19:56:07Z, suspend 21:15:52Z; 114 ok / 47 failed) | 80 vCPU-h |
| Stage 2b rechunk | 11 x 8 vCPU / **480Gi**, par 3 | *estimate 2 h/pod* | *176 vCPU-h* |
| Stage 3 taxonomy | 122 x 4 vCPU / 16Gi, par 20 | *estimate 8 min/pod* | *65 vCPU-h* |
| sidecar + publishers + obis | small | *estimate* | *5 vCPU-h* |
| **total** | | **~9.5 h wall** | **~473 vCPU-h** |

Cluster wall clock is dominated by rechunk at parallelism 3, not by the 400-vCPU fan-out.

## GCP-equivalent cost, one import

us-central1 N2 resource rates ($0.031611/vCPU-h + $0.004237/GB-h), validated against the
published `n2-highmem-16` on-demand price of $1.048/h. Priced as **node shapes**, since on
GCP you rent the whole VM, not the pod request.

| stage | node | node-h | on-demand |
|---|---|---:|---:|
| Stage 1 hex | n2-custom-8 / 51GB | 18.3 | $8.64 |
| Stage 2 consolidate | n2-highmem-16 | 19.9 | $20.84 |
| Stage 2b rechunk | n2-highmem-64 | 22.0 | $92.23 |
| Stage 3 taxonomy | n2-standard-4 | 16.3 | $3.16 |
| sidecars | small | 1.0 | $0.28 |
| **TOTAL** | | **77.5** | **$125** |

- **Order of magnitude: ~$100/import on-demand, ~$35 on Spot** (~71% off).
- Spread from the rechunk unknown: **$65-$222** on-demand, **$19-$65** Spot.

### Storage and egress (GCS Standard us-central1, $0.020/GB-mo)

| item | GB | cost |
|---|---:|---:|
| GBIF build output | 166 | $3.33/mo - $40/yr |
| whole `public-gbif` (two snapshots) | 339 | $6.78/mo - $81/yr |
| **all 65 public buckets** | 3,643 | **$73/mo - $874/yr** |
| ops (~50k Class A + ~1M Class B) | - | ~$0.65 (noise) |
| ingest 285 GB from AWS Open Data | - | **$0** - GCP ingress free, AWS Open Data sponsorship pays the egress |

**Egress is the sleeper, not compute or storage.** At $0.12/GB premium tier, one full
download of the 3.64 TB catalog = **$437**, i.e. six months of storage for everything,
in a single `rclone sync`. For an openly-served catalog that line sets the bill. This is
the main thing the NRP arrangement buys.

## Catalog-wide storage footprint (2026-09-20)

**3.50 TiB / 3.86 TB across 91,501 objects in 71 live buckets.**

### How buckets were enumerated (the naive answer is 6% low)

Anonymous `ListBuckets` on the NRP endpoint returns empty, so there is no server-side
enumeration. Bucket discovery must union three sources, and the repo grep must cover
**three reference syntaxes** — `s3://`, `nrp:` and the public-endpoint URL
`https://s3-west.nrp-nautilus.io/<bucket>/`:

| source | finds | misses |
|---|---|---|
| `git grep` on `origin/main`, all 3 syntaxes | 70 refs | anything in an unmerged PR |
| `gh pr diff` over the 21 open PRs | +7 buckets | buckets in no PR |
| STAC catalog walk (384 docs, 322 collections) | cross-check | unpublished builds, infra buckets |

Dropping the `https://` form costs two buckets (`public-population`, `public-ecoregions`)
and was the error in this note's first draft. Using `main` alone costs seven more and
reports 3.31 TiB / 65 buckets, ~198 GiB low — `public-obis` (99.2 GiB) has 35 references in
PR #661 and none on `main`.

**"Referenced" is not "has a build manifest"**, and the two must be tracked separately:
`public-population` passes the first test and fails the second.

### The disagreements are diagnostic

- **Published, in STAC, with no committed build recipe.** `public-population` (30.5 GiB, 126
  objects) appears on `main` only in `catalog/audit/pregate-verify-sweep/RESULTS-2026-08-*.txt`
  — an audit log recording that we *checked* it — with **no manifest anywhere under
  `catalog/`**. Nothing in the repo says how to rebuild it. This is the #678 drift class.
- **Built and staged, never published.** `public-mesic` (5.2 GiB, 112 objects, PR #691) and
  `public-ca-ccca5` (73.1 MiB, 516 objects, PR #676) hold real data with no STAC entry. An
  unmerged PR says nothing about whether the bucket has data — check the bucket.
- **Stale references (5).** `public-biodiversity`, `public-nwi`, `public-redlining` and
  `public-x` are dead names in docs and scripts. **`public-ecoregions` is the one that bites:**
  it does not exist, and the `ecoregion` workflow pointed at it from live code. Three
  references across two files, with **two different errors** — tested with GDAL 3.8.4 against
  the live bucket:

  | reference | URL | result |
  |---|---|---|
  | `k8s/configmap.yaml:79` (convert command) | `public-ecoregions/raw/…` (bucket **and** path wrong) | `ERROR 4` |
  | `k8s/configmap.yaml:3` (generation comment) | `public-ecoregions/raw/…` (bucket **and** path wrong) | `ERROR 4` |
  | `run.sh:11` | `public-ecoregion/raw/…` (path wrong only) | `ERROR 4` |
  | **corrected** | `public-ecoregion/ecoregions.gdb` | opens — `OpenFileGDB`, layer `Biomes_and_Ecoregions_2017` |

  Two independent mistakes: the bucket is `public-ecoregion` (singular), and the GDB sits at
  the **bucket root**, not under `raw/` — that prefix holds only `ak_eco_l3.zip`,
  `us_eco_l3.zip`, `us_eco_l4.zip` and `ecoregion-src.parquet`, while `ecoregions.gdb/` is 64
  objects / 89.3 MiB at top level. `run.sh` happens to get the bucket right and the path
  wrong, so **there was no working recorded invocation anywhere** — the dataset could not be
  rebuilt from the repo.

  The published data was never affected: `public-ecoregion` is live and complete. The failure
  is latent, and it presents misleadingly — a 404 on a *source read*, not `NoSuchBucket` on
  upload, so it reads as a transient fetch error and sends anyone debugging it to the wrong
  end of the job.

  That the GDB is staged *outside* `raw/` is itself the #545/#656 pattern, and is likely the
  mechanism: the source was re-staged to the bucket root and the manifests pointing at it were
  never updated, with nothing re-running the workflow to catch it. Both files arrived in one
  commit (`dd602a3`) already inconsistent with each other.

  **Fixed in #699**, which also corrects three further defects found in the same script: a
  literal `sleep(4)` (Python syntax, fails under bash), `source ../.venv/…` resolving to
  `catalog/.venv` instead of the repo root, and a missing `--namespace geo-workflows` against
  Hard Boundary 3. Note the flag drift between `run.sh` and the configmap's generation comment
  runs the *opposite* way to how it looks: the generated `ecoregion-hex.yaml` carries
  `parallelism: 50` and `memory: 64Gi`, which only `run.sh`'s flags produce, so the comment was
  the stale side. The namespace migration of the committed manifests
  (`namespace: biodiversity`) remains outstanding.

- **On main, deliberately not in STAC** — infra, not datasets: `public-output` (3.9 GiB),
  `public-requests`, `public-grids`.

Neither correction moves the total: `public-population` was already counted via STAC, and
`public-ecoregions` does not exist.

### Top buckets

| bucket | size | objects | sources |
|---|---:|---:|---|
| public-ca30x30 | 389.3 GiB | 2,263 | main+stac |
| public-bioclimate | 360.9 GiB | 1,414 | main+stac |
| public-gbif | 315.9 GiB | 498 | main+stac |
| public-land-cover | 232.6 GiB | 620 | main+stac |
| public-fire | 203.8 GiB | 1,443 | main+stac |
| public-invasives | 183.5 GiB | 771 | main+stac |
| public-wetlands | 177.9 GiB | 5,069 | main+stac |
| public-rap | 160.8 GiB | 1,568 | main+stac |
| public-carbon | 159.1 GiB | 1,224 | main+stac |
| public-usgs-nhd | 138.8 GiB | 328 | main+stac |
| **public-obis** | **99.2 GiB** | **7,351** | **PR#661+stac** |
| **public-commodities** | **60.3 GiB** | **8** | **PR#622+stac** |
| **public-population** | **30.5 GiB** | **126** | **stac only** |

Full per-bucket table with sources: `footprint_v2.json` (regenerate with the union method
above). At GCS Standard $0.020/GB-mo the corrected total is **$77/mo / $926/yr**; one full
egress at $0.12/GB is **$463**.

## Running it on a DGX Spark (GB10)

20 Arm cores (10x Cortex-X925 @3.3GHz + 10x Cortex-A725), 128 GB LPDDR5x **unified**
(shared CPU/GPU), 4 TB NVMe, ConnectX-7 200GbE. Modelled at ~25 cloud-vCPU-equivalents.

| stage | vCPU-h | 1 Spark | 2 Sparks |
|---|---:|---:|---:|
| Stage 1 hex | 146.7 | 5.9 h | 3.0 h |
| Stage 2 consolidate | 79.6 | 3.2 h | 1.6 h |
| Stage 2b rechunk (1.5x spill penalty) | 176.0 | 10.6 h | 5.4 h |
| Stage 3 taxonomy | 65.1 | 2.6 h | 1.3 h |
| sidecars | 5.0 | 0.2 h | 0.2 h |
| network (pull 285 GB + push 166 GB @ 1 Gb/s) | - | 1.0 h | 1.0 h |
| **total** | | **~23 h** (range 20-32) | **~12.5 h** |

**2 Sparks land at roughly cluster parity (~9.5 h).**

### Does a second Spark fix the RAM constraint? No.

Two Sparks link over **ConnectX-7 200GbE / RDMA**, which is message passing, not a
coherent address space — NVLink-C2C is internal CPU<->GPU only. There is no 256 GB pool,
and DuckDB is single-node with no distributed execution. A second box is a second
independent worker: it **halves throughput, it does not raise the per-partition ceiling.**

Scaling limit: makespan >= max(total/N, largest single partition). The densest h0 is 19%
of rechunk work (~2.0 h), so 2 boxes are near-linear (51% makespan on an LPT split) and
the wall appears around **N=5**, where makespan hits the single-partition floor.

### But we are not doomed to spill

**Partition on a prefix of the sort key** (`ORDER BY h1,h2,h3,h4,h5`), sort each group, and
append groups in ascending prefix order. In a lexicographic sort all rows sharing `(h1,h2)`
are contiguous and the blocks appear in `(h1,h2)` order, so this reproduces the global
ordering. Tracked in **#695**.

**The grouping key must be a prefix — `(h1,h2)`, never `h2` alone.** These columns are *not*
a hierarchy: each `h_k` is an independent `h3_latlng_to_cell(lat,lng,k)`, and H3 cells do not
nest exactly across resolutions. On the densest 2026-06 partition
`h3_cell_to_parent(h2,1) <> h1` for **10.22%** of rows, so `h2` does not determine `h1` and
grouping by it would interleave rows the true sort keeps apart.

Measured on `h0=577023702256844799` (540,407,741 rows):

| grouping | groups | largest group | share | valid |
|---|---:|---:|---:|:--:|
| none (today) | 1 | 540.4 M | 100% | - |
| `h1` (prefix, len 1) | 13 | 201.2 M | 37% | yes, too coarse |
| `h2` alone | 55 | 87.7 M | 16% | **NO - not a prefix** |
| **`(h1,h2)` (prefix, len 2)** | **97** | **75.6 M** | **14%** | **yes** |

75.6 M rows implies a ~60 GB working set (scaled from the 440 GB the 540 M-row sort was
given) - inside the 120Gi tier, and inside a Spark's ~100 GB usable. Recurse to
`(h1,h2,h3)` if a group is ever still too big.

Write groups sequentially with `pyarrow.parquet.ParquetWriter` to keep #279's one-file-per-h0
at 1M-row row groups. Note "byte-identical output" is not achievable even today: the sort key
is far from unique and the job runs `preserve_insertion_order=false`, so the right check is
that the output *is sorted*, not that it matches a previous file.

Dedup is a non-issue for this snapshot: the geocoded source has **zero** duplicate gbifid
(3,729,438,201 total - 159,283,243 null-coordinate = 3,570,154,958, matching both the hex row
count and the distinct-gbifid count). Keep the global post-write assertion as the guard.

This removes spill on the cluster too, and would let the 480Gi rechunk tier disappear.

### GBIF's h-columns are not a parent chain (#697)

A separate defect found while working #695. The `h0` hive partition key is not the H3 parent
of the row's native cell, in the two hand-written occurrence pipelines only:

| collection | built by | rows | `cell_to_parent(native,0) <> h0` |
|---|---|---:|---:|
| `gbif-derived` 2026-09 | bespoke | 3,570,154,958 | **8.713%** |
| `obis-derived` 2026-09-09 | bespoke | 228,567,957 | **7.675%** |
| `inaturalist-ranges` | cng-datasets | 377,963,890 | **0** |
| `unep-wcmc-coral-reefs-points` | cng-datasets | 925 | **0** |

The coral row is the control: same shape as GBIF/OBIS (point geometry, native h8, h0 partition
key) and exact. So the cause is not geometry — it is that `cng-datasets` derives parents with
`cell_to_parent` while the occurrence scripts recompute every resolution from the coordinate.

Consequence: pruning to `h0 = h3_cell_to_parent(h8,0)` silently misses ~8.7% of GBIF and ~7.7%
of OBIS rows, and 0% everywhere else — a query pattern validated on another collection
transfers and returns quietly incomplete results. **`h8 = h8` joins, including GBIF<->OBIS, are
exact and unaffected**; only derived-parent lookups break.

### Ephemeral storage is a genuine Spark advantage

Peak footprint is ~1.1 TB (285 source + 225 chunks + 166 out + ~400 spill) against ~3 TB
spare. The cluster jobs are squeezed the other way: 50Gi ephemeral default, and the
`rechunk-scratch` PVC added as a spill backstop was **dropped after CSI attach timeouts**
(commit fa98a6b). Local NVMe removes that whole failure class. The Spark also keeps the
225 GB of `chunks/` local instead of round-tripping it through S3 — part of why it closes
more of the gap than core count suggests.

### Portability: clean, with one rebuild

| component | arm64? | evidence |
|---|---|---|
| `ghcr.io/boettiger-lab/datasets:latest` | **NO — amd64 only** | manifest lists one platform; `unknown/unknown` is buildx provenance |
| `rocker/ml-spatial` | yes | manifest has linux/arm64 |
| `rocker/geospatial` | yes | manifest has linux/arm64 |
| `rocker/ml-verse` | no | amd64 only |
| DuckDB `h3` community ext | yes | HTTP 200 for `linux_arm64` on v1.3.2 / v1.4.0 / v1.4.1 |
| duckdb / pyarrow / boto3 wheels | yes | manylinux_2_28_aarch64 (duckdb 1.5.5, pyarrow 25.0.1), boto3 pure-python |

So it is an **arm64 image rebuild, not a porting project** — base on `rocker/ml-spatial`.
Do not run the amd64 image under qemu; the estimates above become meaningless.

### The GPU contributes nothing

This is a DuckDB CPU + I/O pipeline — H3 indexing, sort, zstd. The 1 PFLOP FP4 Blackwell
is idle for the whole run. Involving it means rewriting onto cuDF/RAPIDS, and cuSpatial
has no H3 binding.

## Status of the 2026-09 build (checked 2026-09-20)

The `gbif-2026-09-consolidate` **Job object** is still `Suspended` at 114/122 since
2026-09-09T21:15:52Z (`failedIndexes 4,12,15,19-21,34`, index 95 never started) — but the
**build itself completed**. `s3://public-gbif/2026-09/` holds the full 247-object shape:
122 hex partitions / 157.9 GiB / **3,570,154,958 rows**, 122 taxonomy partitions, and all
three sidecars. The rechunk job evidently cleared the 8 stragglers and the later stages ran.

What has *not* happened is publication: `stac-collection.json` still points at `2026-06`,
and #662's acceptance checks are open. Do not read the suspended Job as "the build failed."
