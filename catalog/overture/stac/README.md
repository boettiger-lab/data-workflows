# Overture Maps - Divisions (Regions)

This dataset contains the "Divisions" (Administrative Boundaries) layer from the Overture Maps Foundation. It provides global administrative boundaries, including countries, regions, and other subdivisions.

## Assets

### 1. Divisions (GeoParquet)
**File:** `s3://public-overturemaps/regions.parquet`
The complete Divisions dataset in GeoParquet format.

**Schema:**
- `id`: Overture ID
- `geometry`: WKB Geometry
- `subtype`: Type of division (e.g., country, region)
- `class`: Classification
- `names`: Map of names in various languages
- `country`: Country code
- `region`: Region code
- `is_land`: Boolean flag
- `is_territorial`: Boolean flag

### 2. Divisions (PMTiles)
**File:** `s3://public-overturemaps/regions.pmtiles`
Web-optimized vector tiles for visualization.

### 3. Hexagonal Index (H3)
**Prefix:** `s3://public-overturemaps/regions/hex/` (Partitioned by `h0`)
Spatial index of divisions, likely containing simplified attribution for fast lookups.

**Schema:**
- `id`: Overture ID
- `country`: Country code
- `region`: Region code
- `name`: Primary name
- `h8`: H3 resolution 8 index

### 4. GeoJSON
**File:** `s3://public-overturemaps/regions.geojson`
Standard GeoJSON format (large file).

## Source

- **Producer:** Overture Maps Foundation
- **Link:** [OvertureMaps.org](https://overturemaps.org/)
- **License:** CDLA-Permissive-2.0 (Open Data)

## Usage

This dataset is ideal for:
- Basemaps
- Geocoding/Reverse Geocoding context
- Spatial analysis needing administrative boundaries
- Filtering data by country/region
