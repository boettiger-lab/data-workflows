# GBIF Occurrence Data & Derived Products

This dataset contains processed subsets and aggregations of the Global Biodiversity Information Facility (GBIF) occurrence data.

## Assets

### 1. GBIF Occurrences in Redlined Cities
**File:** `s3://public-gbif/redlined_cities_gbif.parquet`

A spatial join of GBIF occurrences with "Mapping Inequality" (Redlining) polygons for US cities. This dataset allows for analysis of biodiversity distribution across different HOLC grades (A, B, C, D).

**Schema:**
- **GBIF Columns:** `gbifid`, `scientificname`, `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species`, `recordedby`, `date`, `coordinateuncertaintyinmeters`, etc.
- **Redlining Columns:** `city`, `state`, `grade` (A-D), `residential`, `commercial`, `industrial`.

### 2. Taxonomic Aggregations by H3 Hexagon
**Prefix:** `s3://public-gbif/taxonomy/` (Partitioned by `h0`)

Aggregated counts of taxa within H3 resolution 0 hexagons. Useful for broad-scale biodiversity patterns.

**Schema:**
- `scientificname`, `kingdom`, `phylum`, ... `species`: Taxonomic hierarchy.
- `n`: Count of occurrences.
- `h0`: H3 resolution 0 cell ID.

### 3. Taxa List
**File:** `s3://public-gbif/taxa.parquet`

Reference list of taxa found in the dataset.

## Source

- **Producer:** Global Biodiversity Information Facility (GBIF)
- **Citations:**
    - GBIF.org (2024). GBIF Occurrence Download.
    - Nelson, R. K., et al. (2023). Mapping Inequality.

## License

- **GBIF Data:** See [GBIF Data Use Agreement](https://www.gbif.org/terms). Individual records may have specific licenses (CC0, CC-BY, CC-BY-NC).
- **Redlining Data:** CC-BY-NC-SA 4.0.
