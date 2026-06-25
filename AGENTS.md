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
```bash
uv venv && source .venv/bin/activate
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

### Step 1b: Copy raw to `s3://<bucket>/raw/` FIRST

External downloads are slow/rate-limited; restart from S3 if conversion fails. Subsequent jobs read `s3://<bucket>/raw/<file>` (or `/vsicurl/https://s3-west.nrp-nautilus.io/<bucket>/raw/<file>` for GDAL).

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

**stac-collection.json MUST include:**

- **License — REQUIRED on every collection.** Set the top-level STAC `license` field to the **SPDX identifier** of the upstream data license (e.g. `CC-BY-4.0`, `CC-BY-NC-4.0`, `CC-BY-SA-4.0`, `CDLA-Permissive-2.0`, `public-domain`). Use `"other"` **only** when no SPDX id applies, and `"various"` **only** for a meta-collection whose children genuinely differ — never as a lazy default. For `other`/`various` (and recommended for all), add a license link: `{"rel": "license", "href": "<canonical terms URL>", "type": "text/html"}`. **Verify the real upstream terms — do not guess `proprietary`.** The license drives redistribution decisions (e.g. whether a dataset may be mirrored to source.coop); a wrong value is a compliance risk. NonCommercial / ShareAlike licenses are fine but MUST be recorded as such (`CC-BY-NC-*`, `CC-BY-SA-*`) so downstream users aren't misled. US federal works = `public-domain`.

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

- **`table:columns` goes on each parquet asset — NOT at the collection level.** Put it inside the asset object for the GeoParquet and hex assets. Do not add a top-level `table:columns` to the collection. The geo-agent reads asset-level schemas via MCP; collection-level is only a fallback for legacy datasets.

  Each parquet asset documents exactly the columns it contains:
  - **GeoParquet asset**: include the geometry column (`Shape`, `geom`, or `geometry`)
  - **Hex asset**: exclude the geometry column; include H3 index columns (`h0`, `h8`, `h9`, `h10` etc.) and `_cng_fid`/`bbox` if present
  - **COG assets**: no `table:columns` needed (not SQL-queryable)

- **PMTiles assets MUST carry tile-accurate `table:columns` (data-workflows #283).** tippecanoe selects a *subset* of source columns at tile-build time, so the PMTiles fields differ from the GeoParquet schema — the parquet's `table:columns` does NOT tell a consumer what's actually in the tiles. Without tile-level schema the geo-agent (and human app authors) cannot discover which fields are stylable/filterable in MapLibre except by byte-ranging the `.pmtiles` footer. So:
  - List the **actual tile fields** (not the parquet schema) with `name` + `type`, read from the footer's `vector_layers[].fields`. The geometry column is excluded (it's the tile geometry, not a field).
  - Keep `vector:layers` (the source-layer id list) as well.
  - **Document nodata sentinels** on the relevant column (e.g. SVI `RPL_THEMES = -999`) and flag the **intended value column** for continuous styling — neither is inferable from the tiles.
  - Read the footer fields with:
    ```bash
    python3 -c 'import urllib.request,json,struct,gzip; u="https://.../layer.pmtiles"; \
      r=lambda a,b: urllib.request.urlopen(urllib.request.Request(u,headers={"Range":f"bytes={a}-{b}"})).read(); \
      h=r(0,126); o=struct.unpack_from("<Q",h,24)[0]; n=struct.unpack_from("<Q",h,32)[0]; \
      m=json.loads(gzip.decompress(r(o,o+n-1)).decode()); print([(L["id"],L.get("fields")) for L in m["vector_layers"]])'
    ```
  - Gate with `scripts/lint-stac-pmtiles-fields.py <stac-collection.json|url>` (companion to `lint-stac-categorical.py`).

- **Hex assets MUST declare their H3 resolutions explicitly** via `h3:native_resolution` and `h3:parent_resolutions` on the asset itself. Column-name presence (`h10`, `h9`, …) is not enough — downstream tools shouldn't have to enumerate `table:columns` to find out what resolutions exist. `h3:native_resolution` is the finest resolution (one row per feature-cell at this res); `h3:parent_resolutions` is the list of rollup resolutions, which MUST include `0` (the partition key).

- **Hex assets MUST flag per-feature duplication on any attribute a consumer might aggregate.** One hex row = one (feature, cell) pair, so any column that represents a per-feature total — area (`GIS_Acres`, `SHAPE_Area`), length (`SHAPE_Length`), population, count, amount, funding, intensity — is repeated on every cell the feature covers. The column description on the hex asset MUST state this and give a dedup recipe. Use one of:
  - **Area/length from hex count** (never SUM the source value): `COUNT(DISTINCT h<N>) × cell_area_at_resolution_N`. Per-resolution H3 cell areas are H3-standard constants — do not inline them in column descriptions. The agent reads them from `mcp-data-server/h3-guide.md`.
  - **SUM after dedup** (when the attribute is a real per-feature value): `SELECT DISTINCT <feature_key>, <attr> …` or `ROW_NUMBER() OVER (PARTITION BY <feature_key>)` before aggregating.

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
         "description": "Land area in m² of the source district polygon. **Repeated on every hex row the district covers — never SUM(ALAND) on hex data. Compute area from hex count: COUNT(DISTINCT h10) × cell_area_at_resolution_10** (see h3-guide for per-resolution cell areas)."},
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
  - **Repeated features (polygon/point assets).** If the source file has multiple rows per feature (a site split into parcels, multipart polygons), the asset description MUST say so, name the feature id, and give a dedup recipe (`COUNT(DISTINCT <id>)` for counts; dedup by `<id>` before summing per-feature values). e.g. Ramsar: 8,347 rows / 2,551 `ramsarid`. `verify-stac.py` surfaces candidates as **ADVISORY** — the `rows > COUNT(DISTINCT id)` signal over-flags (the column may be a label or provenance key, not the feature id), so confirm against the data before writing the note (see [[per-feature-dup-audit-heuristic]]).
  - **NULL finest-parent cells.** If the hex build caps very large features at a coarser native resolution (WDPA: `h9` is NULL for the 1,297 biggest features, `h8` is complete), the hex asset description MUST name the complete column and say joins should use the coarsest shared resolution (or `h3_cell_to_parent()`), not the finest. `verify-stac.py` **HARD**-flags an undocumented NULL finest hex column.
  - **No-data sentinels.** Document sentinel/fill codes (e.g. land-cover `0`/`200`) so consumers `WHERE col NOT IN (...)` before `SUM`/`AVG` — an undocumented sentinel poisons aggregates to `NaN`.

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

### Step 7: Add a MinIO sync job (new buckets only)

All NRP buckets mirror to MinIO via per-bucket k8s Jobs in `catalog/sync/k8s/`. If the dataset uses an existing bucket — nothing to do.

For a new bucket:
```bash
cp catalog/sync/k8s/sync-public-padus.yaml catalog/sync/k8s/sync-<bucket>.yaml
# Replace "public-padus" everywhere (job name, mkdir, sync src/dest, echoes)
```
Each job `rclone mkdir`s the dest bucket then `rclone sync`s with throttling.

Run/rerun:
```bash
kubectl apply -f catalog/sync/k8s/                    # all
kubectl apply -f catalog/sync/k8s/sync-<bucket>.yaml  # one
kubectl delete job sync-<bucket> -n biodiversity && kubectl apply -f .../sync-<bucket>.yaml  # rerun
kubectl logs job/sync-<bucket>                        # monitor
```

MinIO is the **private backup** of every `public-*` bucket — and the *only* off-NRP copy for datasets whose license forbids public redistribution.

### Step 7b: source.coop public mirror

Public datasets are *also* mirrored to **Source Cooperative** (`us-west-2.opendata.source.coop/cboettig/<repo>`) for discoverability. This is a **license-gated** campaign — **do not** add a bucket without reading the plan first:

- **`catalog/sync/source-coop/README.md`** — campaign plan: scope policy (catalogued **and** license-clear only), the add-a-repo loop, the **account-wide-credentials safety guard**, and the phase-2 STAC href-rewrite.
- **`gen-source-sync.sh`** (`REPOS` + `EXCLUDES`) is the scope source-of-truth; **`license-inventory.md`** has per-collection license verdicts; **`new-repos.md`** lists repos still to create (creation is manual in the web UI — the API is disabled).
- Some datasets **must not** be mirrored — WDPA/WD-OECM/ICCA/IUCN/HydroBASINS forbid redistribution (MinIO-only). Every collection needs a correct STAC `license` (see the License requirement above) before it can be classified.
- **Backup cadence:** a weekly **`source-sync` CronJob** (Sundays 08:00 UTC, `catalog/sync/k8s/source-sync-cron.yaml`) keeps every in-scope repo current automatically. It loops the generated `source-sync-scope` ConfigMap (`repos.txt`) sequentially at 50 MB/s, continue-on-error, then **re-applies the Phase 2 STAC href-rewrite** as its final step. Scope lives in that ConfigMap (regenerated by `gen-source-sync.sh`), so after a scope change run `./gen-source-sync.sh` and `kubectl apply -f catalog/sync/k8s/source-sync-cron-config.yaml`. The per-repo `source-sync-<repo>.yaml` jobs + `run-source-sync.sh` remain for manual/backfill runs.
- **STAC self-consistency (Phase 2, done):** `catalog/sync/source-coop/rewrite-stac-hrefs.py` rewrites the mirrored STAC hrefs to `data.source.coop/cboettig/<repo>/…` (leaving `root`/`parent`→NRP canonical), drops dangling HOLD `child` links, and is idempotent. The data sync would clobber it, so the CronJob runs it after every mirror; run it manually with `--dry-run` first if editing.
- Status & decisions: **issue #158**.

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

### Vector workflow parameters

| Param | Default | When to change |
|---|---|---|
| `--h3-resolution` | 10 | Lower (8, 6) for large polygons. Halving res ≈ 6× fewer cells. |
| `--hex-memory` | 8Gi | Tune from OOM signals. Start low. |
| `--max-completions` | 200 | k8s backend hard limit. With armada: set to feature count for chunk-size 1. |
| `--max-parallelism` | 50 | k8s only — capped by pod quota. Unused with armada. |
| `--parent-resolutions` | "9,8,0" | Use `"0"` when `--h3-resolution 8` (9/8 would duplicate target). |
| `--intermediate-chunk-size` | 10 | Decrease if hex OOMs during unnest — try this before raising memory. |

### Raster workflow parameters

| Param | Default | When to change |
|---|---|---|
| `--h3-resolution` | auto (from pixel size) | Override if auto is wrong |
| `--hex-memory` | 32Gi | Raise if OOM |
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
5. **Flip: purge-and-VERIFY-empty, then sync.** `cng-datasets raster` overwrites the partition for each h0 it produces, but does **not** remove partitions for h0s that now yield no data — so reprocessing to a smaller/different domain (e.g. all-land → wetland-only) leaves **stale partitions** behind that corrupt aggregates. And `rclone purge` can silently no-op under S3 load. So purge staging **and confirm it's empty** before any re-hex. `kubectl apply` on a completed Job is a no-op; `delete`+`apply` to rerun. Jobs TTL-GC 3 h after completion — validate before then.

## Namespace Pod Quota (`biodiversity`)

**Hard limit: 200 pods total** across all simultaneous jobs. Applies to **k8s backend only** — armada queues externally and is not constrained.

**Rule: never submit more than one k8s hex workflow at a time.** With `--max-parallelism 50`, a single hex job can take 50 pods; concurrent hex workflows exhaust the quota:
```
pods "...-hex-60-..." is forbidden: exceeded quota: reached-quota,
  used: pods=200, limited: pods=200
```
Run sequentially:
```bash
for d in dataset-a dataset-b dataset-c; do
  kubectl apply -f catalog/.../k8s/$d/configmap.yaml -f catalog/.../k8s/$d/workflow.yaml
  kubectl wait job/$d-workflow --for=condition=complete --timeout=7200s
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

**Pod keeps getting evicted (`ContainerStatusUnknown`) → diagnose BEFORE resubmitting.** Never resubmit a failing job without `kubectl describe pod <pod>` — same resources will fail the same way.
```bash
kubectl -n biodiversity describe pod <pod-name> | grep -A5 "Reason:\|Message:\|Events:"
```

| Message | Cause | Fix |
|---|---|---|
| `ephemeral local storage usage exceeds the total limit` | DuckDB sort spill | Raise memory AND ephemeral-storage |
| `OOMKilled` | Insufficient RAM | Raise memory |
| `ContainerStatusUnknown` on shared nodes | Preemption | Pin to Berkeley node |

**DuckDB sort jobs need both big RAM and big ephemeral-storage.** `ORDER BY` over large data spills to disk; low RAM spills more. For 1–15 GB compressed partitions: 120Gi RAM, 50Gi ephemeral-storage. Namespace max for ephemeral-storage is **50Gi** — always request the max for sort-heavy jobs.

**When scratch exceeds 50Gi, mount a PVC — do NOT fight the ephemeral cap.** Ephemeral-storage is hard-capped at 50Gi namespace-wide, so any job whose local scratch exceeds that — a raw download bigger than ~45 GB (e.g. the 35 GB RAP CONUS COG), a multi-tile `preprocess-cog` mosaic, a `raster --local-cache-dir` localization of a large COG — must use a **PersistentVolumeClaim**, not a bigger ephemeral request (which the quota will reject). A shared scratch PVC already exists: **`rechunk-scratch`** (2Ti, `RWX` rook-cephfs) — list with `kubectl -n biodiversity get pvc`.
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
