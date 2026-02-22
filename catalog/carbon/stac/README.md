# Irrecoverable Earth: Global Carbon Reserves

## Overview

This dataset maps global "irrecoverable carbon" — carbon stocks that, if lost, cannot be recovered by 2050, making their conservation critical for meeting climate goals. The data also includes "manageable carbon" (stocks that can be influenced by human management) and "vulnerable carbon" (total stocks vulnerable to release upon land conversion).

This collection contains **two releases**:
- **v1 (2021 release)**: 2010 and 2018 data with biomass, soil, and total components (Zenodo 4091029)
- **v2 (2025 update)**: 2010, 2018, 2022, 2023, and 2024 data (total only); includes corrections to the 2018 baseline (Zenodo 17645053)

## Source & Attribution

**Source**: Conservation International  
**Project Page**: https://www.conservation.org/irrecoverable-carbon  

**v1 Data**: https://doi.org/10.5281/zenodo.4091029  
**v2 Data (2025 update)**: https://doi.org/10.5281/zenodo.17645053

**Citation**: Noon, M.L., Goldstein, A., Ledezma, J.C. et al. Mapping the irrecoverable carbon in Earth's ecosystems. *Nat Sustain* **5**, 37–46 (2022). https://doi.org/10.1038/s41893-021-00803-6

**License**: Creative Commons Attribution Non Commercial 4.0 International (CC BY-NC 4.0)

**Key findings from 2025 update**: 5.4% (7.4 Gt) of Earth's irrecoverable carbon has been lost between 2018–2024; global total is now 128.0 Gt.

---

## Data Formats & Access

**Base URL**: `https://s3-west.nrp-nautilus.io/public-carbon/`

---

## v2 Data (2025 Release — Zenodo 17645053)

Covers years **2010, 2018, 2022, 2023, 2024** for total carbon only. The 2018 baseline includes corrections to boreal grassland/shrubland estimates and updated coastal ecosystem extents. Note: irrecoverable carbon is available for all 5 years; vulnerable and manageable are available for 2010, 2018, and 2024 only.

### v2 Cloud-Optimized GeoTIFFs

**Path Pattern**: `v2/cogs/{category}_c_total_{year}.tif`

| File | Year | Description |
|------|------|-------------|
| `v2/cogs/irrecoverable_c_total_2024.tif` | 2024 | Irrecoverable carbon total (corrected baseline) |
| `v2/cogs/irrecoverable_c_total_2023.tif` | 2023 | Irrecoverable carbon total |
| `v2/cogs/irrecoverable_c_total_2022.tif` | 2022 | Irrecoverable carbon total |
| `v2/cogs/irrecoverable_c_total_2018.tif` | 2018 | Irrecoverable carbon total (corrected baseline) |
| `v2/cogs/irrecoverable_c_total_2010.tif` | 2010 | ⚠️ **Not available** — source file has corrupt TIFF IFD (Zenodo upstream issue) |
| `v2/cogs/vulnerable_c_total_2024.tif` | 2024 | Vulnerable carbon total |
| `v2/cogs/vulnerable_c_total_2018.tif` | 2018 | Vulnerable carbon total |
| `v2/cogs/vulnerable_c_total_2010.tif` | 2010 | Vulnerable carbon total |
| `v2/cogs/manageable_c_total_2024.tif` | 2024 | Manageable carbon total |
| `v2/cogs/manageable_c_total_2018.tif` | 2018 | Manageable carbon total |
| `v2/cogs/manageable_c_total_2010.tif` | 2010 | Manageable carbon total |

All v2 COGs are compressed with ZSTD and use GoogleMapsCompatible tiling.

### v2 H3 Hexagonal Parquet

Aggregated carbon stocks at H3 resolution 8 (~0.74 km²), partitioned by H3 resolution 0 (h0) cells.

**Path Pattern**: `v2/{dataset-name}/hex/h0={cell}/data_0.parquet`

| Dataset | Path prefix |
|---------|-------------|
| Irrecoverable carbon 2024 | `v2/irrecoverable-carbon-2024/hex/` |
| Irrecoverable carbon 2023 | `v2/irrecoverable-carbon-2023/hex/` |
| Irrecoverable carbon 2022 | `v2/irrecoverable-carbon-2022/hex/` |
| Irrecoverable carbon 2018 | `v2/irrecoverable-carbon-2018/hex/` |
| Vulnerable carbon 2024    | `v2/vulnerable-carbon-2024/hex/` |
| Vulnerable carbon 2018    | `v2/vulnerable-carbon-2018/hex/` |
| Vulnerable carbon 2010    | `v2/vulnerable-carbon-2010/hex/` |
| Manageable carbon 2024    | `v2/manageable-carbon-2024/hex/` |
| Manageable carbon 2018    | `v2/manageable-carbon-2018/hex/` |
| Manageable carbon 2010    | `v2/manageable-carbon-2010/hex/` |

### v2 Usage Examples

**DuckDB — compare irrecoverable carbon across years:**
```sql
SELECT
    year,
    SUM(carbon) / 1e9 AS total_Gt_C
FROM (
    SELECT 2024 AS year, carbon FROM read_parquet('https://s3-west.nrp-nautilus.io/public-carbon/v2/irrecoverable-carbon-2024/hex/**/*.parquet')
    UNION ALL
    SELECT 2023 AS year, carbon FROM read_parquet('https://s3-west.nrp-nautilus.io/public-carbon/v2/irrecoverable-carbon-2023/hex/**/*.parquet')
    UNION ALL
    SELECT 2022 AS year, carbon FROM read_parquet('https://s3-west.nrp-nautilus.io/public-carbon/v2/irrecoverable-carbon-2022/hex/**/*.parquet')
    UNION ALL
    SELECT 2018 AS year, carbon FROM read_parquet('https://s3-west.nrp-nautilus.io/public-carbon/v2/irrecoverable-carbon-2018/hex/**/*.parquet')
)
GROUP BY year ORDER BY year;
```

---

## v1 Data (2021 Release — Zenodo 4091029)

Covers years **2010 and 2018** with biomass, soil, and total components separately.

### v1 Cloud-Optimized GeoTIFFs

**Path Pattern**: `cogs/{category}_c_{component}_{year}.tif`

**Categories**: `irrecoverable`, `manageable`, `vulnerable`  
**Components**: `biomass`, `soil`, `total`  
**Years**: `2010`, `2018`

Examples:
- `cogs/irrecoverable_c_total_2018.tif`
- `cogs/manageable_c_biomass_2010.tif`
- `cogs/vulnerable_c_soil_2018.tif`

### v1 H3 Hexagonal Parquet

| Dataset | Path |
|---------|------|
| Irrecoverable carbon (total 2018) | `irrecoverable-carbon/hex/h0={cell}/data_0.parquet` |
| Vulnerable carbon (total 2018)    | `vulnerable-carbon/hex/h0={cell}/data_0.parquet` |

---

## Data Dictionary

### Hexagonal Parquet Schema

| Column | Type | Description |
|--------|------|-------------|
| `carbon` | Float | Total carbon stock in the hex cell (Mg C) |
| `h8` | String | H3 hexagon cell ID at resolution 8 |
| `h0` | String | H3 resolution 0 parent cell ID (partition key) |

**Units**: Megagrams of Carbon (Mg C). One Mg = 1 metric ton.

### Terminology

- **Irrecoverable Carbon**: Ecosystem carbon that, if lost, could not be recovered by 2050 through natural regeneration or restoration.
- **Vulnerable Carbon**: Total carbon stocks (biomass + soil) that are vulnerable to release upon land conversion.
- **Manageable Carbon**: Carbon stocks in ecosystems that can be managed by human activities (forestry, agriculture, conservation).

### v2 Corrections vs v1

The v2 (2025) update includes:
1. **Bug fix**: Corrected overestimation of irrecoverable carbon in boreal grasslands and shrublands in Asia (reduces 2018 total from 139.1 Gt to 135.3 Gt)
2. **Updated coastal extents**: Global Mangrove Watch 2022 and UNEP-WCMC 2022 for seagrasses and salt marshes
3. **Annual tracking**: New years 2022, 2023, 2024 for irrecoverable; 2024 for vulnerable and manageable
4. **Updated protection status**: Uses WDPA data through January 2023–October 2025

---

## Background & Methodology

The concept of "irrecoverable carbon" was developed to identify carbon stocks where prevention of loss is more effective than restoration. These areas represent the overlap between:

1. **High carbon density** — Significant climate mitigation value
2. **Low recoverability** — Cannot regenerate by 2050
3. **High threat** — Significant risk of conversion

The dataset integrates:
- Biomass data from multiple sources (Spawn et al., Walker et al.)
- Soil carbon from SoilGrids250m
- Ecosystem vulnerability assessments
- ESA CCI Land Cover for annual conversion tracking (v2 only)
