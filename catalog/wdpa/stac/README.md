# World Database on Protected Areas (WDPA) December 2025

## Overview

The World Database on Protected Areas (WDPA) is the most comprehensive global database of marine and terrestrial protected areas. It is a joint project between the UN Environment Programme and the International Union for Conservation of Nature (IUCN), managed by UNEP World Conservation Monitoring Centre (UNEP-WCMC).

This dataset represents the December 2025 edition, indexed by H3 hexagons (resolution 8) for efficient spatial analysis.

## Source & Attribution

**Source**: UN Environment Programme World Conservation Monitoring Centre (UNEP-WCMC) and International Union for Conservation of Nature (IUCN)  
**Website**: https://www.protectedplanet.net/en/thematic-areas/wdpa  
**Established**: 1981 (Database mandate from 1959)  
**Update Frequency**: Monthly (this is Dec 2025 snapshot)

**Citation**: UNEP-WCMC and IUCN (2025), Protected Planet: The World Database on Protected Areas (WDPA) [Online], December 2025, Cambridge, UK: UNEP-WCMC and IUCN. Available at: www.protectedplanet.net

## Data Format & Access

**Base URL**: `https://s3-west.nrp-nautilus.io/public-wdpa/`

### H3 Hexagonal Parquet

Partitioned by H3 resolution 0 (h0) cells for global scalability.

**Path Pattern**: `hex/h0={cell}/data_0.parquet`

## Data Dictionary

### Identification Fields

| Column | Type | Description |
|--------|------|-------------|
| `OBJECTID` | Integer | Unique object identifier |
| `SITE_ID` | Integer | Unique site identifier |
| `SITE_PID` | String | Protected Site ID |
| `SITE_TYPE` | String | Type of site (e.g., "polygon", "point") |
| `METADATAID` | Integer | Metadata record identifier |

### Names & Designation

| Column | Type | Description |
|--------|------|-------------|
| `NAME` | String | Site name in original language |
| `NAME_ENG` | String | Site name in English |
| `DESIG` | String | Designation type in original language |
| `DESIG_ENG` | String | Designation type in English (e.g., "National Park", "Nature Reserve") |
| `DESIG_TYPE` | String | Designation classification |

### IUCN Classification

| Column | Type | Description |
|--------|------|-------------|
| `IUCN_CAT` | String | IUCN Protected Area Management Category |
| `INT_CRIT` | String | International criteria designation |
| `REALM` | String | Terrestrial or Marine realm |

**IUCN Categories**:
- **Ia**: Strict Nature Reserve - Managed for science
- **Ib**: Wilderness Area - Large unmodified areas
- **II**: National Park - Large-scale ecological protection
- **III**: Natural Monument - Specific natural feature protection
- **IV**: Habitat/Species Management Area - Active management interventions
- **V**: Protected Landscape/Seascape - Cultural-ecological landscapes
- **VI**: Sustainable Use of Natural Resources - Ecosystem conservation with resource use
- **Not Reported/Not Applicable/Not Assigned**: Category not assigned

### Area & Coverage

| Column | Type | Description |
|--------|------|-------------|
| `GIS_AREA` | Float | **GIS-calculated area in km²** (most reliable) |
| `REP_AREA` | Float | Reported area in km² |
| `GIS_M_AREA` | Float | GIS-calculated marine area in km² |
| `REP_M_AREA` | Float | Reported marine area in km² |
| `NO_TAKE` | String | No-take zone designation |
| `NO_TK_AREA` | Float | No-take area in km² |

### Status & Timeline

| Column | Type | Description |
|--------|------|-------------|
| `STATUS` | String | Current status (e.g., "Designated", "Proposed", "Inscribed") |
| `STATUS_YR` | Integer | Year of status designation |
| `VERIF` | String | Verification status |

### Governance & Ownership

| Column | Type | Description |
|--------|------|-------------|
| `GOV_TYPE` | String | Governance type (e.g., "Federal or national ministry or agency", "Collaborative", "Indigenous peoples") |
| `GOVSUBTYPE` | String | Governance sub-type (detailed classification) |
| `OWN_TYPE` | String | Ownership type (e.g., "State", "Community", "Private", "Joint", "Not Reported") |
| `OWNSUBTYPE` | String | Ownership sub-type |

### Management

| Column | Type | Description |
|--------|------|-------------|
| `MANG_AUTH` | String | Managing authority name |
| `MANG_PLAN` | String | Management plan status |

### Geographic & Administrative

| Column | Type | Description |
|--------|------|-------------|
| `ISO3` | String | Country ISO 3-letter code |
| `PRNT_ISO3` | String | Parent country ISO code (for territories) |
| `SUPP_INFO` | String | Supplementary information |
| `CONS_OBJ` | String | Conservation objectives |

### Special Designations

| Column | Type | Description |
|--------|------|-------------|
| `INLND_WTRS` | String | Inland waters designation |
| `OECM_ASMT` | String | Other Effective Area-Based Conservation Measures assessment |

### Spatial Index

| Column | Type | Description |
|--------|------|-------------|
| `h8` | String | H3 hexagon cell ID at resolution 8 (~0.737 km² per hex) |
| `h0` | String | H3 resolution 0 parent cell ID (partition key) |
| `SHAPE_bbox` | Struct | Bounding box coordinates |

## Important Usage Notes

### Overlapping Protected Areas

**CRITICAL**: Multiple protected areas can cover the same hexagon. When calculating total protected area coverage:

```sql
-- WRONG - overcounts overlapping areas
SELECT COUNT(*) * 0.737 FROM wdpa_data;

-- CORRECT - counts unique hexagons
SELECT APPROX_COUNT_DISTINCT(h8) * 0.737 as protected_km2 FROM wdpa_data;
```

Always use `APPROX_COUNT_DISTINCT(h8)` or `SELECT DISTINCT h8` before joining to other datasets to avoid double-counting.

### Area Calculations

- Use `GIS_AREA` field when available (most reliable)
- H3 hexagons at resolution 8 are approximately **0.737 km²** each
- Convert hex counts: `APPROX_COUNT_DISTINCT(h8) * 0.737327598`

## History

The WDPA was established in 1981, with its mandate dating back to 1959 when the UN Economic and Social Council called for a list of national parks and equivalent reserves. The first UN List of Protected Areas was published in 1962.

The database is supported by multiple CBD COP decisions encouraging Parties to share and update protected area information.
