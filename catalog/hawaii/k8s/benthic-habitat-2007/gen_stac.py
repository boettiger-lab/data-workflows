#!/usr/bin/env python3
"""Write the benthic-habitat-2007 STAC collection and README to a directory (#843).

Usage: python3 gen_stac.py [out-dir]

Counts, areas and value lists were measured on the published data with the duckdb-geo MCP on
2026-11-02 (BUILD.md). Field meanings come from the upstream metadata document staged beside
the raw (benthic_habitat.pdf). Asset `created` and collection `created`/`updated` are read
from the S3 Last-Modified of each published object.
"""
import json
import os
import re
import sys
import urllib.request
from email.utils import parsedate_to_datetime

BUCKET = "public-hawaii"
DATASET = "benthic-habitat-2007"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
TITLE = "Benthic Habitats of the Main Hawaiian Islands (NOAA NCCOS, 2007)"
SERVICE = "https://geodata.hawaii.gov/arcgis/rest/services/CoastalMarine/MapServer/1"
LANDING = "https://geoportal.hawaii.gov/datasets/f2fa130e71ea4faaa5c32fb785805249"
NCCOS = "https://products.coastalscience.noaa.gov/collections/benthic/e97hawaii/data2007.aspx"
METADATA_PDF = "https://files.hawaii.gov/dbedt/op/gis/data/benthic_habitat.pdf"
TERMS = "https://portal.ehawaii.gov/page/terms-of-use/"
RETRIEVED = "2026-11-02"
RAW = f"s3://{BUCKET}/raw/benthic-habitat-2007/benthic-habitat-2007-service-response.geojson"
RAW_BYTES = "80,134,352"
RAW_SHA256 = "ff37f44c77853be1a1abec33264118072e33e57a560b49ce4aac131568436dee"

N = 8762
HEX_ROWS = int(os.environ["HEX_ROWS"])
HEX_FIDS = int(os.environ["HEX_FIDS"])
BBOX = [-160.590504, 18.89305298, -154.7968764, 22.2608337]

M_STRUCT = ["Coral Reef and Hardbottom", "Other Delineations", "Unconsolidated Sediment", "Unknown"]
D_STRUCT = ["Aggregate Reef", "Aggregated Patch Reef", "Artificial", "Individual Patch Reef", "Land",
            "Mud", "Pavement", "Pavement with Sand Channels", "Rock/Boulder", "Rubble", "Sand",
            "Scattered Coral/Rock", "Spur and Groove", "Unknown"]
M_COVER = ["Coral", "Coralline Algae", "Emergent Vegetation", "Macroalgae", "Seagrass", "Turf",
           "Unclassified", "Uncolonized", "Unknown"]
P_COVER = [" ", "10%-<50%", "50%-<90%", "90%-100%", "Unknown"]
ZONE = ["Back Reef", "Bank/Shelf", "Bank/Shelf Escarpment", "Channel", "Dredged", "Fore Reef",
        "Lagoon", "Land", "Reef Crest", "Reef Flat", "Reef Hole", "Shoreline Intertidal",
        "Unclassified", "Unknown"]
COVER = ["Coral 10%-<50%", "Coral 50%-<90%", "Coral 90%-100%", "Coralline Algae 10%-<50%",
         "Coralline Algae 50%-<90%", "Emergent Vegetation 10%-<50%", "Emergent Vegetation 50%-<90%",
         "Emergent Vegetation 90%-100%", "Macroalgae 10%-<50%", "Macroalgae 50%-<90%",
         "Macroalgae 90%-100%", "Seagrass 10%-<50%", "Turf 10%-<50%", "Turf 50%-<90%",
         "Turf 90%-100%", "Unclassified", "Uncolonized 90%-100%", "Unknown Unknown"]


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


def listing(vals):
    return ", ".join(f"'{v}'" for v in vals)


ATTRS = [
    {"name": "_cng_fid", "type": "int64",
     "description": "Unique row identifier assigned at conversion, one per habitat polygon. Use COUNT(DISTINCT _cng_fid) to count polygons."},
    {"name": "OGC_FID", "type": "int64",
     "description": "Row number assigned by GDAL when the source was read. Carries no meaning of its own."},
    {"name": "objectid", "type": "int32",
     "description": "Feature identifier in the Hawaiʻi Statewide GIS Program service, unique per polygon."},
    {"name": "uniqueid", "type": "int32",
     "description": "Four-digit code for the polygon's combination of structure and cover classes (96 combinations occur). Polygons with the same code share every class field."},
    {"name": "polygonid", "type": "int32",
     "description": "Running number used by NOAA for quality control during mapping. Not unique: 2,381 distinct values over 8,762 polygons."},
    {"name": "acres", "type": "double",
     "description": "Area of the polygon in acres, as recorded by the source (0.0003 to 2,584,092). Sums to about 5,030,000 acres over all polygons, of which about 4,119,000 acres are land."},
    {"name": "m_struct", "type": "string",
     "description": "Major geomorphological structure of the seafloor. Values: " + listing(M_STRUCT) + ". 'Other Delineations' covers land and artificial structures.",
     "values": M_STRUCT},
    {"name": "d_struct", "type": "string",
     "description": "Detailed geomorphological structure within the major structure class (m_struct). Values: "
                    "Aggregate Reef=coral reef and hardbottom, Aggregated Patch Reef=coral reef and hardbottom, "
                    "Individual Patch Reef=coral reef and hardbottom, Pavement=coral reef and hardbottom, "
                    "Pavement with Sand Channels=coral reef and hardbottom, Rock/Boulder=coral reef and hardbottom, "
                    "Rubble=coral reef and hardbottom, Scattered Coral/Rock=coral reef and hardbottom (scattered in sediment), "
                    "Spur and Groove=coral reef and hardbottom, Mud=unconsolidated sediment, Sand=unconsolidated sediment, "
                    "Land=other delineation (land), Artificial=other delineation (artificial structure), Unknown=not classified.",
     "values": D_STRUCT},
    {"name": "m_cover", "type": "string",
     "description": "Dominant biological cover on the seafloor. Values: " + listing(M_COVER) + ". 'Unclassified' marks the land and artificial polygons, whose cover was not mapped; 'Uncolonized' is bare substrate.",
     "values": M_COVER},
    {"name": "p_cover", "type": "string",
     "description": "Percent of the polygon covered by the dominant cover type. Values: 10%-<50%=10 to under 50 percent, "
                    "50%-<90%=50 to under 90 percent, 90%-100%=90 to 100 percent, "
                    "Unknown=not determined, ' '=not mapped (the land and artificial polygons).",
     "values": P_COVER},
    {"name": "zone", "type": "string",
     "description": "Geomorphological zone of the polygon across the reef, from shore to shelf edge. Values: " + listing(ZONE) + ".",
     "values": ZONE},
    {"name": "cover", "type": "string",
     "description": "Dominant cover and its percent combined in one label, as recorded by the source. Values: " + listing(COVER) + ".",
     "values": COVER},
]
LEAN = [{k: v for k, v in c.items() if k != "description"} for c in ATTRS]
H3_COLS = [
    {"name": "h10", "type": "uint64", "description": "H3 cell ID at resolution 10, the native resolution of this hex asset."},
    {"name": "h9", "type": "uint64", "description": "H3 cell ID at resolution 9."},
    {"name": "h8", "type": "uint64", "description": "H3 cell ID at resolution 8, the catalog's universal join key."},
    {"name": "h0", "type": "int64", "description": "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."},
]

DESCRIPTION = f"""Shallow-water benthic habitats of the eight main Hawaiian Islands (Niʻihau, Kauaʻi, Oʻahu, Molokaʻi, Lānaʻi, Maui, Kahoʻolawe and Hawaiʻi), mapped by NOAA's National Centers for Coastal Ocean Science (NCCOS) as of 2007. Habitats were delineated by hand from IKONOS and QuickBird satellite imagery and classified in a two-tier scheme that combines geomorphological structure (major and detailed) with biological cover (dominant cover type and its percent), across 13 geomorphological zones from shoreline to shelf edge. The data holds {N:,} polygons. It is a baseline from before the coral bleaching of 2014 and 2015.

The layer includes the islands' land as polygons (zone 'Land', about 4,119,000 of the 5,030,000 acres), plus areas NOAA could not classify (zone 'Unknown', about 581,000 acres). For seafloor statistics, exclude them:

```sql
SELECT zone, cover, SUM(acres) AS acres
FROM read_parquet('s3://{BUCKET}/{DATASET}.parquet')
WHERE zone NOT IN ('Land', 'Unknown')
GROUP BY zone, cover
```

Converted to cloud-native formats (GeoParquet, PMTiles and H3 hex) with H3 indexing at resolution 10 (about 0.015 square kilometres per cell), with parents at resolutions 9, 8 and 0. A single space (' ') in p_cover marks the land and artificial polygons, whose cover was not mapped.

Provenance. Source: NOAA National Centers for Coastal Ocean Science, Benthic Habitat Mapping of the Main Eight Hawaiian Islands (2007), in cooperation with the University of Hawaiʻi, BAE Systems Spectral Solutions and Analytical Laboratories of Hawaiʻi ({NCCOS}). The Hawaiʻi Statewide GIS Program downloaded the island files from NCCOS in February 2018, merged them into one statewide layer, and serves it as layer 1 of its CoastalMarine map service. Upstream publishes no edition label beyond the 2007 mapping year. The layer was retrieved from the map service on {RETRIEVED}. The service response is kept unmodified at {RAW}, {RAW_BYTES} bytes, sha256 {RAW_SHA256}, together with the layer definition and the program's metadata document. Two derived source fields, st_area(shape) and st_perimeter(shape), were not carried over: they are in State Plane units and duplicate the geometry.

Licence: public domain. The underlying mapping is a work of the US Government (NOAA), and the State of Hawaiʻi states that the contents of this layer are public domain and exempt from its Terms of Use restrictions, with no warranty of positional or thematic accuracy. Credit: NOAA National Centers for Coastal Ocean Science; Hawaiʻi Statewide GIS Program."""

HEX_DESC = f"""One row per habitat polygon and H3 cell pair at native resolution 10 (about 0.015 square kilometres per cell), with parents h9 and h8 and h0 as the hive partition key. {HEX_ROWS:,} rows covering all {HEX_FIDS:,} polygons. The attributes of each polygon, including acres, are repeated on every hex cell the polygon covers, so acres must be deduplicated by _cng_fid before it is summed:

```sql
-- correct: one acreage value per polygon
SELECT zone, SUM(acres) FROM (
  SELECT DISTINCT _cng_fid, zone, acres
  FROM read_parquet('s3://{BUCKET}/{DATASET}/hex/h0=*/data_0.parquet'))
GROUP BY zone
-- wrong: SUM(acres) over hex rows multiplies each polygon by its cell count
```

Polygon counts behave the same way: use COUNT(DISTINCT _cng_fid), not COUNT(*). For the area of a footprint measured from the cells themselves, see the H3 guide. A cell touched by a polygon's edge counts in full, so area measured from cells runs slightly above the acres field, most for narrow zones such as reef crests and reef holes. Land polygons (zone 'Land') make up most of the rows; filter them out for seafloor work. h10, h9 and h8 have no null values."""

CITATION = ("NOAA National Centers for Coastal Ocean Science (2007). Benthic Habitat Mapping of the "
            "Main Eight Hawaiian Islands. Statewide layer merged by the Hawaiʻi Statewide GIS Program, "
            f"CoastalMarine map service layer 1. Retrieved {RETRIEVED} from {SERVICE}")

T_PARQUET = iso(last_modified(f"{DATASET}.parquet"))
T_PMTILES = iso(last_modified(f"{DATASET}.pmtiles"))
T_HEX = first_hex_write()

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
    "keywords": ["benthic habitat", "coral reefs", "seafloor", "habitat mapping", "NOAA", "NCCOS",
                 "marine", "coastal", "Hawaii", "main Hawaiian Islands", "United States"],
    "providers": [
        {"name": "NOAA National Centers for Coastal Ocean Science (NCCOS)", "roles": ["producer"],
         "url": NCCOS},
        {"name": "Hawaiʻi Statewide GIS Program, Office of Planning and Sustainable Development",
         "roles": ["processor", "licensor", "host"], "url": "https://planning.hawaii.gov/gis/"},
        {"name": "Boettiger Lab", "roles": ["processor", "host"],
         "url": "https://github.com/boettiger-lab"},
    ],
    "sci:citation": CITATION,
    "created": min(T_PARQUET, T_PMTILES, T_HEX),
    "updated": max(T_PARQUET, T_PMTILES, T_HEX),
    "extent": {
        "spatial": {"bbox": [BBOX]},
        "temporal": {"interval": [["2007-01-01T00:00:00Z", "2007-12-31T00:00:00Z"]]},
    },
    "links": [
        {"rel": "self", "href": f"{BASE}/{DATASET}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",
         "type": "application/json"},
        {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
        {"rel": "describedby", "href": f"{BASE}/{DATASET}/README.md", "type": "text/markdown"},
        {"rel": "about", "href": NCCOS, "type": "text/html",
         "title": "NOAA NCCOS: Main Eight Hawaiian Islands benthic habitat data (2007)"},
        {"rel": "about", "href": LANDING, "type": "text/html",
         "title": "Benthic Habitat (Hawaiʻi Statewide GIS Program geoportal)"},
        {"rel": "describedby", "href": METADATA_PDF, "type": "application/pdf",
         "title": "Hawaiʻi Statewide GIS Program metadata: Benthic Habitat"},
        {"rel": "via", "href": SERVICE, "title": "CoastalMarine map service, layer 1"},
        {"rel": "license", "href": TERMS, "type": "text/html",
         "title": "State of Hawaii Terms of Use (contents public domain)"},
    ],
    "assets": {
        f"{DATASET}-parquet": {
            "href": f"{BASE}/{DATASET}.parquet",
            "type": "application/vnd.apache.parquet",
            "title": f"GeoParquet: all {N:,} benthic habitat polygons",
            "description": "One row per habitat polygon, with its structure, cover and zone classes and acreage.",
            "roles": ["data"],
            "created": T_PARQUET,
            "table:columns": ATTRS + [
                {"name": "geom", "type": "geometry", "description": "Habitat polygon boundary, EPSG:4326."}],
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
            "title": "H3 hexagonal index (native resolution 10) of the benthic habitats",
            "description": HEX_DESC,
            "roles": ["data"],
            "created": T_HEX,
            "h3:native_resolution": 10,
            "h3:parent_resolutions": [9, 8, 0],
            "table:columns": ATTRS + H3_COLS,
        },
    },
}

README = f"""# {TITLE}

Shallow-water benthic habitats of the eight main Hawaiian Islands, mapped by NOAA NCCOS from 2007 satellite imagery: {N:,} polygons classed by geomorphological structure, biological cover and reef zone. The layer includes the islands' land as polygons (zone `Land`); exclude it, and zone `Unknown`, for seafloor statistics.

## Files

| Asset | URL |
|---|---|
| GeoParquet | `{BASE}/{DATASET}.parquet` |
| PMTiles | `{BASE}/{DATASET}.pmtiles` |
| H3 hex (resolution 10, parents 9, 8, 0, partitioned by h0) | `{BASE}/{DATASET}/hex/h0=*/data_0.parquet` |

## Columns

| Column | Description |
|---|---|
| `_cng_fid` | Unique row id, one per polygon |
| `objectid` | Feature id in the state service |
| `uniqueid` | Code for the polygon's structure and cover combination |
| `polygonid` | NOAA quality-control number (not unique) |
| `acres` | Polygon area in acres |
| `m_struct`, `d_struct` | Major and detailed geomorphological structure |
| `m_cover`, `p_cover`, `cover` | Dominant biological cover, its percent, and the two combined |
| `zone` | Geomorphological zone (Reef Flat, Fore Reef, Bank/Shelf, Land, …) |
| `h10`, `h9`, `h8`, `h0` | H3 cells (hex asset only) |

On the hex asset each polygon's attributes repeat on every cell, so deduplicate by `_cng_fid` before summing `acres`.

## DuckDB

```sql
INSTALL spatial; LOAD spatial;
SELECT zone, m_cover, SUM(acres) AS acres
FROM read_parquet('{BASE}/{DATASET}.parquet')
WHERE zone NOT IN ('Land', 'Unknown')
GROUP BY zone, m_cover ORDER BY acres DESC;
```

## MapLibre GL JS

The PMTiles `source-layer` is **`{DATASET}`**.

```js
import {{ Protocol }} from "pmtiles";
maplibregl.addProtocol("pmtiles", new Protocol().tile);

map.addSource("hi-benthic", {{
  type: "vector",
  url: "pmtiles://{BASE}/{DATASET}.pmtiles",
}});
map.addLayer({{
  id: "hi-benthic-coral", type: "fill", source: "hi-benthic",
  "source-layer": "{DATASET}",
  filter: ["==", ["get", "m_cover"], "Coral"],
  paint: {{ "fill-color": "#ff7f50", "fill-opacity": 0.6 }},
}});
```

## Provenance and licence

Source: NOAA National Centers for Coastal Ocean Science, 2007 ({NCCOS}); merged statewide and served by the Hawaiʻi Statewide GIS Program ({SERVICE}; metadata {METADATA_PDF}). Retrieved {RETRIEVED}. The service response is kept unmodified at `{RAW}` ({RAW_BYTES} bytes, sha256 `{RAW_SHA256}`).

Licence: public domain (NOAA work; State of Hawaiʻi, {TERMS}). No warranty of accuracy.
"""

out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/hi-benthic"
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "stac-collection.json"), "w") as f:
    json.dump(stac, f, indent=2, ensure_ascii=False)
with open(os.path.join(out, "README.md"), "w") as f:
    f.write(README)
print(f"wrote {out}/stac-collection.json and README.md")
