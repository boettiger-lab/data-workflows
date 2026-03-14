# GBIF Occurrence Data & Derived Products

Processed GBIF occurrence data hexed at H3 resolutions 0-10, plus derived products.

GBIF releases new snapshots periodically. Releases are versioned by `year-month` (e.g., `2025-06`) so multiple versions can coexist in the bucket during transitions. **Always use the most recent release for new work.**

## Current Release: 2025-06

**Path:** `s3://public-gbif/2025-06/hex/`

Global GBIF occurrences partitioned by H3 resolution 0 cell. 94 non-empty h0 partitions covering the globe.

### Schema

- Taxonomic columns: `gbifid`, `datasetkey`, `occurrenceid`, `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species`, `infraspecificepithet`, `taxonrank`, `scientificname`, `verbatimscientificname`, `verbatimscientificnameauthorship`
- Spatial/occurrence columns: `countrycode`, `locality`, `stateprovince`, `occurrencestatus`, `individualcount`, `decimallatitude`, `decimallongitude`, `coordinateuncertaintyinmeters`, `coordinateprecision`, `elevation`, `depth`, `eventdate`, `day`, `month`, `year`, `taxonkey`, `specieskey`, `basisofrecord`, `institutioncode`, `collectioncode`, `catalognumber`, `recordnumber`, `identifiedby`, `dateidentified`, `license`, `rightsholder`, `recordedby`, `typestatus`, `establishmentmeans`, `lastinterpreted`, `mediatype`, `issue`, `geom`
- H3 hex columns: `h0` (VARCHAR, partition key), `h1`-`h10` (UBIGINT)

### DuckDB Example

```sql
INSTALL h3 FROM community; LOAD h3;
INSTALL httpfs; LOAD httpfs;
SET s3_endpoint = 's3-west.nrp-nautilus.io';
SET s3_url_style = 'path';

-- Count occurrences by family in a single h0 cell
SELECT family, COUNT(*) AS n
FROM read_parquet('s3://public-gbif/2025-06/hex/h0=8009fffffffffff/part/*.parquet')
GROUP BY family
ORDER BY n DESC
LIMIT 20;
```

## Deprecated: Legacy Hex (pre-2025)

**Path:** `s3://public-gbif/hex/` — **DEPRECATED, do not use for new work.**

This is the original hex partition with all h0-h11 columns stored as VARCHAR strings. It is retained only for backward compatibility with existing applications. It will be removed once no active apps depend on it. See [GitHub issue](https://github.com/boettiger-lab/data-workflows/issues) for tracking.

## Other Assets

### GBIF Occurrences in Redlined Cities
**File:** `s3://public-gbif/redlined_cities_gbif.parquet`

Spatial join of GBIF occurrences with "Mapping Inequality" (Redlining) polygons for US cities.

**Schema:** `gbifid`, `scientificname`, `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species`, `recordedby`, `date`, `coordinateuncertaintyinmeters`, `city`, `state`, `grade` (A-D), `residential`, `commercial`, `industrial`

### Taxonomic Aggregations by H3 Hexagon
**Prefix:** `s3://public-gbif/taxonomy/` (partitioned by `h0`)

Aggregated counts of taxa within H3 resolution 0 hexagons.

**Schema:** `scientificname`, `kingdom`, `phylum`, ... `species`, `n` (count), `h0`

### Taxa List
**File:** `s3://public-gbif/taxa.parquet`

Reference list of all taxa found in the dataset.

## Source & Citation

- **Producer:** Global Biodiversity Information Facility (GBIF)
- GBIF.org (2025). GBIF Occurrence Download. <https://www.gbif.org/>
- Nelson, R. K., et al. (2023). Mapping Inequality. (for redlined cities asset)

## License

- **GBIF Data:** See [GBIF Data Use Agreement](https://www.gbif.org/terms). Individual records may have specific licenses (CC0, CC-BY, CC-BY-NC).
- **Redlining Data:** CC-BY-NC-SA 4.0.
