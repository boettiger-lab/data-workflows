# GLEN — Boettiger Lab Geospatial Datasets

The **GLEN catalog** is a unified, navigable [STAC](https://stacspec.org) index of the
Boettiger Lab's public, cloud-optimized geospatial datasets, mirrored to Source
Cooperative for open access and long-term recoverability.

This repository is the **root of the source.coop mirror**. Its
[`catalog.json`](./catalog.json) is a STAC `Catalog` whose `child` links reach every
license-clear collection we publish here — biodiversity, conservation, census,
environmental, and infrastructure data in formats optimized for cloud-native
analysis (GeoParquet, PMTiles, H3 hex, and COG).

## Canonical source

The **canonical** catalog and data live on the National Research Platform (NRP) S3
store at `https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json`. This
source.coop copy is a **public mirror**: refreshed weekly, it exists for
discoverability and as an off-NRP recovery copy you can point a client straight at.
Each mirrored collection keeps its `root`/`parent` links pointing at the canonical NRP
root, so **navigation from this catalog is downward**: start at `catalog.json` and
descend into collections and their items.

## How to use it

Point any STAC client at the root catalog and walk the tree:

```python
import pystac
root = pystac.Catalog.from_file(
    "https://data.source.coop/cboettig/glen/catalog.json"
)
for collection in root.get_children():
    print(collection.id, "—", collection.title)
```

Individual assets (GeoParquet, PMTiles, H3 hex, COG) are queryable directly, e.g. with
DuckDB:

```sql
INSTALL spatial; LOAD spatial;
SELECT count(*) FROM read_parquet(
  'https://data.source.coop/cboettig/<collection>/<dataset>.parquet'
);
```

Each collection's `stac-collection.json` documents its own assets, schemas, and usage
(including MapLibre `source-layer` names for PMTiles).

## Scope & licensing

This catalog links **only** the collections that are both catalogued and **license-clear
to redistribute**. Collections under no-redistribution terms (e.g. WDPA / WD-OECM,
ICCA, IUCN Red List, HydroBASINS) are intentionally **absent** from this public mirror
and remain available only from the canonical NRP store under their own terms. Licenses
vary per collection — see each collection's STAC `license` field. The child list is
regenerated automatically from the mirror scope on every weekly sync, so this catalog
always reflects exactly what is currently mirrored.

## Provenance

Generated and maintained by
[boettiger-lab/data-workflows](https://github.com/boettiger-lab/data-workflows)
(`catalog/sync/source-coop/`). The catalog is refreshed by the weekly `source-sync`
job; this README is maintained in-repo.
