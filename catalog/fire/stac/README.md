# Fire Datasets

This bucket contains three fire-related vector datasets:

1. **CAL FIRE Wildfire Perimeters** — California wildfire perimeters through 2024
2. **CAL FIRE Prescribed Burns** — California prescribed burn treatments through 2024
3. **USGS Wildland Fire Combined Dataset** — National wildfire perimeters 1878–2021

All three datasets are polygon geometries processed into GeoParquet, PMTiles, and H3 hex Parquet.

---

## 1. CAL FIRE Wildfire Perimeters (`calfire-2024/firep`)

**Source:** [CAL FIRE FRAP GIS](https://www.fire.ca.gov/what-we-do/fire-resource-assessment-program)
**Features:** 22,810 fire perimeter polygons
**Coverage:** California, 1878–2024
**Source layer:** `firep` (PMTiles source-layer name)

### DuckDB Example

```sql
LOAD spatial;
SELECT YEAR_, FIRE_NAME, AGENCY, GIS_ACRES
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-fire/calfire-2024/firep.parquet')
WHERE YEAR_ >= 2020
ORDER BY GIS_ACRES DESC
LIMIT 10;
```

### MapLibre GL JS Example

```javascript
map.addSource('calfire-firep', {
  type: 'vector',
  url: 'pmtiles://https://s3-west.nrp-nautilus.io/public-fire/calfire-2024/firep.pmtiles'
});
map.addLayer({
  id: 'calfire-firep-fill',
  type: 'fill',
  source: 'calfire-firep',
  'source-layer': 'firep',
  paint: {
    'fill-color': '#d62728',
    'fill-opacity': 0.5
  }
});
```

### Schema

| Column | Type | Description |
|--------|------|-------------|
| YEAR_ | int16 | Calendar year the fire was recorded |
| STATE | string | State abbreviation (always 'CA') |
| AGENCY | string | Responding agency code |
| UNIT_ID | string | CAL FIRE unit identifier |
| FIRE_NAME | string | Name of the fire |
| INC_NUM | string | Local incident number |
| IRWINID | string | IRWIN system incident ID |
| ALARM_DATE | datetime | Date the fire was reported |
| CONT_DATE | datetime | Date the fire was contained |
| C_METHOD | int16 | Collection method code |
| CAUSE | int16 | Fire cause code |
| COMPLEX_NAME | string | Complex fire name (if applicable) |
| COMPLEX_ID | string | Complex fire ID |
| OBJECTIVE | int16 | Management objective code |
| GIS_ACRES | float32 | GIS-calculated area in acres |
| COMMENTS | string | Additional comments |
| FIRE_NUM | string | Historical fire number |
| Shape_Length | float64 | Perimeter length in meters |
| Shape_Area | float64 | Area in square meters |

---

## 2. CAL FIRE Prescribed Burns (`calfire-2024/rxburn`)

**Source:** [CAL FIRE FRAP GIS](https://www.fire.ca.gov/what-we-do/fire-resource-assessment-program)
**Features:** 10,675 prescribed burn polygons
**Coverage:** California, 1980s–2024
**Source layer:** `rxburn` (PMTiles source-layer name)

### DuckDB Example

```sql
LOAD spatial;
SELECT YEAR_, TREATMENT_NAME, AGENCY, TREATED_AC
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-fire/calfire-2024/rxburn.parquet')
WHERE YEAR_ >= 2015
ORDER BY TREATED_AC DESC
LIMIT 10;
```

### MapLibre GL JS Example

```javascript
map.addSource('calfire-rxburn', {
  type: 'vector',
  url: 'pmtiles://https://s3-west.nrp-nautilus.io/public-fire/calfire-2024/rxburn.pmtiles'
});
map.addLayer({
  id: 'calfire-rxburn-fill',
  type: 'fill',
  source: 'calfire-rxburn',
  'source-layer': 'rxburn',
  paint: {
    'fill-color': '#2ca02c',
    'fill-opacity': 0.5
  }
});
```

### Schema

| Column | Type | Description |
|--------|------|-------------|
| YEAR_ | int16 | Calendar year of treatment |
| STATE | string | State abbreviation (always 'CA') |
| AGENCY | string | Responding agency code |
| UNIT_ID | string | CAL FIRE unit identifier |
| TREATMENT_ID | string | Unique treatment identifier |
| TREATMENT_NAME | string | Name of the treatment |
| TREATMENT_TYPE | int16 | Treatment type code |
| START_DATE | datetime | Treatment start date |
| END_DATE | datetime | Treatment end date |
| TREATED_AC | float64 | Reported treated area in acres |
| GIS_ACRES | float32 | GIS-calculated area in acres |
| RX_CONSUM | int16 | Fuel consumption class code |
| PRE_CON_CLASS | int16 | Pre-treatment condition class code |
| POST_CON_CLASS | int16 | Post-treatment condition class code |
| Shape_Length | float64 | Perimeter length in meters |
| Shape_Area | float64 | Area in square meters |

---

## 3. USGS Wildland Fire Combined Dataset (`usgs-fires-2021/combined`)

**Source:** [USGS ScienceBase](https://www.sciencebase.gov/catalog/item/61aa537dd34eb622f699df81)
**Features:** 135,061 fire perimeter polygons
**Coverage:** Continental US, Alaska, Hawaii, US territories, 1878–2021
**Source layer:** `combined` (PMTiles source-layer name)

This dataset combines records from dozens of federal, state, and local data sources into a single de-duplicated national inventory. Where multiple sources cover the same fire, the highest-quality polygon is selected and source attributes are preserved in list fields.

### DuckDB Example

```sql
LOAD spatial;
SELECT Fire_Year, Assigned_Fire_Type, GIS_Acres, Listed_Fire_Names
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-fire/usgs-fires-2021/combined.parquet')
WHERE Fire_Year >= 2000 AND GIS_Acres > 100000
ORDER BY GIS_Acres DESC
LIMIT 20;
```

### H3 Hex Example (burn area by hex cell)

```python
import duckdb

conn = duckdb.connect()
conn.execute("INSTALL httpfs; LOAD httpfs;")
conn.execute("""
CREATE SECRET (
  TYPE S3,
  KEY_ID '',
  SECRET '',
  ENDPOINT 's3-west.nrp-nautilus.io',
  USE_SSL 'TRUE',
  URL_STYLE 'path'
)
""")

result = conn.execute("""
SELECT h3_index, SUM(GIS_Acres) AS total_acres
FROM read_parquet(
  'https://s3-west.nrp-nautilus.io/public-fire/usgs-fires-2021/combined/hex/h0=*/data_0.parquet',
  hive_partitioning=true
)
GROUP BY h3_index
ORDER BY total_acres DESC
LIMIT 20
""").df()
```

### MapLibre GL JS Example

```javascript
map.addSource('usgs-fires', {
  type: 'vector',
  url: 'pmtiles://https://s3-west.nrp-nautilus.io/public-fire/usgs-fires-2021/combined.pmtiles'
});
map.addLayer({
  id: 'usgs-fires-fill',
  type: 'fill',
  source: 'usgs-fires',
  'source-layer': 'combined',
  paint: {
    'fill-color': '#ff7f0e',
    'fill-opacity': 0.4
  }
});
```

### Schema

| Column | Type | Description |
|--------|------|-------------|
| USGS_Assigned_ID | int32 | Unique USGS identifier |
| Assigned_Fire_Type | string | Fire type (Wildfire, Prescribed Fire, etc.) |
| Fire_Year | int16 | Year the fire occurred |
| Fire_Polygon_Tier | int16 | Source quality tier (1 = highest quality) |
| Fire_Attribute_Tiers | string | Quality tier per attribute |
| GIS_Acres | float64 | GIS-calculated area in acres |
| GIS_Hectares | float64 | GIS-calculated area in hectares |
| Source_Datasets | string | Contributing source dataset names |
| Listed_Fire_Types | string | All fire types from contributing sources |
| Listed_Fire_Names | string | All fire names from contributing sources |
| Listed_Fire_Codes | string | All fire codes from contributing sources |
| Listed_Fire_IDs | string | All fire IDs from contributing sources |
| Listed_Fire_IRWIN_IDs | string | All IRWIN IDs from contributing sources |
| Listed_Fire_Dates | string | All fire dates from contributing sources |
| Listed_Fire_Causes | string | All fire causes from contributing sources |
| Listed_Fire_Cause_Class | string | Cause classification |
| Listed_Rx_Reported_Acres | string | Reported Rx acres |
| Listed_Map_Digitize_Methods | string | Digitization methods |
| Listed_Notes | string | Source dataset notes |
| Processing_Notes | string | USGS processing and QA notes |
| Wildfire_Notice | string | Data quality notice for wildfire attribution |
| Prescribed_Burn_Notice | string | Data quality notice for prescribed burn attribution |
| Wildfire_and_Rx_Flag | string | Wildfire/Rx overlap flag |
| Overlap_Within_1_or_2_Flag | string | Temporal overlap flag |
| Circleness_Scale | float64 | Shape circularity (1.0 = circle); low values may be artifacts |
| Circle_Flag | int16 | Suspiciously circular geometry flag |
| Exclude_From_Summary_Rasters | string | Whether to exclude from summary rasters |
| Shape_Length | float64 | Perimeter length in meters |

---

## Citation

**CAL FIRE datasets:**
California Department of Forestry and Fire Protection (CAL FIRE), Forest and Range Assessment Program (FRAP). Fire Perimeter and Prescribed Burn data, 2024 release. https://www.fire.ca.gov/what-we-do/fire-resource-assessment-program

**USGS dataset:**
Welty, J.L., and Jeffries, M.I., 2021, Combined wildfire datasets for the United States and certain territories, 1878-2019: U.S. Geological Survey data release, https://doi.org/10.5066/P9ZXGFY3
