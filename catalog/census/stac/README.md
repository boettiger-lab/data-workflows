# US Census 2022 - Spatial Crosswalk (Tracts to H3)

This dataset provides a spatial index crosswalk between US Census Tracts (2022) and the H3 geospatial indexing system. It allows for efficient integration of census data with other H3-indexed datasets.

**Note:** This dataset currently contains only the **geometry and identifiers** (FIPS codes). It does *not* contain demographic attributes (population, income, etc.), which should be joined by FIPS code from the appropriate Census API or table.

## Source

- **Producer:** US Census Bureau (TIGER/Line Shapefiles)
- **Year:** 2022
- **Level:** Census Tract
- **Processing:** Boettiger Lab (H3 Indexing)

## Data Format

The dataset is partitioned by H3 resolution 0 index for efficient global querying.

- **Parquet:** `s3://public-census/year=2022/tracts-hex-z10.parquet`
- **H3 Resolution:** 10 (Average area ~0.015 km²)

## Data Dictionary

| Column | Type | Description |
|--------|------|-------------|
| `FIPS` | String | 11-digit Federal Information Processing Standards code uniquely identifying the census tract (State+County+Tract) |
| `h10` | List(String) | List of H3 resolution 10 indices that intersect with this tract |
| `STATE` | String | FIPS State Code |
| `COUNTY` | String | FIPS County Code |
| `year` | Integer | Census year (2022) |
| `geom` | Binary | WKB Geometry of the tract |

## Usage

Use this dataset as a "spine" to map tabular Census data to H3 hexagons.

1. **Get Census Data:** Download demographic data (e.g., ACS 5-year estimates) for 2022 tracts using the Census API or libraries like `tidycensus` / `cenpy`.
2. **Join:** Join your tabular data to this dataset on the `FIPS` column (ensure FIPS codes are formatted consistently as 11-character strings).
3. **Spatial Analysis:** Use the `h10` column to aggregate or correlate with other H3 datasets.

## Citation

U.S. Census Bureau. (2022). TIGER/Line Shapefiles. Retrieved from https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html
