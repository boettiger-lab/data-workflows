# WWF Terrestrial Ecoregions of the World

**847 global terrestrial ecoregions** grouped into 14 biomes and 9 biogeographic realms, with Nature Needs Half (NNH) protection status for each.

- **Source**: World Wildlife Fund / Dinerstein et al. (2017)
- **License**: CC-BY 4.0
- **DOI**: [10.1093/biosci/bix014](https://doi.org/10.1093/biosci/bix014)
- **Temporal coverage**: Based on Olson et al. (2001), updated 2017

## Files

| File | Format | Description |
|------|--------|-------------|
| `ecoregion.parquet` | GeoParquet | 847 ecoregion polygons |
| `ecoregion.pmtiles` | PMTiles | Web map tiles (source-layer: `ecoregion`) |
| `ecoregion/hex/` | H3 Parquet (res 8) | Hex-indexed, partitioned by h0 |
| `ecoregions.gdb/` | ESRI GDB | Original source geodatabase |

## Data Dictionary

| Column | Type | Description |
|--------|------|-------------|
| `ECO_NAME` | string | Ecoregion name (unique) |
| `ECO_ID` | float | Unique numeric ecoregion ID |
| `BIOME_NUM` | float | Biome code (1–14) |
| `BIOME_NAME` | string | Biome type (see below) |
| `REALM` | string | Biogeographic realm (see below) |
| `ECO_BIOME_` | string | Combined ecoregion–biome code |
| `NNH` | float | Nature Needs Half code (1–4) |
| `NNH_NAME` | string | NNH category (see below) |
| `COLOR` | string | Hex color for ecoregion display |
| `COLOR_BIO` | string | Hex color for biome display |
| `COLOR_NNH` | string | Hex color for NNH display |
| `LICENSE` | string | Always "CC-BY 4.0" |
| `SHAPE_Area` | float | Area in degrees² (use geometry for real area) |
| `SHAPE` | bytes | WKB geometry, EPSG:4326, MultiPolygon |
| `bbox` | struct | Bounding box (xmin, ymin, xmax, ymax) |
| `h8` | uint64 | H3 res-8 cell (hex parquet only, INTEGER encoding) |
| `h0` | int64 | H3 res-0 partition key (hex parquet only) |

### Biomes (BIOME_NAME)

| Code | Name | Count |
|------|------|-------|
| 1 | Tropical & Subtropical Moist Broadleaf Forests | 230 |
| 2 | Tropical & Subtropical Dry Broadleaf Forests | 56 |
| 3 | Tropical & Subtropical Coniferous Forests | 15 |
| 4 | Temperate Broadleaf & Mixed Forests | 83 |
| 5 | Temperate Conifer Forests | 47 |
| 6 | Boreal Forests/Taiga | 26 |
| 7 | Tropical & Subtropical Grasslands, Savannas & Shrublands | 58 |
| 8 | Temperate Grasslands, Savannas & Shrublands | 48 |
| 9 | Flooded Grasslands & Savannas | 25 |
| 10 | Montane Grasslands & Shrublands | 46 |
| 11 | Tundra | 51 |
| 12 | Mediterranean Forests, Woodlands & Scrub | 40 |
| 13 | Deserts & Xeric Shrublands | 102 |
| 14 | Mangroves | 19 |

### Realms (REALM)

| Realm | Count |
|-------|-------|
| Palearctic | 205 |
| Neotropic | 179 |
| Afrotropic | 116 |
| Nearctic | 115 |
| Indomalayan | 106 |
| Australasia | 83 |
| Oceania | 24 |
| Antarctica | 18 |

### Nature Needs Half (NNH_NAME)

| Code | Category | Count | Meaning |
|------|----------|-------|---------|
| 1 | Half Protected | 98 | ≥50% of ecoregion currently under formal protection |
| 2 | Nature Could Reach Half Protected | 313 | <50% protected but enough intact habitat remains to reach 50% |
| 3 | Nature Could Recover | 228 | Insufficient intact habitat, but restoration could achieve 50% |
| 4 | Nature Imperiled | 207 | Heavily converted; reaching 50% protection would require major restoration |

## Usage Examples

### DuckDB

```sql
INSTALL httpfs; LOAD httpfs;
SET s3_endpoint='s3-west.nrp-nautilus.io';
SET s3_url_style='path';

-- Count ecoregions per biome
SELECT BIOME_NAME, COUNT(*) as n_ecoregions
FROM read_parquet('s3://public-ecoregion/ecoregion.parquet')
GROUP BY BIOME_NAME
ORDER BY n_ecoregions DESC;

-- Join hex parquet with ecoregion attributes
SELECT h8, ECO_NAME, BIOME_NAME, NNH_NAME
FROM read_parquet('s3://public-ecoregion/ecoregion/hex/**/*.parquet')
LIMIT 100;
```

### MapLibre GL JS

```javascript
const map = new maplibregl.Map({ /* ... */ });

map.on('load', () => {
  map.addSource('ecoregion', {
    type: 'vector',
    url: 'pmtiles://https://s3-west.nrp-nautilus.io/public-ecoregion/ecoregion.pmtiles'
  });

  map.addLayer({
    id: 'ecoregion-fill',
    type: 'fill',
    source: 'ecoregion',
    'source-layer': 'ecoregion',   // always 'ecoregion' for this dataset
    paint: {
      'fill-color': ['get', 'COLOR'],
      'fill-opacity': 0.6
    }
  });

  map.addLayer({
    id: 'ecoregion-outline',
    type: 'line',
    source: 'ecoregion',
    'source-layer': 'ecoregion',
    paint: {
      'line-color': '#333',
      'line-width': 0.5
    }
  });
});
```

## Citation

Dinerstein, E., et al. (2017). An Ecoregion-Based Approach to Protecting Half the Terrestrial Realm. *BioScience*, 67(6), 534–545. https://doi.org/10.1093/biosci/bix014

Original classification:
Olson, D. M., et al. (2001). Terrestrial Ecoregions of the World: A New Map of Life on Earth. *BioScience*, 51(11), 933–938.
