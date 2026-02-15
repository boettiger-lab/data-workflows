# Global Wetlands Data

This collection hosts three distinct wetland datasets, providing global and regional coverage of wetland distribution, types, and protection status.

## 1. Ramsar Sites of International Importance
**Source:** [Ramsar Sites Information Service](https://rsis.ramsar.org/)  
**Type:** Vector (Global)  
**Description:** Polygons of wetlands designated as internally important under the Ramsar Convention.

### Assets
- **GeoParquet:** `ramsar/ramsar_wetlands.parquet` (Full dataset)
- **PMTiles:** `ramsar/ramsar_wetlands.pmtiles` (Web-optimized tiles, Layer: `ramsar`)
- **H3 Hexagons:** `ramsar/hex/` (Partitioned by H3 resolution 0)

### Schema (Ramsar)
| Column | Type | Description |
|--------|------|-------------|
| `ramsarid` | Integer | Unique Site ID |
| `Site name` | String | Official Name |
| `Country` | String | Country Name |
| `Area (ha)` | Float | Official Area in Hectares |
| `Wetland Type` | String | Classification Code |

---

## 2. Global Lakes and Wetlands Database (GLWD)
**Source:** [World Wildlife Fund / GWSP](https://www.worldwildlife.org/pages/global-lakes-and-wetlands-database)  
**Type:** Raster & H3 Index (Global)  
**Description:** Level 3 product combining lakes, reservoirs, rivers, and different wetland types into a global raster map.

### Assets
- **Cloud-Optimized GeoTIFF (COG):** `GLWD_v2_0/GLWD_v2_0_area_ha_x10_cog.tif`  
  *Pixel value = Wetland Area in Hectares * 10*
- **H3 Hexagons:** `glwd/hex/` (Partitioned by H3 resolution 0)

---

## 3. National Wetlands Inventory (NWI)
**Source:** [U.S. Fish & Wildlife Service](https://www.fws.gov/program/national-wetlands-inventory)  
**Type:** Vector/H3 Index (USA Only)  
**Description:** Detailed wetland classification for the United States. Due to the massive size of the original vector data, this dataset is primarily served here as an H3 spatial index.

### Assets
- **H3 Hexagons:** `nwi/hex/` (Partitioned by H3 resolution 0)

### Schema (NWI Hex)
| Column | Type | Description |
|--------|------|-------------|
| `h3_index` | String | H3 Cell ID |
| `measure` | Double | Area or Count (verify in data) |
| `...` | ... | (Schema varies, check parquet footer) |

## Access
All data is hosted on the NRP Nautilus S3 bucket `public-wetlands`.

```python
import pandas as pd
# Example: Read NWI Hex Data
df = pd.read_parquet("s3://public-wetlands/nwi/hex/h0=8027fffffffffff/data_0.parquet", 
                     storage_options={"anon": True, "client_kwargs": {"endpoint_url": "https://s3-west.nrp-nautilus.io"}})
```
