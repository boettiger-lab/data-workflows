# US Census 2024 Congressional Districts (119th Congress)

2024 congressional district boundaries for the 119th United States Congress (2025-2027) from the US Census Bureau's TIGER/Line shapefiles, processed into cloud-native formats with H3 hexagonal spatial indexing.

## Dataset Overview

- **Source**: US Census Bureau TIGER/Line 2024
- **Geography Level**: Congressional District (119th Congress)
- **Features**: ~435 congressional districts
- **H3 Resolution**: 10 (~0.015 km² per hex)
- **Parent Resolutions**: 9, 8, 0
- **Last Updated**: February 2026
- **Congress Session**: 119th (2025-2027)

## Available Formats

### GeoParquet
```
s3://public-census/census-2024/cd.parquet
```
- **Format**: GeoParquet with ZSTD compression
- **CRS**: EPSG:4326 (WGS84)
- **Row Groups**: 100,000 features
- **Geometry Type**: MultiPolygon
- **Use Case**: Analytical queries with DuckDB, Polars, GeoPandas

### PMTiles
```
s3://public-census/census-2024/cd.pmtiles
```
- **Format**: PMTiles v3
- **Use Case**: Web map visualization with MapLibre GL JS, Leaflet

### H3 Hex Index
```
s3://public-census/census-2024/cd/hex/h0={cell}/
```
- **Format**: Partitioned Parquet by H3 resolution 0 cells
- **Columns**: `h3_cell` (resolution 10), `feature_id`, plus parent resolutions
- **Use Case**: Fast spatial joins, area-weighted aggregation

## Attributes

Key attributes from TIGER/Line shapefiles:

- `STATEFP`: State FIPS code (2 digits)
- `CD119FP`: Congressional district code for 119th Congress (2 digits)
- `GEOID`: Complete geographic identifier (STATEFP + CD119FP)
- `NAMELSAD`: Full district name (e.g., "Congressional District 1")
- `LSAD`: Legal/Statistical Area Description code
- `CDSESSN`: Congressional session number ("119")
- `ALAND`: Land area (square meters)
- `AWATER`: Water area (square meters)

## Special District Codes

- `00`: At-large district (states with single representative)
- `98`: Nonvoting delegate district (DC, territories)
- `ZZ`: Area with no representation

## Usage Examples

### DuckDB Query
```sql
-- Load congressional districts
LOAD spatial;
CREATE TABLE districts AS 
  SELECT * FROM read_parquet('s3://public-census/census-2024/cd.parquet');

-- Query districts in a specific state (California's 52 districts)
SELECT CD119FP, NAMELSAD, ALAND/1000000 as land_sq_km
FROM districts
WHERE STATEFP = '06'
ORDER BY CD119FP;

-- Find at-large districts (single-rep states)
SELECT STATEFP, NAMELSAD
FROM districts
WHERE CD119FP = '00'
ORDER BY STATEFP;

-- Non-voting delegates
SELECT STATEFP, NAMELSAD
FROM districts
WHERE CD119FP = '98';

-- Join with H3 hex index for spatial queries
CREATE TABLE cd_hexes AS
  SELECT * FROM read_parquet('s3://public-census/census-2024/cd/hex/h0=*/');
  
-- District sizes by hex count (proxy for area at res 10)
SELECT d.GEOID, d.NAMELSAD, COUNT(h.h3_cell) as hex_count
FROM cd_hexes h
JOIN districts d ON h.feature_id = d._cng_fid
GROUP BY d.GEOID, d.NAMELSAD
ORDER BY hex_count DESC
LIMIT 20;
```

### Python (GeoPandas)
```python
import geopandas as gpd

# Read congressional districts
districts = gpd.read_parquet('s3://public-census/census-2024/cd.parquet')

print(f"Total districts: {len(districts)}")

# Count districts per state
by_state = districts.groupby('STATEFP').size().sort_values(ascending=False)
print("States with most districts:")
print(by_state.head(10))

# At-large districts
at_large = districts[districts['CD119FP'] == '00']
print(f"At-large districts: {len(at_large)}")

# Calculate land area statistics
districts['area_km2'] = districts['ALAND'] / 1e6
print(f"Mean district area: {districts['area_km2'].mean():.0f} sq km")
print(f"Largest district: {districts.loc[districts['area_km2'].idxmax()]['NAMELSAD']}")
print(f"Smallest district: {districts.loc[districts['area_km2'].idxmin()]['NAMELSAD']}")
```

### Electoral Analysis Example
```python
import duckdb

# Assign voter addresses to congressional districts using H3
con = duckdb.connect()
con.execute("LOAD spatial; INSTALL h3 FROM community; LOAD h3;")

# Your voter data with lat/lon
voters_df = pd.DataFrame({
    'voter_id': [...],
    'lat': [...],
    'lon': [...]
})

con.execute("""
    -- Convert voter locations to H3 cells
    CREATE TABLE voters AS
    SELECT voter_id, h3_latlng_to_cell(lat, lon, 10) as h3_cell
    FROM voters_df;
    
    -- Join with district hex index to assign districts
    CREATE TABLE voters_by_district AS
    SELECT v.voter_id, d.GEOID, d.NAMELSAD
    FROM voters v
    JOIN read_parquet('s3://public-census/census-2024/cd/hex/h0=*/') h 
      ON v.h3_cell = h.h3_cell
    JOIN read_parquet('s3://public-census/census-2024/cd.parquet') d 
      ON h.feature_id = d._cng_fid;
    
    -- Count voters per district
    SELECT GEOID, NAMELSAD, COUNT(*) as voter_count
    FROM voters_by_district
    GROUP BY GEOID, NAMELSAD
    ORDER BY voter_count DESC;
""")
```

## H3 Spatial Indexing

Each congressional district is indexed into H3 hexagons at resolution 10 (~0.015 km² per hex):

- **Urban districts**: ~5,000-15,000 hexes (compact, high population density)
- **Suburban districts**: ~15,000-50,000 hexes
- **Rural districts**: Can exceed 100,000 hexes (Alaska at-large district ~113M hexes)

The hex index enables:
- **Voter/address assignment**: Fast point-in-district lookups for electoral analysis
- **Demographic aggregation**: Area-weighted census data to district boundaries
- **Redistricting analysis**: Compare district characteristics across different boundary proposals

## Congressional Districts Background

Congressional districts are geographic divisions for electing members of the US House of Representatives:

- **Total Districts**: 435 voting representatives + 6 non-voting delegates
- **Apportionment**: Based on decennial census population
- **Redistricting**: Most states redraw boundaries after each census
- **Equal Population**: Districts within a state must have nearly equal populations (~760,000 people per district)

### 119th Congress (2025-2027)

This dataset reflects the district boundaries for the 119th US Congress based on 2020 Census apportionment.

## Processing Details

### Preprocessing
- **Source Files**: 56 per-state zip files
- **Method**: Parallel download + unzip + merge via `cng-convert-to-parquet`
- **Duration**: 2 minutes 12 seconds
- **Features**: ~435 congressional districts merged into single GeoParquet

### Pipeline
- **Hex Generation**: 200 chunks completed (18 minutes)
  - Initial run: 199/200 (chunk 0 OOMKilled with 16Gi)
  - Chunk 0 retry: Successful with 32Gi memory (77 seconds)
- **PMTiles**: 14 minutes
- **Repartition**: 14 seconds (all 200 chunks)
- **Total Processing Time**: ~35 minutes

## Citation

U.S. Census Bureau (2024). TIGER/Line Shapefiles: Congressional Districts - 119th Congress. Retrieved from https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html

## License

Public domain. No restrictions on use.

## Related Datasets

- [Census 2024 States](state-README.md) - 56 state/territory boundaries
- [Census 2024 Counties](county-README.md) - 3,235 county boundaries
- [Census 2024 Census Tracts](tract-README.md) - ~85,000 tract boundaries

## Access

**Public HTTP Access:**
```
https://s3-west.nrp-nautilus.io/public-census/census-2024/cd.parquet
https://s3-west.nrp-nautilus.io/public-census/census-2024/cd.pmtiles
```

**S3 Access (requires credentials):**
```
s3://public-census/census-2024/cd.parquet
s3://public-census/census-2024/cd.pmtiles
s3://public-census/census-2024/cd/hex/h0=*/  # All 200 chunks
```

## Future Work

- Add demographic/electoral data joins
- Historical congressional district comparisons (118th, 117th, etc.)
- Voter turnout spatial analysis examples
