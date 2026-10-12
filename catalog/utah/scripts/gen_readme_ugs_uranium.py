#!/usr/bin/env python3
"""README for public-utah/ugs-uranium (#708). Writes /tmp/ugs-uranium-README.md."""

README = r"""# Utah Geological Survey — Uranium Districts, Areas, Past Producers, Permitted Mines & Mills

Utah's uranium geology and mining history from the Utah Geological Survey (UGS) and the Utah
Division of Oil, Gas and Mining (UDOGM), distributed through the Utah Geospatial Resource
Center (UGRC/SGID). Utah statewide.

| layer | features | geometry | what it is |
|---|---|---|---|
| `districts` | 58 | polygon | Uranium districts with the survey's uranium potential class |
| `area-boundaries` | 15 | polygon | Broad Colorado Plateau uranium areas (UGS Map 215) |
| `past-producers` | 748 | point | Past uranium producers, full USGS CRIB record |
| `permitted-mines` | 25 | point | Permitted uranium / uranium-vanadium mines |
| `mills` | 2 | point | Utah's two uranium processing mills |

Each layer is published as GeoParquet, PMTiles and an H3 hex parquet at native resolution 8
(parent `h0`).

STAC: <https://s3-west.nrp-nautilus.io/public-utah/ugs-uranium/stac-collection.json>

## Read it with DuckDB

```sql
INSTALL spatial; LOAD spatial;
INSTALL httpfs;  LOAD httpfs;

-- Uranium potential by district
SELECT POTENTIAL, COUNT(*) AS districts
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-utah/ugs-uranium/districts.parquet')
GROUP BY 1 ORDER BY districts DESC;

-- Past producers by county (722 of the 748 carry attributes)
SELECT COUNTY, COUNT(*) AS sites
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-utah/ugs-uranium/past-producers.parquet')
WHERE COUNTY IS NOT NULL
GROUP BY 1 ORDER BY sites DESC;

-- The two mills
SELECT NAME, OPERATOR, COUNTY
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-utah/ugs-uranium/mills.parquet');
```

The hex assets are hive-partitioned on `h0`:

```sql
SELECT COUNT(DISTINCT _cng_fid) AS districts, COUNT(DISTINCT h8) AS cells
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-utah/ugs-uranium/districts/hex/h0=*/data_0.parquet');
```

## Show it on a map

Each layer is its own PMTiles archive. The MapLibre `source-layer` is the layer name:
`districts`, `area-boundaries`, `past-producers`, `permitted-mines`, `mills`.

```js
import maplibregl from 'maplibre-gl';
import * as pmtiles from 'pmtiles';

maplibregl.addProtocol('pmtiles', new pmtiles.Protocol().tile);

const map = new maplibregl.Map({
  container: 'map',
  style: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
  center: [-109.9, 38.3],
  zoom: 6,
});

map.on('load', () => {
  map.addSource('uranium-districts', {
    type: 'vector',
    url: 'pmtiles://https://s3-west.nrp-nautilus.io/public-utah/ugs-uranium/districts.pmtiles',
  });

  map.addLayer({
    id: 'districts-fill',
    type: 'fill',
    source: 'uranium-districts',
    'source-layer': 'districts',          // = the layer name
    paint: {
      'fill-color': [
        'match', ['get', 'POTENTIAL'],
        'High', '#b2182b',
        'Moderate', '#ef8a62',
        'Low', '#fddbc7',
        'None', '#f7f7f7',
        '#cccccc',                         // unclassified (NULL)
      ],
      'fill-opacity': 0.7,
    },
  });

  map.addSource('uranium-past-producers', {
    type: 'vector',
    url: 'pmtiles://https://s3-west.nrp-nautilus.io/public-utah/ugs-uranium/past-producers.pmtiles',
  });

  map.addLayer({
    id: 'past-producers-pts',
    type: 'circle',
    source: 'uranium-past-producers',
    'source-layer': 'past-producers',
    paint: { 'circle-radius': 3, 'circle-color': '#2166ac' },
  });
});
```

## Things to know before you use it

**The two polygon layers are not a hierarchy.** Districts and areas share no key and no
name. 47 of the 58 districts sit entirely inside a single area and 4 more sit 93–98% inside
one, but 7 districts (Spor Mountain, Honeycomb Hills, East Erickson, Blawn Mountain, Silver
Reef, Marysvale, Newton) lie outside every area, because the areas cover the Colorado
Plateau and those districts are in western Utah. Rolling districts up to areas drops those
seven. Relate them spatially:

```sql
SELECT d.NAME AS district, a.NAME AS area
FROM read_parquet('.../districts.parquet') d
LEFT JOIN read_parquet('.../area-boundaries.parquet') a
  ON ST_Intersects(d.geom, a.geom);
```

**Do not add counts across layers.** The layers overlap each other, and overlap the sibling
`ugs-mineral-occurrences` and `usgs-mrds` collections, with no shared identifier. One mine
can appear as a past producer, a permitted mine and a mineral occurrence. Count within a
single layer with `COUNT(DISTINCT _cng_fid)`.

**Production and reserve figures need parsing.** On `past-producers` the `*_AMT`, `*_U`,
`*_ITEM`, `*_ACC`, `*_YEAR` and `*_GRADE` columns follow the USGS CRIB record format:

- Each holds several entries packed into one string, separated by `ý` (U+00FD).
- Each amount is in **thousands** of the unit named in the parallel `*_U` entry.
- Units vary between entries of one record, and spellings vary between records
  (`LB`, `LBS`, `ST`, `TONS`).
- Entries cover different commodities (`U`, `V`, `ORE U`, `CON U`).
- Entry counts disagree between the amount, unit and item fields in 30 records.

Reserves are also reported in three overlapping tables: `RPR_*` is the total, `R_*` its
reserves part and `PR_*` its potential-resources part, so adding all three counts the same
material twice. These columns are published as text exactly as received; parse before any
arithmetic.

**Point layers collapse onto shared hex cells.** At resolution 8 (~0.74 km² per cell) the
748 past producers fall on 551 distinct cells and the 25 permitted mines on 22. Points
sharing a cell are not deduplicated.

**Uranium potential classes are the survey's judgement.** `None` means no potential was
assigned, and is not a missing value; three districts are genuinely unclassified and are
`NULL`. The criteria behind High / Moderate / Low / None are not published by the publisher:
they are absent from the ArcGIS Online item metadata, the FGDC record, the UGRC product page
and UGS Map 215 itself.

**26 past producers have no attributes.** They carry valid coordinates but every descriptive
field is empty, so the count of described past producers is 722, not 748.

## Provenance

Retrieved 2026-09-22 from five ArcGIS Online feature services published by UGRC under the
SGID Energy theme (<https://gis.utah.gov/products/sgid/energy/>). The services are live and
unversioned: the publisher states no edition or release, so the access date is the only
edition marker and a later retrieval may differ.

The retrieved snapshot is staged at `s3://public-utah/raw/`:

| file | bytes | sha256 |
|---|---|---|
| `ugs-uranium-districts.geojson` | 451,808 | `d236c2f9919757aed2e67311dd5799af9b3077c931f25b2b1b071dcd87d4bc7b` |
| `ugs-uranium-area-boundaries.geojson` | 358,579 | `bcd6cab751f6d8d401a0defde91061b0aab3ae1e846926b9cc35364f9060fca1` |
| `ugs-uranium-past-producers.geojson` | 2,637,065 | `a9f397422f1f1124b547a4390ebd441572bf30970002f3f05212a93b80e32e45` |
| `ugs-uranium-permitted-mines.geojson` | 13,723 | `4ed55d3585c27f13190134a0669988753d267d73f029b4cfd80d9f2674229394` |
| `ugs-uranium-mills.geojson` | 773 | `d38f3507945c4d213283274f6ee4f5516558a711db02a67d15dd2c2a395b62c5` |

Underlying compilation: Utah Geological Survey Map 215, *Uranium and Vanadium Map of Utah*
(Gloyn, R.W., Bon, R.L., Wakefield, S., and Krahulec, K., 2005). Past-producer attributes
follow the USGS Computerized Resources Information Bank (CRIB) record format described in
Keefer, E.K., and Calkins, J.A., 1978, *Description of individual data items and codes in
CRIB*: U.S. Geological Survey Circular 755-B, <https://doi.org/10.3133/cir755B>.

Only two changes were made to the source attributes: strings were trimmed of the fixed-width
space padding the SGID extract applies, and values that were empty after trimming were
stored as `NULL`.

## Licence

CC-BY-4.0. Stated verbatim in the `licenseInfo` of all five ArcGIS Online items: "This work
is licensed under a Creative Commons Attribution 4.0 International License."
<https://creativecommons.org/licenses/by/4.0/>

Attribute the Utah Geological Survey and the Utah Geospatial Resource Center.
"""

if __name__ == "__main__":
    out = "/tmp/ugs-uranium-README.md"
    with open(out, "w") as fh:
        fh.write(README)
    print(f"wrote {out}")
