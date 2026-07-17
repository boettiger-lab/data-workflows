# GBIF colonial-provenance hex maps (geo-agent directions)

Reproduce the "who published this biodiversity data" maps from **Faxon & Chapman 2025,
*Beyond spatial bias*** (ERL [10.1088/1748-9326/add6b6](https://iopscience.iop.org/article/10.1088/1748-9326/add6b6);
code: [milliechapman/colonial-patterns-gbif](https://github.com/milliechapman/colonial-patterns-gbif))
as a hex layer in the GeoAgent Map panel.

## Method

For each hex cell, compare **where an occurrence was collected** to **where it was published**:

- **where collected** = the occurrence `countrycode` column
- **where published** = `datasetkey` joined to the GBIF dataset registry → `publishing_country`

The original study did `count(countrycode, year, datasetkey)` over the occurrences and
left-joined the GBIF dataset-registry export
(`https://api.gbif.org/v1/dataset/search/export?format=TSV`) on `datasetkey` to attach
`publishing_country`. Our hex already retains `datasetkey`, so it reproduces directly — no
re-ingest, and no need for a per-occurrence `publishingcountry` column (which GBIF's AWS
parquet does not have anyway).

We publish the registry lookup as a **sidecar parquet pinned to the 2026-06 snapshot**
(`dataset-publishers.parquet`, data-workflows #425), so the join is local and fast — no
external API call mid-query.

## Step 1 — publisher lookup (dataset → publishing country)

```sql
-- sidecar: local, pinned to the 2026-06 registry snapshot (built by gbif-2026-06-publishers.yaml)
read_parquet('s3://public-gbif/2026-06/dataset-publishers.parquet')
-- columns used: dataset_key, publishing_country
```

## Step 2 — aggregate the GBIF hex at a display resolution (h5)

```sql
WITH pub AS (
  SELECT dataset_key AS datasetkey, publishing_country
  FROM read_parquet('s3://public-gbif/2026-06/dataset-publishers.parquet')
)
SELECT g.h5,
       COUNT(*)                                                        AS n_total,
       COUNT(*) FILTER (WHERE p.publishing_country != g.countrycode)   AS n_foreign,
       COUNT(*) FILTER (WHERE p.publishing_country != g.countrycode)::DOUBLE
         / COUNT(*)                                                    AS frac_foreign
FROM read_parquet('s3://public-gbif/2026-06/hex/h0=*/data_0.parquet', hive_partitioning=true) g
JOIN pub p USING (datasetkey)
WHERE g.countrycode IS NOT NULL AND p.publishing_country IS NOT NULL
  AND NOT list_has_any(g.issue,
      ['ZERO_COORDINATE','COORDINATE_INVALID','COORDINATE_OUT_OF_RANGE','COUNTRY_COORDINATE_MISMATCH'])
GROUP BY g.h5
```

## Step 3 — render

Register the result as hex tiles (key column `h5`, value `frac_foreign`) via the
`register_hex_tiles` pattern documented in the `query` tool response, then `add_layer` with a
sequential color ramp: **0 = published locally → 1 = entirely foreign-published**.

## Variant — a specific colonial power

To reproduce their per-empire panels (e.g. Britain), map the fraction of each cell's records
published by one country:

```sql
WITH pub AS (
  SELECT dataset_key AS datasetkey, publishing_country
  FROM read_parquet('s3://public-gbif/2026-06/dataset-publishers.parquet')
)
SELECT g.h5,
       COUNT(*)                                                       AS n_total,
       COUNT(*) FILTER (WHERE p.publishing_country = 'GB')            AS n_gb,
       COUNT(*) FILTER (WHERE p.publishing_country = 'GB')::DOUBLE
         / COUNT(*)                                                   AS frac_gb
FROM read_parquet('s3://public-gbif/2026-06/hex/h0=*/data_0.parquet', hive_partitioning=true) g
JOIN pub p USING (datasetkey)
WHERE g.countrycode IS NOT NULL AND g.countrycode != p.publishing_country   -- exclude in-country
  AND NOT list_has_any(g.issue,
      ['ZERO_COORDINATE','COORDINATE_INVALID','COORDINATE_OUT_OF_RANGE','COUNTRY_COORDINATE_MISMATCH'])
GROUP BY g.h5
```

## Notes

- Resolution: `h5` is a reasonable global default; use `h4`/`h3` for a cleaner whole-globe
  view, `h6` for regional zoom-ins. All are present as parent columns on the hex.
- `countrycode` is the occurrence locality attribute (used here to match the paper). For a
  strict spatial clip to a country, semi-join on `h8` against the Overture divisions hex
  instead (see the GBIF collection description).
- The `issue` filter drops GBIF coordinate noise (a lat=-90 smear etc.); always applied
  before hex rendering.
- The publisher sidecar also carries `publishing_organization_title`, `license`, `type`, and
  `occurrence_records_count` for richer provenance queries (e.g. group by publishing org).
