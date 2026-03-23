# Agent Instructions: Dataset Processing

You are working in a repository that uses `cng-datasets` to process geospatial data into cloud-native formats on a Kubernetes cluster. This document tells you everything you need to know.

## ⛔ HARD BOUNDARY: NRP S3 is the Canonical Source for STAC and Data

**The canonical versions of all datasets and STAC metadata live on NRP S3 buckets** (e.g. `s3://public-census/`, `s3://public-wetlands/`). The public URLs are `https://s3-west.nrp-nautilus.io/<bucket>/...`.

**This git repo does NOT contain copies of STAC JSON or README files.** There are no `catalog/*/stac/` directories. When you need to read, update, or create STAC metadata:

- **Read**: `curl https://s3-west.nrp-nautilus.io/<bucket>/stac-collection.json`
- **Write**: edit locally in `/tmp/`, then `rclone copyto /tmp/stac-collection.json nrp:<bucket>/stac-collection.json`

Never read a local `catalog/*/stac/*.json` file as if it were canonical — it does not exist and would be stale if it did. Never write STAC files into the git repo.

## ⛔ HARD BOUNDARY: Do NOT Touch the `cng-datasets` Tool Repo

**You work exclusively in this repository (`data-workflows`). You do NOT:**
- Edit, commit, push, or PR to `boettiger-lab/datasets` (the `cng-datasets` tool)
- Check out, modify, or hotfix code in any other repository
- Attempt workarounds in the tool code when workflows fail

**If `cng-datasets` has a bug or missing feature:**
1. File a GitHub Issue on `boettiger-lab/datasets` with a **minimal reproducible example (MRE)** — see requirements below
2. Tell the user what you filed and wait for the fix
3. Do NOT attempt to fix it yourself — previous hotfixes have introduced breaking regressions

**Why:** The tool has automated tests and a build/deploy pipeline. Unreviewed hotfixes bypass these safeguards and have caused production failures. Issue reports are the correct escalation path.

### Bug Report Requirements: Minimal Reproducible Example

Every bug report MUST include code you have **actually run** that **reproduces the error**. Do not assert a cause without running code to confirm it.

**The MRE must:**
1. **Isolate the bug to the tool** — verify the upstream input is correct before blaming the tool. E.g., for a coordinate ordering bug: run `ogrinfo` or `ST_Read` on the raw source and confirm coordinates are correct *before* conversion.
2. **Run the tool locally and capture the bad output** — actually execute `cng-convert-to-parquet` or `cng-datasets` and show the wrong result. Do not infer the tool is broken from downstream artifacts (e.g., bad S3 parquet) without running the tool yourself.
3. **Show expected vs actual** with concrete values.
4. **Be minimal** — one feature, one file, not a full dataset.

**Template:**
```bash
# Step 1: show the input is correct
ogrinfo /vsizip/source.zip -al -where "NAME='X'" | grep 'POLYGON\|Extent'
# → correct (lon, lat) coordinates

# Step 2: run the tool
cng-convert-to-parquet source.zip /tmp/output.parquet

# Step 3: show the bug in the output
python3 -c "
import duckdb; conn = duckdb.connect(); conn.execute('LOAD spatial;')
print(conn.execute(\"\"\"
  SELECT ST_AsText(ST_Envelope(geom)), bbox.xmin, bbox.ymin
  FROM read_parquet('/tmp/output.parquet') WHERE NAME='X'
\"\"\").fetchdf())
"
# → wrong output: xmin=38.32 (latitude) instead of -120.07 (longitude)
```

**Do not file a bug report without running these steps.** Circumstantial evidence ("the S3 parquet has bad coordinates therefore the tool is broken") is not an MRE — the S3 data could be stale from an old tool version.

## What You Are Doing

You are taking source geospatial data and producing cloud-native outputs. The outputs depend on whether the dataset is **vector** or **raster**:

### Vector datasets (GDB, Shapefile, GeoPackage, GeoParquet)

| Format | File | Use |
|--------|------|-----|
| GeoParquet | `dataset.parquet` | Analytical queries with DuckDB/Polars |
| PMTiles | `dataset.pmtiles` | Web map visualization |
| H3 Hex Parquet | `dataset/hex/h0={cell}/data_0.parquet` | Spatial joins and aggregation |

### Raster datasets (GeoTIFF, COG)

| Format | File | Use |
|--------|------|-----|
| COG | `dataset-cog.tif` | Cloud-optimized raster visualization (titiler etc.) |
| H3 Hex Parquet | `dataset/hex/h0={cell}/data_0.parquet` | Spatial aggregation and joins |

Rasters do **not** produce GeoParquet or PMTiles, but they **do** produce H3 hex parquet. The COG is often already available as the source; the main processing step is hex tiling.

**H3 hex is supported for polygon and point geometries; line geometries are not supported.** Always check geometry type before submitting a hex job:
```python
# Quick check (run locally with spatial extension)
SELECT ST_GeometryType(geom), COUNT(*) FROM read_parquet('s3://...') GROUP BY 1
```

**Point geometry note:** Point and MultiPoint datasets are supported — each point resolves to a single H3 cell at the requested resolution. This means point data loses no spatial precision at fine resolutions (e.g., 10), but at coarse resolutions (e.g., 6–8) many points may map to the same cell. A warning is emitted during hex processing when point geometries are detected. Document this behavior in the STAC metadata (see STAC documentation guidance below).

**Line geometry:** Line (LineString/MultiLineString) datasets **cannot be hexed** — skip the hex step for line datasets and note the limitation.


**ALWAYS use the k8s workflow for data processing. The local environment does not have all required tools and permissions.**

### Local Environment Setup

The `cng-datasets` CLI is only used locally to generate k8s YAML files:

```bash
uv venv
source .venv/bin/activate
uv pip install git+https://github.com/boettiger-lab/datasets.git
```

## How To Process a Dataset

### Step 1: Identify and verify the source data

**ALWAYS verify URLs exist before generating workflows.** Do not assume file naming patterns.

#### Verify single-file datasets

Use curl to check that the file exists:
```bash
curl -I https://example.com/data.zip
# Look for "HTTP/2 200" - anything else (404, 403) means the file doesn't exist
```

#### Discover multi-file datasets

Many datasets are distributed as **multiple files** (e.g., per-state, per-region). Check the directory listing:

```bash
# List available files in a directory
curl -s https://www2.census.gov/geo/tiger/TIGER2024/TRACT/ | grep '.zip' | head -20

# Check specific file pattern
curl -I https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_01_tract.zip
```

**Common patterns:**
- Census TIGER data: Per-state files (`tl_2024_{STATEFP}_tract.zip`)
- Protected areas: Often per-region or national
- Raster data: May be tiled

#### Preprocessing multi-file zipped datasets

**CRITICAL: `cng-convert-to-parquet` cannot handle multiple .zip URLs — it detects .zip in paths and blocks multi-source processing.**

For datasets distributed as multiple zipped files (e.g., per-state shapefiles):

**✅ CORRECT: Download, unzip, pass shapefiles**
```bash
# Download all in parallel
for id in 01 02 03; do
  curl -sS -O "https://example.com/data_${id}.zip" &
done
wait

# Unzip all
unzip -q -o "*.zip"

# Let the tool merge them (that's what it does!)
cng-convert-to-parquet /tmp/data/*.shp s3://bucket/output.parquet
```

**❌ WRONG: Sequential merging with ogr2ogr**
```bash
# Don't do this - you're reimplementing what the tool already does
ogr2ogr -f Shapefile merged.shp file1.shp
ogr2ogr -update -append merged.shp file2.shp  # Slow!
ogr2ogr -update -append merged.shp file3.shp  # Very slow!
cng-convert-to-parquet merged.shp output.parquet
```

**Why parallel download + direct tool usage is better:**
- Parallel downloads complete in seconds vs sequential minutes
- `cng-convert-to-parquet` already merges multiple shapefiles efficiently
- Don't re-implement what the tool does — let it handle the merge
- Census tracts: 3 minutes total (vs 30+ minutes with sequential ogr2ogr)

**Example: Census TIGER preprocessing job**
```yaml
command: [bash, -c, |
  STATE_FIPS="01 02 04 05 ..."
  mkdir -p /tmp/data && cd /tmp/data
  
  # Parallel download
  for fips in $STATE_FIPS; do
    curl -sS -O "https://example.com/tl_2024_${fips}_tract.zip" &
  done
  wait
  
  # Unzip
  unzip -q -o "*.zip"
  
  # Convert (tool handles merging)
  cng-convert-to-parquet /tmp/data/*.shp s3://bucket/output.parquet
]
```

#### Step 1b: Copy raw source files to S3 /raw/ BEFORE any conversion

**Always upload the original source files to `s3://<bucket>/raw/` as the very first k8s job**, before running any gdal/conversion steps. Reasons:
- Downloads from external providers (Zenodo, Census, etc.) are slow and rate-limited; if a later conversion job fails you can restart from S3 rather than re-downloading
- Conversion jobs (gdal, parquet) have a much higher failure rate than simple download+upload jobs
- The raw data is archived for reproducibility

```yaml
# Example: minimal raw-upload job
command: [bash, -c, |
  curl -L --retry 5 -o /tmp/data.zip "$SOURCE_URL"
  rclone copy /tmp/data.zip nrp:<bucket>/raw/
]
```

Once raw files are in S3, subsequent conversion jobs should read from `s3://<bucket>/raw/<file>` (or `/vsicurl/https://s3-west.nrp-nautilus.io/<bucket>/raw/<file>` for GDAL), not from the original provider URL.

#### Check S3 uploads

If data is already uploaded to S3:
```
https://s3-west.nrp-nautilus.io/<bucket>/raw/<filename>
```

#### Inspect multi-layer files (GDB, GPKG)

For files with multiple layers:
```bash
ogrinfo /vsicurl/<source-url>
```

### Step 2: Generate the pipeline

#### For vector datasets

Run `cng-datasets workflow` locally — this only generates YAML files, it does not process data:

```bash
cng-datasets workflow \
  --dataset <name> \
  --source-url <url> \
  --bucket <bucket> \
  --h3-resolution 10 \
  --parent-resolutions "9,8,0" \
  --hex-memory 32Gi \
  --max-completions 200 \
  --max-parallelism 50 \
  --output-dir catalog/<dataset>/k8s/<name>
```

**Prefer `--backend armada` for hex-heavy workflows.** The default k8s backend is limited to 200 indexed job completions and 200 pods namespace-wide. Armada removes both constraints, allowing thousands of small jobs in the queue simultaneously. This is especially important for datasets with highly variable polygon sizes (e.g., countries, states) where a single chunk containing Russia or China can run for hours while 199 other chunks finish in minutes. With Armada you can use `--chunk-size 1` (one feature per job) to fully parallelise across features:

```bash
cng-datasets workflow \
  --dataset <name> \
  --source-url <url> \
  --bucket <bucket> \
  --h3-resolution 8 \
  --parent-resolutions "0" \
  --hex-memory 32Gi \
  --max-completions <N-features> \
  --max-parallelism 200 \
  --backend armada \
  --output-dir catalog/<dataset>/k8s/<name>
```

With `--backend armada`, the CLI generates armada YAML files for **all steps** (setup-bucket, convert, pmtiles, hex, repartition) alongside the standard k8s manifests. Submit each step in order manually — there is no orchestrator when using Armada:

```bash
armadactl submit catalog/<dataset>/k8s/<name>/armada-<name>-setup-bucket.yaml
armadactl submit catalog/<dataset>/k8s/<name>/armada-<name>-convert.yaml
armadactl submit catalog/<dataset>/k8s/<name>/armada-<name>-pmtiles.yaml
armadactl submit catalog/<dataset>/k8s/<name>/armada-<name>-hex.yaml
# Wait for hex to complete, then:
armadactl submit catalog/<dataset>/k8s/<name>/armada-<name>-repartition.yaml
```

Monitor jobs at: **https://armada-lookout.nrp-nautilus.io**

To convert an existing k8s hex YAML to Armada without regenerating the full workflow (e.g. for rechunking):
```python
from cng_datasets.k8s.armada import k8s_indexed_job_to_armada, save_armada_yaml
import yaml

with open('catalog/<dataset>/k8s/<name>/<name>-hex.yaml') as f:
    job_spec = yaml.safe_load(f)

armada_spec = k8s_indexed_job_to_armada(job_spec, queue='biodiversity', job_set_id='<name>-hex')
save_armada_yaml(armada_spec, 'catalog/<dataset>/k8s/<name>/armada-<name>-hex.yaml')
```

Add `--layer <LayerName>` for multi-layer sources.

**For multi-layer sources**, run one workflow command per spatial layer:
```bash
cng-datasets workflow --dataset mydata/fee --layer FeeLayer ...
cng-datasets workflow --dataset mydata/easement --layer EasementLayer ...
```

The `/` in `--dataset` creates hierarchical S3 paths while using `-` in k8s job names.

#### For raster datasets

Run `cng-datasets raster-workflow` locally:

```bash
cng-datasets raster-workflow \
  --dataset <name> \
  --source-url <cog-url> \
  --bucket <bucket> \
  --h3-resolution 8 \
  --parent-resolutions "0" \
  --value-column <band_name> \
  --hex-memory 32Gi \
  --max-parallelism 61 \
  --output-dir catalog/<dataset>/k8s/<name>
```

Key differences from the vector workflow:
- **Command:** `raster-workflow` not `workflow`
- **No `--max-completions`**: always 122 completions (one per h0 cell globally)
- **Default resolution:** 8 (not 10) — auto-detected from pixel size if omitted
- **Default parent-resolutions:** `"0"` (not `"9,8,0"`)
- **Default hex-memory:** 32Gi (not 8Gi)
- **Default max-parallelism:** 61 (not 50)
- **`--value-column`:** name for the raster band value in the output parquet (default: `value`)
- **`--nodata`:** NoData value to exclude (auto-detected from raster metadata if omitted)
- **No COG step:** the source COG must already exist; this workflow only does hex tiling

**For multi-tile rasters** (e.g., multiple UTM zones), repeat `--source-url` for each tile. The workflow adds a `preprocess-cog` step that mosaics them into a single WGS84 COG before hex tiling:

```bash
cng-datasets raster-workflow \
  --dataset wyoming/rap-arte \
  --source-url s3://public-wyoming/raw/rap_arte_zone12.tif \
  --source-url s3://public-wyoming/raw/rap_arte_zone13.tif \
  --bucket public-wyoming \
  --target-extent "-111.1,40.9,-104.0,45.0" \
  --band 1 \
  --value-column arte \
  --output-dir catalog/wyoming/k8s/rap-arte
```

Additional multi-tile options:
- `--target-extent "xmin,ymin,xmax,ymax"` — clip to bounding box in EPSG:4326
- `--target-resolution <degrees>` — output pixel size (default: derived from finest source)
- `--band <n>` — extract single band from multi-band source (1-indexed)
- `--output-cog-name <key>` — S3 key for intermediate COG (default: `{dataset}-cog.tif`)

#### How `--dataset` controls naming

The `--dataset` flag determines multiple output names. The **last path segment** is particularly important:

| `--dataset` value | S3 path prefix | PMTiles `source-layer` | k8s job prefix |
|---|---|---|---|
| `calenviroscreen-5-0/ces5` | `calenviroscreen-5-0/ces5` | `ces5` | `calenviroscreen-5-0-ces5` |
| `padus-4-1/fee` | `padus-4-1/fee` | `fee` | `padus-4-1-fee` |
| `census-2024/tract` | `census-2024/tract` | `tract` | `census-2024-tract` |

**The PMTiles `source-layer` name = the last segment of `--dataset`.** This is what MapLibre needs in `"source-layer"` to render the tiles. It does NOT come from the GDB/source layer name — it comes from your `--dataset` choice.

**⚠️ Dataset names must not contain dots.** Kubernetes job names (and pod names for indexed jobs) must match `[a-z0-9][a-z0-9-]*[a-z0-9]` — dots are invalid. `cng-datasets` converts `/` to `-` and rejects names with dots at workflow-generation time. Version strings like `2026-02-18.0` must be encoded without dots (e.g., `overture-2026-02-18` or `om-2026`). If you ever work with pre-existing YAMLs that contain dotted names (generated before this validation existed), the k8s indexed jobs will fail with pod scheduling errors — rename the job before applying.

### Step 3: Apply to the cluster

**One-time RBAC setup** (only needed once per cluster/namespace, likely already done):
```bash
kubectl apply -f catalog/<dataset>/k8s/<name>/workflow-rbac.yaml
```

**Per-workflow** (for each dataset):
```bash
kubectl apply -f catalog/<dataset>/k8s/<name>/configmap.yaml \
              -f catalog/<dataset>/k8s/<name>/workflow.yaml
```

**Vector** workflow orchestrator jobs: setup-bucket → convert → pmtiles + hex (parallel) → repartition.

**Raster** workflow orchestrator jobs: setup-bucket → hex (or setup-bucket → preprocess-cog → hex for multi-tile).

**Alternative:** You can manually apply individual job YAMLs for step-by-step control:
```bash
kubectl apply -f catalog/<dataset>/k8s/<name>/<name>-setup-bucket.yaml
kubectl apply -f catalog/<dataset>/k8s/<name>/<name>-convert.yaml   # vector only
kubectl apply -f catalog/<dataset>/k8s/<name>/<name>-hex.yaml
# ... etc
```

### Step 4: Monitor

```bash
kubectl get jobs | grep <name>       # Job status
kubectl logs job/<name>-convert      # Check conversion
kubectl logs job/<name>-workflow     # Orchestrator log
```

A complete run for a ~300K feature dataset typically takes 1-2 hours.

### Step 5: Document

After processing completes, create:
- `catalog/<dataset>/stac/README.md` — data dictionary, usage examples, citation
- `catalog/<dataset>/stac/stac-collection.json` — STAC metadata

**REQUIRED in every README.md:**
- A **MapLibre GL JS example** with the correct `source-layer` name (= last segment of `--dataset`)
- The `source-layer` name documented prominently, not buried
- A **DuckDB example** with the full public URL to the parquet file

**REQUIRED in every stac-collection.json:**
- **Asset key naming**: The JSON key for each asset MUST encode the dataset name, not the format. **Never use generic keys like `"pmtiles"`, `"geoparquet"`, `"h3-parquet"`, `"parquet"`, or `"hex"`** — they break downstream apps when a collection has multiple assets of the same format, and make layer IDs meaningless.

  Use the last segment of `--dataset` as the base name, with a format suffix:

  | Asset type | Key pattern | Example (`--dataset census-2025/sldl`) |
  |---|---|---|
  | GeoParquet | `{name}-parquet` | `sldl-parquet` |
  | PMTiles | `{name}-pmtiles` | `sldl-pmtiles` |
  | H3 hex parquet | `{name}-hex` | `sldl-hex` |
  | COG (raster) | `{name}-cog` | `sldl-cog` |

  For multi-layer collections, prefix with the collection context: `cpad-holdings-parquet`, `cpad-units-hex`, etc.

- **Hex asset `href`**: MUST use the full Hive-partitioned glob pattern — never a bare directory URL. The bare directory URL (`/hex/`) causes downstream tooling to produce mangled paths. Use:
  ```
  https://s3-west.nrp-nautilus.io/<bucket>/<dataset>/hex/h0=*/data_0.parquet
  ```
  ❌ Wrong: `https://s3-west.nrp-nautilus.io/public-census/census-2025/sldl/hex/`
  ✅ Correct: `https://s3-west.nrp-nautilus.io/public-census/census-2025/sldl/hex/h0=*/data_0.parquet`

- Any vector asset with named layers (PMTiles, GDB, GPKG, etc.) MUST include a `"vector:layers": ["<name>"]` array field. This is format-agnostic — the same field works for PMTiles, GeoDatabase, GeoPackage, etc. For PMTiles, the layer name = last segment of `--dataset`.
- A `table:columns` array documenting all columns
- **Point geometry datasets**: The `description` field (or a `"processing:notes"` field) MUST state that each point was resolved to a single H3 cell at the processing resolution, and note the resolution used. Example: *"Point observations were hexed to H3 resolution 10 (each point → one ~15 000 m² cell). Multiple points within the same cell are not deduplicated."*

Upload to the bucket:
```bash
rclone copy catalog/<dataset>/stac/README.md nrp:<bucket>/
rclone copy catalog/<dataset>/stac/stac-collection.json nrp:<bucket>/
```

### Step 6: Update Main Catalog

Add the new collection to the central STAC catalog:

```bash
# Download, edit to add child link, then upload
curl -s https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json > /tmp/catalog.json
# Edit /tmp/catalog.json to add new child link in "links" array
rclone copyto /tmp/catalog.json nrp:public-data/stac/catalog.json
```

The child link should point to your dataset's `stac-collection.json` URL.

## Common Parameters

### Memory and Chunking Mental Model

**Memory usage is driven by the H3 cell count of the single largest feature in a chunk, not by dataset size or total spatial area.**

The hex generation step works by:
1. Pass 1: For each feature polygon, compute all H3 cells that cover it → produces a large array per feature
2. Pass 2 (unnest): Explode those arrays row-by-row into the output table → peak RAM is the size of the largest single feature's cell array

This has a counterintuitive implication: **a global dataset of 10,000 small, simple features may use far less memory than a dataset with a single feature that is a large, complex polygon** (e.g., Russia, Alaska, a national forest boundary). A large dataset with many small polygons can be fine at 8Gi; a small dataset with one continent-scale polygon can OOM at 32Gi.

**What actually drives RAM per chunk:**
- H3 resolution (exponential: res 8 → ~1/170th the cells of res 10 for the same area)
- The area of the *largest single feature* in the chunk at that resolution
- Geometry complexity affects Pass 1 runtime but not RAM much; area dominates Pass 2

**You cannot reliably estimate memory from feature count or dataset bounding box.** The right approach is:

1. **Start with the default** (8Gi for vector) and a chunk size that isolates suspect features
2. **Use Armada with chunk-size 1** for datasets with highly variable feature sizes — this ensures each feature gets its own pod, so one large feature doesn't OOM a chunk containing 49 small ones
3. **When a pod OOMs:** look at which features were in that chunk (check parquet rows by chunk-id offset), identify the large polygon(s), and either:
   - Reduce resolution for that dataset
   - Increase `--hex-memory` for that specific job
   - Re-run that chunk alone with higher memory (see Reprocessing Failed Chunks)
4. **OOMs are expected occasionally** — they are a signal to tune, not a sign of failure. The workflow is designed to retry individual chunks.

**Resolution guidance by dataset type:**

| Dataset type | Recommended resolution | Rationale |
|---|---|---|
| Countries, continents | 8 | Single features can be continent-scale |
| States, provinces, large regions | 8 | Many are still very large polygons |
| Counties, districts | 8–10 | Mostly manageable at 10; watch for outliers |
| Census tracts, parcels | 10 | Small features, fine resolution appropriate |
| Points | 10 | Each point → single H3 cell; coarser resolutions aggregate nearby points |
| Lines | N/A | Hex not supported for line geometries |

#### Vector workflow parameters

| Parameter | Default | When to change |
|-----------|---------|----------------|
| `--h3-resolution` | 10 | Lower (8, 6) for large-polygon datasets. Halving resolution reduces cell count ~6x. |
| `--hex-memory` | 8Gi | Tune based on OOM signals, not upfront estimates. Start low; increase for specific failing chunks. |
| `--max-completions` | 200 | With `--backend k8s`: hard limit of 200. With `--backend armada`: set to feature count for chunk-size 1. |
| `--max-parallelism` | 50 | k8s: capped by namespace quota (see below). Armada: set to 200+ freely. |
| `--parent-resolutions` | "9,8,0" | Use `"0"` when `--h3-resolution` is 8 (intermediate resolutions 9, 8 would duplicate the target). |
| `--intermediate-chunk-size` | 10 | Decrease if hex pods OOM during unnest (Pass 2). This is the first knob to turn before increasing memory. |

#### Raster workflow parameters

| Parameter | Default | When to change |
|-----------|---------|----------------|
| `--h3-resolution` | auto (from pixel size) | Override if auto-detect gives wrong resolution |
| `--hex-memory` | 32Gi | Increase if pods OOM; rasters can be memory-intensive at fine resolutions |
| `--max-parallelism` | 61 | Reduce if hitting namespace pod quota; never exceeds 122 |
| `--parent-resolutions` | "0" | Add intermediate resolutions (e.g., `"7,0"`) if needed |
| `--value-column` | "value" | Set to a meaningful band name (e.g., `carbon`, `arte`, `nlcd`) |
| `--nodata` | auto (from raster metadata) | Override if metadata nodata is wrong or missing |

Raster completions are always **122** (one per h0 cell) — this is not configurable.

### Namespace Pod Quota — CRITICAL for k8s backend

**The `biodiversity` namespace has a hard limit of 200 pods total, shared across ALL jobs running simultaneously.**

This constraint applies only to the **k8s backend**. With `--backend armada`, jobs are queued externally and scheduled onto the cluster as capacity allows — the 200-pod namespace quota does not apply.

#### k8s backend: sequential submission required

With `--max-parallelism 50`, a single hex job can consume up to 50 pods. Running multiple hex workflows at the same time will rapidly exhaust the quota, causing pods to fail with:
```
pods "...-hex-60-..." is forbidden: exceeded quota: reached-quota,
requested: pods=1, used: pods=200, limited: pods=200
```

**Rule: Never submit more than one k8s hex workflow at a time.** Run them sequentially:
```bash
for dataset in dataset-a dataset-b dataset-c; do
  kubectl apply -f catalog/.../k8s/${dataset}/configmap.yaml \
                -f catalog/.../k8s/${dataset}/workflow.yaml
  kubectl wait job/${dataset}-workflow --for=condition=complete --timeout=7200s
done
```

#### Armada backend: submit freely

With Armada you can submit all datasets at once — the scheduler handles queuing. You can also use far more completions than 200, enabling chunk-size 1 (one pod per feature) which eliminates the "one slow pod blocks everything" problem:

## S3 Bucket Layout

**Vector datasets:**
```
bucket/
├── raw/                         # Source data
├── dataset.parquet              # GeoParquet
├── dataset.pmtiles              # PMTiles
├── dataset/
│   └── hex/
│       └── h0={cell}/data_0.parquet
├── README.md
└── stac-collection.json
```

**Raster datasets:**
```
bucket/
├── raw/                         # Source raster(s)
├── dataset-cog.tif              # Cloud-optimized GeoTIFF (may be in raw/ or root)
├── dataset/
│   └── hex/
│       └── h0={cell}/data_0.parquet
├── README.md
└── stac-collection.json
```

## Troubleshooting

**Convert fails with 404 Not Found → verify source URLs:**
The most common failure. Always verify URLs exist BEFORE generating workflows:
```bash
# Check if file exists
curl -I <source-url>

# List directory to find actual file names
curl -s <directory-url> | grep '.zip'
```

**Convert fails with "Cannot mix .zip files with multiple source URLs":**
`cng-convert-to-parquet` cannot process multiple zip URLs. Create a preprocessing job that:
1. Downloads all zips in parallel (`curl -O ... &`)
2. Unzips all files (`unzip -q -o "*.zip"`)
3. Passes unzipped shapefiles to the tool (`cng-convert-to-parquet /tmp/*.shp s3://...`)

See the "Preprocessing multi-file zipped datasets" section for examples.

**Convert fails → check logs:**
```bash
kubectl logs job/<name>-convert
```

**Hex pods OOM → increase memory or chunks:**
Regenerate with `--hex-memory 64Gi` or `--max-completions 200`, delete failed job, reapply.

**S3 throttling (503 SlowDown):** Transient. Wait a few minutes and retry.

**PMTiles renders blank in MapLibre → wrong `source-layer` name:**
The `source-layer` is the last path segment of the `--dataset` flag, NOT the GDB/source layer name. For `--dataset padus-4-1/fee`, the source-layer is `fee` (not `PADUS4_1Fee`). Never guess — derive it from `--dataset`.

**Workflow stuck → check what step it's on:**
```bash
kubectl logs job/<name>-workflow
kubectl get jobs | grep <name>
```

**Hex pods failing with `exceeded quota: reached-quota` → namespace pod limit hit:**
The `biodiversity` namespace allows max 200 pods. Running multiple hex workflows simultaneously exhausts this. Fix:
1. Delete all running hex jobs and their workflow orchestrators
2. Rerun sequentially — one workflow at a time, waiting for each to complete before starting the next
```bash
kubectl get jobs | grep -E 'dataset-a|dataset-b' | awk '{print $1}' | xargs kubectl delete job
# Then resubmit one at a time (see Namespace Pod Quota section)
```

### Reprocessing Failed Chunks

If specific chunks fail (e.g., due to DuckDB parquet page size limits on extremely complex geometries), reprocess them at a coarser H3 resolution:

1. **Identify failed chunk IDs:** `kubectl get pods | grep <name>-hex | grep -E "Error|Failed"`

2. **Generate base YAML and edit for rechunking:**
   ```bash
   # Copy the existing hex job YAML as a template
   cp catalog/<dataset>/k8s/<name>/<name>-hex.yaml <name>-hex-rechunk.yaml
   ```
   
   Edit the YAML to:
   - Change job name: `<name>-hex-rechunk`
   - Set `completions: 4` (number of failed chunks)
   - Change the `cng-datasets vector` command to use a CHUNK_MAP:
   ```yaml
   args:
   - |
     set -e
     CHUNK_MAP=(0 1 2 94)  # Failed chunk IDs
     CHUNK_ID=${CHUNK_MAP[$JOB_COMPLETION_INDEX]}
     echo "Reprocessing chunk $CHUNK_ID at resolution 8"
     
     cng-datasets vector \
       --input s3://<bucket>/<dataset>.parquet \
       --output s3://<bucket>/<dataset>/chunks \
       --chunk-id $CHUNK_ID \
       --chunk-size <same> \
       --intermediate-chunk-size <same> \
       --resolution 8 \
       --parent-resolutions 9,8,0
   ```

3. **Apply and run repartition after completion:**
   ```bash
   kubectl apply -f <name>-hex-rechunk.yaml
   # Wait for completion, then:
   kubectl apply -f catalog/<dataset>/k8s/<name>/<name>-repartition.yaml
   ```

Repartition automatically merges all chunks (both resolutions) from `chunks/` into `hex/` partitioned by h0.

## What NOT To Do

- **Do not process data locally.** The CLI generates k8s jobs. You apply them. The cluster does the work.
- **Do not modify `cng_datasets/` source code** unless fixing a bug in the tool itself. User workflows only touch `catalog/` and generated YAML.
- **Do not hardcode S3 endpoints or credentials.** The generated jobs handle S3 configuration (internal endpoints, secrets) automatically.
- **Do not exceed 200 completions per job.** This is a hard limit to avoid overwhelming the cluster's etcd.
- **Do not use ogr2ogr to sequentially merge shapefiles.** Use parallel downloads and pass all files to cng-convert-to-parquet — it merges efficiently.
- **Do not try to use multiple .zip URLs with cng-datasets workflow.** Create a preprocessing job that downloads, unzips, and converts instead.

## Reference: Complete PAD-US Example

PAD-US is a multi-layer GDB with 5 spatial layers. Each was processed with a separate workflow:

```bash
# Upload raw data first (one-time)
rclone copy PADUS4_1Geodatabase.gdb nrp:public-padus/raw/PADUS4_1Geodatabase.gdb -P

# Generate and apply each layer
for args in \
  "padus-4-1/fee PADUS4_1Fee" \
  "padus-4-1/easement PADUS4_1Easement" \
  "padus-4-1/proclamation PADUS4_1Proclamation" \
  "padus-4-1/marine PADUS4_1Marine" \
  "padus-4-1/combined PADUS4_1Combined_Proclamation_Marine_Fee_Designation_Easement"; do
  set -- $args
  cng-datasets workflow \
    --dataset "$1" \
    --source-url https://s3-west.nrp-nautilus.io/public-padus/raw/PADUS4_1Geodatabase.gdb \
    --bucket public-padus \
    --layer "$2" \
    --h3-resolution 10 --hex-memory 32Gi --max-completions 200 --max-parallelism 50 \
    --parent-resolutions "9,8,0" \
    --output-dir "catalog/pad-us/k8s/$(echo $1 | cut -d/ -f2)"
done

# One-time RBAC setup (only needed once, likely already done)
kubectl apply -f catalog/pad-us/k8s/fee/workflow-rbac.yaml

# Apply all workflows
for layer in fee easement proclamation marine combined; do
  kubectl apply \
    -f catalog/pad-us/k8s/$layer/configmap.yaml \
    -f catalog/pad-us/k8s/$layer/workflow.yaml
done
```

### Lookup Tables

Non-spatial lookup tables (8 tables: Public_Access, Category, Designation_Type, GAP_Status, IUCN_Category, Agency_Name, Agency_Type, State_Name) were extracted using a k8s job with DuckDB:

```bash
# Extract all lookup tables - see catalog/pad-us/k8s/extract-lookup-tables.yaml
kubectl apply -f catalog/pad-us/k8s/extract-lookup-tables.yaml

# Monitor extraction
kubectl logs -f job/padus-extract-lookup-tables

# Files written to: s3://public-padus/padus-4-1/lookup/*.parquet
# Documentation: catalog/pad-us/lookup-tables.md
```

The extraction job uses DuckDB's spatial extension with `/vsis3/` paths to read the GDB from S3 with credentials, then writes each table to parquet. All 204 rows across 8 tables extracted in ~30 seconds.

## Reference: Census 2024 Multi-Source Example

Census TIGER/Line shapefiles are distributed as **per-state files**, not national files. Always verify URL patterns before generating workflows.

**Pattern discovery:**
```bash
# Verify directory exists
curl -I https://www2.census.gov/geo/tiger/TIGER2024/TRACT/

# List actual files available
curl -s https://www2.census.gov/geo/tiger/TIGER2024/TRACT/ | grep '.zip' | head -10
# Output shows: tl_2024_01_tract.zip, tl_2024_02_tract.zip, etc.

# Verify specific file
curl -I https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_01_tract.zip
# HTTP/2 200 ✓
```

**Creating preprocessing job for zipped multi-file datasets:**

Since `cng-convert-to-parquet` cannot handle multiple zip URLs, create a preprocessing job:

```bash
# Create preprocessing job YAML (see catalog/census/k8s/tract/preprocess-tract.yaml)
cat > preprocess-tract.yaml <<'EOF'
apiVersion: batch/v1
kind: Job
metadata:
  name: census-2024-tract-preprocess
  namespace: biodiversity
spec:
  backoffLimit: 1
  template:
    spec:
      restartPolicy: Never
      priorityClassName: opportunistic
      containers:
      - name: preprocess
        image: ghcr.io/boettiger-lab/datasets:latest
        resources:
          requests: {memory: "32Gi", cpu: "8"}
          limits: {memory: "32Gi", cpu: "8"}
        env:
        - name: AWS_ACCESS_KEY_ID
          valueFrom: {secretKeyRef: {name: aws, key: AWS_ACCESS_KEY_ID}}
        - name: AWS_SECRET_ACCESS_KEY
          valueFrom: {secretKeyRef: {name: aws, key: AWS_SECRET_ACCESS_KEY}}
        - name: AWS_S3_ENDPOINT
          value: "rook-ceph-rgw-nautiluss3.rook"
        - name: AWS_VIRTUAL_HOSTING
          value: "FALSE"
        volumeMounts:
        - {name: rclone-config, mountPath: /root/.config/rclone, readOnly: true}
        command: [bash, -c, |
          set -e
          STATE_FIPS="01 02 04 05 06 08 09 10 11 12 13 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 44 45 46 47 48 49 50 51 53 54 55 56 60 66 69 72 78"
          
          echo "Downloading all tract files..."
          mkdir -p /tmp/tracts && cd /tmp/tracts
          
          # Parallel download
          for fips in $STATE_FIPS; do
            curl -sS -O "https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_${fips}_tract.zip" &
          done
          wait
          
          echo "Unzipping..."
          unzip -q -o "*.zip"
          
          # Convert (tool merges all shapefiles)
          echo "Converting to GeoParquet..."
          cng-convert-to-parquet /tmp/tracts/*.shp s3://public-census/census-2024/tract.parquet \
            --compression ZSTD --compression-level 15 --row-group-size 100000
          
          echo "✓ Complete"
        ]
      volumes:
      - name: rclone-config
        secret: {secretName: rclone-config}
EOF

# Apply preprocessing job
kubectl apply -f preprocess-tract.yaml

# Monitor
kubectl logs -f census-2024-tract-preprocess
```

After preprocessing completes (~3 minutes for 56 files), generate and run the pipeline:

```bash
# Generate hex/pmtiles/repartition workflows
cng-datasets workflow \
  --dataset census-2024/tract \
  --source-url s3://public-census/census-2024/tract.parquet \
  --bucket public-census \
  --h3-resolution 10 \
  --parent-resolutions "9,8,0" \
  --hex-memory 16Gi \
  --max-completions 200 \
  --max-parallelism 50 \
  --output-dir catalog/census/k8s/tract

# Apply hex, pmtiles, repartition jobs
kubectl apply -f catalog/census/k8s/tract/census-2024-tract-hex.yaml
kubectl apply -f catalog/census/k8s/tract/census-2024-tract-pmtiles.yaml
# Wait for hex to complete, then:
kubectl apply -f catalog/census/k8s/tract/census-2024-tract-repartition.yaml
```

**Result:** ~85,000 census tracts processed with parallel downloads completing in 3 minutes.

## Reference: Raster Hex Workflow (Carbon Example)

Raster datasets (COGs) are hexed using `cng-datasets raster-workflow`. The carbon irrecoverable carbon maps are a canonical example — each year is a separate COG already in S3.

```bash
# Generate raster workflow YAML (single-tile COG already on S3)
cng-datasets raster-workflow \
  --dataset irrecoverable-carbon-2022 \
  --source-url s3://public-carbon/v2/cogs/irrecoverable_c_total_2022.tif \
  --bucket public-carbon \
  --h3-resolution 8 \
  --parent-resolutions "0" \
  --value-column carbon \
  --hex-memory 32Gi \
  --max-parallelism 61 \
  --output-dir catalog/carbon/k8s/v2/irrecoverable-carbon-2022

# Apply (one-time RBAC setup if not done)
kubectl apply -f catalog/carbon/k8s/v2/irrecoverable-carbon-2022/workflow-rbac.yaml

# Apply workflow
kubectl apply \
  -f catalog/carbon/k8s/v2/irrecoverable-carbon-2022/configmap.yaml \
  -f catalog/carbon/k8s/v2/irrecoverable-carbon-2022/workflow.yaml
```

The generated hex job runs `cng-datasets raster` once per h0 cell:
```bash
cng-datasets raster \
  --input s3://public-carbon/v2/cogs/irrecoverable_c_total_2022.tif \
  --output-parquet s3://public-carbon/irrecoverable-carbon-2022/hex/ \
  --h0-index ${JOB_COMPLETION_INDEX} \
  --resolution 8 \
  --parent-resolutions 0 \
  --value-column carbon
```

This creates 122 indexed pods (one per h0 cell), each writing `hex/h0={cell}/data_0.parquet`. Cells with no raster data are skipped silently. There is no repartition step for rasters — each h0 writes directly to its final partition.

**Key differences from vector hex:**
- Input is a COG (not a parquet), read via GDAL with `/vsicurl/` internally
- Uses `--h0-index` (not `--chunk-id`)
- No `chunks/` intermediate directory — output goes directly to `hex/`
- No repartition step needed
- 122 completions always (not configurable)
