import json
M = json.load(open('/tmp/obis_measurements.json'))
readme = f"""# OBIS Marine Occurrence Records (global, H3 resolution 8)

Global marine species occurrence records from the [Ocean Biodiversity Information System
(OBIS)](https://obis.org), indexed to H3 resolution 8.

- **Records:** {M['total']:,}
- **Source datasets:** {M['datasets']:,}
- **Extent:** global, unclipped
- **Native H3 resolution:** 8 (partition key: resolution 0)
- **Licence:** CC BY-NC 4.0 (non-commercial, attribution required)
- **Accessed:** 2026-09-09

## What this is, and how it differs from GBIF

OBIS is the marine counterpart to GBIF. It aggregates occurrence records from thousands of marine
datasets, matches every name against the World Register of Marine Species (WoRMS), and adds its own
quality control and environmental context.

This catalog also carries GBIF occurrences, and a subset of those is published through the OBIS
network, but the two are not the same data:

| | OBIS (this collection) | GBIF (`gbif-derived`) |
|---|---|---|
| Taxonomy | WoRMS, with `aphiaid` | GBIF Backbone |
| Source datasets | {M['datasets']:,} | 3,522 in the GBIF OBIS network |
| Quality control | OBIS pipeline, `flags` column | GBIF `issue` column |
| Environment flags | `marine`, `brackish` from WoRMS | none |
| Per-record context | depth, sea floor depth, sea surface temperature and salinity | none |
| Absence records | flagged and excluded here | largely absent |
| Native H3 resolution | 8 | 10 |

The dataset identifiers come from different id spaces and do not join. Compare the two spatially,
through their shared H3 resolution 8 cells.

Records that failed OBIS quality control, absence records, and records without a usable coordinate
are excluded from this collection.

## Query with DuckDB

```sql
INSTALL httpfs; LOAD httpfs;

-- occurrence density and species richness per resolution 8 cell
SELECT h8, COUNT(*) AS occurrences, COUNT(DISTINCT species) AS species
FROM read_parquet('s3://public-obis/2026-09-09/hex/h0=*/data_0.parquet', hive_partitioning=true)
WHERE marine
GROUP BY h8;
```

Over the public HTTPS endpoint:

```sql
SELECT species, COUNT(*) AS n
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-obis/2026-09-09/hex/h0=*/data_0.parquet',
                  hive_partitioning=true)
WHERE species IS NOT NULL
GROUP BY species ORDER BY n DESC LIMIT 20;
```

Reading a single resolution 0 partition is far cheaper than scanning the whole collection:

```sql
SELECT "class", COUNT(*) AS n
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-obis/2026-09-09/hex/h0=576495936675512319/data_0.parquet')
GROUP BY "class" ORDER BY n DESC;
```

Note `order` and `class` are reserved words in SQL; quote them.

## Comparing against GBIF at resolution 8

```sql
WITH obis AS (
  SELECT h8, COUNT(*) AS n_obis
  FROM read_parquet('s3://public-obis/2026-09-09/hex/h0=*/data_0.parquet', hive_partitioning=true)
  GROUP BY h8
),
gbif AS (
  SELECT g.h8, COUNT(*) AS n_gbif
  FROM read_parquet('s3://public-gbif/2026-06/hex/h0=*/data_0.parquet', hive_partitioning=true) g
  SEMI JOIN read_parquet('s3://public-gbif/2026-06/obis-datasets.parquet') o USING (datasetkey)
  GROUP BY g.h8
)
SELECT * FROM obis FULL OUTER JOIN gbif USING (h8);
```

## Licensing

The aggregate is **CC BY-NC 4.0**: non-commercial use, attribution required. This is more
restrictive than most of this catalog.

Individual source datasets are licensed CC0, CC BY or CC BY-NC. Per-dataset licence and citation
details are at `s3://public-obis/raw/licenses.tsv`.

> Ocean Biodiversity Information System (OBIS). OBIS Occurrence Data. Intergovernmental
> Oceanographic Commission of UNESCO. https://obis.org. Accessed 2026-09-09.

## Provenance

OBIS publishes this export as a **rolling dataset** at `s3://obis-open-data/occurrence/`,
overwritten in place, with **no edition or version label**. The date in this collection's path is
the date we read it, not an OBIS release.

The raw source as read on that date is staged at `s3://public-obis/raw/`, with
`s3://public-obis/raw/MANIFEST.txt` recording {M['raw_files']:,} files totalling
{M['raw_bytes']:,} bytes and a per-file MD5 checksum. That staged copy and its manifest are the
provenance for this collection, because the upstream path no longer holds the same bytes.

- Landing page: https://obis.org/data/access/
- Export documentation: https://github.com/iobis/obis-open-data

## Build

Scripts and manifests: `catalog/obis/2026-09-09/` in `boettiger-lab/data-workflows`.
Tracked in [#660](https://github.com/boettiger-lab/data-workflows/issues/660).
"""
open('/tmp/README.md','w').write(readme)
print("wrote /tmp/README.md")
