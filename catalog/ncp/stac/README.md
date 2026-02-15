# Nature's Contributions to People (NCP)

This dataset provides global maps of Nature's Contributions to People (NCP), specifically focusing on biodiversity and natural habitat indicators. It is derived from the global modeling work by Chaplin-Kramer et al. (2019).

## Source

- **Publication:** Chaplin-Kramer, R., et al. (2019). Global modeling of nature's contributions to people. *Science*, 366(6462), 255-258. [DOI: 10.1126/science.awx9597](https://doi.org/10.1126/science.awx9597)
- **Project:** Natural Capital Project (Stanford University)

## Data Format

The dataset is available in the following formats:
- **Cloud-Optimized GeoTIFF (COG):**
    - `s3://public-ncp/NCP_biod_nathab_cog.tif` (Biodiversity & Natural Habitat)
    - `s3://public-ncp/NCP_only_cog.tif` (NCP Aggregate/Index)
- **H3 Hexagons:** `s3://public-ncp/preprocess/hex/` (Partitioned by h0)

## Layers

| File / Layer | Description |
|--------------|-------------|
| `ncp_biod_nathab` | Composite indicator of **Biodiversity** and **Natural Habitat** supporting NCPs. Includes metrics related to species richness and habitat extent. |
| `ncp_only` | Aggregated **Nature's Contribution to People** index. Likely represents the realized service flow (population-weighted or demand-adjusted). |

*Note: Precise variable definitions are inferred from the Chaplin-Kramer et al. (2019) framework, which typically models 3 key NCPs: Water Quality Regulation, Coastal Risk Reduction, and Crop Pollination.*

## Citation

Chaplin-Kramer, R., Sharp, R. P., Weil, C., Bennett, E. M., Pascual, U., Arkema, K. K., ... & Daily, G. C. (2019). Global modeling of nature's contributions to people. *Science*, 366(6462), 255-258.
