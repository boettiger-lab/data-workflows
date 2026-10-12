#!/usr/bin/env python3
"""Write the special-tar-sand-areas STAC collection and README to a /tmp directory (#723).

Usage: python3 gen_stac.py [/tmp/stsa]

Counts, bbox and value lists were measured on the published data (BUILD.md, rechecked
2026-10-12 with the duckdb-geo MCP). Asset `created` and collection `created`/`updated` are
read from the S3 Last-Modified of each published object.
"""
import json
import os
import re
import sys
import urllib.request
from email.utils import parsedate_to_datetime

BUCKET = "public-blm"
DATASET = "special-tar-sand-areas"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
TITLE = "BLM Special Tar Sand Areas (Utah)"
ARCHIVE = ("https://web.archive.org/web/20130216005950/"
           "http://ostseis.anl.gov/guide/maps/gis/2012_OSTS_PEIS_Geospatial_Data.zip")
RAW = f"s3://{BUCKET}/raw/2012_OSTS_PEIS_Geospatial_Data.zip"
RAW_BYTES = "2,048,223"
RAW_SHA256 = "be1be303e5377c373299d3ca38dfe5e9dded13a7ecfa90f2dfb5abf6fd2dfb7a"
RETRIEVED = "2026-09-24"

N_PARTS = 37
HEX_ROWS = 5160
BBOX = [-111.2194672, 37.67732227, -109.0861189, 40.57822433]
NAMES = ["P.R. Spring", "Tar Sand Triangle", "Asphalt Ridge", "Sunnyside", "Circle Cliffs",
         "Hill Creek", "San Rafael", "Raven Ridge", "Argyle Canyon", "Pariette", "White Canyon"]
IDS = list(range(1, len(NAMES) + 1))


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

ID_DESC = ("Special Tar Sand Area number, 1 to 11, shared by every polygon part of the same area. "
           "Values: " + ", ".join(f"{i}={n}" for i, n in zip(IDS, NAMES)))
NAME_DESC = ("Name of the Special Tar Sand Area. Several areas are made of more than one polygon "
             "part, so group by NAME or ID to get one row per area.")
AREA_DESC = ("Area of this polygon part in acres, as computed by the source in an equal-area "
             "projection. Ranges from 411 to 273,927 acres. Summing it over all rows gives about "
             "1,026,000 acres for all eleven areas.")
FID_DESC = ("Unique row identifier assigned at conversion, one per polygon part. "
            "Use COUNT(DISTINCT _cng_fid) to count polygons.")
OGC_DESC = "Row number assigned by GDAL when the source was read. Carries no meaning of its own."

ATTRS = [
    {"name": "_cng_fid", "type": "int64", "description": FID_DESC},
    {"name": "OGC_FID", "type": "int64", "description": OGC_DESC},
    {"name": "ID", "type": "int32", "description": ID_DESC, "values": IDS},
    {"name": "NAME", "type": "string", "description": NAME_DESC, "values": NAMES},
    {"name": "area_ac", "type": "double", "description": AREA_DESC},
]
LEAN = [{k: v for k, v in c.items() if k != "description"} for c in ATTRS]

DESCRIPTION = f"""Boundaries of Utah's eleven Special Tar Sand Areas: the areas the Department of the Interior designated as containing substantial deposits of tar sand, in orders of November 20, 1980 (45 FR 76800) and January 21, 1981 (46 FR 6077). Within these areas, federal oil and gas and tar sand rights can be leased together under the Combined Hydrocarbon Leasing Act of 1981. The eleven areas are {", ".join(NAMES[:-1])} and {NAMES[-1]}, covering about 1,026,000 acres in the Uinta Basin and central southeastern Utah. Converted to cloud-native formats (GeoParquet, PMTiles and H3 hex) with H3 indexing at resolution 8 (about 0.74 square kilometres per cell).

The data holds {N_PARTS} polygon parts, not 11 rows: seven of the areas are made of more than one polygon, from 2 parts (Tar Sand Triangle) to 9 (Sunnyside). Group by NAME or ID for one row per area:

```sql
SELECT NAME, COUNT(*) AS parts, SUM(area_ac) AS acres
FROM read_parquet('s3://{BUCKET}/{DATASET}.parquet')
GROUP BY NAME ORDER BY acres DESC
```

These are designated boundaries, not mapped deposits. They show where the leasing framework applies, not where tar sand is present or how much. The boundaries are those compiled by the Bureau of Land Management in 2007 for the Oil Shale and Tar Sands Programmatic Environmental Impact Statement. Coverage is Utah only.

Provenance. BLM publishes no live service for these boundaries. The only public distribution is the 2012 Oil Shale and Tar Sands Programmatic Environmental Impact Statement geospatial data package, prepared by Argonne National Laboratory for the BLM, layer strata_unit_area_tarsand. Its metadata names the Bureau of Land Management as originator, with a publication date of 2007. The package's original site, ostseis.anl.gov, is offline, so the package was retrieved on {RETRIEVED} from the Internet Archive's capture of 2013-02-16. The package is kept unmodified at {RAW}, {RAW_BYTES} bytes, sha256 {RAW_SHA256}. With the original site gone, this stored copy and its checksum are what make this edition resolvable. The package's other layers, including the environmental impact statement's alternative leasing footprints within these areas, are not part of this collection. Three source fields were not carried over: exp_elev (the same value, 500, on every row and undocumented), PDF_FILE (names map files not included in the package), and the source's projected length and area fields."""

HEX_DESC = f"""One row per polygon part and H3 cell pair at native resolution 8 (about 0.74 square kilometres per cell), with h0 as the hive partition key. {HEX_ROWS:,} rows covering all {N_PARTS} polygon parts. The attributes of each polygon part, including area_ac, are repeated on every hex cell the part covers, so area_ac must be deduplicated by _cng_fid before it is summed:

```sql
-- correct: one acreage value per polygon part
SELECT NAME, SUM(area_ac) FROM (
  SELECT DISTINCT _cng_fid, NAME, area_ac
  FROM read_parquet('s3://{BUCKET}/{DATASET}/hex/h0=*/data_0.parquet'))
GROUP BY NAME
-- wrong: SUM(area_ac) over hex rows multiplies each part by its cell count
```

Polygon counts behave the same way: use COUNT(DISTINCT _cng_fid), not COUNT(*). For the area of a footprint measured from the cells themselves, see the H3 guide. h8 has no null values."""

CITATION = (f"U.S. Bureau of Land Management, 2007. Special Tar Sand Areas in Utah "
            f"(strata_unit_area_tarsand). Distributed in the 2012 Oil Shale and Tar Sands "
            f"Programmatic Environmental Impact Statement geospatial data package, Argonne National "
            f"Laboratory. Retrieved {RETRIEVED} from the Internet Archive capture of 2013-02-16 of "
            f"http://ostseis.anl.gov/guide/maps/gis/2012_OSTS_PEIS_Geospatial_Data.zip")

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
    "keywords": ["tar sands", "oil sands", "special tar sand areas", "combined hydrocarbon leasing",
                 "bitumen", "energy", "public lands", "BLM", "Utah", "United States"],
    "providers": [
        {"name": "U.S. Bureau of Land Management", "roles": ["producer", "licensor"],
         "url": "https://www.blm.gov/"},
        {"name": "Argonne National Laboratory (Oil Shale and Tar Sands PEIS)", "roles": ["host"],
         "url": ARCHIVE},
        {"name": "Boettiger Lab", "roles": ["processor", "host"],
         "url": "https://github.com/boettiger-lab"},
    ],
    "sci:citation": CITATION,
    "created": min(T_PARQUET, T_PMTILES, T_HEX),
    "updated": max(T_PARQUET, T_PMTILES, T_HEX),
    "extent": {
        "spatial": {"bbox": [BBOX]},
        "temporal": {"interval": [["1980-11-20T00:00:00Z", None]]},
    },
    "links": [
        {"rel": "self", "href": f"{BASE}/{DATASET}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",
         "type": "application/json"},
        {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
        {"rel": "describedby", "href": f"{BASE}/{DATASET}/README.md", "type": "text/markdown"},
        {"rel": "about", "href": ARCHIVE,
         "title": "2012 Oil Shale and Tar Sands PEIS geospatial data package (Internet Archive capture)"},
        {"rel": "license", "href": "https://www.usa.gov/government-works",
         "title": "U.S. Government Works (public domain)", "type": "text/html"},
    ],
    "assets": {
        f"{DATASET}-parquet": {
            "href": f"{BASE}/{DATASET}.parquet",
            "type": "application/vnd.apache.parquet",
            "title": f"GeoParquet: all {N_PARTS} polygon parts of the 11 Special Tar Sand Areas",
            "description": ("One row per polygon part, with the area number, name and acreage. "
                            "Group by NAME or ID for one row per area."),
            "roles": ["data"],
            "created": T_PARQUET,
            "table:columns": ATTRS + [
                {"name": "geom", "type": "geometry", "description": "Polygon part boundary, EPSG:4326."}],
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
            "title": "H3 hexagonal index (native resolution 8) of the Special Tar Sand Areas",
            "description": HEX_DESC,
            "roles": ["data"],
            "created": T_HEX,
            "h3:native_resolution": 8,
            "h3:parent_resolutions": [0],
            "table:columns": ATTRS + [
                {"name": "h8", "type": "uint64",
                 "description": "H3 cell ID at resolution 8, the native resolution of this hex asset "
                                "and the catalog's universal join key."},
                {"name": "h0", "type": "int64",
                 "description": "H3 cell ID at resolution 0, used as the partition key for "
                                "hive-partitioned reads."},
            ],
        },
    },
}

README = f"""# {TITLE}

Boundaries of Utah's eleven Special Tar Sand Areas, designated by Department of the Interior orders of November 20, 1980 (45 FR 76800) and January 21, 1981 (46 FR 6077) as containing substantial deposits of tar sand. Within them, federal oil and gas and tar sand rights can be leased together under the Combined Hydrocarbon Leasing Act of 1981.

The areas are {", ".join(NAMES[:-1])} and {NAMES[-1]}, about 1,026,000 acres in total. The data holds **{N_PARTS} polygon parts**, not 11 rows, because seven areas are made of several polygons. Group by `NAME` or `ID` for one row per area.

These are designated boundaries, not mapped deposits: they show where the leasing framework applies, not where tar sand is present.

## Files

| Asset | URL |
|---|---|
| GeoParquet | `{BASE}/{DATASET}.parquet` |
| PMTiles | `{BASE}/{DATASET}.pmtiles` |
| H3 hex (resolution 8, partitioned by h0) | `{BASE}/{DATASET}/hex/h0=*/data_0.parquet` |

## Columns

| Column | Description |
|---|---|
| `_cng_fid` | Unique row id, one per polygon part |
| `ID` | Area number 1 to 11 |
| `NAME` | Area name |
| `area_ac` | Area of the polygon part in acres |
| `h8`, `h0` | H3 cells (hex asset only) |

On the hex asset each part's attributes repeat on every cell, so deduplicate by `_cng_fid` before summing `area_ac`.

## DuckDB

```sql
INSTALL spatial; LOAD spatial;
SELECT NAME, COUNT(*) AS parts, SUM(area_ac) AS acres
FROM read_parquet('{BASE}/{DATASET}.parquet')
GROUP BY NAME ORDER BY acres DESC;
```

## MapLibre GL JS

The PMTiles `source-layer` is **`{DATASET}`**.

```js
import {{ Protocol }} from "pmtiles";
maplibregl.addProtocol("pmtiles", new Protocol().tile);

map.addSource("stsa", {{
  type: "vector",
  url: "pmtiles://{BASE}/{DATASET}.pmtiles",
}});
map.addLayer({{
  id: "stsa-fill", type: "fill", source: "stsa",
  "source-layer": "{DATASET}",
  paint: {{ "fill-color": "#6b3e26", "fill-opacity": 0.4 }},
}});
map.addLayer({{
  id: "stsa-line", type: "line", source: "stsa",
  "source-layer": "{DATASET}",
  paint: {{ "line-color": "#3b1f10", "line-width": 1 }},
}});
```

## Provenance and licence

Source: Bureau of Land Management, 2007, layer `strata_unit_area_tarsand` in the 2012 Oil Shale and Tar Sands Programmatic Environmental Impact Statement geospatial data package (Argonne National Laboratory). The original site (ostseis.anl.gov) is offline. The package was retrieved on {RETRIEVED} from the Internet Archive capture of 2013-02-16 and is kept unmodified at `{RAW}` ({RAW_BYTES} bytes, sha256 `{RAW_SHA256}`).

Licence: public domain, as a US federal government work (https://www.usa.gov/government-works).
"""

out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/stsa"
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "stac-collection.json"), "w") as f:
    json.dump(stac, f, indent=2)
with open(os.path.join(out, "README.md"), "w") as f:
    f.write(README)
print(f"wrote {out}/stac-collection.json and {out}/README.md")
