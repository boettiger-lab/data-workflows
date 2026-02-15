# CPAD & CCED 2025b: California Protected Areas and Conservation Easements

## Overview

This dataset provides comprehensive spatial data on California's protected lands and conservation easements in three cloud-optimized formats. The data consists of two complementary databases:

- **CPAD (California Protected Areas Database) 2025b**: Inventories over 50 million acres across 16,000+ parks and protected areas owned by 1,200+ public agencies and nonprofits
- **CCED (California Conservation Easement Database) 2025b**: Inventories 3+ million acres across 3,800+ conservation easements held by 180+ agencies and nonprofits

## Data Formats & Access

All data is publicly available via the National Research Platform S3 bucket:

**Base URL**: `https://s3-west.nrp-nautilus.io/public-cpad/`

### 1. Cloud-Optimized GeoParquet

Parquet files with spatial geometries, optimized for cloud-native queries:

- **CPAD Holdings** (parcel-level detail): `cpad-2025b-holdings.parquet` (72 MB)
- **CPAD Units** (named holdings within counties): `cpad-2025b-units.parquet` (53 MB)  
- **CCED Easements**: `cced-2025b.parquet` (18 MB)

### 2. PMTiles

Vector tile format for efficient web mapping with progressive loading:

- **CPAD Holdings**: `cpad-2025b-holdings.pmtiles` (170 MB)
  - Layer name: `cpad-2025b-holdings`
- **CPAD Units**: `cpad-2025b-units.pmtiles` (85 MB)
  - Layer name: `cpad-2025b-units`
- **CCED Easements**: `cced-2025b.pmtiles` (27 MB)
  - Layer name: `cced-2025b`

### 3. H3 Hexagonal Tilings

Hierarchical hexagonal grid at resolution 10 (~15,000 m² per hex), partitioned by H3 resolution 0 (h0) cell:

- **CPAD Holdings**: `cpad-2025b-holdings/hex/h0={cell}/data_0.parquet`
- **CPAD Units**: `cpad-2025b-units/hex/h0={cell}/data_0.parquet`
- **CCED Easements**: `cced-2025b/hex/h0={cell}/data_0.parquet`

H3 hexes include parent resolutions 0, 8, and 9 for hierarchical aggregation.

## Database Structure

### CPAD Geographic Levels

CPAD provides three levels of spatial aggregation:

1. **HOLDINGS**: Individual parcels of protected land - most detailed level for analysis
2. **UNITS**: Aggregations of holdings with common name, access level, and managing agency within each county
3. **SUPER UNITS**: Dissolved aggregations across county boundaries by park name and managing agency - useful for recreation and cartography

### Key Field Descriptions

#### CPAD Holdings Core Fields

| Field | Description |
|-------|-------------|
| `HOLDING_ID` | Unique identifier for each parcel |
| `UNIT_ID` | ID linking to parent unit |
| `SUID_NMA` | Super unit ID |
| `UNIT_NAME` | Name of the park/unit |
| `AGNCY_NAME` | Full name of owning agency |
| `AGNCY_LEV` | Jurisdiction level: City, County, Special District, Joint, State, Federal, Non Profit, Private |
| `AGNCY_TYP` | Detailed agency type (e.g., State Agency, Non Profit - Land Trust, Recreation/Parks District) |
| `MNG_AGNCY` | Managing agency if different from owner |
| `ACCESS_TYP` | Public access level: Open Access, Restricted, No Public Access |
| `LAND_WATER` | Whether holding is land or water |
| `COUNTY` | County containing the holding |
| `CITY` | City containing the holding (if applicable) |
| `ACRES` | Acreage calculated by GIS |
| `SPEC_USE` | Special uses: Cemetery, Golf Course, School JUA, Trail Corridor, Wildlife Sanctuary, etc. |
| `YR_PROTECT` | Year parcel was acquired |
| `YR_EST` | Year the park/unit was established |

#### GAP Status Codes

Conservation status based on USGS GAP Analysis Program:

| Field | Description |
|-------|-------------|
| `GAP1_acres` | Acres managed for biodiversity where disturbance events proceed or are mimicked |
| `GAP2_acres` | Acres managed for biodiversity where disturbance events are suppressed |
| `GAP3_acres` | Acres managed for multiple uses including extraction (mining, logging) or OHV use |
| `GAP4_acres` | Acres with no known mandate for protection |
| `GAP_tot_ac` | Sum of all GAP acres |
| `GAP_Source` | Source of GAP data: USGS PAD-US, CDPR, or managing agency |

#### CPAD Units Fields

Units have fewer attributes than holdings, primarily used for sub-county analysis:

- Same core fields as holdings: `UNIT_ID`, `UNIT_NAME`, `SUID_NMA`, access, agency fields
- Aggregated statistics: `ACRES`, GAP acres by category
- No parcel-level details (no `LAND_WATER`, `SITE_NAME`, `SPEC_USE`)

#### CPAD Super Units Fields

Super Units are the most generalized representation:

| Field | Description |
|-------|-------------|
| `SUID_NMA` | Unique super unit ID |
| `PARK_NAME` | Name of the park |
| `MNG_AGENCY` | Managing agency name |
| `MNG_AG_LEV` | Managing agency jurisdiction level |
| `MNG_AG_TYP` | Detailed managing agency type |
| `ACCESS_TYP` | Public access level |
| `ACRES` | Total acreage |
| `YR_EST` | Year established |
| GAP acres by category |

### CCED Easement Fields

| Field | Description |
|-------|-------------|
| `e_hold_id` | Unique easement record ID |
| `sitename` | Site name as reported by agency |
| `ease_label` | Generic label "Conservation Easement" for mapping |
| `esmthldr` | Primary easement holder agency name |
| `eholdtyp` | Holder type: federal, state, local, NGO, other |
| `s_emthd1` | Any additional easement holders |
| `e_type` | Main purpose of easement (under development) |
| `pubaccess` | Access status: closed, restricted, or open (almost all are closed) |
| `duration` | Permanent or term-limited (if 10+ years) |
| `term` | Numeric term length if applicable |
| `date_est` | Full date established (MM/DD/YYYY) |
| `year_est` | Year established (YYYY) |
| `county` | County (or mostly within) |
| `gis_acres` | Acres calculated by GIS |
| `GAP1_acres`, `GAP2_acres`, `GAP3_acres`, `GAP4_acres` | GAP status acreage |
| `TOT_GAP_AC` | Sum of GAP acres |
| `GAP_Source` | Source of GAP data: PADUS, CDPR, Local Agencies |
| `iucncat` | IUCN management category: Ia, Ib, II, III, IV, V, VI, N/A |

**Important**: CCED lands are predominantly **Closed to public access**. Conservation easements are on primarily private lands with legal restrictions on development.

## Key Data Characteristics

### CPAD Protected Status

Lands in CPAD have fee title ownership dedicated to open space purposes:

- **Habitat Conservation**: Wildlife or plant reserves
- **Recreation**: Parks, trails, beaches
- **Forestry**: Active forest management
- **Agriculture/Ranching**: Crop lands and grazing lands
- **Water Supply**: Watersheds and waterways
- **Flood Control**: Natural flood control areas
- **Scenic Areas**: Viewscape protection

### CCED Conservation Purposes

Easements restrict future land uses to preserve:

- Habitat conservation
- General open space
- Historical/cultural sites
- Forestry, agriculture, ranching
- Water supply and watersheds
- Scenic viewscapes
- Flood control

### Ownership vs Management

- **CPAD**: Tracks by owning agency; if managed by different agency, both are recorded
- **CCED**: Tracks by managing agency (easement holder); land ownership not included

### Access Levels

- **Open Access**: Open to public for agency-designated use (no guarantee of specific activities)
- **Restricted Access**: Requires permits or has limited hours/seasons
- **No Public Access**: Not open to the public

*Always consult managing agencies for current access information and allowed activities.*

### Land and Water

CPAD holdings distinguish land vs water areas (tidal zones, coastal areas, lakes/reservoirs). Water boundaries use National Hydrography Dataset (NHD) and aerial imagery. Small water bodies (<10 acres) and streams are excluded.

## Example SQL Queries with DuckDB

### Query 1: Find Total Protected Acres by County at Each GAP Level

```sql
SELECT 
    county,
    SUM(GAP1_acres) as gap1_acres,
    SUM(GAP2_acres) as gap2_acres,
    SUM(GAP3_acres) as gap3_acres,
    SUM(GAP4_acres) as gap4_acres,
    SUM(acres) as total_acres
FROM read_parquet('s3://public-cpad/cpad-2025b-holdings/hex/*/*.parquet', 
                   hive_partitioning=1)
WHERE county IS NOT NULL
GROUP BY county
ORDER BY total_acres DESC;
```

### Query 2: Identify Open Access State Parks in Hex Cells

```sql
SELECT 
    h3_10,
    county,
    unit_name,
    agncy_name,
    acres,
    gap1_acres,
    gap2_acres
FROM read_parquet('s3://public-cpad/cpad-2025b-units/hex/*/*.parquet',
                   hive_partitioning=1)
WHERE access_typ = 'Open Access'
  AND agncy_lev = 'State'
  AND agncy_typ = 'State Agency'
  AND unit_name NOT LIKE 'Unnamed%'
ORDER BY acres DESC
LIMIT 100;
```

### Query 3: Compare Protected Areas vs Conservation Easements by County

```sql
WITH protected AS (
    SELECT county, SUM(acres) as protected_acres
    FROM read_parquet('s3://public-cpad/cpad-2025b-holdings/hex/*/*.parquet',
                       hive_partitioning=1)
    GROUP BY county
),
easements AS (
    SELECT county, SUM(gis_acres) as easement_acres
    FROM read_parquet('s3://public-cpad/cced-2025b/hex/*/*.parquet',
                       hive_partitioning=1)
    GROUP BY county
)
SELECT 
    COALESCE(p.county, e.county) as county,
    COALESCE(protected_acres, 0) as protected_acres,
    COALESCE(easement_acres, 0) as easement_acres,
    COALESCE(protected_acres, 0) + COALESCE(easement_acres, 0) as total_conserved
FROM protected p
FULL OUTER JOIN easements e ON p.county = e.county
ORDER BY total_conserved DESC;
```

### Query 4: Find H3 Hexagons with High Biodiversity Protection (GAP 1 & 2)

```sql
SELECT 
    h3_10,
    h3_0,
    COUNT(*) as num_holdings,
    SUM(gap1_acres + gap2_acres) as high_protection_acres,
    SUM(acres) as total_hex_acres,
    SUM(gap1_acres + gap2_acres) / NULLIF(SUM(acres), 0) as protection_ratio
FROM read_parquet('s3://public-cpad/cpad-2025b-holdings/hex/*/*.parquet',
                   hive_partitioning=1)
WHERE gap1_acres + gap2_acres > 0
GROUP BY h3_10, h3_0
HAVING protection_ratio > 0.8  -- 80%+ high protection
ORDER BY high_protection_acres DESC
LIMIT 100;
```

## Data Quality Notes

### CPAD

- Aligned to assessor parcel boundaries in developed areas; rural areas may use PLSS boundaries
- Water boundaries from NHD; some Bay Area tidal zones refined
- Not all holdings have GAP status codes
- Best used at scales above 1:24,000

### CCED

- Easement boundaries often NOT aligned to parcels (digitized independently or from agency data)
- Easements may cover entire parcels or portions
- Some stacked/overlapping polygons exist where multiple easement holders or funding sources apply
- Use caution when calculating total acreage statistics
- Not all small local/city easements are captured
- No land/water distinction

## Data Sources & Attribution

- **CPAD**: Developed by GreenInfo Network with support from California Natural Resources Agency
- **CCED**: Developed by GreenInfo Network with funding from California Strategic Growth Council, USGS Gap Analysis Program, California Natural Resources Agency, and Department of Water Resources
- **Release**: Version 2025b (December 2025)
- **Documentation**: Full manuals available at [CALands.org](https://www.calands.org)

## License & Usage

Both CPAD and CCED are public records data. These datasets are suitable for planning, assessment, analysis, and display. **Not for official regulatory or legal actions** - those require official land records from county recorders or managing agencies.

For errors or corrections: cpad@CALands.org

---

*This dataset represents California's comprehensive conservation landscape, enabling analysis of biodiversity protection, recreation access, land management patterns, and conservation planning at multiple spatial scales.*
