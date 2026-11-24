#!/usr/bin/env python3
"""Write the STAC collection for public-usfws/species-ranges (#944) to the path given.

    gen_species_ranges_stac.py OUT.json

Writes to a local path only; a publish job uploads it (AGENTS.md Hard Boundary 1). Every number is
measured: the staged raw's size and sha256 by stage-raw.yaml, feature, row and value counts on the
built files through duckdb-geo (2026-11-17), object sizes and dates read live from S3 here.
"""
import json
import sys
import urllib.request
from email.utils import parsedate_to_datetime

S3 = "https://s3-west.nrp-nautilus.io"
BASE = f"{S3}/public-usfws"
SRC = "https://ecos.fws.gov/docs/species/shapefiles/usfws_complete_species_current_range.zip"


def head(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["Content-Length"]), parsedate_to_datetime(
            r.headers["Last-Modified"]).strftime("%Y-%m-%dT%H:%M:%SZ")


STATUS = [  # STATUS_ABB, measured counts 2026-11-17
    ("Endangered", 1212), ("Threatened", 372), ("Resolved Taxon", 224), ("Species of Concern", 144),
    ("Under Review", 84), ("Recovery", 59), ("Experimental Population, Non-Essential", 58),
    ("Status Undefined", 46), ("Not Listed", 27), ("Proposed Endangered", 22),
    ("Proposed Threatened", 21), ("Extinction", 12), ("Similarity of Appearance (Threatened)", 6),
    ("Original Data in Error - Not a listable entity", 4), ("Pre-Act Delisted Taxon", 3),
    ("Original Data in Error - Taxonomic Revision", 1),
    ("Original Data in Error - New Information Discovered", 1),
    ("Proposed Similarity of Appearance (Threatened)", 1),
]
VIP = ["P01", "I01", "V01", "V02", "I02", "V03", "I03", "V04", "V05", "V06", "V11", "V12", "V13",
       "V16", "V20"]

COLUMNS = [
    ("_cng_fid", "int64", "Feature ID assigned during conversion, one per range polygon."),
    ("fid", "int64", "Row number in the merged source file."),
    ("RANGE_NOTE", "string", "FWS note on the range's scale. Every range in this release carries the "
     "same note: 'This range has been defined at a scale of finer resolution than \"statewide\"'."),
    ("RANGE_ID", "int64", "FWS identifier of the range polygon; unique per row."),
    ("ENTITY_ID", "int64", "ECOS entity ID of the species or listed population; unique per row, and "
     "the key that joins to ECOS species pages and to the critical habitat layers."),
    ("SPCODE", "string", "FWS four-character species code. A species with several listed "
     "populations has one SPCODE and several ENTITY_IDs."),
    ("VIPCODE", "string", "Taxonomic group and population number: the first letter is V=vertebrate, "
     "I=invertebrate, P=plant; the digits number the listed populations of one species (01 for the "
     "first). Values: " + ", ".join(VIP) + "."),
    ("COMNAME", "string", "Common name."),
    ("SCINAME", "string", "Scientific name."),
    ("POP_ABBREV", "string", "The listed population, where the listing covers part of a species' "
     "range (for example 'U.S.A. (portions of NC and TN)'); empty for whole-species entities."),
    ("STATUS_ABB", "string", "Status of the species or population in FWS's ECOS system. Values: "
     + ", ".join(f"{s} ({n} ranges)" for s, n in STATUS) + "."),
    ("FAMILY", "string", "Taxonomic family."),
    ("geom_bbox", "struct", "Bounding box of the range (xmin, ymin, xmax, ymax), for fast spatial filtering."),
    ("geom", "geometry", "Range polygon in WGS84 (EPSG:4326)."),
    ("h8", "uint64", "H3 cell ID at resolution 8 (about 0.74 square kilometres)."),
    ("h0", "int64", "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."),
]
ATTRS = [c[0] for c in COLUMNS if c[0] not in ("geom_bbox", "geom", "h8", "h0")]
TILE_TYPE = {"int64": "Number", "string": "String"}


def main(out):
    pq_size, pq_time = head(f"{BASE}/species-ranges.parquet")
    pm_size, pm_time = head(f"{BASE}/species-ranges.pmtiles")
    dic = []
    for name, typ, desc in COLUMNS:
        c = {"name": name, "type": typ, "description": desc}
        if name == "STATUS_ABB":
            c["values"] = [s for s, _ in STATUS]
        if name == "VIPCODE":
            c["values"] = VIP
        dic.append(c)
    doc = {
        "type": "Collection", "stac_version": "1.1.0", "id": "usfws-species-ranges",
        "title": "USFWS Current Species Ranges",
        "description": (
            "Current range of every species and population that the U.S. Fish and Wildlife Service "
            "tracks in its Environmental Conservation Online System (ECOS): 2,297 range polygons, one "
            "per species entity, covering the United States and its territories. Species ranges are "
            "the first check in an Endangered Species Act Section 7 review of a federal action, as in "
            "FWS's Information for Planning and Consultation (IPaC) screening.\n\n"
            "It is broader than the list of protected species. Of the 2,297 ranges, 1,212 are "
            "Endangered, 372 Threatened and 43 proposed for listing; the rest are species under "
            "review, of concern, recovered, delisted or resolved taxonomically, and experimental "
            "populations. Filter on STATUS_ABB to the statuses that matter for a question.\n\n"
            "```sql\n-- listed and proposed species whose range includes one cell (Santa Monica Mountains, CA: 27 listed)\n"
            "SELECT DISTINCT SCINAME, COMNAME, STATUS_ABB\n"
            f"FROM read_parquet('{BASE}/species-ranges/hex/h0=*/data_0.parquet')\n"
            "WHERE h8 = 613221929121218559\n"
            "  AND STATUS_ABB IN ('Endangered', 'Threatened', 'Proposed Endangered', 'Proposed Threatened');\n```\n\n"
            "Every range carries FWS's note that it is defined at a scale finer than statewide. A "
            "range is where a species may occur, not a survey of where it does.\n\n"
            f"Provenance: FWS download {SRC} (Last-Modified 2026-11-12, accessed 2026-11-17), staged "
            "at s3://public-usfws/raw/usfws_complete_species_current_range.zip (2,736,742,848 bytes, "
            "sha256 60ed98c9668a85bd0d7fb9313efbb0eef8cd2f459a924b968e23ac34f00bac16). The zip holds "
            "two shapefiles with the same columns (1,000 and 1,297 ranges), merged into one table "
            "and reprojected from NAD83 to WGS84."),
        "license": "public-domain",
        "keywords": ["endangered species", "threatened species", "species range", "ESA", "IPaC",
                     "USFWS", "ECOS", "Section 7"],
        "providers": [
            {"name": "U.S. Fish and Wildlife Service (USFWS)", "roles": ["producer", "licensor"],
             "url": "https://ecos.fws.gov/"},
            {"name": "Boettiger Lab", "roles": ["processor", "host"],
             "url": "https://boettigerlab.berkeley.edu"},
        ],
        "sci:citation": ("U.S. Fish and Wildlife Service. (2026). Current ranges of species in the "
                         "Environmental Conservation Online System (usfws_complete_species_current_range, "
                         "updated 2026-11-12) [Data set]. " + SRC + ". Accessed 2026-11-17."),
        "stac_extensions": [
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
            "https://stac-extensions.github.io/vector/v0.1.0/schema.json",
        ],
        "extent": {"spatial": {"bbox": [[-180.0, -14.548729, 180.0, 74.706736]]},
                   "temporal": {"interval": [["2026-11-12T00:00:00Z", "2026-11-12T00:00:00Z"]]}},
        "created": pq_time, "updated": pm_time,
        "table:columns": dic,
        "assets": {
            "species-ranges-parquet": {
                "href": f"{BASE}/species-ranges.parquet", "type": "application/x-parquet",
                "title": "USFWS Current Species Ranges — GeoParquet", "roles": ["data"],
                "description": "One row per range polygon (2,297 rows).",
                "created": pq_time, "file:size": pq_size, "table:row_count": 2297,
                "table:columns": [{"name": n, "type": t} for n, t, _ in COLUMNS if n not in ("h8", "h0")],
            },
            "species-ranges-pmtiles": {
                "href": f"{BASE}/species-ranges.pmtiles", "type": "application/vnd.pmtiles",
                "title": "USFWS Current Species Ranges — PMTiles", "roles": ["data", "visual"],
                "description": "Vector tiles of the range polygons for web maps; overlapping ranges are drawn on top of one another.",
                "created": pm_time, "file:size": pm_size, "vector:layers": ["species-ranges"],
                "table:columns": [{"name": n, "type": TILE_TYPE[t]} for n, t, _ in COLUMNS if n in ATTRS],
            },
            "species-ranges-hex": {
                "href": f"{BASE}/species-ranges/hex/h0=*/data_0.parquet", "type": "application/x-parquet",
                "title": "USFWS Current Species Ranges — H3 hex (resolution 8)", "roles": ["data"],
                "description": (
                    "One row per (range, H3 resolution 8 cell): 132,961,215 rows over 28.6 million "
                    "distinct cells. Every attribute of a range is repeated on every cell the range "
                    "covers, and ranges of different species overlap, so count species with "
                    "COUNT(DISTINCT ENTITY_ID) and area from distinct h8 cells, never by summing rows."),
                "h3:native_resolution": 8, "h3:parent_resolutions": [0], "table:row_count": 132961215,
                "table:columns": [{"name": n, "type": t} for n, t, _ in COLUMNS if n != "geom"],
            },
        },
        "links": [
            {"rel": "self", "href": f"{BASE}/species-ranges/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": f"{S3}/public-data/stac/catalog.json", "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "about", "href": "https://ecos.fws.gov/", "type": "text/html",
             "title": "FWS Environmental Conservation Online System"},
            {"rel": "license", "href": "https://www.usa.gov/government-copyright", "type": "text/html",
             "title": "US Government works are in the public domain"},
            {"rel": "pmtiles", "href": f"{BASE}/species-ranges.pmtiles", "type": "application/vnd.pmtiles",
             "title": "USFWS Current Species Ranges", "pmtiles:layers": ["species-ranges"]},
        ],
    }
    with open(out, "w") as fh:
        fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
