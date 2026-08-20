# Agent Instructions: Dataset Processing

You work in `data-workflows`, which uses `cng-datasets` to convert geospatial data into cloud-native formats on Kubernetes. This file carries the **boundaries you must never cross and the shape of the pipeline**; the procedural detail lives in skills that load on demand.

## Skills — load the one that matches what you are doing

These are `.claude/skills/<name>/SKILL.md` in this repo. They work in Claude Code and opencode
alike (both read `.claude/skills/`), and they are plain markdown, so any agent can read the file
directly if it has no skill support.

| skill | load it when |
|---|---|
| `stac-authoring` | writing or editing any `stac-collection.json` or dataset README (Steps 5–6) |
| `raster-hexing` | ingesting or re-hexing a GeoTIFF/COG — resolution, reducer, mosaicking |
| `hex-tuning` | a hex job OOMs, or choosing native/parent H3 resolutions and chunk sizes |
| `job-troubleshooting` | a job fails, hangs, or a published parquet will not read |
| `dataset-recipes` | starting an ingest that resembles a worked example |

Everything below is always in force, skill or no skill.

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

### ⛔ Serialization standard: keep parquet row groups small

A single parquet column chunk in the **~2.8–2.88 GB compressed** range makes DuckDB's httpfs
reader abort with **`SQL Error: stoi`** — a reader bug on the `https://` path, not corrupt data
(fully diagnosed in datasets [#106](https://github.com/boettiger-lab/datasets/issues/106)).

**Prevention is the fix: use `--row-group-size 2000` as the default for geometry-heavy
datasets**, so no geometry column chunk approaches ~1 GB compressed. The default 100000 can pack
a single chunk past the cliff on national-scale multipolygons.

Full diagnosis, what does *not* matter (CRS tag, writer, one bad geometry), and how to rescue an
already-published file: **skill `job-troubleshooting`**.
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

**Credentials you have, and the only two you ever need:**
- **Public buckets (almost everything).** Build jobs read and write **NRP only**, with the
  `aws` + `rclone-config` secrets already in `geo-workflows`. Reading public data needs no
  credential at all. Stage raw under `s3://<bucket>/raw/` (Step 1b).
  A workflow-namespace `rclone-config` holding only `[nrp]` is **correct, not a
  missing-remote bug** (internal endpoint `http://rook-ceph-rgw-nautiluss3.rook`,
  `upload_concurrency=16`, `chunk_size=64Mi`).
- **Private buckets** (`private-wyoming`, `private-tpl`) live only on MinIO. Mount a
  **scoped, single-bucket, on-demand EXPIRING mint** for that one bucket
  (`mc admin user svcacct add <parent> --policy <one-bucket> --expiry …`; the
  `wyoming-publish` model) — never a standing broad key. This is the only MinIO access a
  build job ever has.

⛔ **Never add any other remote or secret to a workflow namespace.** If a job appears to need
one, it is out of scope — stop and ask.

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

> 💡 To read a schema, a lookup table, or one layer's coverage out of a multi-GB remote zip,
> use GDAL range reads (`/vsizip//vsicurl/…`) instead of localizing the archive — a small job,
> seconds to minutes, no PVC. Worked examples: **skill `dataset-recipes`**.
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

**`cng-convert-to-parquet` rejects multiple `.zip` URLs.** For per-state/per-region zips, run a
preprocess job that downloads in parallel, unzips, and passes the shapefiles (the tool merges
them automatically). Worked k8s job: **skill `dataset-recipes`**.
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

Rasters produce **COG + hex only** (no GeoParquet/PMTiles); a WGS84 COG is always created on NRP
S3 first and the hex reads from that COG. Completions are always **122** (one per h0 cell) — not
configurable.

⛔ **Two choices here silently corrupt the data if you get them wrong, and both are measurements,
not preferences:**

- **`--h3-resolution` — match the source pixel.** Finer than the source adds no information at
  ~7× cost per step. Never rely on auto-detection.
- **`--hex-resampling` — the reducer** (`sum` / `mean` / `mode` / `max` / `min`, default `mean`).
  Summing a *density* is the recurring error: the reducer follows the source **units**, not the
  conceptual quantity.

Resolution anchors, the reducer decision table, many-tile mosaicking, and the re-hex campaign
checklist: **skill `raster-hexing`**.
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

⛔ **Do not hand-check the STAC rules — run the gate.**

```bash
scripts/verify-stac.py --no-data /tmp/stac-collection.json       # pre-publish (static)
scripts/verify-stac.py --bucket <bucket> --dataset <dataset>     # post-cluster (full, data-backed)
```

Fix every HARD finding before `rclone copyto`; the post-cluster run must exit 0. CI runs the same
verifier on the PR, deriving collections from the `s3://` paths in changed `catalog/**` YAMLs — so
a RED check at PR-open is correct, and you re-fire it after the cluster jobs land.

Everything about *what to write* — the user-facing description register, `table:columns`
placement, SPDX license rules, categorical `values`, hex per-feature duplication notes, `h3:*`
declarations, point/line notes — is in **skill `stac-authoring`**. Load it before writing or
editing any `stac-collection.json` or README.
### Step 6: Register in the parent sub-catalog

**The STAC catalog is a TREE** — datasets belong in their domain/bucket sub-catalog, not the root.
Only touch the root when adding a **new** top-level sub-catalog. Procedure: **skill
`stac-authoring`**.
### Step 7: Get the licence right

**This is a metadata step and nothing else.** Every collection carries an accurate SPDX
`license` plus a `{"rel": "license"}` link in its STAC (Step 5). Getting it wrong is how data
ends up over- or under-published.

- Record what upstream actually granted, with evidence.
- If the terms are genuinely unconfirmed or no licence was granted, say so: a non-committal
  `license` **and** a description sentence stating it. Never assert an SPDX id upstream did not
  grant, and never name a provider as `licensor` when no licence was granted. This has gone
  wrong in both directions — `rivers/american-rivers/*` asserted `CC-BY-4.0` with no `licensor`
  behind it, and `hazard/mid-century-habitat-climate-exposure` asserts `CC-BY-4.0` while its own
  description says the terms "require confirmation".
- Do not invent a terms URL to clear the gate. If no public terms page exists, the finding
  stands; record the facts in the description and say so in the issue.

## Hex sizing and resolution

**RAM is driven by the H3 cell count of the single largest feature in a chunk — not dataset
size, not bounding box.** 10,000 small features at 8Gi can be fine while one continent-scale
polygon OOMs at 32Gi. OOMs are a tuning signal, not a failure.

**`h8` is the catalog's universal join key.** Default native resolution is **8**; every dataset
finer than 8 (native `h9`/`h10`) MUST carry `h8` as a parent, and **`h0` always** (it is the hive
partition key and the coarsest common join). Go coarser than 8 only when feature size or source
pixel genuinely forces it — such a dataset *cannot* carry `h8`, which is a sanctioned case that
must be stated in the hex asset description so an agent does not conclude the data is broken.

**Always record the chosen native + parent resolutions in the GitHub issue** (scope) and in the
hex asset's `h3:native_resolution` / `h3:parent_resolutions`.

Full memory model, resolution and parent-set decision tables, vector/raster workflow parameters,
and reprocessing failed chunks: **skill `hex-tuning`** (raster specifics: **`raster-hexing`**).
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

**Diagnose before resubmitting.** `kubectl -n geo-workflows describe pod <pod>` first — the same
resources will fail the same way. ⛔ **Never `kubectl delete pod --force` / `--grace-period=0`**;
let the control plane reap it (skill `k8s-never-force-delete`).

Causes and fixes — OOMKilled, evictions, `ContainerStatusUnknown`, flaky-node hangs,
ephemeral-storage limits and PVC scratch, pod-quota errors, 404s on convert, blank PMTiles in
MapLibre, DuckDB `stoi` — plus how to reprocess failed chunks: **skill `job-troubleshooting`**.
## What NOT To Do

- **Do not process data locally.** CLI generates YAML; the cluster does the work.
- **Do not modify `cng_datasets/` source.** File an issue (see Hard Boundary 2).
- **Do not request more than 50Gi ephemeral-storage.** The namespace caps it at 50Gi; generated YAMLs default to 250Gi — reduce to 50Gi and add `limits.ephemeral-storage: 50Gi` before applying.
- **Do not use multiple .zip URLs with `cng-datasets workflow`.** Preprocess first.
- **Do not record operational/how-to-work lessons in agent memory (`~/.claude/.../memory`).** This repo is cloned and run by students — and soon by always-on headless agents (Hermes/openclaw). Anything that should shape how tasks run here belongs in **this AGENTS.md or a local skill (`.claude/skills/`)**, so every clone and headless run behaves the same. A lesson saved only to one VM's memory silently diverges your experience from everyone else's. (Memory remains fine for genuinely personal, non-shareable session context.)

## Reference Examples

Worked end-to-end ingests to copy from — PAD-US multi-layer GDB (5 spatial layers), Census TIGER
per-state zips with a preprocess job, and a single-COG carbon raster: **skill `dataset-recipes`**.
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
