#!/usr/bin/env python3
"""Emit the census-2025/roads dataset collection to /tmp for rclone upload (AGENTS.md Hard
Boundary 1 — this repo never contains STAC JSON or README files).

One source schema (COLUMNS) is written identically to the flat GeoParquet and the hex so the
mcp-data-server#303 per-column fold never drops a variant. PMTiles gets the lean form.

Counts and the MTFCC `values` list are read from `_measured.json`, which is written by
`measure.py` against the INGESTED parquet after the merge — verify-stac.py checks declared
values against DISTINCT in the data, so they must come from the data, not from the Census
code list.

    python3 measure.py > _measured.json     # via the duckdb-geo MCP, cluster-side
    python3 gen_stac.py
"""
import json
import os

BUCKET = "public-census"
DATASET = "census-2025/roads"
NAME = "roads"          # last path segment: PMTiles source-layer, asset-key prefix
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
SRC_DIR = "https://www2.census.gov/geo/tiger/TIGER2025/ROADS/"

TITLE = "TIGER/Line Roads 2025"

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "_measured.json")) as f:
    M = json.load(f)

N_FEATURES = M["n_features"]
N_COUNTIES = M["n_counties"]
N_HEX_ROWS = M["n_hex_rows"]
BBOX = M["bbox"]
MTFCC_PRESENT = M["mtfcc"]          # sorted list of codes actually in the data
RTTYP_PRESENT = M["rttyp"]

# Census MTFCC definitions (2025 TIGER/Line technical documentation). Only the codes
# actually present in the ingested data are emitted into `values`.
MTFCC_DEFS = {
    "S1100": "Primary road — limited-access highway, interstate or other, with interchanges",
    "S1200": "Secondary road — main arterial, US/state highway, not limited access",
    "S1400": "Local neighborhood road, rural road, city street",
    "S1500": "Vehicular trail (4WD) — unpaved, navigable only by four-wheel drive",
    "S1630": "Ramp — connects roads at an interchange",
    "S1640": "Service drive — runs parallel to a limited-access highway",
    "S1710": "Walkway or pedestrian trail — NOT a motor vehicle travelway",
    "S1720": "Stairway — NOT a motor vehicle travelway",
    "S1730": "Alley — service road with no house numbers",
    "S1740": "Private road for service vehicles — logging, oil field, ranch, industrial",
    "S1750": "Internal US Census Bureau use",
    "S1780": "Parking lot road",
    "S1820": "Bike path or trail — NOT a motor vehicle travelway",
    "S1830": "Bridle path — NOT a motor vehicle travelway",
    "S2000": "Road median",
}

PEDESTRIAN = ["S1710", "S1720", "S1820", "S1830"]

MTFCC_DEF = (
    "MAF/TIGER Feature Class Code — the road classification, and the column any road analysis "
    "must filter on. **Four of these classes are not motor vehicle travelways at all**: S1710 "
    "walkway, S1720 stairway, S1820 bike path, S1830 bridle path. They are retained here so the "
    "choice stays visible, but including them in a 'distance to road' calculation is wrong under "
    "36 CFR 294.11, which defines a road as 'a motor vehicle travelway over 50 inches wide'. "
    "Values: " + "; ".join(f"{c}={MTFCC_DEFS.get(c, 'see Census TIGER/Line documentation')}"
                           for c in MTFCC_PRESENT)
)

# name, type, description, values
COLUMNS = [
    ("_cng_fid", "int64",
     f"Stable per-feature identifier assigned during conversion, unique across all "
     f"{N_FEATURES:,} road features.", None),
    ("LINEARID", "string",
     "Census permanent linear feature identifier. Stable across TIGER vintages, which makes it "
     "the key for change detection between years. Not unique within this layer: a road that "
     "crosses a county line is stored as one feature per county, and each carries the same "
     "LINEARID. Use _cng_fid to count features, LINEARID to follow a road across years.", None),
    ("FULLNAME", "string",
     "Road name as rendered by Census, including type and direction (e.g. 'N Main St', "
     "'State Hwy 20'). NULL for a large share of local and unnamed rural roads.", None),
    ("RTTYP", "string",
     "Route type code. Values: C=County, I=Interstate, M=Common name, O=Other, S=State "
     "recognized, U=US. NULL where the road carries no route designation.", RTTYP_PRESENT),
    ("MTFCC", "string", MTFCC_DEF, MTFCC_PRESENT),
    ("GEOID_COUNTY", "string",
     "Five-digit state+county FIPS code (e.g. '30029' = Flathead County, Montana), injected "
     "during ingest from the source filename. **This column does not exist in the TIGER "
     "shapefiles**, which carry only LINEARID, FULLNAME, RTTYP and MTFCC — there is otherwise no "
     "way to recover which county a road came from once the 3,233 per-county files are merged. "
     f"{N_COUNTIES:,} distinct values.", None),
]

H3_COLUMNS = [
    ("h8", "uint64",
     "H3 cell identifier at resolution 8 (native resolution for this layer, and the catalog's "
     "universal join key).", None),
    ("h0", "int64",
     "H3 cell identifier at resolution 0, used as the partition key for hive-partitioned reads.",
     None),
]

GEOM = ("geometry", "geometry", "Road centerline geometry (GeoParquet), in EPSG:4326.", None)


def cols(entries, lean=False):
    out = []
    for name, typ, desc, values in entries:
        c = {"name": name, "type": typ}
        if not lean:
            c["description"] = desc
        if values is not None:
            c["values"] = values
        out.append(c)
    return out


HEX_NOTE = (
    f"One row per (road feature, resolution 8 cell) pair — {N_HEX_ROWS:,} rows for "
    f"{N_FEATURES:,} features. Line features were hexed to H3 resolution 8 by buffering each "
    "segment by the H3 cell circumradius before polyfill.\n\n"
    "**This layer carries no per-feature length column, which removes the usual hex "
    "double-counting trap** — but the feature itself is still repeated on every cell it "
    "touches, so counts must go through `_cng_fid`:\n\n"
    "```sql\n"
    "-- correct: number of road features\n"
    "SELECT COUNT(DISTINCT _cng_fid) FROM read_parquet('…/hex/h0=*/data_0.parquet');\n"
    "-- wrong: COUNT(*) counts (feature, cell) pairs\n"
    "```\n\n"
    "**Road density per cell must come from the H3 footprint, not from a length column.** A "
    "feature's length is not apportioned across the cells it crosses.\n\n"
    "At resolution 8 (~0.7 km2 cells) essentially every developed cell in the country contains "
    "a road, so this asset is useful for joining roads to other hex layers, and close to "
    "useless as a road-scarcity indicator."
)

DESCRIPTION = (
    f"Every road in the Census Bureau's TIGER/Line 2025 road network — {N_FEATURES:,} features "
    f"across all {N_COUNTIES:,} counties and county equivalents, national including Alaska, "
    "Hawaii, Puerto Rico and the island areas. Published 2025-09-22.\n\n"
    "**This is the non-federal complement to the Forest Service road layer.** USFS RoadCore "
    "(public-usfs/roadcore-fs) contains only roads under Forest Service jurisdiction; state, "
    "county and private roads are absent from it by construction. The 2026 Roadless Rule Draft "
    "EIS buffered 'National Forest System roads and other authorized public roads' (Vol I "
    "fn. 10), and this layer supplies the second half. A road-proximity analysis run against "
    "either layer alone undercounts.\n\n"
    "**Filter on MTFCC before treating these as roads.** Four MTFCC classes are pedestrian "
    "infrastructure, not motor vehicle travelways: S1710 walkway, S1720 stairway, S1820 bike "
    "path, S1830 bridle path. They are retained at ingest so the decision stays explicit and "
    "reversible, but 36 CFR 294.11 defines a road as 'a motor vehicle travelway over 50 inches "
    "wide', so they must be excluded from any regulatory road-distance calculation:\n\n"
    "```sql\n"
    f"SELECT * FROM read_parquet('{BASE}/{DATASET}.parquet')\n"
    "WHERE MTFCC NOT IN ('S1710','S1720','S1820','S1830');\n"
    "```\n\n"
    "**GEOID_COUNTY is added by this ingest and is not in the source.** TIGER ships one "
    "shapefile per county carrying only LINEARID, FULLNAME, RTTYP and MTFCC — no FIPS code — so "
    "the county identity is only recoverable from the filename, and is lost forever once the "
    "3,233 files are merged. It is injected here at preprocess time.\n\n"
    "**For distance and buffer work, use the GeoParquet, not the hex.** Resolution 8 cells are "
    "about 0.7 km2, coarser than the buffer distances road proximity turns on (0.5 mile = "
    "805 m). Buffer in an equal-area projection, not in degrees.\n\n"
    "TIGER/Line road geometry is a cartographic representation with positional accuracy that "
    "varies by county and vintage; it is not a survey product and centerlines can be offset "
    "from the true roadway by tens of metres in rural areas."
)


def dataset_collection():
    flat_cols = cols(COLUMNS) + cols([GEOM])
    hex_cols = cols(COLUMNS) + cols(H3_COLUMNS)
    pm_cols = cols(COLUMNS, lean=True)
    extent = f"({BBOX[0]}, {BBOX[1]}, {BBOX[2]}, {BBOX[3]})"
    return {
        "stac_version": "1.0.0",
        "type": "Collection",
        "id": DATASET,
        "title": f"{TITLE} — national",
        "description": DESCRIPTION,
        "license": "public-domain",
        "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json"],
        "extent": {
            "spatial": {"bbox": [BBOX]},
            "temporal": {"interval": [["2025-01-01T00:00:00Z", "2025-12-31T23:59:59Z"]]},
        },
        "providers": [
            {"name": "US Census Bureau, Geography Division",
             "roles": ["producer", "licensor"],
             "url": "https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html"},
            {"name": "Boettiger Lab / cirrus", "roles": ["processor", "host"],
             "url": f"{BASE}/"},
        ],
        "links": [
            {"rel": "self", "href": f"{BASE}/{DATASET}/stac-collection.json",
             "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "license", "href": "https://www.usa.gov/government-works",
             "type": "text/html", "title": "US Government work — public domain"},
            {"rel": "via", "href": SRC_DIR, "type": "text/html",
             "title": "Source: Census TIGER/Line 2025 ROADS (3,233 per-county shapefiles)"},
            {"rel": "related",
             "href": "https://s3-west.nrp-nautilus.io/public-usfs/roadcore-fs/stac-collection.json",
             "type": "application/json",
             "title": "USFS RoadCore — the National Forest System half of the road network"},
        ],
        "assets": {
            f"{NAME}-parquet": {
                "href": f"{BASE}/{DATASET}.parquet",
                "type": "application/x-parquet",
                "title": f"{TITLE} {extent} — GeoParquet",
                "description":
                    f"One row per road feature ({N_FEATURES:,} rows). **This is the asset to use "
                    "for distance, buffer and proximity work** — it holds true centerline "
                    "geometry, whereas the hex is a resolution-8 approximation on ~0.7 km2 "
                    "cells, coarser than the buffer distances road proximity turns on. Buffer in "
                    "an equal-area projection (EPSG:5070 for the conterminous US, 3338 for "
                    "Alaska, 32161 for Puerto Rico), not in degrees. Filter MTFCC first.",
                "roles": ["data"],
                "table:columns": flat_cols,
            },
            f"{NAME}-pmtiles": {
                "href": f"{BASE}/{DATASET}.pmtiles",
                "type": "application/vnd.pmtiles",
                "title": f"{TITLE} {extent} — PMTiles",
                "description":
                    "Vector tiles for web mapping. At this feature count tippecanoe drops "
                    "features aggressively at low zoom (--drop-densest-as-needed), so tiles are "
                    "a display product, not a complete rendering of the layer — count and "
                    "measure against the GeoParquet.",
                "roles": ["data", "visual"],
                "vector:layers": [NAME],
                "table:columns": pm_cols,
            },
            f"{NAME}-hex": {
                "href": f"{BASE}/{DATASET}/hex/h0=*/data_0.parquet",
                "type": "application/x-parquet",
                "title": f"{TITLE} {extent} — H3 Hex (resolution 8)",
                "description": HEX_NOTE + "\n\nUse this asset to join roads against other hex "
                               "datasets in the catalog on h8 — **not** for road-proximity "
                               "distance, which belongs on the GeoParquet.",
                "roles": ["data"],
                "h3:native_resolution": 8,
                "h3:parent_resolutions": [0],
                "table:columns": hex_cols,
            },
        },
    }


if __name__ == "__main__":
    out = "/tmp/census-2025-roads-stac.json"
    with open(out, "w") as f:
        json.dump(dataset_collection(), f, indent=2)
        f.write("\n")
    print("wrote", out)
