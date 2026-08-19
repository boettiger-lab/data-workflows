---
name: dataset-recipes
description: >-
  Worked end-to-end examples of dataset ingests to copy from: PAD-US multi-layer GDB, Census TIGER per-state zips with a preprocess job, a single-COG carbon raster, reading one small table out of a huge remote zip via GDAL range reads, and preprocessing multi-file zipped sources. Use as a starting template when a new ingest resembles one of these shapes.
---

# Dataset Recipes

Copy the closest-shaped recipe rather than deriving a pipeline from scratch.

## 💡 Read one small table out of a HUGE remote zip — range reads, no localize (#518)

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

## Step 1c: Preprocessing multi-file zipped datasets

**`cng-convert-to-parquet` rejects multiple .zip URLs.** For per-state/per-region zips, preprocess: download in parallel, unzip, pass shapefiles (the tool merges them automatically):
```bash
for id in 01 02 03; do curl -sS -O "https://example.com/data_${id}.zip" & done
wait && unzip -q -o "*.zip"
cng-convert-to-parquet /tmp/data/*.shp s3://bucket/output.parquet
```
See `catalog/census/k8s/tract/preprocess-tract.yaml` for a complete k8s job.

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
