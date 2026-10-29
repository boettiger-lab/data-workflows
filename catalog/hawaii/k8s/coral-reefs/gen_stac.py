#!/usr/bin/env python3
"""Write the coral-reefs STAC collection, its README, and the public-hawaii bucket-level
collection to a /tmp directory (#782).

Usage: python3 gen_stac.py [/tmp/hi-coral]

Counts, bbox and value lists were measured on the published data with the duckdb-geo MCP
(BUILD.md). Asset `created` and collection `created`/`updated` are read from the S3
Last-Modified of each published object.
"""
import json
import os
import re
import sys
import urllib.request
from email.utils import parsedate_to_datetime

BUCKET = "public-hawaii"
DATASET = "coral-reefs"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
TITLE = "Coral Reefs from NOAA Nautical Charts (Main Hawaiian Islands)"
LANDING = "https://geoportal.hawaii.gov/datasets/9229d814438349948c99b5e61a084418_7/about"
SERVICE = "https://geodata.hawaii.gov/arcgis/rest/services/CoastalMarine/MapServer/7"
METADATA_PDF = "https://files.hawaii.gov/dbedt/op/gis/data/coralreefs_nc.pdf"
TERMS = "https://portal.ehawaii.gov/page/terms-of-use/"
RAW = f"s3://{BUCKET}/raw/coral-reefs-service-response.geojson"
RAW_BYTES = "2,527,148"
RAW_SHA256 = "d42b995ce1c37dab2a06f6a7e1cbec624132b9ad728bc737db96ae02823dca9c"
RETRIEVED = "2026-10-14"

N = 474
HEX_ROWS = 8028
BBOX = [-159.78876389, 18.96662909, -155.01463308, 22.23112327]
NOTES = ["", "Bare at Low Water", "Coral Reef  Extremely Shoal", "Coral Reef Awash",
         "Coral Reef Breakers", "Coral Reef Extremely Shoal", "Foul with Rocks and Coral Heads",
         "Foul with Submerged Coral", "Rocks and Submerged Coral", "Submerged Coral",
         "Submerged Reef"]
CHART1 = ["19320_1", "19322_3", "19324_1", "19327_1", "19327_3", "19329_1", "19331_1", "19332_1",
          "19340_1", "19341_1", "19342_1", "19342_2", "19347_1", "19347_2", "19350_1", "19351_1",
          "19351_2", "19353_1", "19357_1", "19358_1", "19361_1", "19364_1", "19369_1", "19380_1",
          "19381_1", "19382_1", "19383_1", "19385_1", "19386_1"]
CHART2 = ["", "19327_3", "19331_1", "19332_1", "19342_1", "19347_1", "19350_1", "19351_1",
          "19351_2", "19357_1", "19358_1", "19361_1", "19364_1", "19369_1", "19380_1", "19385_1",
          "19386_1"]
THEMES = {"Coral reefs_hawa": "Hawaiʻi", "Coral reefs_kaua": "Kauaʻi",
          "Coral reefs_lana": "Lānaʻi", "Coral reefs_maui": "Maui",
          "Coral reefs_molo": "Molokaʻi", "Coral reefs_oahu": "Oʻahu"}


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def last_modified(key):
    req = urllib.request.Request(f"{BASE}/{key}", method="HEAD")
    with urllib.request.urlopen(req) as r:
        return parsedate_to_datetime(r.headers["Last-Modified"])


def first_hex_write():
    url = f"{BASE}?list-type=2&prefix={DATASET}/hex/"
    with urllib.request.urlopen(url) as r:
        stamps = re.findall(r"<LastModified>([^<.]+)", r.read().decode())
    return min(stamps) + "Z"


T_PARQUET = iso(last_modified(f"{DATASET}.parquet"))
T_PMTILES = iso(last_modified(f"{DATASET}.pmtiles"))
T_HEX = first_hex_write()

CHART_DESC = ("NOAA nautical chart the reef was digitized from, coded as chart number and panel: "
              "19351_1 = NOAA chart 19351, panel 1.")
ATTRS = [
    {"name": "_cng_fid", "type": "int64",
     "description": "Unique row identifier assigned at conversion, one per reef polygon. "
                    "Use COUNT(DISTINCT _cng_fid) to count reefs."},
    {"name": "OGC_FID", "type": "int64",
     "description": "Row number assigned by GDAL when the source was read. Carries no meaning of its own."},
    {"name": "objectid", "type": "int32",
     "description": "Feature identifier in the Hawaii Statewide GIS Program service, unique per reef polygon."},
    {"name": "acres", "type": "double",
     "description": "Area of the reef polygon in acres, as recorded by the source. Ranges from 0 to "
                    "3,190 acres and sums to about 33,355 acres over all 474 polygons. One polygon "
                    "records 0 acres."},
    {"name": "chart1", "type": "string", "description": CHART_DESC, "values": CHART1},
    {"name": "chart2", "type": "string",
     "description": "Second NOAA chart the reef was digitized from, for reefs that span two charts, "
                    "coded as chart number and panel: 19358_1 = NOAA chart 19358, panel 1. "
                    "Empty string = no second chart (419 of the 474 polygons).",
     "values": CHART2},
    {"name": "notes", "type": "string",
     "description": "Chart annotation for the reef, as printed on the nautical chart. "
                    "Empty string = no annotation (457 polygons). Values: " + ", ".join(f"'{v}'" for v in NOTES) + ". Two spellings of "
                    "Coral Reef Extremely Shoal occur, one with a double space, as in the source.",
     "values": NOTES},
    {"name": "sourcethm", "type": "string",
     "description": "Island-level shapefile the reef came from before the statewide merge. Values: "
                    + ", ".join(f"{k}={v}" for k, v in THEMES.items()),
     "values": list(THEMES)},
]
LEAN = [{k: v for k, v in c.items() if k != "description"} for c in ATTRS]

DESCRIPTION = f"""Coral reefs in the marine waters around the main Hawaiian Islands (Kauaʻi, Oʻahu, Molokaʻi, Lānaʻi, Maui and Hawaiʻi), as drawn on NOAA nautical charts. The Hawaii Statewide GIS Program digitized every reef shown on the NOAA raster nautical charts of 2002, chart by chart, and merged them into one statewide layer, completed December 2002. The data holds {N} reef polygons covering about 33,355 acres. Converted to cloud-native formats (GeoParquet, PMTiles and H3 hex) with H3 indexing at resolution 10 (about 0.015 square kilometres per cell), with parents at resolutions 9, 8 and 0.

These are chart features, mapped for navigation: they show reefs a mariner needs to know about, at the scale of each chart, and are not a habitat or benthic survey. Live coral cover and condition are not recorded. The source carries this caution: the data are not to be used for navigation, and were not reviewed or authenticated by NOAA's Office of Coast Survey. Coverage is the main Hawaiian Islands only. The Northwestern Hawaiian Islands are not included. For a global coral reef layer, see the UNEP-WCMC Global Distribution of Coral Reefs collection.

Provenance. Source: NOAA Raster Nautical Charts, 2002, digitized by the Hawaii Statewide GIS Program (Office of Planning and Sustainable Development, State of Hawaii), which maintains the layer as layer 7 of its CoastalMarine map service. In June 2024 the program removed fields left over from a 2016 database conversion. Upstream publishes no edition label. The layer was retrieved from the map service on {RETRIEVED}. The service response is kept unmodified at {RAW}, {RAW_BYTES} bytes, sha256 {RAW_SHA256}, together with the layer definition and the program's metadata document. One source field, id, was not carried over: it is 0 on every row.

Licence: public domain. The State of Hawaii states that the contents are public domain and exempt from its Terms of Use restrictions, with no warranty of positional or thematic accuracy. Credit: NOAA Raster Nautical Charts, 2002; Hawaii Statewide GIS Program."""

HEX_DESC = f"""One row per reef polygon and H3 cell pair at native resolution 10 (about 0.015 square kilometres per cell), with parents h9 and h8 and h0 as the hive partition key. {HEX_ROWS:,} rows covering all {N} polygons. The attributes of each polygon, including acres, are repeated on every hex cell the polygon covers, so acres must be deduplicated by _cng_fid before it is summed:

```sql
-- correct: one acreage value per reef polygon
SELECT sourcethm, SUM(acres) FROM (
  SELECT DISTINCT _cng_fid, sourcethm, acres
  FROM read_parquet('s3://{BUCKET}/{DATASET}/hex/h0=*/data_0.parquet'))
GROUP BY sourcethm
-- wrong: SUM(acres) over hex rows multiplies each polygon by its cell count
```

Reef counts behave the same way: use COUNT(DISTINCT _cng_fid), not COUNT(*). For the area of a footprint measured from the cells themselves, see the H3 guide. h10, h9 and h8 have no null values."""

H3_COLS = [
    {"name": "h10", "type": "uint64", "description": "H3 cell ID at resolution 10, the native resolution of this hex asset."},
    {"name": "h9", "type": "uint64", "description": "H3 cell ID at resolution 9."},
    {"name": "h8", "type": "uint64", "description": "H3 cell ID at resolution 8, the catalog's universal join key."},
    {"name": "h0", "type": "int64", "description": "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."},
]

CITATION = ("NOAA Raster Nautical Charts, 2002; Hawaii Statewide GIS Program, Office of Planning and "
            "Sustainable Development, State of Hawaii. Coral Reefs (Nautical Charts), CoastalMarine "
            f"map service layer 7. Retrieved {RETRIEVED} from {SERVICE}")

stac = {
    "type": "Collection",
    "stac_version": "1.0.0",
    "stac_extensions": [
        "https://stac-extensions.github.io/table/v1.2.0/schema.json",
        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
    ],
    "id": DATASET,
    "title": TITLE,
    "description": DESCRIPTION,
    "license": "public-domain",
    "keywords": ["coral reefs", "reefs", "nautical charts", "NOAA", "marine", "coastal",
                 "Hawaii", "main Hawaiian Islands", "United States"],
    "providers": [
        {"name": "NOAA Office of Coast Survey (Raster Nautical Charts)", "roles": ["producer"],
         "url": "https://nauticalcharts.noaa.gov/"},
        {"name": "Hawaii Statewide GIS Program, Office of Planning and Sustainable Development",
         "roles": ["processor", "licensor", "host"], "url": "https://planning.hawaii.gov/gis/"},
        {"name": "Boettiger Lab", "roles": ["processor", "host"],
         "url": "https://github.com/boettiger-lab"},
    ],
    "sci:citation": CITATION,
    "created": min(T_PARQUET, T_PMTILES, T_HEX),
    "updated": max(T_PARQUET, T_PMTILES, T_HEX),
    "extent": {
        "spatial": {"bbox": [BBOX]},
        "temporal": {"interval": [["2002-01-01T00:00:00Z", "2002-12-31T00:00:00Z"]]},
    },
    "links": [
        {"rel": "self", "href": f"{BASE}/{DATASET}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",
         "type": "application/json"},
        {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
        {"rel": "describedby", "href": f"{BASE}/{DATASET}/README.md", "type": "text/markdown"},
        {"rel": "about", "href": LANDING, "type": "text/html",
         "title": "Coral Reefs (Hawaii Statewide GIS Program geoportal)"},
        {"rel": "describedby", "href": METADATA_PDF, "type": "application/pdf",
         "title": "Hawaii Statewide GIS Program metadata: Coral Reefs (Nautical Charts)"},
        {"rel": "via", "href": SERVICE, "title": "CoastalMarine map service, layer 7"},
        {"rel": "license", "href": TERMS, "type": "text/html",
         "title": "State of Hawaii Terms of Use (contents public domain)"},
    ],
    "assets": {
        f"{DATASET}-parquet": {
            "href": f"{BASE}/{DATASET}.parquet",
            "type": "application/vnd.apache.parquet",
            "title": f"GeoParquet: all {N} coral reef polygons",
            "description": "One row per reef polygon, with its acreage, source chart and chart annotation.",
            "roles": ["data"],
            "created": T_PARQUET,
            "table:columns": ATTRS + [
                {"name": "geom", "type": "geometry", "description": "Reef polygon boundary, EPSG:4326."}],
        },
        f"{DATASET}-pmtiles": {
            "href": f"{BASE}/{DATASET}.pmtiles",
            "type": "application/vnd.pmtiles",
            "title": "PMTiles vector tiles for web map display",
            "description": f"Vector tiles for MapLibre GL JS. The source layer is {DATASET}.",
            "roles": ["visual"],
            "created": T_PMTILES,
            "vector:layers": [DATASET],
            "table:columns": LEAN,
        },
        f"{DATASET}-hex": {
            "href": f"{BASE}/{DATASET}/hex/h0=*/data_0.parquet",
            "type": "application/vnd.apache.parquet",
            "title": "H3 hexagonal index (native resolution 10) of the coral reefs",
            "description": HEX_DESC,
            "roles": ["data"],
            "created": T_HEX,
            "h3:native_resolution": 10,
            "h3:parent_resolutions": [9, 8, 0],
            "table:columns": ATTRS + H3_COLS,
        },
    },
}

BUCKET_STAC = {
    "type": "Collection",
    "stac_version": "1.0.0",
    "id": "public-hawaii",
    "title": "Hawaiʻi Datasets",
    "description": "Datasets specific to the Hawaiian Islands, from state and federal sources.",
    "license": "public-domain",
    "extent": {
        "spatial": {"bbox": [BBOX]},
        "temporal": {"interval": [["2002-01-01T00:00:00Z", None]]},
    },
    "links": [
        {"rel": "self", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",
         "type": "application/json"},
        {"rel": "parent", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",
         "type": "application/json"},
        {"rel": "child", "href": f"{BASE}/{DATASET}/stac-collection.json",
         "type": "application/json", "title": TITLE},
        {"rel": "license", "href": TERMS, "type": "text/html",
         "title": "State of Hawaii Terms of Use (contents public domain)"},
    ],
}

README = f"""# {TITLE}

Coral reefs in the marine waters around the main Hawaiian Islands, digitized by the Hawaii Statewide GIS Program from the NOAA raster nautical charts of 2002. {N} reef polygons, about 33,355 acres.

These are chart features mapped for navigation, not a habitat survey. They are not to be used for navigation. Coverage is the main Hawaiian Islands only.

## Files

| Asset | URL |
|---|---|
| GeoParquet | `{BASE}/{DATASET}.parquet` |
| PMTiles | `{BASE}/{DATASET}.pmtiles` |
| H3 hex (resolution 10, parents 9, 8, 0, partitioned by h0) | `{BASE}/{DATASET}/hex/h0=*/data_0.parquet` |

## Columns

| Column | Description |
|---|---|
| `_cng_fid` | Unique row id, one per reef polygon |
| `objectid` | Feature id in the state service |
| `acres` | Reef polygon area in acres |
| `chart1`, `chart2` | NOAA chart number and panel the reef was digitized from |
| `notes` | Chart annotation (e.g. Submerged Reef, Coral Reef Awash) |
| `sourcethm` | Island shapefile before the statewide merge |
| `h10`, `h9`, `h8`, `h0` | H3 cells (hex asset only) |

On the hex asset each polygon's attributes repeat on every cell, so deduplicate by `_cng_fid` before summing `acres`.

## DuckDB

```sql
INSTALL spatial; LOAD spatial;
SELECT sourcethm, COUNT(*) AS reefs, SUM(acres) AS acres
FROM read_parquet('{BASE}/{DATASET}.parquet')
GROUP BY sourcethm ORDER BY acres DESC;
```

## MapLibre GL JS

The PMTiles `source-layer` is **`{DATASET}`**.

```js
import {{ Protocol }} from "pmtiles";
maplibregl.addProtocol("pmtiles", new Protocol().tile);

map.addSource("hi-coral-reefs", {{
  type: "vector",
  url: "pmtiles://{BASE}/{DATASET}.pmtiles",
}});
map.addLayer({{
  id: "hi-coral-reefs-fill", type: "fill", source: "hi-coral-reefs",
  "source-layer": "{DATASET}",
  paint: {{ "fill-color": "#ff7f50", "fill-opacity": 0.6 }},
}});
```

## Provenance and licence

Source: NOAA Raster Nautical Charts, 2002; Hawaii Statewide GIS Program ({LANDING}; metadata {METADATA_PDF}). Retrieved {RETRIEVED} from {SERVICE}. The service response is kept unmodified at `{RAW}` ({RAW_BYTES} bytes, sha256 `{RAW_SHA256}`).

Licence: public domain, per the State of Hawaii ({TERMS}). No warranty of accuracy.
"""

out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/hi-coral"
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "stac-collection.json"), "w") as f:
    json.dump(stac, f, indent=2, ensure_ascii=False)
with open(os.path.join(out, "bucket-stac-collection.json"), "w") as f:
    json.dump(BUCKET_STAC, f, indent=2, ensure_ascii=False)
with open(os.path.join(out, "README.md"), "w") as f:
    f.write(README)
print(f"wrote {out}/stac-collection.json, bucket-stac-collection.json and README.md")
