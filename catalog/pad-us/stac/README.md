# PAD-US 4.1 Combined: Protected Areas Database of the United States

## Overview

The Protected Areas Database of the United States (PAD-US) is America's official national inventory of protected areas, managed by the USGS Gap Analysis Project (GAP). This dataset represents the **Combined layer** which integrates all protection types: fee ownership, easements, proclamation boundaries, marine protected areas, and designation areas into a comprehensive national resource.

PAD-US 4.1 combines data from federal, state, local, and private land management agencies to provide a complete picture of conservation lands and waters in the United States, including territories and freely associated states.

## Citation

U.S. Geological Survey (USGS) Gap Analysis Project (GAP). 2023. Protected Areas Database of the United States (PAD-US) 4.1: U.S. Geological Survey data release. https://doi.org/10.5066/P96WBCHS

## License

**Public Domain (U.S. Government Work)** - As a work of the U.S. Government, PAD-US is not subject to copyright protection within the United States (17 U.S.C. § 105). International copyright and database rights may apply.

**Attribution:** When using PAD-US data, please cite the USGS GAP as shown above.

## Data Formats

This dataset is available in three cloud-native formats:

| Format | Path | Use Case |
|--------|------|---------|
| **GeoParquet** | `s3://public-padus/padus-4-1/combined.parquet` | Analytical queries with DuckDB, Polars, pandas |
| **PMTiles** | `s3://public-padus/padus-4-1/combined.pmtiles` | Web map visualization at multiple zoom levels |
| **H3 Hex Parquet** | `s3://public-padus/padus-4-1/combined/hex/h0=*/` | Spatial joins, aggregation by H3 hexagons (resolution 10 + 8) |

### H3 Resolution Notes

Most features (99.997%) are indexed at **H3 resolution 10** (~15m² cells). However, **20 features** with extremely complex geometries (>800K vertices) are indexed at the coarser **H3 resolution 8** (~0.74 km² cells) due to computational constraints. These features include:

- Tongass National Forest (2 parts)
- Arctic District Office
- Yukon Delta National Wildlife Refuge (2 parts)
- Alaska Maritime National Wildlife Refuge (5 parts)
- Anchorage Field Office
- Chugach National Forest
- Appalachian National Scenic Trail
- Joint Base Langley-Eustis
- Aleutian Islands Wilderness Area
- Marjory Stoneman Douglas Wilderness Area
- Oregon Islands National Wildlife Refuge
- Glacier Bay Wilderness Area
- West Chichagof-Yakobi Wilderness
- Chincoteague National Wildlife Refuge

All features maintain consistent parent resolution columns (h9, h8, h0) enabling seamless integration during spatial queries.

## Dataset Statistics

- **Total Features:** 656,986 protected areas
- **Coverage:** United States (50 states + DC, Puerto Rico, U.S. Virgin Islands, territories, freely associated states)
- **Temporal Range:** 1800s to present (Date_Est field)
- **Spatial Reference:** EPSG:4326 (WGS84)
- **Original CRS:** USA Contiguous Albers Equal Area Conic (USGS version, NAD83)

## Data Dictionary

### Administrative & Identification Fields

| Column | Type | Description |
|--------|------|-------------|
| `_cng_fid` | integer | Cloud-native geometry feature ID (unique identifier) |
| `Source_PAID` | string | Protected Area ID from source agency dataset |
| `Unit_Nm` | string | Unit name - official name of the protected area unit |
| `Loc_Nm` | string | Local name - alternative or historical name if different from Unit_Nm |
| `State_Nm` | string | State, territory, or freely associated state name |

### Classification & Designation

| Column | Type | Description |
|--------|------|-------------|
| `FeatClass` | string | Feature class: Fee (ownership), Easement, Designation (administrative boundary),  Marine, or Proclamation |
| `Category` | string | GAP stewardship category: Federal Land, State Land, Local Land, Private Conservation Land, Joint Ownership, Designation Area |
| `Des_Tp` | string | Designation type code (see Designation_Type lookup table) |
| `Loc_Ds` | string | Local designation - official designation in original language or local terminology |

### Ownership

| Column | Type | Description |
|--------|------|-------------|
| `Own_Type` | string | Owner type: FED (Federal), STAT (State), LOC (Local), PVT (Private), JNT (Joint), TRIB (Tribal), TERR (Territorial), DIST (District), NGO (Non-Governmental Organization) |
| `Own_Name` | string | Owner name - specific agency, organization, or entity that holds title |
| `Loc_Own` | string | Local owner - owner name in local terminology or original language |

### Management

| Column | Type | Description |
|--------|------|-------------|
| `Mang_Type` | string | Manager type code - same categories as Own_Type |
| `Mang_Name` | string | Manager name - agency or organization responsible for day-to-day management |
| `Loc_Mang` | string | Local manager - manager name in local terminology |

### Conservation Status

| Column | Type | Description |
|--------|------|-------------|
| `GAP_Sts` | string | GAP Status Code: 1 = Permanent protection, biodiversity as primary goal; 2 = Permanent protection, biodiversity as primary/major goal; 3 = Permanent protection, multiple uses; 4 = No known biodiversity mandate. See GAP_Status lookup table |
| `GAPCdSrc` | string | Source of GAP Status Code assignment |
| `GAPCdDt` | string | Date GAP Status Code was assigned (YYYYMMDD or YYYY) |
| `IUCN_Cat` | string | IUCN Protected Area Management Category: Ia (Strict Nature Reserve), Ib (Wilderness Area), II (National Park), III (Natural Monument), IV (Habitat/Species Management), V (Protected Landscape/Seascape), VI (Protected Area with Sustainable Use). See IUCN_Category lookup table |
| `IUCNCtSrc` | string | Source of IUCN Category assignment |
| `IUCNCtDt` | string | Date IUCN Category was assigned |
| `WDPA_Cd` | integer | World Database on Protected Areas (WDPA) site code for internationally recognized sites |

### Public Access

| Column | Type | Description |
|--------|------|-------------|
| `Pub_Access` | string | Public access status: OA (Open Access), RA (Restricted Access), XA (Closed/No Public Access), UK (Unknown). See Public_Access lookup table |
| `Access_Src` | string | Source of public access information |
| `Access_Dt` | string | Date public access status was determined |

### Temporal Information

| Column | Type | Description |
|--------|------|-------------|
| `Date_Est` | string | Date established - when protection was formally established (YYYYMMDD, YYYY, or text description) |
| `Term` | integer | Term flag: 1 = Temporary/Term protection, 0 or NULL = Permanent protection |
| `Duration` | string | Duration description for temporary protections (e.g., "20 years", "until 2050") |

### Data Provenance

| Column | Type | Description |
|--------|------|-------------|
| `Agg_Src` | string | Aggregator source - organization that aggregated/compiled the data (often state agencies) |
| `GIS_Src` | string | GIS source - original GIS data provider or source dataset name |
| `Src_Date` | string | Source date - date of source data (YYYYMMDD or YYYY) |
| `Comments` | string | Additional information, caveats, or notes about the feature |

### Spatial Measures

| Column | Type | Description |
|--------|------|-------------|
| `GIS_Acres` | integer | GIS-calculated area in acres (most reliable area measure, calculated from geometry) |
| `SHAPE_Length` | double | Perimeter length in meters (original CRS units) |
| `SHAPE_Area` | double | Area in square meters (original CRS units) |

### Geometry Fields

| Column | Type | Description |
|--------|------|-------------|
| `SHAPE` | geometry | Geometry in WKB format (EPSG:4326, typically MULTIPOLYGON) |
| `bbox` | struct | Bounding box with xmin, ymin, xmax, ymax in EPSG:4326 coordinates |

## Usage Examples

### Query by State

```sql
-- Find all protected areas in California
SELECT Unit_Nm, Category, GAP_Sts, GIS_Acres
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-padus/padus-4-1/combined.parquet')
WHERE State_Nm = 'CA'
ORDER BY GIS_Acres DESC;
```

### Filter by GAP Status

```sql
-- Get highest protection status areas (GAP 1 or 2)
SELECT Unit_Nm, Own_Name, Des_Tp, GIS_Acres
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-padus/padus-4-1/combined.parquet')
WHERE GAP_Sts IN ('1', '2')
  AND GIS_Acres > 1000;
```

### Calculate Federal Land by Manager

```sql
-- Total federal acres by managing agency
SELECT Mang_Name, 
       COUNT(*) as num_units,
       SUM(GIS_Acres) as total_acres
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-padus/padus-4-1/combined.parquet')
WHERE Own_Type = 'FED'
GROUP BY Mang_Name
ORDER BY total_acres DESC;
```

### Spatial Join with H3 Hexagons

```sql
-- Find all protected areas intersecting specific H3 cells
SELECT pa.Unit_Nm, pa.GAP_Sts, hex.h3
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-padus/padus-4-1/combined/hex/h0=*/') hex
JOIN read_parquet('https://s3-west.nrp-nautilus.io/public-padus/padus-4-1/combined.parquet') pa
  ON hex._cng_fid = pa._cng_fid
WHERE hex.h8 = 612845965541203967;
```

## Important Notes

1. **Overlapping Features:** The Combined layer contains overlapping features (fee, easement, designation, marine, proclamation). A single location may be covered by multiple records. When calculating total protected area, use geometric operations to handle overlaps appropriately.

2. **Temporal Coverage:** Features span from the 1800s to present. Check `Date_Est` and `Src_Date` fields for temporal relevance.

3. **Access vs. Protection:** `Pub_Access` indicates public access rights, not protection status. A highly protected area (GAP 1) may have no public access (XA).

4. **Mixed Resolutions:** Most features use H3 resolution 10, but 20 extremely complex features use resolution 8. Both resolutions share common parent columns (h9, h8, h0) for compatibility.

5. **Null Values:** Many fields may be NULL where information is not available or not applicable to that protection type.

## Related Resources

- **USGS GAP Analysis Project:** https://www.usgs.gov/programs/gap-analysis-project
- **PAD-US Data Portal:** https://www.usgs.gov/programs/gap-analysis-project/science/pad-us-data-download
- **DOI:** https://doi.org/10.5066/P96WBCHS
- **PAD-US Standards Manual:** https://www.usgs.gov/programs/gap-analysis-project/science/pad-us-standards-and-methods

## Contact

For questions about PAD-US data content and standards, contact USGS GAP Analysis Project.

For questions about this cloud-native format, contact the Boettiger Lab at UC Berkeley.

## Processing Notes

This cloud-native version was processed using the `cng-datasets` tool:
- Source: PADUS4_1Combined_Proclamation_Marine_Fee_Designation_Easement layer from PADUS4_1Geodatabase.gdb
- Converted to GeoParquet with spatial indexes
- Generated PMTiles at zoom levels 0-14
- Indexed by H3 hexagons at resolutions 10 and 8
- Original CRS converted from USA Contiguous Albers Equal Area Conic to EPSG:4326

Last updated: February 2026
