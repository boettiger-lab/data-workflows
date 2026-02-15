# HydroBasins Global Watershed Boundaries

## Overview

This directory contains processed global watershed boundary data from HydroBasins, organized by hierarchical basin levels. The data has been compiled from multiple continental datasets into unified global layers.

## Data Source

**Original Data:** HydroSHEDS HydroBasins v1c  
**Source URL:** https://www.hydrosheds.org/products/hydrobasins  
**Download Date:** December 2, 2025  
**Data Version:** v1c  
**Spatial Reference:** WGS 84 (EPSG:4326)  

## Description

HydroBasins provides a series of polygon layers that depict watershed boundaries at different hierarchical levels (also known as Pfafstetter levels). Level 1 represents the largest continental-scale basins, while Level 12 represents the finest sub-basin delineations.

The dataset uses the Pfafstetter coding system, which provides a systematic method for assigning IDs to hydrographic units based on the topology of the drainage network.

## Geographic Coverage

The compiled dataset includes HydroBasins data from all available continents:
- Africa (af)
- Arctic (ar)
- Asia (as)
- Australia/Oceania (au)
- Europe (eu)
- Greenland (gr)
- North America (na)
- South America (sa)
- Siberia (si)

Global extent: Longitude -180° to 180°, Latitude -55.99° to 83.63°

## File Structure

### GeoPackage (combined_hydrobasins.gpkg)

A single multi-layer GeoPackage containing all 12 hierarchical levels:

| Layer Name | Feature Count | Description |
|------------|--------------|-------------|
| level_01   | 10           | Coarsest resolution - major global basins |
| level_02   | 62           | Continental-scale basins |
| level_03   | 292          | Large regional basins |
| level_04   | 1,342        | Regional basins |
| level_05   | 4,734        | Sub-regional basins |
| level_06   | 16,397       | Major watersheds |
| level_07   | 57,646       | Watersheds |
| level_08   | 190,675      | Sub-watersheds |
| level_09   | 508,190      | Fine sub-watersheds |
| level_10   | 941,012      | Very fine sub-watersheds |
| level_11   | 1,031,785    | Near-finest resolution |
| level_12   | 1,034,083    | Finest resolution - detailed sub-basins |

### GeoParquet Files (level_*.parquet)

Individual GeoParquet files for each hierarchical level, optimized for cloud-native spatial data access:

| File Name           | Size  | Feature Count | Use Case |
|---------------------|-------|---------------|----------|
| level_01.parquet    | 19M   | 10            | Global/continental analysis |
| level_02.parquet    | 25M   | 62            | Continental basins |
| level_03.parquet    | 32M   | 292           | Large regional basins |
| level_04.parquet    | 52M   | 1,342         | Regional analysis |
| level_05.parquet    | 81M   | 4,734         | Sub-regional watersheds |
| level_06.parquet    | 130M  | 16,397        | Major watershed analysis |
| level_07.parquet    | 214M  | 57,646        | Watershed-scale studies |
| level_08.parquet    | 353M  | 190,675       | Sub-watershed analysis |
| level_09.parquet    | 550M  | 508,190       | Fine-scale watershed studies |
| level_10.parquet    | 754M  | 941,012       | Very detailed basin analysis |
| level_11.parquet    | 793M  | 1,031,785     | High-resolution studies |
| level_12.parquet    | 794M  | 1,034,083     | Maximum detail analysis |

**Total GeoParquet Size:** ~3.8 GB (compressed)

### H3 Hexagon Versions (Levels 03-06)

Processed H3 resolution 8 hexagon versions are available for levels 03-06, enabling efficient spatial analysis and web-based visualization. These datasets are stored in the cloud and can be accessed via the MinIO (mc) endpoint.

**Storage Location:** `nrp/public-hydrobasins/`

| Level | H3 Hexagons | PMTiles | Source Features | Description |
|-------|-------------|---------|-----------------|-------------|
| L3 | `nrp/public-hydrobasins/L3/` | `L3.pmtiles` | 292 | Large regional basins hexed at H3 resolution 8 |
| L4 | `nrp/public-hydrobasins/L4/` | `L4.pmtiles` | 1,342 | Regional basins hexed at H3 resolution 8 |
| L5 | `nrp/public-hydrobasins/L5/` | `L5.pmtiles` | 4,734 | Sub-regional basins hexed at H3 resolution 8 |
| L6 | `nrp/public-hydrobasins/L6/` | `L6.pmtiles` | 16,397 | Major watersheds hexed at H3 resolution 8 |

**H3 Hex Data Structure:**
- Partitioned by H3 resolution 0 cells for efficient spatial querying
- Format: Parquet files organized by `h0` prefix
- Preserved attributes from source: `HYBAS_ID`, `PFAF_ID`, `UP_AREA`, `SUB_AREA`, `MAIN_BAS`
- Each hex includes H3 cell identifier (`h8`) and associated basin attributes

**PMTiles:**
- Vector tile format optimized for web mapping
- Can be served directly from cloud storage without a tile server
- Includes all basin attributes for interactive visualization

**Access via MinIO Client:**
```bash
# List available levels
mc ls nrp/public-hydrobasins/

# List H3 hexagons for a specific level
mc ls nrp/public-hydrobasins/L3/

# Download PMTiles for visualization
mc cp nrp/public-hydrobasins/L3.pmtiles .

# Example: Read data with DuckDB
duckdb -c "SELECT * FROM read_parquet('s3://public-hydrobasins/L6/**/*.parquet') LIMIT 10"
```

### Source Shapefiles

The original downloaded shapefiles are organized in continent-specific subdirectories:
```
africa/          - African basins (levels 01-12)
arctic/          - Arctic region basins (levels 01-12)
asia/            - Asian basins (levels 01-12)
australia/       - Australian/Oceania basins (levels 01-12)
europe/          - European basins (levels 01-12)
greenland/       - Greenland basins (levels 01-12)
north_america/   - North American basins (levels 01-12)
south_america/   - South American basins (levels 01-12)
siberia/         - Siberian basins (levels 01-12)
```

Each continent directory contains 12 shapefiles (one per level) with associated .shx, .dbf, and .prj files.

## Attributes

Each basin polygon contains the following attributes:

| Attribute  | Type    | Description |
|------------|---------|-------------|
| HYBAS_ID   | Integer | Unique basin identifier |
| NEXT_DOWN  | Integer | ID of the next downstream basin |
| NEXT_SINK  | Integer | ID of the most downstream basin (sink) |
| MAIN_BAS   | Integer | ID of the main basin |
| DIST_SINK  | Float   | Distance to sink (outlet) in km |
| DIST_MAIN  | Float   | Distance to main basin outlet in km |
| SUB_AREA   | Float   | Sub-basin area in km² |
| UP_AREA    | Float   | Upstream area in km² |
| PFAF_ID    | Integer | Pfafstetter code |
| ENDO       | Integer | Endorheic basin flag (1=yes, 0=no) |
| COAST      | Integer | Coastal basin flag (1=yes, 0=no) |
| ORDER      | Integer | Strahler stream order |
| SORT       | Integer | Topological sort order |

## Data Processing

### Processing Date
December 2, 2025

### Processing Steps

1. **Download:** Retrieved HydroBasins v1c shapefiles for all 9 continents from hydrosheds.org
2. **Extraction:** Unzipped all continental datasets (108 shapefiles total: 9 continents × 12 levels)
3. **Consolidation:** Merged continental datasets by level into unified global layers
4. **GeoPackage Creation:** Combined all levels into a single multi-layer GeoPackage
5. **GeoParquet Export:** Generated individual GeoParquet files for each level

### Tools Used
- `wget` - Data download
- `unzip` - Archive extraction  
- `ogr2ogr` (GDAL 3.x) - Shapefile to GeoPackage conversion
- `geopandas` (Python) - GeoParquet generation
- `pyarrow` - Parquet file writing

### H3 Hexagon Processing (Levels 03-06)

The H3 hexagon versions are created through a parallel processing pipeline:

1. **Hex Generation:** Basin polygons are converted to H3 resolution 8 hexagons using parallel Kubernetes jobs
   - Script: `vec.py` in each level directory
   - Chunk processing for parallelization (100 features per chunk)
   - Typical parallelism: 50 workers
   
2. **Repartitioning:** Hexagons are reorganized by H3 resolution 0 cells for optimal spatial queries
   - Script: `repartition.py` in each level directory
   - Groups hexagons by h0 prefix
   - Outputs Parquet files organized by spatial proximity

3. **PMTiles Generation:** Vector tiles created for web visualization
   - Script: `create_pmtiles.sh` in each level directory
   - Uses `tippecanoe` for tile generation
   - Outputs single PMTiles file per level

**Processing Infrastructure:**
- Kubernetes cluster with distributed processing
- Cloud storage (S3-compatible) for input/output
- DuckDB for efficient spatial queries
- H3 library for hexagonal indexing

See individual level directories (`level_03/`, `level_04/`, `level_05/`, `level_06/`) for detailed processing configurations and job definitions.

## Citations

When using this data, please cite:

**HydroSHEDS Database:**
> Lehner, B., Grill G. (2013). Global river hydrography and network routing: baseline data and new approaches to study the world's large river systems. Hydrological Processes, 27(15): 2171-2186. https://doi.org/10.1002/hyp.9740

**HydroBasins:**
> Lehner, B., Grill G. (2013). Global river hydrography and network routing: baseline data and new approaches to study the world's large river systems. Hydrological Processes, 27(15): 2171-2186.

## License

This dataset is derived from HydroSHEDS, which is available for non-commercial use. Please refer to the [HydroSHEDS website](https://www.hydrosheds.org) for the most current licensing information.

## Notes

- The GeoPackage format includes some MULTIPOLYGON geometries in POLYGON layers, which is handled by the GDAL driver but may produce warnings.
- GeoParquet files are more efficient for cloud-based analysis and selective spatial queries.
- All data uses WGS 84 geographic coordinates (EPSG:4326).

## Contact

For questions about this processed dataset, please contact the repository maintainers.  
For questions about the original HydroBasins data, visit https://www.hydrosheds.org
