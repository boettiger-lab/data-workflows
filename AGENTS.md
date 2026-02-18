# Agent Instructions: Dataset Processing

You are working in a repository that uses `cng-datasets` to process geospatial data into cloud-native formats on a Kubernetes cluster. This document tells you everything you need to know.

## What You Are Doing

You are taking source geospatial data and producing three outputs per dataset:

| Format | File | Use |
|--------|------|-----|
| GeoParquet | `dataset.parquet` | Analytical queries with DuckDB/Polars |
| PMTiles | `dataset.pmtiles` | Web map visualization |
| H3 Hex Parquet | `dataset/hex/h0={cell}/data_0.parquet` | Spatial joins and aggregation |


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

Add `--layer <LayerName>` for multi-layer sources.

**For multi-layer sources**, run one workflow command per spatial layer:
```bash
cng-datasets workflow --dataset mydata/fee --layer FeeLayer ...
cng-datasets workflow --dataset mydata/easement --layer EasementLayer ...
```

The `/` in `--dataset` creates hierarchical S3 paths while using `-` in k8s job names.

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

The workflow orchestrator automatically creates all jobs: setup-bucket → convert → pmtiles + hex (parallel) → repartition.

**Alternative:** You can manually apply individual job YAMLs for step-by-step control:
```bash
kubectl apply -f catalog/<dataset>/k8s/<name>/<name>-setup-bucket.yaml
kubectl apply -f catalog/<dataset>/k8s/<name>/<name>-convert.yaml
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

**Memory usage is driven by SPATIAL AREA, not geometry complexity:**

The hex generation step creates millions of H3 cells that must be unnested in memory. At resolution 10:
- Each hex covers ~0.015 km²
- Large spatial areas → many hexes → high memory usage
- A US state like Alaska (~1.7M km²) → ~113M hexes → requires 64Gi+ memory per chunk

**For US-scale datasets at resolution 10:**
- **Always use max-completions 200 and max-parallelism 50** (not 1!)
- Small feature count does NOT mean low memory - 50 US states need chunking just as much as 85K census tracts
- If hex pods OOM, increase `--hex-memory` (not decrease completions)

| Parameter | Default | When to change |
|-----------|---------|----------------|
| `--h3-resolution` | 10 | Lower (8, 6) for coarser data OR to reduce hex count for very large areas |
| `--hex-memory` | 8Gi | Increase to 16-64Gi based on spatial area per chunk, not feature count |
| `--max-completions` | 200 | Keep at 200 for any US-scale dataset (states, counties, tracts) |
| `--max-parallelism` | 50 | Reduce if cluster is already busy |
| `--parent-resolutions` | "9,8,0" | Almost never change this |
| `--intermediate-chunk-size` | auto | Decrease if hex pods OOM during unnest step |

## S3 Bucket Layout

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

**Workflow stuck → check what step it's on:**
```bash
kubectl logs job/<name>-workflow
kubectl get jobs | grep <name>
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
