# US Census 2024 Census Tracts

2024 census tract boundaries from the US Census Bureau's TIGER/Line shapefiles, processed into cloud-native formats with H3 hexagonal spatial indexing.

## Dataset Overview

- **Source**: US Census Bureau TIGER/Line 2024
- **Geography Level**: Census Tract
- **Features**: ~85,000 census tracts
- **H3 Resolution**: 10 (~0.015 km² per hex)
- **Parent Resolutions**: 9, 8, 0
- **Last Updated**: February 2026

## Available Formats

### GeoParquet
```
s3://public-census/census-2024/tract.parquet
```
- **Format**: GeoParquet with ZSTD compression
- **CRS**: EPSG:4326 (WGS84)
- **Row Groups**: 100,000 features
- **Geometry Type**: MultiPolygon
- **Use Case**: Analytical queries with DuckDB, Polars, GeoPandas

### PMTiles
```
s3://public-census/census-2024/tract.pmtiles
```
- **Format**: PMTiles v3
- **Use Case**: Web map visualization with MapLibre GL JS, Leaflet

### H3 Hex Index
```
s3://public-census/census-2024/tract/hex/h0={cell}/
```
- **Format**: Partitioned Parquet by H3 resolution 0 cells
- **Columns**: `h3_cell` (resolution 10), `feature_id`, plus parent resolutions
- **Use Case**: Fast spatial joins, area-weighted aggregation

## Attributes

Key attributes from TIGER/Line shapefiles:

- `STATEFP`: State FIPS code (2 digits)
- `COUNTYFP`: County FIPS code (3 digits)
- `TRACTCE`: Census tract code (6 digits)
- `GEOID`: Complete geographic identifier (STATEFP + COUNTYFP + TRACTCE)
- `NAME`: Census tract name/number
- `NAMELSAD`: Full name with legal/statistical description
- `ALAND`: Land area (square meters)
- `AWATER`: Water area (square meters)

## Usage Examples

### DuckDB Query
```sql
-- Load census tract boundaries
LOAD spatial;
CREATE TABLE tracts AS 
  SELECT * FROM read_parquet('s3://public-census/census-2024/tract.parquet');

-- Query tracts in a specific county (Los Angeles)
SELECT NAME, ALAND/1000000 as land_sq_km
FROM tracts
WHERE STATEFP = '06' AND COUNTYFP = '037'
ORDER BY NAME;

-- Find tracts with minimal land area (often islands or special cases)
SELECT GEOID, NAME, ALAND
FROM tracts
WHERE ALAND < 100000
ORDER BY ALAND;

-- Join with H3 hex index for spatial analysis
CREATE TABLE tract_hexes AS
  SELECT * FROM read_parquet('s3://public-census/census-2024/tract/hex/h0=*/');
  
-- Calculate hex density per tract
SELECT t.GEOID, t.NAME, 
       COUNT(h.h3_cell) as hex_count,
       t.ALAND/1000000 as land_sq_km,
       COUNT(h.h3_cell) / (t.ALAND/1000000) as hexes_per_sq_km
FROM tract_hexes h
JOIN tracts t ON h.feature_id = t._cng_fid
WHERE t.STATEFP = '06' AND t.COUNTYFP = '037'
GROUP BY t.GEOID, t.NAME, t.ALAND
ORDER BY hex_count DESC
LIMIT 20;
```

### Python (GeoPandas)
```python
import geopandas as gpd
import pandas as pd

# Read census tracts
tracts = gpd.read_parquet('s3://public-census/census-2024/tract.parquet')

# Filter to a specific state (California)
ca_tracts = tracts[tracts['STATEFP'] == '06']
print(f"California census tracts: {len(ca_tracts)}")

# Urban vs rural tracts (using land area as proxy)
ca_tracts['area_km2'] = ca_tracts['ALAND'] / 1e6
urban_threshold = 10  # sq km
urban = ca_tracts[ca_tracts['area_km2'] < urban_threshold]
rural = ca_tracts[ca_tracts['area_km2'] >= urban_threshold]

print(f"Urban tracts: {len(urban)} ({len(urban)/len(ca_tracts)*100:.1f}%)")
print(f"Rural tracts: {len(rural)} ({len(rural)/len(ca_tracts)*100:.1f}%)")

# Find coastal tracts (high water percentage)
ca_tracts['water_pct'] = (ca_tracts['AWATER'] / 
                           (ca_tracts['ALAND'] + ca_tracts['AWATER'])) * 100
coastal = ca_tracts[ca_tracts['water_pct'] > 20].sort_values('water_pct', ascending=False)
print(coastal[['GEOID', 'NAME', 'water_pct']].head())
```

### Spatial Join Example
```python
import duckdb

# Point-in-tract assignment using H3 join
con = duckdb.connect()
con.execute("LOAD spatial")

# Your point data with lat/lon
points_df = pd.DataFrame({
    'event_id': range(1000),
    'lat': [...],  # your latitudes
    'lon': [...]   # your longitudes
})

# Convert points to H3 cells (resolution 10)
con.execute("""
    INSTALL h3 FROM community;
    LOAD h3;
    
    CREATE TABLE points AS
    SELECT event_id, h3_latlng_to_cell(lat, lon, 10) as h3_cell
    FROM points_df;
    
    -- Join with tract hex index
    CREATE TABLE events_by_tract AS
    SELECT t.GEOID, t.NAME, COUNT(*) as event_count
    FROM points p
    JOIN read_parquet('s3://public-census/census-2024/tract/hex/h0=*/') h 
      ON p.h3_cell = h.h3_cell
    JOIN read_parquet('s3://public-census/census-2024/tract.parquet') t 
      ON h.feature_id = t._cng_fid
    GROUP BY t.GEOID, t.NAME
    ORDER BY event_count DESC;
""")

results = con.execute("SELECT * FROM events_by_tract").df()
```

## H3 Spatial Indexing

Each census tract is indexed into H3 hexagons at resolution 10 (~0.015 km² per hex):

- **Urban tracts**: ~1,000-5,000 hexes (dense, small area)
- **Suburban tracts**: ~5,000-20,000 hexes 
- **Rural tracts**: Can exceed 50,000 hexes for large areas

The hex index enables:
- **Fast point-in-tract queries**: Convert points to H3, join with hex index (millions of points/second)
- **Area-weighted aggregation**: Aggregate raster data to tracts using hex coverage
- **Multi-resolution analysis**: Parent resolutions (9, 8, 0) support hierarchical queries

## Census Tract Geography

Census tracts are small, relatively permanent statistical subdivisions of counties:

- **Typical population**: 1,200 to 8,000 people (optimally 4,000)
- **Coverage**: Entire US including territories
- **Designed for**: Demographic data collection and analysis
- **Updates**: Every 10 years with decennial census, boundaries may change

## Processing Details

### Preprocessing
- **Source Files**: 56 per-state zip files
- **Method**: Parallel download + unzip + merge via `cng-convert-to-parquet`
- **Duration**: 3 minutes 2 seconds
- **Features**: ~85,000 census tracts merged into single GeoParquet

### Pipeline
- **Hex Generation**: 200 chunks, 200/200 completed (10 minutes)
- **PMTiles**: 18 minutes
- **Repartition**: 2 minutes 14 seconds
- **Total Processing Time**: ~23 minutes

## Citation

U.S. Census Bureau (2024). TIGER/Line Shapefiles: Census Tracts. Retrieved from https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html

## License

Public domain. No restrictions on use.

## Related Datasets

- [Census 2024 States](state-README.md) - 56 state/territory boundaries
- [Census 2024 Counties](county-README.md) - 3,235 county boundaries
- [Census 2024 Congressional Districts](cd-README.md) - 119th Congress districts

## Access

**Public HTTP Access:**
```
https://s3-west.nrp-nautilus.io/public-census/census-2024/tract.parquet
https://s3-west.nrp-nautilus.io/public-census/census-2024/tract.pmtiles
```

**S3 Access (requires credentials):**
```
s3://public-census/census-2024/tract.parquet
s3://public-census/census-2024/tract.pmtiles
s3://public-census/census-2024/tract/hex/h0=*/
```

## Notes

This dataset was preprocessed from 56 per-state zip files using parallel download and direct shapefile merging (see [AGENTS.md](../../../AGENTS.md) for methodology). The efficient preprocessing approach reduced processing time from 30+ minutes (sequential) to ~3 minutes (parallel).
