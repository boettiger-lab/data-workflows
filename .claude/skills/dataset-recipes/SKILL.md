---
name: dataset-recipes
description: >-
  Worked end-to-end examples of dataset ingests to copy from: PAD-US multi-layer GDB, Census TIGER per-state zips with a preprocess job, a single-COG carbon raster, reading one small table out of a huge remote zip via GDAL range reads, preprocessing multi-file zipped sources, and checking feature count and spatial coverage against the source before publishing. Use as a starting template when a new ingest resembles one of these shapes.
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

## 💡 Check coverage against the source before you publish (#615)

A source file can be **valid, readable, internally consistent — and still be a fraction of the
dataset**. Nothing downstream notices: convert, pmtiles, hex and `verify-stac.py` all pass on a
short read, because none of them knows what the source was supposed to contain. `fmmp-2022`
shipped and was consumed for two months holding 45,285 of 127,133 features — 13 of 38 counties,
missing Riverside, Monterey, Stanislaus, Sacramento and Imperial.

So before publishing, compare the build against the source on **two axes**, not one:

1. **Feature count** — the number the source itself reports.
2. **Spatial coverage** — the count of whole units the data should span (counties, states, HU4s,
   ecoregions, tiles). A truncated export usually stops on a unit boundary, which makes the count
   alone look merely "smaller" while the unit list is visibly short.

The second is what would have caught this fastest: 13 counties in a statewide layer is obvious to
anyone who looks, whereas 45,285 features is a plausible-looking number.

```sql
-- coverage, from the built parquet (mcp__duckdb-geo__query)
SELECT COUNT(*) AS features, COUNT(DISTINCT county_nam) AS units
FROM read_parquet('s3://<bucket>/<dataset>.parquet')
```

Then assert it in the staging job so a short read fails the build instead of publishing quietly —
a green pipeline over partial data is the failure mode, not a crash. Worked manifest:
`catalog/ca30x30/k8s/fmmp-2022/fmmp-2022-stage-raw.yaml` (asserts count, distinct ids, and unit
count before staging).

**Where "what the source should contain" comes from** depends on the source: an ArcGIS service
answers `returnCountOnly` and a `groupByFieldsForStatistics` unit breakdown directly; a national
file has a published record count or a unit list; upstream documentation often states the unit
count ("FMMP surveys 38 counties"). Any of these beats trusting the file you were handed.

⚠️ **A pre-built export is a claim, not the data.** The `fmmp-2022` truncation came from an ArcGIS
Hub export artifact that had been cached since 2025-10-24 while the item's own metadata reported
the full `recordCount` — the export and the service disagreed, and only the service was right.
When a source offers both a canned download and a queryable service, the service is authoritative;
page it (`resultOffset` + `orderByFields`, `maxRecordCount` per page) rather than trusting the
export. See `catalog/ca30x30/k8s/fmmp-2022/page_featureserver.py`.

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
