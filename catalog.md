---
title: The catalog
subtitle: Proven at scale on real, open datasets
---

The pipeline produces a growing, public catalog of cloud-native datasets, each
described by STAC and queryable without download. The geospatial collections below
are the proven track record — the same machinery now extends to other domains.

[**Browse the full catalog in STAC Browser →**](https://radiantearth.github.io/stac-browser/#/external/s3-west.nrp-nautilus.io/public-data/stac/catalog.json)

## What's published

Datasets are hosted on [NRP Nautilus](https://nrp.ai) object storage and span
biodiversity, protected areas, census geographies, carbon, and earth-observation
rasters — produced in partnership with **NASA**, **The Nature Conservancy**, and
**California Fish & Wildlife**, among others.

Each collection ships with:

- **Cloud-native data** — columnar Parquet for tables, COG/Zarr for rasters and arrays.
- **Derived spatial indexes** — for fast joins and aggregation across datasets.
- **STAC metadata** — schemas, asset roles, units, coded-value definitions, and provenance.

## Query without downloading

Because outputs are cloud-native and streamed by range-request, you can query a
multi-gigabyte dataset directly from a notebook — pulling only the rows and columns a
query touches:

```python
import duckdb

con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs;")
con.execute("""
    SELECT COUNT(*)
    FROM read_parquet('https://s3-west.nrp-nautilus.io/<bucket>/<dataset>.parquet')
""").fetchall()
```

An AI agent connected through [`mcp-data-server`](ecosystem.md) does the same — but
reads the STAC metadata first, so it knows which dataset to open and what each column
means before it writes the query.
