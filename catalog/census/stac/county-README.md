# US Census 2024 County Boundaries

2024 county and equivalent boundaries from the US Census Bureau's TIGER/Line shapefiles, processed into cloud-native formats with H3 hexagonal spatial indexing.

## Dataset Overview

- **Source**: US Census Bureau TIGER/Line 2024
- **Geography Level**: County/Equivalent
- **Features**: 3,235 counties and equivalents
- **H3 Resolution**: 10 (~0.015 km² per hex)
- **Parent Resolutions**: 9, 8, 0
- **Last Updated**: February 2026

## Available Formats

### GeoParquet
```
s3://public-census/census-2024/county.parquet
```
- **Format**: GeoParquet with ZSTD compression
- **CRS**: EPSG:4326 (WGS84)
- **Row Groups**: 100,000 features
- **Geometry Type**: MultiPolygon
- **Use Case**: Analytical queries with DuckDB, Polars, GeoPandas

### PMTiles
```
s3://public-census/census-2024/county.pmtiles
```
- **Format**: PMTiles v3
- **Use Case**: Web map visualization with MapLibre GL JS, Leaflet

### H3 Hex Index
```
s3://public-census/census-2024/county/hex/h0={cell}/
```
- **Format**: Partitioned Parquet by H3 resolution 0 cells
- **Columns**: `h3_cell` (resolution 10), `feature_id`, plus parent resolutions
- **Use Case**: Fast spatial joins, area-weighted aggregation

## Attributes

Key attributes from TIGER/Line shapefiles:

- `STATEFP`: State FIPS code (2 digits)
- `COUNTYFP`: County FIPS code (3 digits)
- `COUNTYNS`: County GNIS identifier
- `GEOID`: Complete geographic identifier (STATEFP + COUNTYFP)
- `NAME`: County/equivalent name
- `NAMELSAD`: Full name with legal/statistical description (e.g., "Los Angeles County")
- `LSAD`: Legal/Statistical Area Description code
- `CLASSFP`: FIPS class code
- `ALAND`: Land area (square meters)
- `AWATER`: Water area (square meters)

## Usage Examples

### DuckDB Query
```sql
-- Load county boundaries
LOAD spatial;
CREATE TABLE counties AS 
  SELECT * FROM read_parquet('s3://public-census/census-2024/county.parquet');

-- Query by state and county name
SELECT NAMELSAD, ALAND/1000000 as land_sq_km, AWATER/1000000 as water_sq_km
FROM counties
WHERE STATEFP = '06' AND NAME = 'Los Angeles';

-- Find largest counties by land area
SELECT STATEFP, NAMELSAD, ALAND/1000000 as land_sq_km
FROM counties
ORDER BY ALAND DESC
LIMIT 10;

-- Join with H3 hex index for spatial queries
CREATE TABLE county_hexes AS
  SELECT * FROM read_parquet('s3://public-census/census-2024/county/hex/h0=*/');
  
-- Count H3 cells per county in California
SELECT c.NAMELSAD, COUNT(h.h3_cell) as hex_count
FROM county_hexes h
JOIN counties c ON h.feature_id = c._cng_fid
WHERE c.STATEFP = '06'
GROUP BY c.NAMELSAD
ORDER BY hex_count DESC
LIMIT 20;
```

### Python (GeoPandas)
```python
import geopandas as gpd

# Read county boundaries
counties = gpd.read_parquet('s3://public-census/census-2024/county.parquet')

# Filter to California counties
ca_counties = counties[counties['STATEFP'] == '06']

# Calculate total land area
print(f"California counties: {len(ca_counties)}")
print(f"Total land area: {ca_counties['ALAND'].sum() / 1e6:.0f} sq km")

# Find coastal counties (high water area ratio)
counties['water_pct'] = counties['AWATER'] / (counties['ALAND'] + counties['AWATER']) * 100
coastal = counties[counties['water_pct'] > 10].sort_values('water_pct', ascending=False)
print(coastal[['NAMELSAD', 'water_pct']].head(10))
```

### Web Mapping (MapLibre GL JS)
```javascript
map.addSource('counties', {
  type: 'vector',
  url: 'pmtiles://https://s3-west.nrp-nautilus.io/public-census/census-2024/county.pmtiles'
});

map.addLayer({
  id: 'counties-fill',
  type: 'fill',
  source: 'counties',
  'source-layer': 'county',
  paint: {
    'fill-color': '#888',
    'fill-opacity': 0.2
  }
});

map.addLayer({
  id: 'counties-line',
  type: 'line',
  source: 'counties',
  'source-layer': 'county',
  paint: {
    'line-color': '#000',
    'line-width': 1
  }
});
```

## H3 Spatial Indexing

Each county boundary is indexed into H3 hexagons at resolution 10 (~0.015 km² per hex):

- **San Bernardino County, CA**: ~2M hexes (largest by area)
- **Los Angeles County, CA**: ~1.2M hexes (largest by population)
- **Kalawao County, HI**: ~140 hexes (smallest)

The hex index enables:
- Fast point-in-polygon queries for assigning events to counties
- Area-weighted aggregation of raster data to county boundaries
- Multi-resolution spatial analysis with parent resolutions (9, 8, 0)

## County Equivalents

This dataset includes not just counties but all county-level statistical equivalents:

- **Counties**: 1,901 (traditional county governments)
- **Parishes**: 64 (Louisiana)
- **Boroughs/Census Areas**: 29 (Alaska)
- **Independent Cities**: 41 (VA, MO, MD, NV)
- **Municipios**: 78 (Puerto Rico)
- **Islands/Atolls**: Other territories

## Processing Details

- **Source URL**: https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/tl_2024_us_county.zip
- **Processing Date**: February 2026
- **Pipeline**: convert (72s) → hex (191 completions, 4m02s) → pmtiles (9m16s) → repartition (94s)
- **Total Features**: 3,235 counties/equivalents
- **Total Processing Time**: ~15 minutes

## Citation

U.S. Census Bureau (2024). TIGER/Line Shapefiles: County and Equivalent. Retrieved from https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html

## License

Public domain. No restrictions on use.

## Related Datasets

- [Census 2024 States](state-README.md) - 56 state/territory boundaries
- [Census 2024 Census Tracts](tract-README.md) - ~85,000 tract boundaries
- [Census 2024 Congressional Districts](cd-README.md) - 119th Congress districts

## Access

**Public HTTP Access:**
```
https://s3-west.nrp-nautilus.io/public-census/census-2024/county.parquet
https://s3-west.nrp-nautilus.io/public-census/census-2024/county.pmtiles
```

**S3 Access (requires credentials):**
```
s3://public-census/census-2024/county.parquet
s3://public-census/census-2024/county.pmtiles
s3://public-census/census-2024/county/hex/h0=*/
```
