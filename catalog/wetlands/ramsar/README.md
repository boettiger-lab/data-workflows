

# Ramsar Wetlands

## Source Data

The Ramsar dataset is built from multiple data sources to maximize coverage:

1. **Original Ramsar polygons**: `s3://public-wetlands/ramsar/ramsar_wetlands.parquet` (7,401 features)
2. **Site details metadata**: `s3://public-wetlands/ramsar/site-details.parquet` - comprehensive site information
3. **WDPA database**: `s3://public-wdpa/WDPA_Dec2025.parquet` - used for fuzzy matching missing sites
4. **Centroid points**: `s3://public-wetlands/ramsar/raw/features_centroid_publishedPoint.parquet` - fallback for sites without polygons

## Processing Pipeline

### 1. Combined Dataset Creation

Create a comprehensive Ramsar dataset by joining multiple data sources:

**Script:** `join_ramsar_data.py`  
**Job:** `parquet-job.yaml`

The script performs the following steps:
1. Joins existing Ramsar polygons with site details metadata
2. Identifies sites in the metadata that lack polygon data
3. Matches missing sites with WDPA database using fuzzy matching (name + area similarity)
4. For remaining sites, uses centroid point geometries
5. Combines all sources into a unified dataset with source attribution

```bash
kubectl apply -f wetlands/ramsar/parquet-job.yaml
```

**Output:** `s3://public-wetlands/ramsar/ramsar_wetlands.parquet` (comprehensive dataset with all available sites)

### 2. PMTiles Generation

Create vector tiles for web mapping:

**Script:** `create_pmtiles.sh`  
**Job:** `pmtiles-job.yaml`

The script converts GeoParquet → GeoJSONSeq → PMTiles using tippecanoe. Uses the combined dataset.

```bash
kubectl apply -f wetlands/ramsar/pmtiles-job.yaml
```

**Output:** `s3://public-wetlands/ramsar/ramsar_wetlands.pmtiles`

### 3. H3 Hexagon Processing

Process polygons into H3 hexagons at multiple resolutions. Uses the combined dataset.

**Script:** `vec.py`  
**Helper:** `calculate_completions.py`  
**Job:** `hex-job.yaml`

#### Before deploying, calculate required completions:

```bash
python wetlands/ramsar/calculate_completions.py \
  --input-url s3://public-wetlands/ramsar/ramsar_wetlands.parquet \
  --chunk-size 50
```

This tells you the exact number of completions needed in `hex-job.yaml`.

#### Update and deploy:

Edit `hex-job.yaml` and set the `completions` field, then:

```bash
kubectl apply -f wetlands/ramsar/hex-job.yaml
```

**Output:** `s3://public-wetlands/ramsar/chunks/chunk_*.parquet` (~148 files)

### 4. Repartitioning by H3 Resolution 0

Reorganize hex chunks into hive-partitioned format by h0 cell:

**Script:** `repartition.py`  
**Job:** `repartition-job.yaml`

Reads all chunks and writes with h0 partitioning for efficient spatial queries.

```bash
kubectl apply -f wetlands/ramsar/repartition-job.yaml
```

**Output:** `s3://public-wetlands/ramsar/hex/h0=*/` (hive-partitioned by h0)

## Final Outputs

- **Combined GeoParquet:** `s3://public-wetlands/ramsar/ramsar_complete.parquet` - Comprehensive dataset with geometries from multiple sources
- **Summary Report:** `s3://public-wetlands/ramsar/ramsar_summary.parquet` - Processing statistics and coverage metrics
- **PMTiles:** `s3://public-wetlands/ramsar/ramsar_wetlands.pmtiles` - Vector tiles for web mapping
- **H3 Hexagons:** `s3://public-wetlands/ramsar/hex/` - Hive-partitioned by h0, resolution 8 hexagons

## Data Sources Attribution

Each record includes a `source` field indicating geometry origin:
- `original`: From original Ramsar polygon export
- `WDPA`: Matched from WDPA database via fuzzy matching
- `centroid`: Point geometry from Ramsar centroid data

## Attributes

The combined dataset includes comprehensive metadata:

**Identifiers & Basic Info:**
- `ramsarid`: Ramsar site ID
- `Site name`: Official name of the wetland
- `iso3` / `Country` / `Territory`: Location information
- `Region`: Geographic region

**Designation Details:**
- `Designation date`: When site was designated
- `Last publication date`: Most recent update
- `Area (ha)`: Official area in hectares

**Ecological Criteria:**
- `Criterion1` through `Criterion9`: Ramsar designation criteria met

**Site Characteristics:**
- `Wetland Type`: Classification of wetland type
- `Maximum elevation` / `Minimum elevation`: Elevation range
- `Annotated summary`: Site description

**Management & Status:**
- `Management plan implemented` / `Management plan available`: Plan status
- `Montreux listed`: Whether on Montreux Record (sites with adverse changes)

**Designations & Protection:**
- `Global international legal designations`
- `Regional international legal designations`
- `National conservation designation`

**Other:**
- `Ecosystem services`: Services provided by the wetland
- `Threats`: Identified threats to the site
- `source`: Data source for geometry (original/WDPA/centroid)
 