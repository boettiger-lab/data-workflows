# iNaturalist Species Ranges & Taxonomy

This dataset contains species range maps, taxonomic information, and vernacular names from iNaturalist. It appears to be derived from the iNaturalist Geomodel or similar range estimation products.

## Assets

### 1. Species Ranges (GeoParquet)
**Prefix:** `s3://public-inat/taxon/`
Partitioned by `iconic_taxon_name` (e.g., Animalia, Plantae, Insecta).

**Schema:**
- `taxon_id`: iNaturalist Taxon ID
- `scientificName`: Scientific Name
- `geom`: Geometry (likely modeled range polygons)
- `geomodel_version`: Version of the range model
- `kingdom`, `phylum`, `class`,...: Taxonomic hierarchy

### 2. Range Hexagons (H4)
**File:** `s3://public-inat/ranges.parquet`
Species ranges rasterized/indexed to H3 resolution 4 hexagons.

**Schema:**
- `taxon_id`: iNaturalist Taxon ID
- `name`: Species Name
- `h4`: H3 resolution 4 index
- `iconic_taxon_name`: High-level group

### 3. Taxonomy & Common Names
**Files:**
- `s3://public-inat/taxonomy/taxa.parquet`: Core taxonomy table.
- `s3://public-inat/taxonomy/taxa_and_common.parquet`: Taxonomy with common names.
- `s3://public-inat/taxonomy/vernacular/*.csv`: Common names in hundreds of languages.

## Source

- **Producer:** iNaturalist
- **Link:** [iNaturalist.org](https://www.inaturalist.org/)
- **Note:** This dataset likely represents the "Geomodel" or expert range maps used by iNaturalist for automated identification priors.

## License

- **iNaturalist Data:** See [iNaturalist Terms of Service](https://www.inaturalist.org/pages/terms).
- **Open Data:** Many iNaturalist datasets are CC0 or CC-BY, but check specific taxon licensing.
