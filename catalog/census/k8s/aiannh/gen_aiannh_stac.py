#!/usr/bin/env python3
"""Write the STAC collection for public-census/census-2024/aiannh (#945) to the path given.

    gen_aiannh_stac.py OUT.json

Writes a local file only; a publish job uploads it (AGENTS.md Hard Boundary 1). Code definitions are
from the Census entity-and-attribute metadata shipped in the zip (tl_2024_us_aiannh.shp.ea.iso.xml),
except MTFCC G2101/G2102, which neither that file nor the 2022 MTFCC list defines; their meaning is
measured (every G2101 row has COMPTYP R, every G2102 row COMPTYP T). Counts are measured on the
built files through duckdb-geo (2026-11-17); object sizes and dates are read live from S3.
"""
import json
import sys
import urllib.request
from email.utils import parsedate_to_datetime

S3 = "https://s3-west.nrp-nautilus.io"
BASE = f"{S3}/public-census/census-2024"
SRC = "https://www2.census.gov/geo/tiger/TIGER2024/AIANNH/tl_2024_us_aiannh.zip"


def head(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["Content-Length"]), parsedate_to_datetime(
            r.headers["Last-Modified"]).strftime("%Y-%m-%dT%H:%M:%SZ")


def coded(desc, pairs):
    return desc + " Values: " + ", ".join(f"{k}={v}" for k, v in pairs) + ".", [k for k, _ in pairs]


CLASSFP = [  # measured counts in brackets
    ("D0", "statistical or legal area administered or claimed by two or more tribes (joint-use area) [7]"),
    ("D2", "legal federally recognized American Indian area consisting of reservation only [152]"),
    ("D3", "legal federally recognized American Indian area consisting of off-reservation trust land only [13]"),
    ("D4", "legal state recognized American Indian area [10]"),
    ("D5", "the off-reservation trust land part of a federally recognized entity that has both a reservation and trust land [160]"),
    ("D6", "statistical American Indian area for a federally recognized tribe with no reservation or trust land (Oklahoma tribal statistical areas, tribal designated statistical areas) [32]"),
    ("D8", "the reservation part of a federally recognized entity that has both a reservation and trust land [160]"),
    ("D9", "statistical American Indian area for a state-recognized tribe with no reservation or trust land (state designated tribal statistical area) [35]"),
    ("E1", "Alaska Native village statistical area, the densely settled part of an Alaska Native village [221]"),
    ("F1", "Hawaiian home land, held in trust for the benefit of Native Hawaiians [74]"),
]
COMPTYP = [("R", "reservation or statistical area [617]"), ("T", "off-reservation trust land [247]")]
AIANNHR = [("F", "federally recognized [819]"), ("S", "state recognized [45]")]
FUNCSTAT = [("A", "active federally recognized entity [498]"), ("N", "nonfunctioning legal entity [74]"),
            ("S", "statistical entity [292]")]
MTFCC = [("G2101", "American Indian reservation (every row has COMPTYP R) [322]"),
         ("G2102", "American Indian off-reservation trust land (every row has COMPTYP T) [173]"),
         ("G2120", "Hawaiian home land [74]"), ("G2130", "Alaska Native village statistical area [221]"),
         ("G2140", "Oklahoma tribal statistical area [25]"),
         ("G2150", "state designated tribal statistical area [35]"),
         ("G2160", "tribal designated statistical area [7]"), ("G2170", "American Indian joint-use area [7]")]
LSAD = [("00", "blank"), ("78", "Hawaiian Home Land"), ("79", "Alaska Native Village Statistical Area"),
        ("80", "Tribal Designated Statistical Area"), ("81", "Colony"), ("82", "Community"),
        ("83", "Joint-Use Area"), ("84", "Pueblo"), ("85", "Rancheria"), ("86", "Reservation"),
        ("87", "Reserve"), ("88", "Oklahoma Tribal Statistical Area"), ("89", "Trust Land"),
        ("90", "joint-use Oklahoma Tribal Statistical Area"), ("91", "Ranch"),
        ("92", "State Designated Tribal Statistical Area"), ("93", "Indian Village"), ("94", "Village"),
        ("95", "Indian Community"), ("96", "Indian Reservation"), ("97", "Indian Rancheria"),
        ("98", "Indian Colony"), ("99", "Pueblo de (prefix)"), ("9C", "Pueblo of (prefix)"),
        ("9D", "settlement"), ("OT", "off-reservation trust land part of an entity with a reservation")]

C = [
    ("_cng_fid", "int64", "Feature ID assigned during conversion, one per area.", None),
    ("OGC_FID", "int64", "Row number in the source shapefile.", None),
    ("AIANNHCE", "string", "Census area code (4 digits) identifying the American Indian, Alaska Native or Native Hawaiian area. An area's reservation and its off-reservation trust land share this code.", None),
    ("AIANNHNS", "string", "GNIS identifier of the area (8 digits).", None),
    ("GEOID", "string", "Geographic identifier: AIANNHCE followed by the COMPTYP letter, R for the reservation or statistical part and T for the off-reservation trust land part (for example 1075R, 1075T). Unique per row.", None),
    ("GEOIDFQ", "string", "Fully qualified geographic identifier.", None),
    ("NAME", "string", "Area name, without its legal or statistical description.", None),
    ("NAMELSAD", "string", "Area name with its legal or statistical description (for example 'Navajo Nation Reservation').", None),
    ("LSAD", "string", *coded("Legal or statistical area description code, the term that follows (or precedes) the name.", LSAD)),
    ("CLASSFP", "string", *coded("Census class code: what kind of area this is, legally. It separates federal reservations and trust land, which are legal land bases, from statistical areas, which are not.", CLASSFP)),
    ("COMPTYP", "string", *coded("Component type: whether the row is a reservation or statistical area, or off-reservation trust land.", COMPTYP)),
    ("AIANNHR", "string", *coded("Federal or state recognition of the tribe.", AIANNHR)),
    ("MTFCC", "string", *coded("MAF/TIGER feature class code. G2101 and G2102 are not defined in the Census metadata; their meaning here is measured from COMPTYP.", MTFCC)),
    ("FUNCSTAT", "string", *coded("Functional status.", FUNCSTAT)),
    ("ALAND", "int64", "Land area of the area in square metres.", None),
    ("AWATER", "int64", "Water area of the area in square metres.", None),
    ("INTPTLAT", "string", "Latitude of the area's internal point.", None),
    ("INTPTLON", "string", "Longitude of the area's internal point.", None),
    ("geom", "geometry", "Area boundary in WGS84 (EPSG:4326).", None),
    ("h8", "uint64", "H3 cell ID at resolution 8 (about 0.74 square kilometres).", None),
    ("h0", "int64", "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads.", None),
]
ATTRS = [c[0] for c in C if c[0] not in ("geom", "h8", "h0")]
TILE = {"int64": "Number", "string": "String"}


def main(out):
    pq_size, pq_time = head(f"{BASE}/aiannh.parquet")
    pm_size, pm_time = head(f"{BASE}/aiannh.pmtiles")
    dic = []
    for name, typ, desc, values in C:
        col = {"name": name, "type": typ, "description": desc}
        if values:
            col["values"] = values
        dic.append(col)
    doc = {
        "type": "Collection", "stac_version": "1.0.0", "id": "census-2024-aiannh",
        "title": "American Indian, Alaska Native and Native Hawaiian Areas (Census TIGER/Line 2024)",
        "description": (
            "Boundaries of American Indian, Alaska Native and Native Hawaiian areas from the US Census "
            "Bureau's 2024 TIGER/Line shapefiles: 864 areas across the United States, including federal "
            "reservations and off-reservation trust land, Oklahoma tribal statistical areas, Alaska Native "
            "village statistical areas, tribal and state designated statistical areas, state reservations "
            "and Hawaiian home lands.\n\n"
            "Legal and statistical areas mean different things. Reservations and off-reservation trust "
            "land (CLASSFP D2, D3, D5, D8; state reservations D4) are legal land bases. Statistical areas "
            "(D6, D9, E1, and the joint-use areas D0) are drawn by the Census Bureau with tribes for "
            "counting purposes and are not land holdings; Oklahoma tribal statistical areas cover much of "
            "eastern Oklahoma. Filter on CLASSFP or COMPTYP for the question at hand. An area with both a "
            "reservation and trust land has two rows, one per part, sharing AIANNHCE.\n\n"
            "```sql\n-- legal land base (reservations and trust land) of federally recognized tribes\n"
            f"SELECT NAMELSAD, CLASSFP FROM read_parquet('{BASE}/aiannh.parquet')\n"
            "WHERE CLASSFP IN ('D2', 'D3', 'D5', 'D8') AND AIANNHR = 'F';\n```\n\n"
            "These are Census boundaries for statistics; the Bureau of Indian Affairs' Land Area "
            "Representations map trust land more exactly.\n\n"
            f"Provenance: Census download {SRC} (Last-Modified 2025-06-27, accessed 2026-11-17), staged at "
            "s3://public-census/raw/tl_2024_us_aiannh.zip (9,149,754 bytes, sha256 "
            "75e7bc8ccc1799f4813492f180d641ae2f8e3c98c7c2c137dbd0aa0845ee70cb). Code definitions are from "
            "the Census entity-and-attribute metadata in that file."),
        "license": "public-domain",
        "keywords": ["American Indian", "Alaska Native", "Native Hawaiian", "tribal lands", "reservation",
                     "trust land", "Census", "TIGER/Line", "tribal consultation"],
        "providers": [
            {"name": "U.S. Census Bureau", "roles": ["producer", "licensor"],
             "url": "https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html"},
            {"name": "Boettiger Lab", "roles": ["processor", "host"], "url": "https://boettigerlab.berkeley.edu"},
        ],
        "sci:citation": ('U.S. Census Bureau, "tl_2024_us_aiannh," TIGER/Line Shapefiles, 2024, '
                         "<https://www2.census.gov/geo/tiger/TIGER2024/AIANNH/>. Accessed 2026-11-17."),
        "stac_extensions": [
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
            "https://stac-extensions.github.io/vector/v0.1.0/schema.json",
        ],
        "extent": {"spatial": {"bbox": [[-174.235988, 18.91069, -67.035518, 71.340186]]},
                   "temporal": {"interval": [["2024-01-01T00:00:00Z", "2024-12-31T23:59:59Z"]]}},
        "created": pq_time, "updated": pm_time,
        "table:columns": dic,
        "assets": {
            "aiannh-parquet": {
                "href": f"{BASE}/aiannh.parquet", "type": "application/x-parquet", "roles": ["data"],
                "title": "AIANNH areas 2024 — GeoParquet", "description": "One row per area part (864 rows).",
                "created": pq_time, "file:size": pq_size, "table:row_count": 864,
                "table:columns": [{"name": n, "type": t} for n, t, _, _ in C if n not in ("h8", "h0")],
            },
            "aiannh-pmtiles": {
                "href": f"{BASE}/aiannh.pmtiles", "type": "application/vnd.pmtiles", "roles": ["data"],
                "title": "AIANNH areas 2024 — PMTiles", "description": "Vector tiles of the area boundaries for web maps.",
                "created": pm_time, "file:size": pm_size, "vector:layers": ["aiannh"],
                "table:columns": [{"name": n, "type": TILE[t]} for n, t, _, _ in C if n in ATTRS],
            },
            "aiannh-hex": {
                "href": f"{BASE}/aiannh/hex/h0=*/data_0.parquet", "type": "application/x-parquet",
                "roles": ["data"], "title": "AIANNH areas 2024 — H3 hex (resolution 8)",
                "description": (
                    "One row per (area, H3 resolution 8 cell): 661,835 rows over 661,680 distinct cells. "
                    "Every attribute of an area, ALAND and AWATER included, is repeated on every cell the "
                    "area covers, so deduplicate by _cng_fid or GEOID before summing them. A few areas "
                    "overlap (155 cells are in more than one area), so count distinct h8 for area."),
                "h3:native_resolution": 8, "h3:parent_resolutions": [0], "table:row_count": 661835,
                "table:columns": [{"name": n, "type": t} for n, t, _, _ in C if n != "geom"],
            },
        },
        "links": [
            {"rel": "self", "href": f"{BASE}/aiannh/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": f"{S3}/public-data/stac/catalog.json", "type": "application/json"},
            {"rel": "parent", "href": f"{S3}/public-census/stac-collection.json", "type": "application/json"},
            {"rel": "about", "type": "text/html",
             "href": "https://www.census.gov/programs-surveys/geography/technical-documentation/complete-technical-documentation/tiger-geo-line.html"},
            {"rel": "license", "href": "https://www.usa.gov/government-works", "title": "U.S. Government Works"},
            {"rel": "pmtiles", "href": f"{BASE}/aiannh.pmtiles", "type": "application/vnd.pmtiles",
             "title": "AIANNH areas 2024", "pmtiles:layers": ["aiannh"]},
        ],
    }
    with open(out, "w") as fh:
        fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
