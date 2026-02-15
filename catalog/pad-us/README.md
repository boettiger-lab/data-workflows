# PAD-US 4.1: Protected Areas Database of the United States

**Source:** https://www.sciencebase.gov/catalog/item/652d4fc5d34e44db0e2ee45e  
**Metadata:** https://doi.org/10.5066/P96WBCHS  
**Overview:** https://www.usgs.gov/programs/gap-analysis-project/science/pad-us-data-overview/  

## Raw Data

The source geodatabase is stored at:

```
nrp:public-padus/raw/PADUS4_1Geodatabase.gdb
```

Accessible via:
- **Inside k8s cluster:** `http://rook-ceph-rgw-nautiluss3.rook/public-padus/raw/PADUS4_1Geodatabase.gdb`
- **Public URL:** `https://s3-west.nrp-nautilus.io/public-padus/raw/PADUS4_1Geodatabase.gdb`

## GDB Layers

The geodatabase contains 12 layers — 5 spatial (Multi Polygon) and 7 non-spatial lookup tables.

### Spatial Layers (Multi Polygon)

| Layer | Features | Description |
|-------|----------|-------------|
| `PADUS4_1Fee` | 296,456 | Fee-owned protected areas (federal, state, local, private) |
| `PADUS4_1Easement` | 341,954 | Conservation easements |
| `PADUS4_1Proclamation` | 3,439 | Proclamation boundaries (authorized boundaries of protected areas) |
| `PADUS4_1Marine` | 1,739 | Marine protected areas |
| `PADUS4_1Combined_Proclamation_Marine_Fee_Designation_Easement` | 656,986 | Combined layer of all protection types |

CRS is USA Contiguous Albers Equal Area Conic (USGS version, based on NAD83). The `cng-datasets` tool handles reprojection to EPSG:4326 automatically.

### Non-Spatial Layers (Lookup Tables)

| Layer | Rows | Description |
|-------|------|-------------|
| `Public_Access` | 4 | Access codes (Open, Restricted, Closed, Unknown) |
| `Designation_Type` | 63 | Designation type codes |
| `GAP_Status` | 4 | GAP protection status codes (1–4) |
| `IUCN_Category` | 10 | IUCN protection category codes |
| `Agency_Name` | 44 | Managing agency names |
| `Agency_Type` | 11 | Agency type codes (Federal, State, Local, etc.) |
| `State_Name` | 61 | US state/territory names |

## Target Bucket Organization

Following the CPAD pattern (`nrp:public-cpad/`), outputs go to `nrp:public-padus/`:

```
nrp:public-padus/
├── raw/                                          # Source data (already uploaded)
│   └── PADUS4_1Geodatabase.gdb/
├── padus-4-1/                                    # Processed outputs (version-prefixed)
│   ├── fee.parquet                               # GeoParquet
│   ├── fee.pmtiles                               # PMTiles for web maps
│   ├── fee/hex/h0={cell}/data_0.parquet          # H3 hex-indexed
│   ├── easement.parquet
│   ├── easement.pmtiles
│   ├── easement/hex/h0={cell}/data_0.parquet
│   ├── proclamation.parquet
│   ├── proclamation.pmtiles
│   ├── proclamation/hex/h0={cell}/data_0.parquet
│   ├── marine.parquet
│   ├── marine.pmtiles
│   ├── marine/hex/h0={cell}/data_0.parquet
│   ├── combined.parquet
│   ├── combined.pmtiles
│   └── combined/hex/h0={cell}/data_0.parquet
├── README.md
└── stac-collection.json
```

## Processing Commands

### Spatial Layers (via `cng-datasets workflow`)

Each spatial layer gets its own `cng-datasets workflow` invocation. The `--dataset` uses a `/` to create the `padus-4-1/<layer>` S3 path structure within the bucket. The `--layer` flag selects the GDB layer. The tool generates a full k8s job pipeline: setup-bucket → convert to GeoParquet → PMTiles + H3 hex (parallel) → repartition.

```bash
# Fee layer (296k features)
cng-datasets workflow \
  --dataset padus-4-1/fee \
  --source-url https://s3-west.nrp-nautilus.io/public-padus/raw/PADUS4_1Geodatabase.gdb \
  --bucket public-padus \
  --layer PADUS4_1Fee \
  --h3-resolution 10 \
  --hex-memory 32Gi \
  --max-completions 200 \
  --max-parallelism 50 \
  --parent-resolutions "9,8,0" \
  --output-dir catalog/pad-us/k8s/fee

# Easement layer (342k features)
cng-datasets workflow \
  --dataset padus-4-1/easement \
  --source-url https://s3-west.nrp-nautilus.io/public-padus/raw/PADUS4_1Geodatabase.gdb \
  --bucket public-padus \
  --layer PADUS4_1Easement \
  --h3-resolution 10 \
  --hex-memory 32Gi \
  --max-completions 200 \
  --max-parallelism 50 \
  --parent-resolutions "9,8,0" \
  --output-dir catalog/pad-us/k8s/easement

# Proclamation layer (3.4k features)
cng-datasets workflow \
  --dataset padus-4-1/proclamation \
  --source-url https://s3-west.nrp-nautilus.io/public-padus/raw/PADUS4_1Geodatabase.gdb \
  --bucket public-padus \
  --layer PADUS4_1Proclamation \
  --h3-resolution 10 \
  --hex-memory 32Gi \
  --parent-resolutions "9,8,0" \
  --output-dir catalog/pad-us/k8s/proclamation

# Marine layer (1.7k features)
cng-datasets workflow \
  --dataset padus-4-1/marine \
  --source-url https://s3-west.nrp-nautilus.io/public-padus/raw/PADUS4_1Geodatabase.gdb \
  --bucket public-padus \
  --layer PADUS4_1Marine \
  --h3-resolution 10 \
  --hex-memory 32Gi \
  --parent-resolutions "9,8,0" \
  --output-dir catalog/pad-us/k8s/marine

# Combined layer (657k features — largest)
cng-datasets workflow \
  --dataset padus-4-1/combined \
  --source-url https://s3-west.nrp-nautilus.io/public-padus/raw/PADUS4_1Geodatabase.gdb \
  --bucket public-padus \
  --layer PADUS4_1Combined_Proclamation_Marine_Fee_Designation_Easement \
  --h3-resolution 10 \
  --hex-memory 32Gi \
  --max-completions 200 \
  --max-parallelism 50 \
  --parent-resolutions "9,8,0" \
  --output-dir catalog/pad-us/k8s/combined
```

Each command generates k8s YAML files. Apply with:

```bash
kubectl apply -f catalog/pad-us/k8s/<layer>/workflow-rbac.yaml
kubectl apply -f catalog/pad-us/k8s/<layer>/configmap.yaml
kubectl apply -f catalog/pad-us/k8s/<layer>/workflow.yaml
```

### Non-Spatial Layers (lookup tables)

The 7 lookup tables (4–63 rows each) are tiny reference tables. Processing TBD.

## Code Changes Made

Two bugs were fixed in `cng_datasets/k8s/workflows.py` to support multi-layer GDB files and hierarchical S3 paths:

1. **`_count_source_features()` now accepts a `layer` parameter.** Previously it used `ogrinfo -so -al` which returns all layers and grabbed the first `Feature Count:` line — wrong for multi-layer GDB files. Now when `layer` is specified, it queries that specific layer with `ogrinfo -so <path> <layer>`.

2. **S3 paths can now contain `/` via the `s3_dataset` parameter.** The `--dataset` argument (e.g., `padus-4-1/fee`) is passed through to S3 paths as-is, while k8s resource names are derived by replacing `/` with `-` (e.g., `padus-4-1-fee`). This lets multi-layer datasets share a bucket with a clean hierarchical layout.

## Status

- **Fee layer:** k8s YAML generated in `catalog/pad-us/k8s/fee/`. First run attempted but used old flat path structure and was stopped. Re-generated with correct `padus-4-1/fee` paths. Ready to apply.
- **Easement layer:** k8s YAML generated in `catalog/pad-us/k8s/easement/`. Ready to apply.
- **Proclamation, Marine, Combined:** Not yet generated. Waiting to validate fee layer first.