# IUCN Red List 2025: Global Species Richness & Range Maps

## Overview

This dataset provides global species richness and range-weighted richness maps derived from the IUCN Red List of Threatened Species (2025). The data covers five major taxonomic groups: Amphibians, Birds, Mammals, Reptiles, and Freshwater Fish.

Data is available in two cloud-optimized formats:
1. **Cloud-Optimized GeoTIFF (COG)**: For visualization and raster analysis
2. **H3 Hexagonal Tiling (Resolution 8)**: For spatial indexing and efficient analytical queries

## Data Formats & Access

**Base URL**: `https://s3-west.nrp-nautilus.io/public-iucn/`

### 1. H3 Hexagonal Parquet

Partitioned by H3 resolution 0 (h0) cells for global scalability.

**Path Pattern**: `hex/{layer_name}/h0={cell}/data_0.parquet`

**Layers available**:
- `amphibians_sr`, `amphibians_thr_sr`
- `birds_sr`, `birds_thr_sr`
- `mammals_sr`, `mammals_thr_sr`
- `reptiles_sr`, `reptiles_thr_sr`
- `fw_fish_sr`, `fw_fish_thr_sr`
- `combined_sr`, `combined_thr_sr`
- `combined_rwr`, `combined_thr_rwr`

### 2. Cloud-Optimized GeoTIFFs (COGs)

Full global rasters with internal tiling and overviews.

**Path**: `cog/richness/{Layer_Name}.tif`

## Data Dictionary and Column Descriptions

### Layer Naming Convention

- **SR**: **Species Richness** - Count of all species in the group present in the cell
- **THR_SR**: **Threatened Species Richness** - Count of species listed as Vulnerable (VU), Endangered (EN), or Critically Endangered (CR)
- **RWR**: **Range-Weighted Richness** - Sum of the inverse range sizes of species present (1 / range_area). metric where small-range (rare) species contribute more value.

### Parquet Schema

Each H3 parquet file contains the following columns:

| Column | Type | Description |
|--------|------|-------------|
| `{layer_name}` | Integer/Float | The richness value (count or weighted sum). Column name matches the layer (e.g., `amphibians_sr`). |
| `h8` | UInt64 | H3 hexagon cell ID at resolution 8. |
| `h0` | UInt64 | H3 resolution 0 parent cell ID (partition key). |

### Taxonomic Groups

| Group | Layers | Description |
|-------|--------|-------------|
| **Amphibians** | `amphibians_sr`, `amphibians_thr_sr` | Frogs, toads, salamanders, etc. |
| **Birds** | `birds_sr`, `birds_thr_sr` | Global avian ranges (BirdLife International) |
| **Mammals** | `mammals_sr`, `mammals_thr_sr` | Terrestrial and marine mammals |
| **Reptiles** | `reptiles_sr`, `reptiles_thr_sr` | Snakes, lizards, turtles, etc. |
| **Freshwater Fish** | `fw_fish_sr`, `fw_fish_thr_sr` | Inland water fish species |
| **Combined** | `combined_sr`, `combined_thr_sr` | Aggregate of all above groups |

## Data Source & Attribution

**Source**: IUCN Red List of Threatened Species
**Version**: 2025.1
**URL**: https://www.iucnredlist.org/resources/spatial-data-download

## Citation

IUCN 2025. The IUCN Red List of Threatened Species. Version 2025.1. <https://www.iucnredlist.org>

## Usage Notes

- **H3 Resolution 8**: Hexagons are approximately 0.74 km² in area.
- **Values**: Integers for SR/THR_SR (species counts). Floats for RWR.
- **Zero Values**: Cells with 0 richness are generally omitted to save space (sparse format).
