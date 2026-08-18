# Agent Instructions: Dataset Processing

You work in `data-workflows`, which uses `cng-datasets` to convert geospatial data into cloud-native formats on Kubernetes. This file tells you everything you need.

## ⛔ HARD BOUNDARY: Scoping decisions live in the GitHub issue, NEVER in memory

Every decision that defines *what* a dataset task delivers — **spatial extent** (full upstream coverage vs. a regional clip), **H3 resolution**, reducer, source product/version, target bucket and naming, acceptance criteria — MUST be written into the GitHub issue before you act on it. Sessions are disposable: the laptop dies, agent memory is wiped, a different agent picks up the task. The issue is the single source of truth that survives all of that. Treat yourself like any professional developer — nobody is expected to carry scope "in their head," and you must not rely on agent memory (`~/.claude/.../memory`) for scope. Memory is for *how you work*, never *what a task delivers*.

- **Before building:** if the issue does not state the extent, resolution, and acceptance criteria explicitly, the issue is underspecified. **Stop, propose the scope, get agreement, and edit the issue to record it** (`gh issue edit` / a scoping comment) before running cluster jobs. A vague label like "the wyoming group" is not a scope.
- **When scope changes mid-task** (e.g. "extend to the full upstream extent, not the regional clip"): update the issue body in the same turn you learn it — don't just remember it.
- **Never infer scope** from the bucket name, an existing clipped COG, or a prior build's resolution. Those are artifacts of how an earlier (possibly wrong) pass happened to run, not statements of intent.
- A reviewer (human or agent) must be able to read the issue alone and know exactly what to build. If you found yourself reconstructing scope from code, S3 layout, or memory, that is the signal the issue needs updating.

## ⛔ HARD BOUNDARY 0: Big-data compute runs on the cluster, NOT your laptop

For ANY query/scan/aggregation over S3 parquet — catalog data **and** large intermediate/build files (e.g. a 24 GB consolidated GeoParquet) — use the **`mcp__duckdb-geo__query` MCP server**. It runs on generously-provisioned cluster metal with the **internal NRP S3 endpoint** and a **100 Gb/s** network, and DuckDB **streams** (larger-than-memory spills to disk) — so it does not hit the RAM limits or the slow public endpoint (~12 MB/s) that bottleneck the laptop.

- ❌ Do NOT shell out to local `duckdb`/`python -c "import duckdb"`/`uv run --with duckdb`.
- ❌ Do NOT spin up k8s jobs running `pyarrow`/`geopandas`/`duckdb` to scan big parquet, and never read big parquet over `https://s3-west.nrp-nautilus.io/...` (public endpoint) — use `s3://` (internal) inside jobs and the MCP for queries.
- ✅ Verify counts/schema, scan for pathological geometries/bbox/validity, distinct counts, ST_*/h3_* → `mcp__duckdb-geo__query`.
- The tool is deferred: `ToolSearch select:mcp__duckdb-geo__query` first. **If ToolSearch returns no match the MCP server is disconnected — ask the user to reconnect it; do NOT fall back to the slow RAM-bound path.**
- Heavy *writes/transforms* the MCP can't do still run as cluster jobs, but over the **internal** endpoint (`rook-ceph-rgw-nautiluss3.rook`, `AWS_HTTPS=false`), never the laptop.

## ⛔ Serialization standard: DuckDB httpfs `stoi` crash on oversized column chunks

The MCP can abort with **`SQL Error: stoi`** when reading GeoParquet over S3/httpfs. The root cause is a **DuckDB httpfs bug on large Parquet column chunks** — not the CRS tag, writer, or geometry content. Fully diagnosed in datasets [#106](https://github.com/boettiger-lab/datasets/issues/106).

### What triggers it

A single Parquet column chunk in the **~2.8–2.88 GB compressed / ~3.73–3.84 GB uncompressed** range causes the httpfs reader to abort with `stoi`. No spatial function needed — `SELECT COUNT(geom)` (which decodes the column) is sufficient to crash; `SELECT COUNT(*)` (footer only, no decode) is fine. **Local file reads always work** — this is exclusively an httpfs path bug.

```sql
SELECT COUNT(*)  FROM read_parquet('https://…/repro-100000.parquet');   -- ✅ OK
SELECT COUNT(geom) FROM read_parquet('https://…/repro-100000.parquet'); -- ❌ stoi
```

The crash appears "plan-dependent" because queries that skip decoding the geometry column (e.g. filtered reads that never touch the oversized chunk) avoid it. Every individual row is valid; the data is not corrupt.

### What does NOT matter

| Hypothesis | Verdict |
|---|---|
| `creator: geopandas` | ❌ cng-convert-written file crashes identically |
| `OGC:CRS84` vs `EPSG:4326` CRS tag | ❌ re-tagging as `EPSG:4326` still crashes |
| Plain DuckDB `COPY` re-write | ❌ still crashes |
| A single pathological geometry | ❌ local read of same file returns all rows |

### Prevention (the real fix)

**Keep row groups small enough that no single geometry column chunk exceeds ~1 GB compressed.** For large-feature geometry (complex multipolygons, national-scale data), the default `--row-group-size 100000` can pack a single chunk well past the 2.8 GB cliff. Use `--row-group-size 2000` as a safe default for geometry-heavy datasets, or estimate `avg(octet_length(ST_AsWKB(geom)))` on a sample and size accordingly. Tracked in cng-datasets [#106](https://github.com/boettiger-lab/datasets/issues/106).

### Mitigation if a published file already crashes

Use `s3://` (internal endpoint, not `https://`) inside cluster jobs — the httpfs path is the public endpoint only. For MCP queries (which always go over https), re-publish the file with smaller row groups via a cluster DuckDB job:

```sql
COPY (SELECT * FROM read_parquet('s3://bucket/file.parquet'))
TO 's3://bucket/file-rg2000.parquet'
(FORMAT PARQUET, ROW_GROUP_SIZE 2000, COMPRESSION ZSTD);
```

### geopandas-written files

Still avoid publishing geopandas-written GeoParquet — use the cng-datasets DuckDB-native path. But the failure mode is different (geoarrow extension type, any DuckDB version; upstream [duckdb/duckdb#21691](https://github.com/duckdb/duckdb/issues/21691)) and orthogonal to the httpfs chunk-size crash above.

## ⛔ HARD BOUNDARY 1: NRP S3 is Canonical for STAC and Data

Canonical STAC/data live on NRP S3 (`s3://public-<bucket>/`, public URL `https://s3-west.nrp-nautilus.io/<bucket>/...`). **This repo does NOT contain STAC JSON or README files.** Never create `catalog/*/stac/`, never `git add` STAC JSON or README.

- Read: `curl https://s3-west.nrp-nautilus.io/<bucket>/stac-collection.json`
- Write: edit in `/tmp/`, then `rclone copyto /tmp/... nrp:<bucket>/...`

## Git workflow

**Use a worktree for every dataset task.** Sessions in this repo frequently open on a stale in-flight branch (e.g. last week's paused ingest); committing there silently mixes unrelated work and forces cherry-picks later. Before staging changes:

1. `git branch --show-current` — if it isn't the branch you want, invoke `superpowers:using-git-worktrees` to spin up an isolated workspace off `origin/main`.
2. Work in the worktree, commit, push, open the PR from there.
3. Read-only investigation can stay on whatever branch is checked out — the gate is *committing*, not exploring.

## ⛔ HARD BOUNDARY 2: Do NOT Touch the `cng-datasets` Tool Repo

Work only in `data-workflows`. Do not edit/commit/push/PR to `boettiger-lab/datasets` or any other repo. If `cng-datasets` has a bug: file a GitHub issue on `boettiger-lab/datasets` with a minimal reproducible example (see below), tell the user, and wait. Prior hotfixes have caused production failures — the tool has tests and a deploy pipeline, and unreviewed hotfixes bypass them.

### Bug reports must include a tested MRE

Every bug report MUST include code you have **actually run** that reproduces the error. Circumstantial evidence (e.g. "the S3 parquet has bad coords, so the tool is broken" — S3 could be stale) is not an MRE.

The MRE must:
1. **Isolate to the tool** — verify the upstream input is correct first (e.g. `ogrinfo` on the raw source).
2. **Run the tool locally and capture bad output** — actually execute `cng-convert-to-parquet`/`cng-datasets`. Don't infer from downstream artifacts.
3. **Show expected vs actual** with concrete values.
4. **Be minimal** — one feature, one file.

Template:
```bash
# 1. Input is correct:
ogrinfo /vsizip/source.zip -al -where "NAME='X'" | grep 'POLYGON\|Extent'
# 2. Run the tool:
cng-convert-to-parquet source.zip /tmp/output.parquet
# 3. Show the bug:
python3 -c "import duckdb; c=duckdb.connect(); c.execute('LOAD spatial;');
print(c.execute(\"SELECT ST_AsText(ST_Envelope(geom)) FROM read_parquet('/tmp/output.parquet') WHERE NAME='X'\").fetchdf())"
# → wrong: xmin=38.32 (lat) instead of -120.07 (lon)
```

## ⛔ HARD BOUNDARY 3: Jobs run in `geo-workflows`, not `biodiversity`

**Status (2026-07-05): MIGRATION IN PROGRESS** (geo-agent-ops#21). `geo-workflows`
is provisioned as the least-privilege job-submission namespace; `biodiversity` keeps
the fleet apps + MCP + LLM proxy (and its 26 app/LLM/private secrets). Existing
`biodiversity` job manifests are **legacy artifacts** — reshape them by regenerating
with `--namespace geo-workflows` (below). Use `geo-workflows` for all new and re-run
work; any residual `biodiversity` reference in an old manifest is legacy, not a target.

**Why.** `geo-workflows` holds ONLY NRP-canonical credentials (`aws` + `rclone-config`).
A confused or compromised job there can damage only *recoverable* NRP-canonical data —
it cannot reach the app / LLM / oauth / private-data secrets that live in
`biodiversity`. That confinement is the whole point; **never reintroduce other
credentials into `geo-workflows`.**

**How to target it — the CLI already supports it, just pass the flag:**
```bash
cng-datasets workflow        --namespace geo-workflows  ...   # all other args unchanged
cng-datasets raster-workflow --namespace geo-workflows  ...
```
It stamps the namespace on every generated manifest (and, for armada, the queue).
Apply and monitor with `-n geo-workflows`:
```bash
kubectl apply -n geo-workflows -f catalog/<dataset>/k8s/<name>/workflow-rbac.yaml   # once
kubectl apply -n geo-workflows -f .../configmap.yaml -f .../workflow.yaml
kubectl -n geo-workflows get jobs | grep <name>
```

**What's already provisioned there** (manifest: geo-agent-ops `k8s/geo-workflows-provisioning.yaml`):
- Secrets `aws` (NRP S3) + `rclone-config` (nrp-only). **Nothing else.**
- Orchestrator SAs `cng-datasets-workflow` / `workflow-runner` (create/watch/delete child Jobs).
- Child job pods run as the `default` SA, **hardened to mount no k8s token** (they need only S3).
- `rechunk-scratch` PVC (2Ti RWX) for >50Gi scratch (binds once Ceph is healthy).
- **No enforced ResourceQuota** — but keep the good-practice targets anyway:
  **≤200 simultaneous pods** and **≤50Gi ephemeral per job** (`limits.ephemeral-storage`),
  especially on large-completion fan-out jobs. Oversubscribing is antisocial on shared nodes.

**Credential rule — three data classes (the redistribution axis is NOT the credential axis):**
- **Classes 1 & 2 — public-bucket data.** Includes the *non-redistributable* sets
  (WDPA / WD-OECM, IUCN, ICCA, HydroBASINS): those are ordinary `public-*` buckets on
  NRP + MinIO backup, merely **excluded from the source.coop mirror** (a mirror-scope
  policy, not a credential boundary). Their build jobs **read/write NRP only.** Stage raw
  under `s3://<bucket>/raw/` (Step 1b); **never** write intermediates to MinIO with a
  personal key; reading public data needs **no** credential. No MinIO cred in `geo-workflows`.
- **Class 3 — strictly private data** (`private-wyoming`, `private-tpl`): single-homed on
  MinIO, **not on any NRP bucket**. Mount a **scoped, single-bucket, on-demand EXPIRING
  MinIO mint** for that one bucket (`mc admin user svcacct add <parent> --policy <one-bucket>
  --expiry …`; the `wyoming-publish` model) — **never** a standing broad MinIO key.

### Why the workflow `rclone-config` is nrp-only

Build jobs run in `geo-workflows` with NRP-canonical credentials only. The MinIO and source.coop
remotes live in a different secret, in a namespace this repo has no membership in, owned by
geo-agent-ops. The separation is deliberate and two-sided: a confused or compromised build job
cannot reach the backup credentials, so it cannot propagate a delete or a corruption into the
backups. Recovery, not just prevention.

What that means for a build, concretely:

- **A workflow-namespace `rclone-config` holding only `[nrp]` is CORRECT** — not a
  missing-remote bug. (Verified 2026-07-12 during #392 in both `geo-workflows` and
  `biodiversity`: internal endpoint `http://rook-ceph-rgw-nautiluss3.rook`,
  `upload_concurrency=16`, `chunk_size=64Mi`.)
- **Never add a MinIO or source.coop remote — or the `rclone-backup` secret — to a workflow
  namespace.** That re-opens the boundary the split exists to close.
- **Treat NRP canonical as corruptible.** It is not the last copy, and restoring it is not your
  job and not within your reach.

**MinIO matters to a build for exactly one reason:** it is the canonical, **sole** home for
class-3 private data (`private-wyoming`, `private-tpl`, …), which lives on no NRP bucket and no
mirror — losing MinIO loses it. Reading such an input through a scoped, expiring, single-bucket
mint (above) is normal, and is the only MinIO access a build job ever has. MinIO's other roles
(backup vault; the fine-grained-IAM tier NRP lacks) belong to geo-agent-ops.

## What You Produce

**Vector datasets (GDB, Shapefile, GeoPackage, GeoParquet):**
| Format | File | Use |
|---|---|---|
| GeoParquet | `dataset.parquet` | DuckDB/Polars queries |
| PMTiles | `dataset.pmtiles` | Web map visualization |
| H3 Hex Parquet | `dataset/hex/h0={cell}/data_0.parquet` | Spatial joins/aggregation |

**Raster datasets (GeoTIFF, COG):**
| Format | File | Use |
|---|---|---|
| COG | `dataset-cog.tif` | Cloud-optimized raster (titiler etc.) |
| H3 Hex Parquet | `dataset/hex/h0={cell}/data_0.parquet` | Spatial aggregation |

Rasters produce COG + hex only (no GeoParquet/PMTiles). Workflow: create WGS84 COG first, then hex from the NRP S3 COG (not the original source URL).

**Geometry support:** polygon, point, line. Check before hexing:
```sql
SELECT ST_GeometryType(geom), COUNT(*) FROM read_parquet('s3://...') GROUP BY 1
```
- **Points/MultiPoints:** each point → one H3 cell. At coarse resolutions (6–8) many points collapse to the same cell. Warning emitted during hex. Document in STAC.
- **Lines/MultiLines:** supported as of `cng-datasets` PR #69. Each line is buffered by the H3 circumradius at the target resolution before polyfill. Default resolution **8** (auto-detected). Document: *"Line features were hexed to H3 resolution 8 by buffering each segment by the H3 cell circumradius before polyfill."*

**ALWAYS use the k8s workflow. Local env lacks tools and permissions.**

### Local env (YAML generation only)

`cng-datasets` does `from osgeo import gdal` at **import time**, so even the pure-templating
`workflow`/`raster-workflow` subcommands won't load without the Python GDAL binding — you get
`ModuleNotFoundError: No module named 'osgeo'`. libgdal is already installed on the standard
image (`gdal-config --version` works); you only need the matching Python binding. Use the
committed bootstrap, which pins the binding to the system libgdal so it works on any clone:

```bash
scripts/setup-venv.sh          # creates .venv with gdal==$(gdal-config --version) + cng-datasets
source .venv/bin/activate
```

Or by hand:
```bash
uv venv && source .venv/bin/activate
uv pip install "gdal==$(gdal-config --version)"   # match system libgdal (auto-detected via gdal-config)
uv pip install git+https://github.com/boettiger-lab/datasets.git
```

## How to Process a Dataset

### Step 1: Verify source URLs

**Always verify before generating workflows.** Do not assume naming patterns.

```bash
curl -I https://example.com/data.zip                         # single file
curl -s https://.../TIGER2024/TRACT/ | grep '.zip' | head    # directory listing
ogrinfo /vsicurl/<source-url>                                # multi-layer file
```

Common patterns: Census TIGER = per-state (`tl_2024_{STATEFP}_tract.zip`); protected areas = per-region or national; rasters may be tiled.

#### 💡 Read one small table out of a HUGE remote zip — range reads, no localize (#518)

To inspect a schema, a lookup/domain table, or one layer's coverage inside a multi-GB zipped
GDB, do **not** localize the archive (a PVC + 30 GB download for a 126-row table). GDAL's
`/vsizip//vsicurl/` reads the zip central directory plus only the bytes it needs over HTTP
range requests — a small cluster job, seconds to a couple of minutes:

```bash
# authoritative coded domain out of the archived 30 GB national GDB (internal endpoint)
SRC="/vsizip//vsicurl/http://rook-ceph-rgw-nautiluss3.rook/public-usgs-nhd/raw/NHD_H_National_GDB.zip/NHD_H_National_GDB.gdb"
ogr2ogr -f CSV /vsistdout/ "$SRC" NHDFCode          # 126 rows, ~25 s, no PVC
ogrinfo -ro -q "$SRC" -dialect SQLITE \
  -sql "SELECT COUNT(*), SUM(StreamOrde > 0) FROM NHDPlusFlowlineVAA"
```

- Works on a **public** source URL too (`/vsizip//vsicurl/https://prd-tnm.s3.amazonaws.com/...`) —
  ideal for pre-flighting a candidate import before committing to a build.
- Use `-dialect SQLITE`: **OGR SQL has no `CASE`**, and keep the SQL on **one line** (a folded
  YAML block mangles multi-line SQL). `SUM(cond)` works in the SQLITE dialect.
- Full-table `COUNT(*)` over range reads is slow (minutes) because it decodes every feature;
  schema reads and small tables are fast. Aggregate on the small table, not the geometry layer.
- Working manifests: `catalog/usgs-nhd/k8s/extract-fcode-domain.yaml`,
  `catalog/usgs-nhd/k8s/preflight-nhdplus-hr-vaa.yaml`.
- ⛔ Never hand-write a coded domain from memory (#294) — this is how you get the real one.

### Step 1b: Copy raw to `s3://<bucket>/raw/` FIRST

External downloads are slow/rate-limited; restart from S3 if conversion fails. Subsequent jobs read `s3://<bucket>/raw/<file>` (or `/vsicurl/https://s3-west.nrp-nautilus.io/<bucket>/raw/<file>` for GDAL).

> ⚠️ **Brand-new bucket? Run the `*-setup-bucket` job BEFORE any stage-raw/download job.** The
> bucket does not exist until `cng-datasets storage setup-bucket` creates it, and
> `rclone ... --s3-no-check-bucket` will happily scrape/build for many minutes and then fail the
> upload with `NoSuchBucket` (404) — wasting the whole download. For an existing bucket this
> ordering doesn't matter (the orchestrator runs setup-bucket first anyway); it bites only the
> first dataset in a new bucket, where stage-raw runs *outside* the orchestrator.

```yaml
command: [bash, -c, |
  curl -L --retry 5 -o /tmp/data.zip "$SOURCE_URL"
  rclone copy /tmp/data.zip nrp:<bucket>/raw/
]
```

### Step 1c: Preprocessing multi-file zipped datasets

**`cng-convert-to-parquet` rejects multiple .zip URLs.** For per-state/per-region zips, preprocess: download in parallel, unzip, pass shapefiles (the tool merges them automatically):
```bash
for id in 01 02 03; do curl -sS -O "https://example.com/data_${id}.zip" & done
wait && unzip -q -o "*.zip"
cng-convert-to-parquet /tmp/data/*.shp s3://bucket/output.parquet
```
See `catalog/census/k8s/tract/preprocess-tract.yaml` for a complete k8s job.

### Step 2: Generate the pipeline

#### Vector
```bash
cng-datasets workflow \
  --dataset <name> --source-url <url> --bucket <bucket> \
  --h3-resolution 10 --parent-resolutions "9,8,0" \
  --hex-memory 32Gi --max-completions 200 --max-parallelism 50 \
  --output-dir catalog/<dataset>/k8s/<name>
```

Add `--layer <LayerName>` for multi-layer sources (one workflow per layer). The `/` in `--dataset` creates hierarchical S3 paths; `-` is used in k8s job names.

**Prefer `--backend armada` for hex-heavy workflows.** k8s backend caps at 200 indexed completions and 200 pods namespace-wide. Armada removes both and allows `--chunk-size 1` (one feature per job), critical when polygon sizes vary wildly (a single Russia/China chunk can run for hours while 199 others finish in minutes):
```bash
cng-datasets workflow ... --h3-resolution 8 --parent-resolutions "0" \
  --max-completions <N-features> --backend armada ...
```
With `--backend armada` the CLI emits armada YAMLs for all steps alongside k8s manifests. Submit in order manually (no orchestrator):
```bash
armadactl submit catalog/<dataset>/k8s/<name>/armada-<name>-setup-bucket.yaml
armadactl submit catalog/<dataset>/k8s/<name>/armada-<name>-convert.yaml
armadactl submit catalog/<dataset>/k8s/<name>/armada-<name>-pmtiles.yaml
armadactl submit catalog/<dataset>/k8s/<name>/armada-<name>-hex.yaml
# wait for hex, then:
armadactl submit catalog/<dataset>/k8s/<name>/armada-<name>-repartition.yaml
```
Monitor: **https://armada-lookout.nrp-nautilus.io**

Convert an existing k8s hex YAML to Armada (for rechunking):
```python
from cng_datasets.k8s.armada import k8s_indexed_job_to_armada, save_armada_yaml
import yaml
with open('<name>-hex.yaml') as f: job_spec = yaml.safe_load(f)
armada_spec = k8s_indexed_job_to_armada(job_spec, queue='biodiversity', job_set_id='<name>-hex')
save_armada_yaml(armada_spec, 'armada-<name>-hex.yaml')
```

#### Raster
```bash
cng-datasets raster-workflow \
  --dataset <name> --source-url <cog-url> --bucket <bucket> \
  --h3-resolution 8 --parent-resolutions "0" --value-column <band_name> \
  --hex-memory 32Gi --max-parallelism 61 \
  --output-dir catalog/<dataset>/k8s/<name>
```

Differences from vector:
- Command: `raster-workflow`
- Completions always 122 (one per h0 cell) — not configurable
- Defaults: `--h3-resolution` 8, `--parent-resolutions "0"`, `--hex-memory 32Gi`, `--max-parallelism 61`
- `--value-column` — raster band name in output (default `value`)
- `--nodata` — value to exclude (auto from metadata)
- `--hex-resampling` — **how pixels aggregate into each cell (`sum`/`mean`/`mode`/`max`/`min`, default `mean`). Picking the wrong one silently corrupts the data — see "Choosing the aggregation reducer" below. As important as `--value-column`.**
- Always creates a WGS84 COG on NRP S3 first; hex reads from that COG

**Multi-tile rasters** (e.g. multiple UTM zones): repeat `--source-url`. Adds `preprocess-cog` step that mosaics into one WGS84 COG:
```bash
cng-datasets raster-workflow --dataset wyoming/rap-arte \
  --source-url s3://.../rap_arte_zone12.tif \
  --source-url s3://.../rap_arte_zone13.tif \
  --bucket public-wyoming \
  --target-extent "-111.1,40.9,-104.0,45.0" --band 1 --value-column arte \
  --output-dir catalog/wyoming/k8s/rap-arte
```
Extra options: `--target-extent "xmin,ymin,xmax,ymax"` (EPSG:4326 clip), `--target-resolution <degrees>`, `--band <n>` (1-indexed), `--output-cog-name <key>`.

#### ⚠️ Mosaicking a MANY-tile source (thousands of 1° tiles) into one global COG — two traps

For a source shipped as thousands of small tiles (Copernicus GLO-30/90 DEM = 26,475 tiles; many
global rasters), repeating `--source-url` is unusable and the naïve single-job mosaic fails two ways.
Both were hit and fixed on the DEM import (data-workflows #426; manifests at
`catalog/dem/k8s/copernicus-glo90/` are the working pattern):

1. **rook-cephfs metadata latency kills the file-opens, NOT bandwidth.** Localizing 26k tiles to the
   `rechunk-scratch` **cephfs** PVC and running `gdalbuildvrt` over them crawled — each file open pays
   a network-metadata RTT (~150 ms), so 26k opens = 60+ min *each* for the localize and the VRT build,
   at idle CPU. Local NVMe opens the same files in <1 s. **Fix: localize to LOCAL ephemeral (`/tmp`),
   not the PVC.** 66 GB > the 50Gi ephemeral cap, so split into N balanced **contiguous longitude
   bands** (integer-degree cuts → tile-aligned, seamless), one indexed pod per band on local NVMe →
   regional COGs, then a tiny merge job stitches the few regional COGs into the global COG (a handful
   of large-file opens is fine on cephfs). ~35 min total vs "never finished." Reserve the cephfs PVC
   for the *merge* (few big files), never the many-small-file localize.
2. **`gdalbuildvrt` default `-resolution average` silently downsamples.** Tiles whose pixel size in
   *degrees* varies (Copernicus DEM narrows column counts toward the poles to hold ~90 m ground
   spacing) get averaged to a bogus middle X-resolution — the equator was squished ~2.5× (Everest read
   8146 m instead of ~8700). **Always pass `-resolution highest`** (→ the uniform finest grid) for a
   lat/lon global mosaic. Sanity-check a known peak's pixel value against the raw source tile.

Also: `gdalinfo -stats` writes a `.tif.aux.xml` sidecar and **reads cached stats from it on a rerun** —
if you rebuild the COG in the same scratch dir, a stale `.aux.xml` reports the OLD min/max/mean. `rm`
the `.aux.xml` too, or verify values with a fresh `gdallocationinfo`/`ComputeStatistics`, not the sidecar.

#### ⚠️ Choosing the aggregation reducer (`--hex-resampling`)

`--hex-resampling` controls how source pixels collapse into each H3 cell. **The right reducer depends entirely on what the pixel value *means*, and the wrong one silently produces nonsense** (summing land-cover class codes, averaging species counts). Decide this per dataset, every time. Supported: `sum`, `mean`, `mode`, `max`, `min` (default `mean`).

| Pixel value is… | Reducer | Examples |
|---|---|---|
| **Amount already integrated *per pixel*** — each pixel holds the whole-pixel total | `sum` | population *per pixel* (GHS-POP persons/cell), fishing-effort hours per cell, counts |
| **Density / intensity / rate / fraction** — a *per-area* or normalized quantity | `mean` | carbon **density** (Mg C **ha⁻¹** — Noon irrecoverable/vulnerable/manageable carbon), NDVI, % cover (RAP), depth (GEBCO), indices (NCP) |
| **Categorical** — discrete class codes | `mode` | land cover (CGLS-LC100, NLCD), wetland class (GLWD) |

**⛔ The density-vs-amount trap (the #1 way `sum` goes wrong) — check the source UNITS before choosing the reducer.** `sum` is correct *only* when each pixel value is an amount **already integrated over the pixel** (GHS-POP stores persons *per pixel*, so `sum` recovers the population total). If the value is a **density** — a per-area quantity like Mg C **ha⁻¹**, t km⁻², persons km⁻² — then `sum` produces a meaningless *sum of densities*, off from the true total by roughly the pixel area (carbon was ~7× low; data-workflows #171/#202). **A stock can be a density:** "carbon stock" is conceptually extensive, but the Noon et al. carbon rasters store Mg C **per hectare**, so they need area-integration, *not* `sum`. The reducer follows the **units**, not the conceptual quantity — read the source READMEs / band metadata / paper to confirm whether a value is per-pixel or per-area.

To get a **total from a density raster**: use `mean` (area-weighted mean density per cell), then multiply by the H3 cell ground area downstream — `total = mean_density × cell_area` (h3 `cell_area`; cells are ~equal-area per resolution). There is no one-step density→total reducer yet ([`boettiger-lab/datasets#105`](https://github.com/boettiger-lab/datasets/issues/105)). For an existing density-`sum` build, the equivalent correction is `value × pixel_area_ha` per cell (pixel area is latitude-dependent on a WGS84 grid, ≈ `9·cos(lat)` ha for a ~300 m grid).

**Correctness check:** for an amount-per-pixel `sum`, the catalog-wide `SUM(value)` over the hex parquet MUST equal the source COG's pixel sum within sub-pixel rounding (compute the COG sum with a GDAL block-sum job; query the hex sum via the MCP). **For a density layer, the COG pixel-sum is itself *not* a total — validate the area-corrected `SUM` against the published global total instead** (e.g. irrecoverable carbon 2018 ≈ 137 Gt vs Noon et al. 139.1 Gt). `mean`/`mode` have no global invariant — spot-check the hex against the COG over a known region.

**Species richness / "peak" quantities** (MOBI, IUCN richness): the correct reducer is `max` — **not** `sum` (double-counts species) and **not** `mean` (averages away hotspots). `max` (and `min`) are supported as of [`boettiger-lab/datasets#95`](https://github.com/boettiger-lab/datasets/issues/95) (closed 2026-06-01); MOBI and IUCN-richness were rebuilt with `max` at res 8/5 (data-workflows #194). Validate: hex `MAX(value)` == COG max, and every cell value within `[COG min, COG max]` (roll up to coarser resolutions with `GROUP BY h<parent> + MAX`, never `AVG`/`SUM`).

**`mode` keeps only the *dominant* class** per cell; the class mix is discarded. Fine for "dominant class" maps, but **inadequate for area-accounting** ("how much wetland?"), which then undercounts to plurality cells only. Per-class fractional coverage (one column per class) is not produced by the current pipeline — flag it if a use case needs class areas.

**Reducer choice is independent of geometry correctness.** The raster pipeline integrates each cell's true footprint, including the antimeridian/poles (fixed in `cng-datasets` #88/#92). But any **global** raster hexed before that fix is inflated at the ±180/pole seam and must be re-hexed regardless of reducer.

#### How `--dataset` controls naming

The **last path segment** drives PMTiles `source-layer`, S3 path, and k8s job prefix:

| `--dataset` value | S3 prefix | PMTiles `source-layer` | k8s job prefix |
|---|---|---|---|
| `calenviroscreen-5-0/ces5` | `calenviroscreen-5-0/ces5` | `ces5` | `calenviroscreen-5-0-ces5` |
| `padus-4-1/fee` | `padus-4-1/fee` | `fee` | `padus-4-1-fee` |
| `census-2024/tract` | `census-2024/tract` | `tract` | `census-2024-tract` |

The PMTiles `source-layer` that MapLibre needs = last segment of `--dataset`. It does NOT come from the GDB/source layer name.

**⚠️ No dots in dataset names.** k8s pod names must match `[a-z0-9][a-z0-9-]*[a-z0-9]`. `cng-datasets` rejects dotted names at YAML generation. Encode versions without dots (e.g. `overture-2026-02-18`, not `2026-02-18.0`). Pre-existing dotted YAMLs fail pod scheduling — rename before applying.

### Step 3: Apply to the cluster

One-time RBAC (likely already done): `kubectl apply -f catalog/<dataset>/k8s/<name>/workflow-rbac.yaml`

Per workflow:
```bash
kubectl apply -f catalog/<dataset>/k8s/<name>/configmap.yaml \
              -f catalog/<dataset>/k8s/<name>/workflow.yaml
```

Orchestrator DAG:
- Vector: setup-bucket → convert → pmtiles + hex (parallel) → repartition
- Raster: setup-bucket → hex (+ preprocess-cog before hex for multi-tile)

You can also apply individual job YAMLs (`<name>-setup-bucket.yaml`, `<name>-convert.yaml`, `<name>-hex.yaml`, etc.) for step-by-step control.

### Step 4: Monitor
```bash
kubectl get jobs | grep <name>
kubectl logs job/<name>-convert       # conversion
kubectl logs job/<name>-workflow      # orchestrator
```
A ~300K-feature vector run typically takes 1–2 hours.

### Step 5: Document

**Write STAC/README to `/tmp/` only — never to `catalog/<dataset>/stac/`.** Upload directly:
```bash
rclone copyto /tmp/README.md nrp:<bucket>/README.md
rclone copyto /tmp/stac-collection.json nrp:<bucket>/<dataset>/stac-collection.json
```

#### ⛔ Verify the STAC — don't hand-check the rules

Every STAC rule below is enforced by **`scripts/verify-stac.py`** (license, nav links,
asset keys, hex glob, `h3:*` resolutions, `vector:layers`, `table:columns` placement,
per-feature-dup warnings, categorical completeness + PMTiles fields via the two
sibling linters, and a **data-backed `values` == ingested `DISTINCT`** check via the
MCP that automates the #114/#294 lesson). Do not re-verify these by hand or by
spending agent context on MCP `SELECT DISTINCT` sweeps — run the gate.

```bash
# 1. PRE-PUBLISH (static, against the /tmp file you just wrote):
scripts/verify-stac.py --no-data /tmp/stac-collection.json
#    Fix every HARD finding before rclone copyto. (Data checks need the data live, so
#    they run post-publish; --no-data skips them here.)

# 2. POST-CLUSTER (full, against the live S3 STAC, once data + STAC are published):
scripts/verify-stac.py --bucket <bucket> --dataset <dataset>
#    Must exit 0 (no HARD findings). ADVISORY lines are informational.
```

CI runs the same verifier on the PR (`.github/workflows/verify-stac.yml`), deriving the
collection(s) from the `s3://` paths in the changed `catalog/**` YAMLs. **The gate
evaluates the produced artifact, not the proposal:** the cluster run lands after the PR
opens, so a RED check at PR-open (STAC not published yet) is correct — don't merge
before the recipe has actually produced valid output. GitHub status checks don't
auto-refresh from S3, so **after your cluster jobs finish, re-fire the check** (Actions
→ Verify STAC → *Run workflow*, or it re-runs on the next push). Merge requires it green.

**README.md MUST include:**
- A MapLibre GL JS example with the correct `source-layer` (= last segment of `--dataset`), documented prominently
- A DuckDB example with the full public parquet URL

#### ✍️ Descriptions are USER-FACING COPY — agents quote them to end users

Asset, column and collection `description` fields are not internal documentation. The geo-agent
reads them and **quotes them, nearly verbatim, into answers for end users** — for ca-30x30 that is
state-agency staff and conservation partners, often non-spatial. Write them as product copy, not as
notes to the next engineer (data-workflows#512, where issue prose reached a user as
"joining at res-8 avoids the ~11 pp overstatement that a coarse `GROUP BY` would introduce").

**Say:** what the asset is, what it is for, what resolution it is at, and the one thing a consumer
must know to use it correctly. Spell things out — "resolution 8", not "res-8".

**Do NOT put in a description:**
- issue or PR numbers, repo names (`data-workflows#506`) — those belong in the issue and the commit;
- defect magnitudes or what a previous consumer got wrong ("overstates conserved share by ~11pp");
- unexplained abbreviations (`pp`), bare column/asset keys as the subject of a sentence;
- shouted imperatives (`ALREADY A MEAN`, `do NOT re-aggregate`, `NEVER SUM`) — they read as
  scolding when quoted, and prose imperatives are exactly what leaks into an answer.

**Express a real constraint as a short SQL example instead** — it is clearer than an imperative and
does not leak as prose:

```sql
-- correct: combine cells weighted by land area
SELECT SUM((w1 + w2) * land_area_km2) / SUM(land_area_km2) FROM …
-- wrong: weighting by a cell COUNT assumes equal-area cells — H3 cells are not equal-area
-- wrong: taking the largest or any single cell's value overstates the share
```

> The count-weighted version of that example (`… * nland) / SUM(nland`) was what this file
> recommended until #522, and it is latitude-biased: over California (32.5N-42N) it returned a
> 25.684% conserved share against an area-weighted 26.135%. If a rollup asset exposes only a
> child-cell *count*, ship the child-cell *area* alongside it — the correct query should be the
> short one, not the one requiring an `h3_cell_area()` call the consumer has to remember.

The mechanical rules elsewhere in this file still apply on top of this: per-column text stays
**identical across assets** (the mcp-data-server#303 fold), the hex per-feature-duplication note
still has to be present and still has to match what `verify-stac.py` looks for (phrases like
"repeated on every … cell"), and the H3 area recipe still must not be inlined (#389). Plain register,
same guarantees.

**Publishing lags by ~15 minutes.** `mcp-data-server` refreshes its STAC cache on a **~15-minute**
cycle, so right after `rclone copyto` the agent (and the app) still read the previous text — verified
during #512, where `verify-stac.py` (which fetches S3 directly) saw the new copy while
`get_stac_details` returned the old, then agreed after the refresh. So: verify prose against the S3
URL for correctness, and wait out the cycle before judging what an agent or the app will quote. **No
cache-invalidation or restart is needed** — do not go reaching into the MCP's namespace for one.

**One text per column NAME per collection.** The `#303` fold is per column *name* across every asset
in the collection, and **first-seen wins**, so a column documented differently on two assets loses
one version silently. Two traps, both hit in #512:
- Adding a new hex-like asset with its own wording for `h10`/`h9`/`h8`/`h0` meant the older asset's
  text won — and that text said "one row per (feature, h10) pair", which was true there and **false**
  for the new per-cell assets. Keep shared H3 columns grain-neutral and identical; state grain in the
  asset `description`, which is always rendered.
- Appending a hex-only clause to a column that also exists on the flat GeoParquet (e.g. "…repeated on
  every hex cell — dedup first") makes the two differ, so the clause is dropped. Put that note in the
  hex asset's `description` instead. After editing, check no column name carries two different texts
  within the collection — `verify-stac.py` reports this as `column-description-divergent`
  (ADVISORY today; it becomes HARD once the pre-gate catalog is fold-clean, #509).

**The title and description state the FOOTPRINT, not which tranche you ingested.** A set of
whole administrative or hydrologic units is **never** a state extent, and a consumer — human or
model — trusts the title over the geometry. `usgs-nhdplus-hr-flowline` was titled *"(California)"*
and said *"COVERAGE IS CALIFORNIA ONLY"*, both true about which VPUs had been ingested and both
read as claims about the footprint, which is 13 whole HU4 units with **30.3% of its stream length
in Nevada, Utah, Oregon and Arizona**. A model skipped the California mask and its headline number
was 8.5 points wrong — the same mechanism as the pinyon-juniper defect (#505). So:

- **Title the unit set** — "…(13 California hydrologic units)", not "…(California)". Same for
  counties, ecoregions, watersheds, and every later tranche of a national build.
- **State the footprint near the top of the description**: what the units are, that they are not
  clipped to the region, how much lies outside, and the mask a region-level statistic needs
  (for California, join `h8` + `h0` against the `ca30x30-ecoregion` hex). Give the mask as a short
  SQL example, per the register rules above.
- **Never write "X ONLY" for "only the X tranche is ingested so far"** — say the ingest scope and
  the footprint as two separate facts.
- The `bbox` is usually already correct; it is the prose that lies. `verify-stac.py` flags a title
  naming one US state whose bbox reaches >1° outside it with no footprint sentence
  (`title-names-state-but-bbox-exceeds-it`, ADVISORY) — the fix is the sentence, not a narrower bbox.

**stac-collection.json MUST include:**

- **License — REQUIRED on every collection.** Set the top-level STAC `license` field to the **SPDX identifier** of the upstream data license (e.g. `CC-BY-4.0`, `CC-BY-NC-4.0`, `CC-BY-SA-4.0`, `CDLA-Permissive-2.0`, `public-domain`). Use `"other"` **only** when no SPDX id applies, and `"various"` **only** for a meta-collection whose children genuinely differ — never as a lazy default. For `other`/`various` (and recommended for all), add a license link: `{"rel": "license", "href": "<canonical terms URL>", "type": "text/html"}`. **Exception — a meta-collection (one with `child` links) may use `various`/`other` WITHOUT a license link:** its real licenses live on the child collections (each carrying + verified for its own license), and redistribution gating (source.coop excludes, etc.) keys on those per-child licenses, not the parent. A single parent-level link would misrepresent genuinely mixed children. `verify-stac.py` enforces the link only on **leaf** collections (and always for `proprietary`). **Verify the real upstream terms — do not guess `proprietary`.** The license drives redistribution decisions (e.g. whether a dataset may be mirrored to source.coop); a wrong value is a compliance risk. NonCommercial / ShareAlike licenses are fine but MUST be recorded as such (`CC-BY-NC-*`, `CC-BY-SA-*`) so downstream users aren't misled. US federal works = `public-domain`.

- **Temporal extent — RFC 3339, or the dataset vanishes from the served catalog.** Every
  `extent.temporal.interval` endpoint must be a full RFC 3339 date-time with a timezone
  (`"1920-05-15T00:00:00Z"`), or `null` for a genuinely open start/end. This is not
  cosmetic: pystac parses these **eagerly** when it loads a collection, so one malformed
  value makes the entire collection fail to load for every MCP consumer — the dataset
  simply isn't there, with nothing but a warning in the server log. Seven BLM MLRS
  mineral collections shipped this way and were invisible for weeks.
  **When composing the string from a query result, slice the date part explicitly**
  (`str(v)[:10]`): the MCP `query` tool renders a DuckDB `DATE` as
  `"1974-03-01T00:00:00.000000"`, so appending `"T00:00:00Z"` to the raw value produces a
  doubled time component. `verify-stac.py` HARD-fails a non-RFC-3339 endpoint, a missing
  interval, and a start that is after its end.

- **Navigation links — every collection needs all four:**

  ```json
  "links": [
    {"rel": "self",   "href": "https://s3-west.nrp-nautilus.io/<bucket>/<path>/stac-collection.json", "type": "application/json"},
    {"rel": "root",   "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",        "type": "application/json"},
    {"rel": "parent", "href": "<URL of the collection that links to this one as a child>",             "type": "application/json"},
    {"rel": "child",  "href": "<URL of each sub-collection>",                                          "type": "application/json"}
  ]
  ```

  Rules:
  - `self` = the collection's own S3 URL.
  - `root` = always the NRP root catalog (`public-data/stac/catalog.json`).
  - `parent` = the collection that holds this one as a `child` link. For top-level bucket collections this is the root catalog. For nested sub-collections (e.g. `public-rivers/american-rivers/dam-removal/`) this is the domain collection (`public-rivers/american-rivers/stac-collection.json`), **not** the root.
  - `child` = `"rel": "child"` (not `"item"`) for every sub-collection. `"rel": "item"` is for individual STAC Items (features), not Collections.
  - **Without `self`/`root`/`parent`, geo-agent cannot traverse the tree and the collection won't expand.**

- **Asset keys encode the dataset, not the format.** Never use generic keys (`pmtiles`, `geoparquet`, `h3-parquet`, `parquet`, `hex`) — they collide and break downstream apps. Use `{last-segment}-{format}`:

  | Asset | Pattern | Example (`--dataset census-2025/sldl`) |
  |---|---|---|
  | GeoParquet | `{name}-parquet` | `sldl-parquet` |
  | PMTiles | `{name}-pmtiles` | `sldl-pmtiles` |
  | H3 hex | `{name}-hex` | `sldl-hex` |
  | COG | `{name}-cog` | `sldl-cog` |

  Multi-layer collections: prefix with collection context (`cpad-holdings-parquet`, `cpad-units-hex`).

- **Hex asset `href` MUST use the Hive-partitioned glob — never a bare directory:**
  - ❌ `.../census-2025/sldl/hex/`
  - ✅ `.../census-2025/sldl/hex/h0=*/data_0.parquet`

- **Any vector asset with named layers** (PMTiles, GDB, GPKG, etc.) MUST include `"vector:layers": ["<name>"]`. For PMTiles the layer name = last segment of `--dataset`.

- **`table:columns` goes on each parquet asset — NOT at the collection level.** Put it inside the asset object for the GeoParquet and hex assets. Do not add a top-level `table:columns` to the collection. `verify-stac.py` HARD-fails a collection-level `table:columns`.

  **Every queryable parquet asset is fully self-describing** — it carries the full per-column schema (name, type, description, `values`), the SAME text on the flat GeoParquet and the hex. This is deliberate: the mcp-data-server renderer dedups identical per-column descriptions across assets at read time (mcp-data-server#303), so full-both costs nothing to the LLM; and a consumer targeting a single asset directly still gets the full schema. That last point is not optional — **raster-derived datasets have a hex but no GeoParquet**, so the hex must stand alone. The single authority is the **build/relocation tool** (one source schema written identically to every asset), never a hand-edit of one asset — identical text means the #303 "first-seen wins" merge never drops anything.

  Each parquet asset documents exactly the columns it contains:
  - **GeoParquet asset** (vector, when present): include the geometry column (`Shape`, `geom`, or `geometry`).
  - **Hex asset**: full per-column descriptions identical to the flat (minus the geometry column); include the H3 index columns (`h0`, `h8`, `h9`, `h10` etc.) and `_cng_fid`/`bbox`. The hex is the primary query target (and the sole one for rasters), so it is never "lean."
  - **COG assets**: no `table:columns` needed (not SQL-queryable).

- **`_cng_fid` is the universal per-feature id — REQUIRED on every vector asset, flat GeoParquet *and* hex (#369).** cng-datasets `convert_to_parquet` synthesizes it on every conversion (always, additive, row-unique), so one uniform key works for dedup / `COUNT(DISTINCT)` across all datasets instead of per-dataset id discovery (the over-count class behind #309). Source ids (`ramsarid`, `tpl_id`, `GEOID`) may accompany it for cross-collection joins but never replace it. `verify-stac.py` **HARD**-fails a vector flat GeoParquet (has a geometry column) or a vector hex that lacks `_cng_fid`; if the data genuinely lacks it, reprocess through cng-datasets. **Exempt:** raster-derived hex (a raster reduce into H3, not a feature conversion — detected as a hex/`h0=*`-partitioned asset in a collection with no vector source; covers carbon/ghs-pop *and* the richness/cwhr/gbif reductions). A **non-spatial** parquet table (no geometry, not a hex) is **ADVISORY** — it may be a feature fact table that should carry `_cng_fid` (e.g. tpl `…-funding`) or a legit lookup/crosswalk/coefficient/scores table; use judgment.

- **PMTiles assets MUST carry tile-accurate `table:columns` (data-workflows #283/#320), in LEAN form.** The geo-agent (and human app authors) can only learn which fields are stylable/filterable in MapLibre from the PMTiles asset's own schema — an empty `table:columns` forces them to byte-range the `.pmtiles` footer. **Empirically, our tippecanoe step keeps ALL attribute columns: the tile field set is just `GeoParquet attrs − geometry + _cng_fid`** (types coarsened to String/Number/Boolean). So the standard is to **mirror the canonical GeoParquet schema onto the PMTiles asset** — do NOT hand-scrape thin metadata from the footer, and do NOT duplicate the prose:
  - **Lean columns:** each PMTiles column carries **`name` + `type` + `values`** (the `values` enumeration is the styling-critical part for categoricals) — copied from the GeoParquet column of the same name. **Omit the prose `description`** — it stays CANONICAL on the GeoParquet asset (duplicating it across 3 assets just bloats agent context; the agent reads definitions there).
  - Drop the geometry column; include `_cng_fid` (present in tiles).
  - Keep `vector:layers` (the source-layer id list).
  - **Continuous (choropleth) layers only:** add the **nodata sentinel** and flag the **intended value column** for styling, as a short `description` on that one column (e.g. SVI `RPL_THEMES = -999`) — these are viz-specific and not inferable from the GeoParquet schema.
  - **Generate it** with `scripts/mirror-pmtiles-columns.py <stac-url>` — it reads the footer to *validate* the field set (and flags the rare genuine-subset case, e.g. SVI, where tippecanoe really did drop columns), mirrors the GeoParquet `name`/`type`/`values`, and writes the updated STAC to `/tmp`. Then `rclone copyto` to S3.
  - Because PMTiles mirrors the GeoParquet, **fix the GeoParquet/hex categoricals FIRST** (the #303 work), then mirror — otherwise you copy incomplete `values`.
  - Gate with `scripts/lint-stac-pmtiles-fields.py <stac-collection.json|url>` (companion to `lint-stac-categorical.py`); it requires `name` + `type` and does NOT require descriptions.

- **Hex assets MUST declare their H3 resolutions explicitly** via `h3:native_resolution` and `h3:parent_resolutions` on the asset itself. Column-name presence (`h10`, `h9`, …) is not enough — downstream tools shouldn't have to enumerate `table:columns` to find out what resolutions exist. `h3:native_resolution` is the finest resolution (one row per feature-cell at this res); `h3:parent_resolutions` is the list of rollup resolutions, which MUST include `0` (the partition key).

- **Vector (GeoParquet/PMTiles) assets MUST flag per-feature ROW duplication — and you MUST first decide whether it is *true* duplication or *real* multi-row data.** A source file often stores one logical feature as several rows sharing a feature id (a Ramsar site split into polygon parcels; a ballot measure spanning multiple counties). Two opposite causes demand opposite rules, and confusing them silently corrupts answers (data-workflows #309):
  - **REPEATED** — the per-feature value is *copied* onto every row (e.g. a measure's total funds repeated on each county row). A raw `SUM` double-counts → **dedup by the key first** (`SELECT DISTINCT key, col …` or `GROUP BY key`), and `COUNT(DISTINCT key)` is the feature count.
  - **VARIES** — genuinely distinct per-row records that share a key (e.g. one conservation site funded by several *sponsors*, each a *different amount*). Here `SUM` is **correct** and dedup would **undercount** by dropping real rows. A repeated polygon + repeated attributes is NOT proof of duplication — a sponsor split looks identical except the varying amount.

  **Two duplication axes — and `_cng_fid` only fixes one of them.** cng-datasets always assigns `_cng_fid` as a synthetic id that is *one per input row* (never derived from a source id). So:
  - **Axis 1 — feature → H3 cell** (hexing makes one polygon span many cells). Dedup key = `_cng_fid` (or `h<N>`). `COUNT(DISTINCT _cng_fid)` collapses the cell expansion. This is the standard hex guidance below.
  - **Axis 2 — upstream source rows** (the *input file* already holds several rows per logical entity). Dedup key = an **upstream domain id** (`ramsarid`, `landvote_id`, WDPA `SITE_ID`). `_cng_fid` is unique per row, so it does NOT collapse this — `COUNT(DISTINCT _cng_fid)` still counts rows/polygons, not entities.

  For most datasets each input row *is* one logical feature, so the two keys coincide and only axis 1 exists — that is why the standard guidance leans on `_cng_fid`. Axis 2 only appears in files with upstream duplication (ramsar, landvote); there the domain id is the dedup key, and **the hex asset must also carry that domain id** or it cannot be deduped to entities (e.g. landvote's hex carries only `_cng_fid`, so it can't be reduced to distinct measures — a gap). Auditing on a per-row id always reports "clean", masking axis 2.

  **The decisive test is data-backed: does the value VARY within the key?** Do NOT guess the key from a column name — a 34%-blank source id (PAD-US `Source_PAID`) or a class label that covers thousands of parcels (Landmark `name`) fakes duplication, and a per-row id (`_cng_fid`) hides it. Run the auditor with the *upstream domain id* as `--key` (it uses the duckdb-geo MCP, not local duckdb):
  ```bash
  scripts/audit-feature-dup.py <parquet-url|stac-url --asset KEY> --key <feature-id-col>
  ```
  It reports rows vs `COUNT(DISTINCT key)`, warns on blank keys, classifies each column REPEATED vs VARIES, and quantifies raw-vs-deduped `SUM` inflation. Then document the verdict in the asset's `table:columns`: name the key, mark REPEATED columns "dedup before SUM", and (if any) note VARIES columns are safe to SUM. A clean one-row-per-feature file needs no note.

- **Hex assets MUST flag per-feature duplication — at the hex ASSET-description level, NOT per-column.** One hex row = one (feature, cell) pair, so any column that represents a per-feature total — area (`GIS_Acres`, `SHAPE_Area`), length (`SHAPE_Length`), population, count, amount, funding, intensity — is repeated on every cell the feature covers. Put this warning (name the pattern + the **dedup key**, list the affected columns) in the **hex asset's `description`**, because the mcp-data-server#303 renderer keeps per-column descriptions identical across the flat and hex (single authority) and would silently drop a per-column note that differs between them — whereas the per-asset `description` line is always rendered. `verify-stac.py` accepts the note at the asset (or collection) level. (Raster hex: the asset note states reducer semantics instead — e.g. "`sum` reducer, SUM is the catalog total" or "mean density → × cell area for totals".) The two safe patterns:
  - **SUM after dedup** (the attribute is a real per-feature value): `SELECT DISTINCT <feature_key>, <attr> …` or `ROW_NUMBER() OVER (PARTITION BY <feature_key>)` before aggregating.
  - **Area/extent from the H3 footprint** (when there is no trustworthy source value): the generic recipe — `SUM(h3_cell_area(h<N>, 'km^2'))` over DISTINCT cells, exact per cell, **never** a nominal per-resolution constant — lives in `mcp-data-server/h3-guide.md`. **Do NOT inline that formula into the column description** — it is generic guidance the geo-agent already reads from the h3-guide, and a copy baked into STAC goes stale and becomes actively harmful (a nominal-constant copy undercounted the ca-30x30 California extent ~6%, mcp-data-server#294 / #389). Just flag the column as a per-feature total not to be SUMmed on hex; the agent derives area from the h3-guide.

  Columns that are safe to aggregate on hex (H3 indexes, `_cng_fid`, `bbox`) don't need a warning. If no column on the hex asset is safe to SUM, say so once in the collection description too.

  ```json
  "assets": {
    "sldl-parquet": {
      "href": "https://…/sldl.parquet",
      "type": "application/x-parquet",
      "title": "…",
      "table:columns": [
        {"name": "GEOID", "type": "string", "description": "…"},
        {"name": "ALAND", "type": "int64", "description": "Land area in m² of the source district polygon."},
        {"name": "geometry", "type": "geometry", "description": "Feature geometry (GeoParquet)"}
      ]
    },
    "sldl-hex": {
      "href": "https://…/sldl/hex/h0=*/data_0.parquet",
      "type": "application/x-parquet",
      "title": "…",
      "h3:native_resolution": 10,
      "h3:parent_resolutions": [9, 8, 0],
      "table:columns": [
        {"name": "GEOID", "type": "string", "description": "…"},
        {"name": "ALAND", "type": "int64",
         "description": "Land area in m² of the source district polygon. **Repeated on every hex row the district covers — never SUM(ALAND) on hex data; dedup first (SELECT DISTINCT GEOID, ALAND).** For area from the H3 footprint see the h3-guide."},
        {"name": "h10", "type": "uint64", "description": "H3 cell ID at resolution 10 (native resolution; one row per (feature, h10) pair)."},
        {"name": "h9",  "type": "uint64", "description": "H3 cell ID at resolution 9."},
        {"name": "h8",  "type": "uint64", "description": "H3 cell ID at resolution 8."},
        {"name": "h0",  "type": "int64",  "description": "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."}
      ]
    }
  }
  ```

  For **coded categorical** columns, the description MUST list all valid values in `CODE=Definition, …` format and include a `"values"` array. Discover actual values via DuckDB before writing:
  ```sql
  SELECT column_name, COUNT(*) AS n FROM read_parquet('s3://…') GROUP BY column_name ORDER BY n DESC
  ```
  Example:
  ```json
  {"name": "owner_type", "type": "string",
   "description": "Owner type code. Values: FED=Federal, STAT=State, LOC=Local, NGO=Non-governmental/non-profit, TRIB=Tribal/Indigenous, PVT=Private, UNK=Unknown",
   "values": ["FED", "STAT", "LOC", "NGO", "TRIB", "PVT", "UNK"]}
  ```
  Missing definitions cause LLM agents to guess values (e.g. `WHERE owner_type = 'Federal'` instead of `'FED'`) and return empty results.

- **Categorical rasters (COG assets with discrete pixel-value classes):** the COG asset's `raster:bands[0]` MUST include `classification:classes` (STAC classification extension v2.0.0). Each entry: `{ value, name, description, color_hint }` where `color_hint` is a 6-character RGB hex (no leading `#`). Add `https://stac-extensions.github.io/classification/v2.0.0/schema.json` to `stac_extensions`. Do **not** use the legacy `class_values` field from the raster extension — geo-agent reads `classification:classes` and `color_hint` to build both the discrete legend swatches and the titiler categorical colormap; without those colors the layer falls back to a continuous gradient. Use the dataset's standard published palette where one exists (NLCD MRLC colors, etc.); otherwise pick distinguishable accessible colors and note the choice in the asset description.
  ```json
  "stac_extensions": [
    "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
    "https://stac-extensions.github.io/classification/v2.0.0/schema.json"
  ],
  "assets": {
    "nlcd-cog": {
      "raster:bands": [{
        "name": "land_cover_class", "data_type": "uint8", "nodata": 0,
        "classification:classes": [
          {"value": 11, "name": "Open Water", "description": "…", "color_hint": "466B9F"},
          {"value": 41, "name": "Deciduous Forest", "description": "…", "color_hint": "68AB5F"}
        ]
      }]
    }
  }
  ```

- **Per-feature row duplication / NULL finest-parent cells / no-data sentinels (data-workflows #309, gated by #311).** Three aggregation traps the geo-agent accuracy sweep surfaced — document each on the relevant asset:
  - **Repeated features (polygon/point assets).** Handled by the REPEATED-vs-VARIES per-feature row-duplication rule above — run `scripts/audit-feature-dup.py` to get the verdict and document it. `verify-stac.py`'s `polygon-row-dup-candidate` **ADVISORY** is just the automatic CI tripwire that flags a `rows ≫ COUNT(DISTINCT id)` candidate; treat it as a prompt to run that auditor, not a defect on its own (the signal over-flags — the column may be a label or provenance key, not the feature id).
  - **NULL finest-parent cells.** If the hex build caps very large features at a coarser native resolution (WDPA: `h9` is NULL for the 1,297 biggest features, `h8` is complete), the hex asset description MUST name the complete column and say joins should use the coarsest shared resolution (or `h3_cell_to_parent()`), not the finest. `verify-stac.py` **HARD**-flags an undocumented NULL finest hex column.
  - **No-data sentinels.** Document sentinel/fill codes (e.g. land-cover `0`/`200`) so consumers `WHERE col NOT IN (...)` before `SUM`/`AVG` — an undocumented sentinel poisons aggregates to `NaN`.

  ⛔ **MEASURE every added column's range and sentinels — never document one from upstream docs or
  memory.** When a build introduces columns new to this catalog, run one query per new column
  (`MIN`/`MAX`, `COUNT(*) FILTER (WHERE col < 0)`, distinct count) *before* writing STAC. This is
  the #518 lesson generalised, and it recurred three times in one session while fixing #518
  (data-workflows #205/#525):
  - `-9999` on four NHDPlus VAA columns (and `-9` on a fifth) — **the same 2,745 rows** — was
    documented nowhere in the first draft; an unfiltered `AVG(slope)`/`MIN(totdasqkm)` is poisoned.
  - Worse than omission: a sentinel note copied from upstream documentation said "check for
    negative values", which would have told consumers to discard **real** below-sea-level
    elevations (10,349 rows, min −85.61 m in Death Valley). **A negative value is not automatically
    a sentinel** — filter the exact sentinel (`<> -9998`), never a sign test, unless you have
    measured that no legitimate negatives exist.
  - A `values` array copied from a sibling collection missed 13 codes actually present. Coded
    domains come from the authoritative source table (#294), and `values` from the ingest.
  Record the measured ranges in the dataset's `BUILD.md` so the next reader inherits evidence
  rather than assumption — see `catalog/usgs-nhd/k8s/nhdplus-hr/BUILD.md` for the pattern.

- **Point datasets:** `description` or `"processing:notes"` MUST state each point resolved to one H3 cell at the processing resolution, and name the resolution. Example: *"Point observations were hexed to H3 resolution 10 (each point → one ~15 000 m² cell). Multiple points within the same cell are not deduplicated."*

### Step 6: Register in the parent sub-catalog

**The STAC catalog is a TREE.** Datasets belong in their domain/bucket sub-catalog, not the root. Root `public-data/stac/catalog.json` only links top-level sub-catalogs (e.g. `public-high-seas`, `public-padus`, `public-census`).

Before linking:
1. Check for existing sub-catalog: `curl -s https://s3-west.nrp-nautilus.io/<bucket>/stac-collection.json | jq '.links[] | select(.rel=="child")'`
2. Exists → add child link there.
3. Brand-new bucket/domain → create bucket-level `stac-collection.json`, register children in it, then link that bucket-level collection from root.

```bash
curl -s https://s3-west.nrp-nautilus.io/<bucket>/stac-collection.json > /tmp/parent.json
# Edit /tmp/parent.json to append {"rel": "child", "id": "...", "href": "...", "title": "..."}
rclone copyto /tmp/parent.json nrp:<bucket>/stac-collection.json
```

Only touch the root when adding a **new** top-level sub-catalog.

### Step 7: License the collection — you register NOTHING for backup or mirror

Backups and the source.coop mirror are **owned end to end by geo-agent-ops**, in a namespace
this repo has no membership in. That tier derives its own scope, holds its own credentials, and
vendors its own code. In its own words (geo-agent-ops `k8s/minio-sync-cron.yaml`):

> data-workflows supplies NOTHING to the backup tier — no code, no scope, no manifest.
> It produces datasets on NRP and nothing else.

So there is **no registration step here** — not for a new bucket, not for an existing one, not
for a new collection in an existing bucket. Nothing in this repo is read by the backup tier.

**Your one obligation is metadata.** Every collection must carry an accurate SPDX `license` and
a license link in its STAC (Step 5). That field is the *advisory input* the mirror-scope auditor
reads, so it is how a licence fact actually reaches the backup tier — and a wrong one is how
data gets over- or under-published.

- Record the **licence fact**: what upstream granted, with evidence. That is a STAC field and it
  belongs here.
- Do **not** record a **redistribution verdict** ("may we mirror this?"). That decision, and its
  holds and blocklist, live in geo-agent-ops `scripts/check-source-scope.py`. A verdict written
  down in this repo reaches nothing.
- If a licence is genuinely unconfirmed, say so — `license: "other"` **and** a description that
  states it. Never assert an SPDX id upstream did not grant, and never list a provider as
  `licensor` when no licence was granted; the auditor acts on a clean-looking `license` string.
  This has gone wrong in both directions: `rivers/american-rivers/*` asserted `CC-BY-4.0` with
  no `licensor` behind it, and `hazard/mid-century-habitat-climate-exposure` asserts
  `CC-BY-4.0` while its own description says the terms "require confirmation".
- Notice a scope problem — something mirrored that should not be, or held that should not be —
  **file an issue on geo-agent-ops.** Do not try to fix it here; there is nothing here to fix.

⛔ **Never execute any part of the backup or mirror tier from this repo or namespace.** No
`kubectl` against `sync-*` / `source-sync-*` / `minio-sync` Jobs or CronJobs, no source.coop
repo creation, no MinIO bucket policy, and never add a MinIO or source.coop remote (or the
`rclone-backup` secret) to a workflow namespace. You hold none of those credentials, and that is
the design, not an oversight.

## Memory and Chunking Mental Model

**RAM is driven by the H3 cell count of the single largest feature in a chunk — not dataset size or bounding box.**

Hex generation is two passes:
1. For each feature polygon, compute covering H3 cells (large array per feature)
2. Unnest arrays row-by-row; **peak RAM = size of the largest single feature's cell array**

Counterintuitive result: 10,000 small features at 8Gi can be fine, while a single continent-scale polygon OOMs at 32Gi. What drives RAM:
- H3 resolution (exponential: res 8 ≈ 1/170th the cells of res 10 for the same area)
- Area of the largest single feature in the chunk
- Geometry complexity affects Pass 1 runtime, not Pass 2 RAM

**Right approach:** start with default (8Gi vector), then tune from OOM signals.
1. Use Armada with `--chunk-size 1` for variable feature sizes (each feature its own pod)
2. On OOM: identify the large polygon(s) and either lower resolution, raise `--hex-memory`, or re-run that chunk alone (see Reprocessing Failed Chunks)
3. OOMs are expected — a tuning signal, not failure.

**Resolution guidance:**

| Dataset type | Resolution | Rationale |
|---|---|---|
| Countries, continents | 8 | Continent-scale features |
| States, provinces | 8 | Still very large |
| Counties, districts | 8–10 | Mostly OK at 10; watch outliers |
| Census tracts, parcels | 10 | Small features |
| Points | 10 | Each point → one cell; coarser = aggregation |
| Lines | 8 | Buffered by H3 circumradius; default 8 auto-detected |

#### ⭐ H3 resolution & parent convention (join compatibility — pick native res AND parents deliberately)

Native resolution alone is not the whole decision — the **parent-resolution set** is what
makes a dataset joinable to the rest of the catalog. Two datasets join cheaply only at a
resolution they **both physically carry** (`h<N> = h<N>`); otherwise a consumer must
`h3_cell_to_parent()` on the fly, which LLM agents do unreliably (wrong direction, skipped,
empty joins). So encode the joins into the data, don't hope the model derives them.

- **`h8` is the catalog's universal join key. Default native resolution is 8**, and **every
  dataset finer than 8 (native `h9`/`h10`) MUST carry `h8`** as a parent. Rationale: raster
  hexes (carbon, GHS-POP, richness) are native `h8`, and vector hexes (native `h10`) carry
  `h8` — so nearly everything meets at `h8`. A one-off native `h7` (e.g. the gHM 1 km raster
  before this rule) is an **outlier with no `h8`** and silently breaks those joins — don't do it.
- **`h0` always** — it is the hive partition key and the coarsest common join; every hex asset
  carries it (it must be in `--parent-resolutions`).
- **`h10` is currently our finest.** Small features (parcels, tracts, points) → native `h10`,
  parents `9,8,0` (the generator default) so they carry `h8`.
- **Coarser than 8 only when features are genuinely huge** — continent- or ocean-scale polygons
  (e.g. large marine areas hexed at `h5`) to keep hex cell-count/RAM sane. Such a dataset
  *cannot* carry `h8` (finer than native); consumers roll finer data **up** to `h5` to join it.
  Use a coarse native res because the feature size forces it, never as a cost shortcut on data
  that should be `h8`.
- **A dataset may declare a *set* of parents** (e.g. native `h8` with `--parent-resolutions
  "5,4,0"` → columns `h8,h5,h4,h0`) so it joins at several standard resolutions at once. Pick the
  parent set from the resolutions of the datasets it will be joined against.
- Always record the chosen native + parents in the issue (scope) and in the hex asset's
  `h3:native_resolution` / `h3:parent_resolutions` (STAC).

### Vector workflow parameters

| Param | Default | When to change |
|---|---|---|
| `--h3-resolution` | 10 | Lower (8, 6) for large polygons. Halving res ≈ 6× fewer cells. |
| `--hex-memory` | 8Gi | Tune from OOM signals. Start low. |
| `--max-completions` | 200 | Number of hex chunks. With armada: set to feature count for chunk-size 1. **⛔ Not a hard cap — a silent coverage limit (data-workflows #494):** the k8s hex uses a FIXED `--chunk-size 1000`, so total features hexed = `max-completions × 1000`. The default 200 silently caps a build at **200,000 features** — anything beyond that is never hexed and the repartition/STAC look "complete." For any dataset **>200k features**, set `--max-completions ≥ ceil(feature_count / 1000)` (e.g. 711,583 → 720). The generator can't count features in a zip/parquet source, so it can't warn you. **Always** confirm coverage post-build: `COUNT(DISTINCT _cng_fid)` on the hex must equal the flat parquet's feature count (not just that h0 partitions exist). |
| `--max-parallelism` | 50 | k8s only — capped by pod quota. Unused with armada. |
| `--parent-resolutions` | "9,8,0" | Use `"0"` when `--h3-resolution 8` (9/8 would duplicate target). |
| `--intermediate-chunk-size` | 10 | Decrease if hex OOMs during unnest — try this before raising memory. |

### Raster workflow parameters

| Param | Default | When to change |
|---|---|---|
| `--h3-resolution` | auto (from pixel size) | Override if auto is wrong |
| `--hex-memory` | 32Gi | Raise if OOM. **Res-8 hex of a 300 m global raster needs 64Gi** — `exact_extract` on the densest h0 cells (~5.76 M cells/h0) OOMs at 32Gi (`exit 137`); with `backoffLimit: 0` it silently retries forever, with `backoffLimitPerIndex` it can blow `maxFailedIndexes` and **fail the job** (observed on nci-frontiers `flii`/forestry). Use 64Gi for res-8 300 m layers; coarser res or coarser source can stay at 32Gi. |
| `--max-parallelism` | 61 | k8s only; reduce on quota hit; cap 122 |
| `--parent-resolutions` | "0" | Add intermediate (e.g. `"7,0"`) if needed |
| `--value-column` | "value" | Use meaningful name (`carbon`, `arte`, `nlcd`) |
| `--nodata` | auto | Override if metadata nodata is wrong/missing |

Raster completions are always **122** — not configurable.

### Re-hexing an existing raster (campaign-style reprocessing)

Most rework here comes from skipped pre-flight checks, not hard problems. Do, in order:

1. **Pre-flight the COG** with one GDAL job (rclone-localize → read; never `/vsis3` for GDAL — it's flaky/node-dependent). Report size, dtype, **real nodata** (published STAC nodata is often wrong), and the value summary that becomes your validation truth (class histogram for `mode`; pixel-SUM for `sum`; min/max/mean for `mean`). **Confirm the COG is non-empty** — published "total" COGs have shipped 100% nodata.
2. **Resolution = match the source pixel** (≈100 m → res 9; ≈500 m → res 8). Don't bump blindly; res finer than the pixel is 7× cost for no gain.
3. **Hex job musts:** mount the `rclone-config` secret (the tool localizes the COG via rclone first; generated YAML omits it → fails), `backoffLimitPerIndex: 2` + `maxFailedIndexes` (not `backoffLimit: 0`), output to a **staging** prefix. `:latest` has the seam fix — no runtime clone.
4. **Validate value AND coverage.** `sum`: hex `SUM` == COG pixel-SUM. Note `sum`/area layers are a **full h0 grid** (one row per cell, `value = 0` where the feature is absent) — same shape as carbon/ghs-pop; that's expected, not bloat. Check that the count of **nonzero** cells matches the feature extent, not the total. `mode`: sparse (cells with no valid pixel are dropped); only canonical codes + distribution tracks the histogram. **Seam (all reducers):** dateline h0 `576707042908045311` — fixed builds span ±180°, buggy ones are bloated and miss the dateline.
   **⛔ h0-partition COVERAGE gate (data-workflows #409).** An indexed 122-completion hex Job that dies/gets-preempted mid-run can leave a *subset* of h0 partitions on S3 and get published as if complete. Two defenses, both required: (a) never treat a hex build as done unless the k8s Job reports `Complete=True` with empty `failedIndexes` — a partial run must surface as `Failed`, so keep `backoffLimitPerIndex` + `maxFailedIndexes` (never `backoffLimit: 0`); and (b) after the job, run the cheap partition-set gate against a reference build from the same COG (e.g. the fractional-coverage layer) or an explicit expected h0 set:
   ```bash
   scripts/check-hex-coverage.sh nrp:<bucket>/<dataset>/hex/ \
       --reference nrp:<bucket>/<dataset>/hex-fractions/   # or --expect-count N / --expect-h0 h0a,h0b,...
   ```
   It is a metadata listing (rclone `lsf` sizes of `h0=*`), not a big-data scan — safe on a laptop. **⚠️ Compare POPULATED partitions, not directories.** A `mode` (sparse) reducer writes a partition only where valid pixels exist; a `sum`/coverage reducer writes a *full grid* — a `data_0.parquet` for every h0 it touches, including empty (0-row, ~214 B) partitions for all-nodata h0. So a raw `h0=*` directory count of a full-grid layer is a **superset** of its data extent, and a naive dir-vs-dir comparison across reducers reports **phantom gaps** — exactly what made NLCD mode look like "6 of 11" when its 6 populated h0 were complete and the fractions reference merely had 5 extra empty dirs (the #409/#410 false alarm). The gate therefore filters both sides to partitions whose bytes exceed `--min-bytes` (default 4096; a real partition is MB–GB). Exit non-zero + the missing h0 set means genuinely-missing populated partitions; re-run before publishing/validating values. The gate **also reports any empty partitions it finds under the target** as purge candidates (advisory by default; `--fail-on-empty` makes their presence a hard failure) — purge them (`rclone purge …/h0=<cell>/` then re-verify empty) so they don't pollute `**` globs or fake gaps for the next reader.
5. **Flip: purge-and-VERIFY-empty, then sync.** `cng-datasets raster` overwrites the partition for each h0 it produces, but does **not** remove partitions for h0s that now yield no data — so reprocessing to a smaller/different domain (e.g. all-land → wetland-only) leaves **stale partitions** behind that corrupt aggregates. And `rclone purge` can silently no-op under S3 load. So purge staging **and confirm it's empty** before any re-hex. `kubectl apply` on a completed Job is a no-op; `delete`+`apply` to rerun. Jobs TTL-GC 3 h after completion — validate before then.

## Pod-count good practice (`geo-workflows`)

**Keep ≤200 simultaneous pods** across all your jobs. `geo-workflows` has **no enforced
ResourceQuota** (unlike the legacy `biodiversity` namespace, which hard-capped at 200), but
≤200 is the good-practice target — oversubscribing is antisocial on shared nodes. Applies to
the **k8s backend only** — armada queues externally and is not constrained.

**Rule: never submit more than one k8s hex workflow at a time.** With `--max-parallelism 50`, a
single hex job can take 50 pods; on the legacy `biodiversity` namespace concurrent hex workflows
tripped its quota (`exceeded quota: reached-quota, used: pods=200`); on `geo-workflows` there is
no wall, so self-limit. Run sequentially:
```bash
for d in dataset-a dataset-b dataset-c; do
  kubectl apply -n geo-workflows -f catalog/.../k8s/$d/configmap.yaml -f catalog/.../k8s/$d/workflow.yaml
  kubectl wait -n geo-workflows job/$d-workflow --for=condition=complete --timeout=7200s
done
```

With armada, submit freely — chunk-size 1 (one pod per feature) eliminates "one slow pod blocks everything."

## S3 Bucket Layout

```
# Vector                                # Raster
bucket/                                 bucket/
├── raw/                                ├── raw/
├── dataset.parquet                     ├── dataset-cog.tif
├── dataset.pmtiles                     ├── dataset/hex/h0={cell}/data_0.parquet
├── dataset/hex/h0={cell}/data_0.parquet├── README.md
├── README.md                           └── stac-collection.json
└── stac-collection.json
```

## Troubleshooting

**404 on convert → verify source URLs** with `curl -I` and directory listings (most common failure — always verify BEFORE generating YAMLs).

**"Cannot mix .zip files with multiple source URLs"** → preprocess job: download in parallel, unzip, pass shapefiles to `cng-convert-to-parquet`.

**Check convert logs:** `kubectl logs job/<name>-convert`

**Repeated preemptions on shared nodes → pin to Berkeley node** `stratus1.nrp-espm.berkeley.edu` (currently carries `nautilus.io/issue` taint):
```yaml
spec:
  template:
    spec:
      nodeSelector:
        kubernetes.io/hostname: stratus1.nrp-espm.berkeley.edu
      tolerations:
      - {key: "nautilus.io/issue", operator: Exists, effect: NoSchedule}
```

⛔ **This pin is a *reactive last resort* for observed, recurring preemption — NEVER a default.** By default let the k8s scheduler place pods. Many nodes across the cluster can service big requests (256/512 GB, multi-cpu) — the Berkeley node is only one of them. **Pinning a large-memory job to one node serializes it:** a 256Gi/8cpu pod fills the node, so `parallelism: N` becomes 1-at-a-time while the rest sit `Pending: Insufficient cpu` (this turned a CONUS res-10 hex from hours into 30-50h — #307). The cluster headroom is there to *request when a job genuinely needs it*; reach for `backoffLimitPerIndex` retries to absorb the occasional preemption before you ever reach for a node pin.

✅ **You do NOT need to exclude GPU nodes for CPU-only jobs.** The generated `nodeAffinity` excludes GPU nodes (`feature.node.kubernetes.io/pci-10de.present NotIn true`), but GPU nodes usually have plenty of **spare CPU/RAM** that our hex/convert/COG jobs can use. Dropping the GPU exclusion **widens the schedulable pool**, which finishes fan-out jobs faster and — importantly — reduces the chance of pods piling onto a flaky node. Keep the exclusion only if a job genuinely needs to avoid GPU-host contention.

⚠️ **Flaky-node hangs — and ⛔ NEVER `--force`-delete pods.** Some shared nodes (observed: `hpc-nrp-g1.nmsu.edu`, `service-02.nrp.mghpcc.org`) have broken egress/S3 connectivity: pods schedule but **hang on `rclone` localize / external download** ("Localizing input →" with no progress; "Could not resolve host") or sit `Pending` with the container never starting. A `backoffLimit: 0` job never recovers (pod Running/Pending, not Failed) and blocks the whole run.

- ⛔ **Never `kubectl delete pod --grace-period=0 --force`.** It drops the API object while the container may still be running on an unreachable node → split-brain / duplicate S3 writes. (Standing rule from the user.)
- ✅ **Let the control plane reap it — the safe equivalent.** A graceful `kubectl delete pod` (no `--force`) plus the node-lifecycle controller's eviction marks pods on an unreachable node `Failed` after the eviction timeout (~5 min); with `podReplacementPolicy: Failed` (the default once `backoffLimitPerIndex` is set) the Job then recreates that index on a healthy node. Net cost of *not* forcing is ~5 min, **not** a block — verified: a 4-index hang on `service-02` self-healed to 122/122 with zero force-deletes.
- **Defenses, in order (prevention beats cure):** (1) exclude known-bad hosts via a `kubernetes.io/hostname NotIn [hpc-nrp-g1.nmsu.edu, service-02.nrp.mghpcc.org, …]` nodeAffinity term so pods never land there; (2) `activeDeadlineSeconds` on the **pod template** (turns a running-hang into a Failure the Job can retry); (3) `backoffLimitPerIndex` + `maxFailedIndexes` (retry the index elsewhere). Note `activeDeadlineSeconds` only helps a *Running* hang — a `Pending` pod (container never started) is cleared only by control-plane eviction, so (1) is the real fix.

**Pod keeps getting evicted (`ContainerStatusUnknown`) → diagnose BEFORE resubmitting.** Never resubmit a failing job without `kubectl describe pod <pod>` — same resources will fail the same way.
```bash
kubectl -n geo-workflows describe pod <pod-name> | grep -A5 "Reason:\|Message:\|Events:"
```

| Message | Cause | Fix |
|---|---|---|
| `ephemeral local storage usage exceeds the total limit` | DuckDB sort spill | Raise memory AND ephemeral-storage |
| `OOMKilled` | Insufficient RAM | Raise memory |
| `ContainerStatusUnknown` on shared nodes | Preemption | Pin to Berkeley node |

**DuckDB sort jobs need both big RAM and big ephemeral-storage.** `ORDER BY` over large data spills to disk; low RAM spills more. For 1–15 GB compressed partitions: 120Gi RAM, 50Gi ephemeral-storage. Namespace max for ephemeral-storage is **50Gi** — always request the max for sort-heavy jobs.

**When scratch exceeds 50Gi, mount a PVC — do NOT fight the ephemeral cap.** Ephemeral-storage is hard-capped at 50Gi namespace-wide, so any job whose local scratch exceeds that — a raw download bigger than ~45 GB (e.g. the 35 GB RAP CONUS COG), a multi-tile `preprocess-cog` mosaic, a `raster --local-cache-dir` localization of a large COG — must use a **PersistentVolumeClaim**, not a bigger ephemeral request (which the quota will reject). A shared scratch PVC already exists: **`rechunk-scratch`** (2Ti, `RWX` rook-cephfs) — list with `kubectl -n geo-workflows get pvc`.
- Mount it and redirect the tool's scratch onto it; keep ephemeral small (~10Gi):
  ```yaml
  volumeMounts:
  - {name: scratch, mountPath: /scratch, subPath: <job-name>}   # subPath → per-job isolation on the shared PVC
  volumes:
  - {name: scratch, persistentVolumeClaim: {claimName: rechunk-scratch}}
  env:
  - {name: TMPDIR, value: /scratch}        # Python tempfile.mkdtemp (mosaic temp) honors TMPDIR
  # and pass: cng-datasets raster --local-cache-dir /scratch ...   (input localization; CLI default is /tmp/cng-raster-cache)
  ```
- **`RWX` + concurrency caveat:** `rechunk-scratch` is ReadWriteMany, but `--local-cache-dir` localizes to a fixed basename, so **N concurrent pods sharing one mountPath collide on the same file**. Use a per-pod `subPath` (or per-pod cache subdir) for fan-out jobs. The 122-pod raster **hex** step localizes a multi-GB COG per pod and is best left on **per-pod ephemeral** (the mosaic COG fits in 50Gi); reserve the PVC for the **single-pod** `preprocess-cog`/download/stage steps where the file genuinely exceeds 50Gi.

**Hex OOM** → regenerate with `--hex-memory 64Gi` and/or more `--max-completions`, delete failed job, reapply.

**503 SlowDown (S3 throttle)** → transient, retry.

**PMTiles renders blank in MapLibre → wrong `source-layer`.** It's the last path segment of `--dataset`, NOT the GDB/source layer name. For `--dataset padus-4-1/fee`, it's `fee` (not `PADUS4_1Fee`).

**Workflow stuck:** `kubectl logs job/<name>-workflow` and `kubectl get jobs | grep <name>`.

**`exceeded quota: reached-quota`** → pod limit hit. Delete running hex jobs and resubmit sequentially (see Namespace Pod Quota):
```bash
kubectl get jobs | grep -E 'dataset-a|dataset-b' | awk '{print $1}' | xargs kubectl delete job
```

### Reprocessing Failed Chunks

For chunks that fail (e.g. DuckDB parquet page-size limits on complex geometries), reprocess at coarser H3:
1. Identify failed IDs: `kubectl get pods | grep <name>-hex | grep -E "Error|Failed"`
2. Copy `<name>-hex.yaml` → `<name>-hex-rechunk.yaml`, rename the job, set `completions: <N-failed>`, and replace the command with a CHUNK_MAP:
   ```yaml
   args:
   - |
     set -e
     CHUNK_MAP=(0 1 2 94)
     CHUNK_ID=${CHUNK_MAP[$JOB_COMPLETION_INDEX]}
     cng-datasets vector \
       --input s3://<bucket>/<dataset>.parquet \
       --output s3://<bucket>/<dataset>/chunks \
       --chunk-id $CHUNK_ID --chunk-size <same> --intermediate-chunk-size <same> \
       --resolution 8 --parent-resolutions 9,8,0
   ```
3. Apply, then run `<name>-repartition.yaml`. Repartition merges both resolutions from `chunks/` → `hex/` by h0.

## What NOT To Do

- **Do not process data locally.** CLI generates YAML; the cluster does the work.
- **Do not modify `cng_datasets/` source.** File an issue (see Hard Boundary 2).
- **Do not request more than 50Gi ephemeral-storage.** The namespace caps it at 50Gi; generated YAMLs default to 250Gi — reduce to 50Gi and add `limits.ephemeral-storage: 50Gi` before applying.
- **Do not use multiple .zip URLs with `cng-datasets workflow`.** Preprocess first.
- **Do not record operational/how-to-work lessons in agent memory (`~/.claude/.../memory`).** This repo is cloned and run by students — and soon by always-on headless agents (Hermes/openclaw). Anything that should shape how tasks run here belongs in **this AGENTS.md or a local skill (`.claude/skills/`)**, so every clone and headless run behaves the same. A lesson saved only to one VM's memory silently diverges your experience from everyone else's. (Memory remains fine for genuinely personal, non-shareable session context.)

## Reference Examples

### PAD-US (multi-layer GDB, 5 spatial layers)
```bash
# One-time raw upload
rclone copy PADUS4_1Geodatabase.gdb nrp:public-padus/raw/PADUS4_1Geodatabase.gdb -P

# Generate per-layer workflows
for args in \
  "padus-4-1/fee PADUS4_1Fee" \
  "padus-4-1/easement PADUS4_1Easement" \
  "padus-4-1/proclamation PADUS4_1Proclamation" \
  "padus-4-1/marine PADUS4_1Marine" \
  "padus-4-1/combined PADUS4_1Combined_Proclamation_Marine_Fee_Designation_Easement"; do
  set -- $args
  cng-datasets workflow --dataset "$1" \
    --source-url https://s3-west.nrp-nautilus.io/public-padus/raw/PADUS4_1Geodatabase.gdb \
    --bucket public-padus --layer "$2" \
    --h3-resolution 10 --hex-memory 32Gi --max-completions 200 --max-parallelism 50 \
    --parent-resolutions "9,8,0" \
    --output-dir "catalog/pad-us/k8s/$(echo $1 | cut -d/ -f2)"
done

kubectl apply -f catalog/pad-us/k8s/fee/workflow-rbac.yaml   # once
for layer in fee easement proclamation marine combined; do
  kubectl apply -f catalog/pad-us/k8s/$layer/configmap.yaml -f catalog/pad-us/k8s/$layer/workflow.yaml
done
```
Non-spatial lookup tables: see `catalog/pad-us/k8s/extract-lookup-tables.yaml` and `catalog/pad-us/lookup-tables.md`.

### Census 2024 (per-state zips → preprocess → pipeline)
TIGER/Line ships per-state. Discover pattern:
```bash
curl -I https://www2.census.gov/geo/tiger/TIGER2024/TRACT/
curl -s https://www2.census.gov/geo/tiger/TIGER2024/TRACT/ | grep '.zip' | head
# tl_2024_01_tract.zip, tl_2024_02_tract.zip, ...
```
Preprocess job (`catalog/census/k8s/tract/preprocess-tract.yaml`) parallel-downloads, unzips, and calls `cng-convert-to-parquet /tmp/tracts/*.shp s3://...` (tool merges). ~3 min for 56 files. Then:
```bash
cng-datasets workflow --dataset census-2024/tract \
  --source-url s3://public-census/census-2024/tract.parquet --bucket public-census \
  --h3-resolution 10 --parent-resolutions "9,8,0" \
  --hex-memory 16Gi --max-completions 200 --max-parallelism 50 \
  --output-dir catalog/census/k8s/tract
kubectl apply -f catalog/census/k8s/tract/census-2024-tract-hex.yaml
kubectl apply -f catalog/census/k8s/tract/census-2024-tract-pmtiles.yaml
# after hex:
kubectl apply -f catalog/census/k8s/tract/census-2024-tract-repartition.yaml
```
Result: ~85,000 tracts.

### Carbon raster (single COG already on S3)
```bash
cng-datasets raster-workflow --dataset irrecoverable-carbon-2022 \
  --source-url s3://public-carbon/v2/cogs/irrecoverable_c_total_2022.tif \
  --bucket public-carbon --h3-resolution 8 --parent-resolutions "0" \
  --value-column carbon --hex-memory 32Gi --max-parallelism 61 \
  --output-dir catalog/carbon/k8s/v2/irrecoverable-carbon-2022

kubectl apply -f catalog/carbon/k8s/v2/irrecoverable-carbon-2022/workflow-rbac.yaml
kubectl apply -f catalog/carbon/k8s/v2/irrecoverable-carbon-2022/configmap.yaml \
              -f catalog/carbon/k8s/v2/irrecoverable-carbon-2022/workflow.yaml
```
Hex job runs `cng-datasets raster` once per h0 cell (122 indexed pods), writing `hex/h0={cell}/data_0.parquet`. Empty cells skipped silently. No repartition step — output goes directly to its final partition.

## Checking for User Dataset Requests

Request form: **https://data-requests.nrp-nautilus.io/** (per-app routes, e.g. `/tpl`). Submissions stored as JSON in `s3://public-requests/dataset-requests/`.

Check at session start:
```bash
curl -s https://data-requests.nrp-nautilus.io/api/requests | python3 -m json.tool
rclone ls nrp:public-requests/dataset-requests/
```
Each submission: `app`, `timestamp`, plus user fields (dataset name, description, contact).

Triage:
1. Review; decide if in scope.
2. If yes: file a GitHub issue on `boettiger-lab/data-workflows` with the dataset import template (source URL, deliverables, bucket).
3. Tag with the `app` if it came from a specific form.

Form deployment: `dataset-requests/` — see `dataset-requests/README.md` for adding routes / redeploying.
