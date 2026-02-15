# Irrecoverable Earth: Global Carbon Reserves

## Overview

This dataset maps global "irrecoverable carbon" — carbon stocks that, if lost, cannot be recovered by 2050, making their conservation critical for meeting climate goals. The data also includes "manageable carbon" (stocks that can be influenced by human management) and "vulnerable carbon" (total stocks vulnerable to release upon land conversion).

Irrecoverable carbon represents the intersection of carbon stocks with high climate mitigation value and ecosystems facing significant threats. These are the carbon reserves we cannot afford to lose if we are to achieve climate stabilization targets.

## Source & Attribution

**Source**: Conservation International  
**Project Page**: https://www.conservation.org/irrecoverable-carbon  
**Original Data**: https://doi.org/10.5281/zenodo.4091029

**Citation**: Noon, M.L., Goldstein, A., Ledezma, J.C. et al. Mapping the irrecoverable carbon in Earth's ecosystems. *Nat Sustain* **5**, 37–46 (2022). https://doi.org/10.1038/s41893-021-00803-6

## Data Formats & Access

**Base URL**: `https://s3-west.nrp-nautilus.io/public-carbon/`

### 1. Cloud-Optimized GeoTIFFs (COGs)

Global rasters at ~300m resolution for 2010 and 2018, covering three carbon categories:

**Path Pattern**: `cogs/{category}_c_{component}_{year}.tif`

**Categories**:
- **Irrecoverable Carbon**: Stocks that cannot recover by 2050 if lost
- **Manageable Carbon**: Stocks that can be influenced by human management
- **Vulnerable Carbon**: Total stocks at risk from land conversion

**Components** (for each category):
- `biomass`: Above and belowground biomass carbon
- `soil`: Soil organic carbon
- `total`: Combined biomass + soil

**Years**: 2010, 2018

### 2. H3 Hexagonal Parquet

Aggregated carbon stocks partitioned by H3 resolution 0 (h0) cells for global analysis at Resolution 8 (~0.74 km²).

**Datasets**:
- **Irrecoverable Carbon**: `irrecoverable-carbon/hex//h0={cell}/data_0.parquet`
- **Vulnerable Carbon**: `vulnerable-carbon/hex/h0={cell}/data_0.parquet`

*Note: The `irrecoverable-carbon` path contains a double slash `//` after `hex` due to object key naming.*

## Data Dictionary

### Hexagonal Parquet Schema

| Column | Type | Description |
|--------|------|-------------|
| `carbon` | Float/Integer | Total carbon stock in the hex cell (Mg C). |
| `h8` | String | H3 hexagon cell ID at resolution 8. |
| `h0` | String | H3 resolution 0 parent cell ID (partition key). |

- **Irrecoverable Carbon**: `carbon` column is **Float**. Represents total irrecoverable carbon (Mg C).
- **Vulnerable Carbon**: `carbon` column is **Integer**. Represents total vulnerable carbon (Mg C).

### Terminology

- **Irrecoverable Carbon**: Ecosystem carbon that, if lost, could not be recovered by 2050 through natural regeneration or restoration.
- **Vulnerable Carbon**: Total carbon stocks (biomass + soil) that are vulnerable to release upon land conversion.
- **Manageable Carbon**: Carbon stocks in ecosystems that can be managed by human activities (e.g., forestry, agriculture).

### Technical Notes

- **Units**: Megagrams of Carbon (Mg C). One Mg = One Metric Ton.
- **Resolution**: Original data at ~300m, aggregated to H3 resolution 8 for hexagonal format.
- **Coverage**: Global terrestrial ecosystems.

## Background & Methodology

The concept of "irrecoverable carbon" was developed to identify carbon stocks where prevention of loss is more effective than restoration. These areas represent the overlap between:

1. **High carbon density** - Significant climate mitigation value
2. **Low recoverability** - Cannot regenerate by 2050
3. **High threat** - Significant risk of conversion

The dataset integrates:
- Biomass data from multiple sources (Spawn et al., Walker et al.)
- Soil carbon from SoilGrids250m
- Ecosystem vulnerability assessments
- Recovery potential modeling

This spatial prioritization helps identify where conservation efforts will have the greatest impact on climate mitigation.
