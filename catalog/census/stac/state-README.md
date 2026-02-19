# US Census 2024 State Boundaries

2024 state and territory boundaries from the US Census Bureau's TIGER/Line shapefiles, processed into cloud-native formats with H3 hexagonal spatial indexing.

## Dataset Overview

- **Source**: US Census Bureau TIGER/Line 2024
- **Geography Level**: State/Territory
- **Features**: 56 (50 states + DC + 5 territories)
- **H3 Resolution**: 10 (~0.015 km² per hex)
- **Parent Resolutions**: 9, 8, 0
- **Last Updated**: February 2026

## Available Formats

### GeoParquet
```
s3://public-census/census-2024/state.parquet
```
- **Format**: GeoParquet with ZSTD compression
- **CRS**: EPSG:4326 (WGS84)
- **Row Groups**: 100,000 features
- **Geometry Type**: MultiPolygon
- **Use Case**: Analytical queries with DuckDB, Polars, GeoPandas

### PMTiles
```
s3://public-census/census-2024/state.pmtiles
```
- **Format**: PMTiles v3
- **Use Case**: Web map visualization with MapLibre GL JS, Leaflet

### H3 Hex Index
```
s3://public-census/census-2024/state/hex/h0={cell}/
```
- **Format**: Partitioned Parquet by H3 resolution 0 cells
- **Columns**: `h3_cell` (resolution 10), `feature_id`, plus parent resolutions
- **Use Case**: Fast spatial joins, area-weighted aggregation

## Attributes

Key attributes from TIGER/Line shapefiles:

- `STATEFP`: State FIPS code (2 digits)
- `STATENS`: State GNIS identifier
- `GEOID`: Complete geographic identifier (= STATEFP)
- `STUSPS`: 2-letter state postal abbreviation
- `NAME`: State/territory name
- `LSAD`: Legal/Statistical Area Description
- `ALAND`: Land area (square meters)
- `AWATER`: Water area (square meters)

## Usage Examples

### DuckDB Query
```sql
-- Load state boundaries
LOAD spatial;
CREATE TABLE states AS 
  SELECT * FROM read_parquet('s3://public-census/census-2024/state.parquet');

-- Query by state name
SELECT NAME, STUSPS, ALAND/1000000 as land_sq_km
FROM states
WHERE NAME = 'California';

-- Join with H3 hex index for spatial aggregation
CREATE TABLE state_hexes AS
  SELECT * FROM read_parquet('s3://public-census/census-2024/state/hex/h0=*/');
  
-- Count H3 cells per state
SELECT s.NAME, COUNT(h.h3_cell) as hex_count
FROM state_hexes h
JOIN states s ON h.feature_id = s._cng_fid
GROUP BY s.NAME
ORDER BY hex_count DESC;
```

### Python (GeoPandas)
```python
import geopandas as gpd

# Read state boundaries
states = gpd.read_parquet('s3://public-census/census-2024/state.parquet')

# Filter West Coast states
west_coast = states[states['STUSPS'].isin(['CA', 'OR', 'WA'])]

# Calculate total land area
print(f"West Coast land area: {west_coast['ALAND'].sum() / 1e6:.0f} sq km")
```

### Web Mapping (MapLibre GL JS)
```javascript
map.addSource('states', {
  type: 'vector',
  url: 'pmtiles://https://s3-west.nrp-nautilus.io/public-census/census-2024/state.pmtiles'
});

map.addLayer({
  id: 'states-fill',
  type: 'fill',
  source: 'states',
  'source-layer': 'state',
  paint: {
    'fill-color': '#088',
    'fill-opacity': 0.3,
    'fill-outline-color': '#000'
  }
});
```

## H3 Spatial Indexing

Each state boundary is indexed into H3 hexagons at resolution 10 (~0.015 km² per hex):

- **Alaska**: ~113M hexes (largest)
- **Texas**: ~70M hexes
- **Rhode Island**: ~300K hexes (smallest state)

The hex index enables:
- Fast point-in-polygon queries (join point data with hex, then hex with features)
- Area-weighted aggregation (count events per state using hex coverage)
- Multi-resolution analysis (parent resolutions 9, 8, 0 included)

## Processing Details

- **Source URL**: https://www2.census.gov/geo/tiger/TIGER2024/STATE/tl_2024_us_state.zip
- **Processing Date**: February 2026
- **Pipeline**: convert (17s) → hex (56 completions, 6m47s) → pmtiles (4m33s) → repartition (65s)
- **Total Features**: 56 states/territories
- **Total Processing Time**: ~12 minutes

## Citation

U.S. Census Bureau (2024). TIGER/Line Shapefiles: State and Equivalent. Retrieved from https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html

## License

Public domain. No restrictions on use.

## Related Datasets

- [Census 2024 Counties](county-README.md) - 3,235 county boundaries
- [Census 2024 Census Tracts](tract-README.md) - ~85,000 tract boundaries
- [Census 2024 Congressional Districts](cd-README.md) - 119th Congress districts

## Access

**Public HTTP Access:**
```
https://s3-west.nrp-nautilus.io/public-census/census-2024/state.parquet
https://s3-west.nrp-nautilus.io/public-census/census-2024/state.pmtiles
```

**S3 Access (requires credentials):**
```
s3://public-census/census-2024/state.parquet
s3://public-census/census-2024/state.pmtiles
s3://public-census/census-2024/state/hex/h0=*/
```
