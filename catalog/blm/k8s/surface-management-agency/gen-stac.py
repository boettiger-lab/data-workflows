#!/usr/bin/env python3
"""Write the STAC collection for BLM National Surface Management Agency (issue #561).

Writes /tmp/blm-sma-stac/stac-collection.json (never into this repo). Every number below
was measured on the published GeoParquet / hex via the duckdb-geo MCP; see BUILD.md.
Publish with:
    rclone copyto /tmp/blm-sma-stac/stac-collection.json \
        nrp:public-blm/surface-management-agency/stac-collection.json
"""
import json
import os
import sys

OUT_DIR = "/tmp/blm-sma-stac"
BASE = "https://s3-west.nrp-nautilus.io/public-blm"
DS = "surface-management-agency"

# --- measured facts (fill hex figures from BUILD.md after the hex build) ---------------
N_FEATURES = 464_680
RAW_SIZE = 1_113_064_445
RAW_SHA256 = "aede58f2d7084a77e129e090d85b9f62f8c29d9f6a526a49fe53e1de9a6e1b31"
PARQUET_CREATED = "2026-10-10T16:57:16Z"
PARQUET_SIZE = 1_369_021_750
PMTILES_CREATED = os.environ.get("PMTILES_CREATED")
PMTILES_SIZE = int(os.environ.get("PMTILES_SIZE", "0")) or None
HEX_CREATED = os.environ.get("HEX_CREATED")
HEX_ROWS = int(os.environ.get("HEX_ROWS", "0")) or None
HEX_CELLS = int(os.environ.get("HEX_CELLS", "0")) or None

# --- coded domains --------------------------------------------------------------------
# Definitions are BLM's SMA data-standard domains SMA_DOM_ADMIN_AGENCY_CODE and
# SMA_DOM_ADMIN_DEPT_CODE, read 2026-10-10 from the BLM Arizona SMA feature service
# (https://gis.blm.gov/azarcgis/rest/services/lands/BLM_AZ_SMA/FeatureServer, layer fields).
# The national file ships no domains, and the domain list in the national item's FGDC
# metadata is an older one (FS, BOR, AF) that does not match the codes in the data (USFS,
# USBR, USAF); the feature-service domain covers every code present. `values` lists only
# codes actually present in the ingested data.
AGENCY = {
    "ARMY": "Army", "BIA": "Bureau of Indian Affairs", "BLM": "Bureau of Land Management",
    "BOP": "Bureau of Prisons", "BPA": "Bonneville Power Administration",
    "DOD": "Department of Defense", "DOE": "Department of Energy",
    "DOI": "Department of the Interior", "DOT": "Department of Transportation",
    "FAA": "Federal Aviation Administration", "FHA": "Federal Housing Administration",
    "FWS": "Fish and Wildlife Service", "GSA": "General Services Administration",
    "HHS": "Department of Health and Human Services", "LG": "Local Government",
    "NAVY": "Navy", "NOAA": "National Oceanic and Atmospheric Administration",
    "NPS": "National Park Service", "NTVALL": "Alaska Native Allotment",
    "NTVPIC": "Alaska Native Lands Patented or Interim Conveyed",
    "OTHFE": "Other Federal", "PVT": "Private", "ST": "State",
    "UND": "Undetermined", "USACE": "Army Corps of Engineers", "USAF": "Air Force",
    "USBR": "Bureau of Reclamation", "USCG": "Coast Guard",
    "USDA": "Department of Agriculture", "USFS": "Forest Service", "USMC": "Marine Corps",
    "USPS": "United States Postal Service", "VA": "Department of Veterans Affairs",
}
AGENCY_PRESENT = ["UND", "ST", "NTVPIC", "FWS", "PVT", "USFS", "NPS", "BLM", "NTVALL",
                  "LG", "BIA", "ARMY", "USAF", "USCG", "OTHFE", "FAA", "USACE", "NAVY",
                  "NOAA", "USPS", "USBR", "DOD", "GSA", "USMC", "DOT", "USDA", "DOE",
                  "HHS", "FHA", "BOP", "DOI", "VA", "BPA"]
HOLD_AGENCY_PRESENT = ["BIA", "FWS", "USFS", "PVT", "NPS", "BLM", "ST", "USAF", "NAVY",
                       "USBR", "ARMY", "LG", "USMC", "USACE", "UND", "OTHFE", "DOD",
                       "USCG", "USDA"]
DEPT = {
    "DHS": "Department of Homeland Security", "DOC": "Department of Commerce",
    "DOD": "Department of Defense", "DOE": "Department of Energy",
    "DOI": "Department of the Interior", "DOJ": "Department of Justice",
    "DOT": "Department of Transportation", "HHS": "Department of Health and Human Services",
    "HUD": "Department of Housing and Urban Development", "IA": "Independent Agency",
    "LG": "Local Government", "NTVALL": "Alaska Native Allotment",
    "NTVPIC": "Alaska Native Lands Patented or Interim Conveyed", "OTHFE": "Other Federal",
    "PVT": "Private", "ST": "State", "UND": "Undetermined",
    "USDA": "Department of Agriculture", "VA": "Department of Veterans Affairs",
}
DEPT_PRESENT = ["UND", "ST", "NTVPIC", "DOI", "PVT", "USDA", "NTVALL", "LG", "DOD", "DHS",
                "OTHFE", "DOT", "DOC", "IA", "DOE", "HHS", "HUD", "DOJ", "VA"]
HOLD_DEPT_PRESENT = ["DOI", "USDA", "PVT", "ST", "DOD", "LG", "UND", "OTHFE", "DHS"]
STATE_OFFICE = {
    "AK": "Alaska", "AZ": "Arizona", "CA": "California", "CO": "Colorado",
    "ES": "Eastern States (the BLM office for the states east of the western tier)",
    "ID": "Idaho", "MT": "Montana (also North and South Dakota)",
    "NM": "New Mexico (also Oklahoma, Kansas and Texas)", "NV": "Nevada",
    "OR": "Oregon (also Washington)", "UT": "Utah", "WY": "Wyoming (also Nebraska)",
}
UNIT_TYPES = [
    "ANCSA Region", "ANCSA Village", "Agency", "Air Force Base", "Air Force Station",
    "American Indian Reservation", "Army Base", "Army Depot", "Army Training Installation",
    "Arsenal", "Aviation Center", "Branch", "Bureau of Land Management AZ",
    "Bureau of Land Management CA", "Bureau of Land Management CO",
    "Bureau of Land Management ID", "Bureau of Land Management MT",
    "Bureau of Land Management NM", "Bureau of Land Management NV",
    "Bureau of Land Management OR", "Bureau of Land Management UT",
    "Bureau of Land Management WY", "Community", "Department",
    "Ecological and Historical Preserve", "Indian Township", "Marine Corps Air Station",
    "Marine Corps Base", "Medical Center", "Military Reservation", "National Battlefield",
    "National Battlefield Park", "National Conservation Area", "National Forest",
    "National Guard Camp", "National Historic Park", "National Historic Site",
    "National Historical Park", "National Historical Park and Preserve",
    "National Lakeshore", "National Memorial", "National Military Park",
    "National Monument", "National Park", "National Parkway", "National Petroleum Reserve",
    "National Preserve", "National Recreation Area", "National River",
    "National Scenic River", "National Seashore", "National Wildlife Refuge",
    "Naval Academy", "Naval Air Station", "Naval Base", "Naval Station", "None",
    "Not Applicable", "Park", "Parkway", "Parkway and National Scenic Trail",
    "Proving Ground", "Pueblo", "Reservation", "State Community Park",
    "State Historical Park", "State Marine Park", "State Park", "State Preserve",
    "State Recreation Area", "State Special Management Area", "State Trail",
    "State Wilderness Park", "Wild River", "Wild and Scenic River", "Wilderness",
]


def coded(prefix, mapping, present):
    missing = [c for c in present if c not in mapping]
    if missing:
        sys.exit(f"codes without a definition: {missing}")
    return prefix + " Values: " + ", ".join(f"{c}={mapping[c]}" for c in present) + "."


# One text per column name, shared by every asset (the per-name fold keeps first-seen).
COLS = [
    ("_cng_fid", "int64",
     "Feature identifier added during conversion, one per source polygon (1 to 464,680). "
     "Use it to count or deduplicate polygons. It is not a BLM identifier and is not "
     "stable across editions.", None),
    ("OBJECTID", "int64",
     "Record number from the BLM file geodatabase. Not stable across BLM editions.", None),
    ("SMA_ID", "int16",
     "BLM key for the combination of administering department, agency and land "
     "designation (35 distinct values in this edition).", None),
    ("HOLD_ID", "int16",
     "BLM key for the holding department and agency. Present on the same 338 polygons "
     "that carry HOLD_AGENCY_CODE; empty on the rest.", None),
    ("ADMIN_ST", "string",
     "The BLM state office that maintains the polygon, not necessarily the state the land "
     "lies in. " + "Values: " + ", ".join(f"{k}={v}" for k, v in STATE_OFFICE.items()) + ".",
     list(STATE_OFFICE)),
    ("FAU_ID", "int16",
     "Identifier carried from the BLM source. BLM's published metadata for this layer does "
     "not define it.", None),
    ("ADMIN_UNIT_NAME", "string",
     "Name of the land designation the polygon belongs to, for example a national forest, "
     "wildlife refuge or Alaska Native corporation. Empty on 269,685 polygons, including "
     "most of the lower 48 states, where the layer stores one combined polygon per agency "
     "per state office rather than one per named unit.", None),
    ("ADMIN_UNIT_TYPE", "string",
     "Category of the land designation, for example National Forest, National Wildlife "
     "Refuge, Wilderness or ANCSA Village. Describes the designation the polygon falls "
     "inside, so a private or undetermined inholding inside a national forest can carry "
     "National Forest here; use ADMIN_AGENCY_CODE for who manages the surface. Empty on "
     "192,654 polygons. 'None' and 'Not Applicable' are values BLM recorded, distinct from "
     "an empty field.", UNIT_TYPES),
    ("ADMIN_DEPT_CODE", "string",
     coded("Department of the agency that manages the surface. Non-federal classes (state, "
           "local, private, Alaska Native, undetermined) repeat their agency code here.",
           DEPT, DEPT_PRESENT), DEPT_PRESENT),
    ("ADMIN_AGENCY_CODE", "string",
     coded("The agency that manages the surface: the main field of this layer.",
           AGENCY, AGENCY_PRESENT), AGENCY_PRESENT),
    ("HOLD_DEPT_CODE", "string",
     coded("Department of the holding agency, where BLM records one. Present on 338 of "
           "464,680 polygons.", DEPT, HOLD_DEPT_PRESENT), HOLD_DEPT_PRESENT),
    ("HOLD_AGENCY_CODE", "string",
     coded("Holding agency, where BLM records one. Present on 338 of 464,680 polygons; "
           "uses the same codes as ADMIN_AGENCY_CODE.", AGENCY, HOLD_AGENCY_PRESENT),
     HOLD_AGENCY_PRESENT),
    ("SHAPE_Length", "double",
     "Perimeter of the polygon as computed by BLM's GIS in Web Mercator metres. Web "
     "Mercator stretches distances away from the equator, so this overstates true "
     "length, increasingly so toward Alaska.", None),
    ("SHAPE_Area", "double",
     "Area of the polygon as computed by BLM's GIS in Web Mercator square metres. This is "
     "not ground area: Web Mercator inflates area by roughly 1.5 times in the southern "
     "lower 48 and about 4 times in Alaska. Compute ground area from the geometry instead, "
     "for example ST_Area_Spheroid(ST_FlipCoordinates(SHAPE)).", None),
]
GEOM = ("SHAPE", "geometry", "Polygon or multipolygon in WGS84 longitude/latitude "
        "(reprojected from Web Mercator).", None)


def col(name, typ, desc, values, lean=False):
    c = {"name": name, "type": typ}
    if not lean:
        c["description"] = desc
    if values is not None:
        c["values"] = values
    return c


flat_cols = [col(*c) for c in COLS] + [col(*GEOM)]
hex_cols = [col(*c) for c in COLS] + [
    col("h8", "uint64", "H3 cell ID at resolution 8.", None),
    col("h0", "uint64", "H3 cell ID at resolution 0, the partition key for hive-partitioned "
        "reads.", None),
]
pm_cols = [col(*c, lean=True) for c in COLS]

DESCRIPTION = f"""Which agency manages the surface of each piece of land: the Bureau of Land Management's national Surface Management Agency layer, {N_FEATURES:,} polygons classifying land by the federal agency with administrative jurisdiction over its surface (Bureau of Land Management, Forest Service, National Park Service, Fish and Wildlife Service, Bureau of Reclamation, the military services and other federal agencies), and the remaining land as state, local government, private, Alaska Native or undetermined. Converted to GeoParquet, PMTiles and an H3 hexagonal index at resolution 8.

Footprint. The layer covers the conterminous United States and Alaska wall to wall, including private and undetermined land, from latitude 24.4 to 71.4 and across the antimeridian in the Aleutians. BLM's description of the product also names Hawaii, Puerto Rico, Guam, American Samoa and the US Virgin Islands, but no polygons for them are present in this edition.

Two very different grains share the file. Alaska is mapped parcel by parcel: 463,556 polygons, most with a named designation. The lower 48 states are stored as just 1,124 large multipolygons, roughly one per agency per BLM state office, so there a single row such as Bureau of Land Management land in Nevada covers about 184,000 square kilometres and most rows have no unit name. To find a named unit in the lower 48, such as a particular national forest, use a layer that maps units, for example the Protected Areas Database of the United States; this layer answers who manages the surface, not which unit it belongs to.

ADMIN_ST is the BLM state office that maintains a polygon, not the state it lies in: Eastern States (ES) covers the whole eastern United States, and Wyoming, Montana, New Mexico and Oregon each also cover neighbouring states. Select land within a state by intersecting with a state boundary, not by filtering ADMIN_ST.

SHAPE_Area and SHAPE_Length are carried from BLM's file as published and are measured in Web Mercator, so they overstate ground area and length; compute area from the geometry or from the H3 cells.

Public domain. These are US federal government data. BLM's use terms ask that BLM be cited as the source in products derived from the data, that modifications be described, and that changes not be presented as approved by BLM; they also note the data are neither legal documents nor land surveys, and that official federal land status records should be consulted for ownership details. Modifications made here: reprojected from Web Mercator to WGS84 longitude/latitude, a feature identifier (_cng_fid) added, and H3 index and vector tiles derived. Attribute values are unchanged.

Provenance. Source: ArcGIS item 6bf2e737c59d4111be92420ee5ab0b46, "BLM National SMA Surface Management Agency Area Polygons", file SMA_WM.gdb.zip, feature class SurfaceManagementAgency. BLM publishes no edition label; the item was last modified on 2026-06-30 and was downloaded on 2026-10-10. The downloaded archive is kept at s3://public-blm/raw/SMA_WM.gdb.zip, {RAW_SIZE:,} bytes, sha256 {RAW_SHA256}. Because BLM updates this item in place without notice, that stored copy and its checksum identify this edition."""

HEX_DESC = (
    "One row per polygon and H3 cell pair at native resolution 8 (about 0.74 square "
    "kilometres per cell), with h0 as the hive partition key"
    + (f": {HEX_ROWS:,} rows covering {HEX_CELLS:,} distinct resolution 8 cells and all "
       f"{N_FEATURES:,} polygons" if HEX_ROWS else "")
    + ". Polygons smaller than one cell are assigned the single cell containing them. "
    "This asset carries h8 and h0 only.\n\n"
    "Every polygon attribute is repeated on every cell the polygon covers, so SHAPE_Area "
    "and SHAPE_Length are per-polygon values that must be deduplicated by _cng_fid before "
    "they are summed, and polygons are counted with COUNT(DISTINCT _cng_fid). For the area "
    "managed by an agency, count distinct cells and take their area from the H3 footprint:\n\n"
    "```sql\n"
    "-- land managed by the Bureau of Land Management, by distinct resolution 8 cell\n"
    "SELECT COUNT(DISTINCT h8) AS cells\n"
    f"FROM read_parquet('s3://public-blm/{DS}/hex/h0=*/data_0.parquet')\n"
    "WHERE ADMIN_AGENCY_CODE = 'BLM'\n"
    "```\n\n"
    "A cell on the boundary between two polygons appears once for each, so a per-agency "
    "breakdown of cells sums to slightly more than the distinct cells of the whole area."
)

assets = {
    f"{DS}-parquet": {
        "href": f"{BASE}/{DS}.parquet",
        "type": "application/vnd.apache.parquet",
        "title": f"GeoParquet: all {N_FEATURES:,} surface management agency polygons",
        "description": "One row per polygon with the managing agency and designation "
                       "attributes exactly as BLM publishes them. Use this asset for "
                       "polygon-level queries and exact geometry.",
        "roles": ["data"],
        "created": PARQUET_CREATED,
        "file:size": PARQUET_SIZE,
        "table:columns": flat_cols,
    },
    f"{DS}-pmtiles": {
        "href": f"{BASE}/{DS}.pmtiles",
        "type": "application/vnd.pmtiles",
        "title": "PMTiles vector tiles for web map display",
        "description": f"Vector tiles for MapLibre GL JS. The source layer is {DS}. Style "
                       "by ADMIN_AGENCY_CODE to show which agency manages the surface.",
        "roles": ["visual"],
        "vector:layers": [DS],
        "table:columns": pm_cols,
    },
    f"{DS}-hex": {
        "href": f"{BASE}/{DS}/hex/h0=*/data_0.parquet",
        "type": "application/vnd.apache.parquet",
        "title": "H3 hexagonal index (native resolution 8) of the surface management "
                 "agency polygons",
        "description": HEX_DESC,
        "roles": ["data"],
        "h3:native_resolution": 8,
        "h3:parent_resolutions": [0],
        "table:columns": hex_cols,
    },
}
if PMTILES_CREATED:
    assets[f"{DS}-pmtiles"]["created"] = PMTILES_CREATED
if PMTILES_SIZE:
    assets[f"{DS}-pmtiles"]["file:size"] = PMTILES_SIZE
if HEX_CREATED:
    assets[f"{DS}-hex"]["created"] = HEX_CREATED

stac = {
    "stac_version": "1.0.0",
    "stac_extensions": [
        "https://stac-extensions.github.io/table/v1.2.0/schema.json",
        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
    ],
    "type": "Collection",
    "id": "blm-surface-management-agency",
    "title": "BLM National Surface Management Agency (conterminous US and Alaska)",
    "description": DESCRIPTION,
    "license": "public-domain",
    "sci:citation": "Bureau of Land Management. BLM National SMA Surface Management Agency "
                    "Area Polygons. ArcGIS item 6bf2e737c59d4111be92420ee5ab0b46, last "
                    "modified 2026-06-30. Accessed 2026-10-10.",
    "keywords": ["surface management agency", "SMA", "land status", "federal lands",
                 "public lands", "land management", "BLM", "Forest Service",
                 "National Park Service", "Fish and Wildlife Service", "Alaska",
                 "United States"],
    "providers": [
        {"name": "U.S. Bureau of Land Management", "roles": ["producer", "licensor"],
         "url": "https://gbp-blm-egis.hub.arcgis.com/datasets/BLM-EGIS::blm-natl-sma-surface-management-agency-area-polygons"},
        {"name": "Boettiger Lab", "roles": ["processor", "host"],
         "url": "https://github.com/boettiger-lab/data-workflows"},
    ],
    "extent": {
        "spatial": {"bbox": [[-179.149171, 24.39630584, 179.7749131, 71.3869351]]},
        "temporal": {"interval": [["2026-06-30T00:00:00Z", "2026-06-30T00:00:00Z"]]},
    },
    "created": PARQUET_CREATED,
    "updated": HEX_CREATED or PMTILES_CREATED or PARQUET_CREATED,
    "links": [
        {"rel": "self", "href": f"{BASE}/{DS}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",
         "type": "application/json"},
        {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
        {"rel": "license", "href": "https://www.arcgis.com/home/item.html?id=6bf2e737c59d4111be92420ee5ab0b46",
         "type": "text/html", "title": "BLM use terms for the national SMA layer"},
        {"rel": "about", "href": "https://gbp-blm-egis.hub.arcgis.com/datasets/BLM-EGIS::blm-natl-sma-surface-management-agency-area-polygons",
         "type": "text/html", "title": "BLM national SMA area polygons (landing page)"},
        {"rel": "describedby", "href": "https://www.arcgis.com/sharing/rest/content/items/6bf2e737c59d4111be92420ee5ab0b46/info/metadata/metadata.xml",
         "type": "application/xml", "title": "BLM metadata (FGDC/ISO)"},
    ],
    "assets": assets,
}

os.makedirs(OUT_DIR, exist_ok=True)
with open(os.path.join(OUT_DIR, "stac-collection.json"), "w") as f:
    json.dump(stac, f, indent=2, ensure_ascii=False)
print(os.path.join(OUT_DIR, "stac-collection.json"))
