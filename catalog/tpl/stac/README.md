# TPL Conservation Almanac 2024

Protected and conserved lands in the United States compiled by The Trust for Public Land (TPL).

- **Upstream source:** https://conservationalmanac.org/about/
- **Features:** 90,068 MULTIPOLYGON geometries
- **Coverage:** United States
- **License:** See https://conservationalmanac.org/about/ for terms of use

## Assets

| Asset | URL |
|-------|-----|
| GeoParquet | `https://s3-west.nrp-nautilus.io/public-tpl/conservation-almanac-2024.parquet` |
| PMTiles | `https://s3-west.nrp-nautilus.io/public-tpl/conservation-almanac-2024.pmtiles` |
| H3 Hex Parquet | `https://s3-west.nrp-nautilus.io/public-tpl/conservation-almanac-2024/hex/h0={cell}/data_0.parquet` |
| Raw source | `https://s3-west.nrp-nautilus.io/public-tpl/raw/conservation-almanac-2024.parquet` |

## Data Dictionary

| Column | Type | Description |
|--------|------|-------------|
| fid | integer | Feature ID |
| tpl_id | integer | TPL internal identifier |
| state_id | string | State FIPS code |
| state | string | State name |
| county | string | County name |
| municipality | string | Municipality name |
| site | string | Site name |
| acres | double | Area in acres |
| year | integer | Year of protection |
| date | timestamp | Date of protection |
| owner | string | Owner name |
| owner_type | string | Owner type (Federal, State, Local, Non-profit, Private, etc.) |
| manager | string | Manager name |
| manager_type | string | Manager type |
| purchase_type | string | Acquisition method (Fee, Easement, etc.) |
| easement | string | Easement holder name |
| easement_type | string | Easement type |
| access_type | string | Public access level (Open, Restricted, Closed, Unknown) |
| purpose_type | string | Conservation purpose |
| duration_type | string | Permanent or temporary protection |
| data_provider | string | Organization providing the data record |
| data_source | string | Source dataset name |
| source_date | timestamp | Date of source data |
| data_aggregator | string | Organization aggregating the data |
| comments | string | Notes |
| amount | double | Transaction amount (dollars) |
| program_id | integer | Funding program ID |
| program | string | Funding program name |
| sponsor_id | integer | Sponsor organization ID |
| sponsor | string | Sponsor organization name |
| sponsor_type | string | Sponsor organization type |
| geom | geometry | MULTIPOLYGON in WGS84 (EPSG:4326) |

## DuckDB Example

```sql
INSTALL spatial; LOAD spatial;

SELECT state, owner_type, SUM(acres) as total_acres, COUNT(*) as n_sites
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-tpl/conservation-almanac-2024.parquet')
GROUP BY state, owner_type
ORDER BY total_acres DESC
LIMIT 20;
```

H3 hex aggregation (resolution 8):

```sql
SELECT hex8, SUM(acres) as total_acres
FROM read_parquet(
  'https://s3-west.nrp-nautilus.io/public-tpl/conservation-almanac-2024/hex/h0=*/data_0.parquet',
  hive_partitioning=true
)
WHERE resolution = 8
GROUP BY hex8
ORDER BY total_acres DESC;
```

## MapLibre GL JS Example

The PMTiles `source-layer` name is `conservation-almanac-2024`.

```javascript
import * as pmtiles from 'pmtiles';

const protocol = new pmtiles.Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);

map.addSource('tpl', {
  type: 'vector',
  url: 'pmtiles://https://s3-west.nrp-nautilus.io/public-tpl/conservation-almanac-2024.pmtiles'
});

map.addLayer({
  id: 'tpl-fill',
  type: 'fill',
  source: 'tpl',
  'source-layer': 'conservation-almanac-2024',
  paint: {
    'fill-color': '#2d6a4f',
    'fill-opacity': 0.5
  }
});
```

## Citation

Trust for Public Land. Conservation Almanac (2024). https://conservationalmanac.org/

## Versioning

Future updates use the naming convention `conservation-almanac-YYYY` (e.g., `conservation-almanac-2025`).
