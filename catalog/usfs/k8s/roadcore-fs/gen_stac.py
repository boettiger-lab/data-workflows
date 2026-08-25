#!/usr/bin/env python3
"""Emit the roadcore-fs dataset collection to /tmp for rclone upload (AGENTS.md Hard
Boundary 1 — this repo never contains STAC JSON or README files).

One source schema (COLUMNS) is written identically to the flat GeoParquet and the hex so
the mcp-data-server#303 per-column fold never drops a variant. PMTiles gets the lean form
(name + type + values, no prose).

Every `values` list below was MEASURED from the ingested parquet on 2026-08-25, not copied
from the FGDC metadata — the data carries codes the FGDC domain does not document
(OPER_MAINT_LEVEL '0 - NOT MAINTAINED' and 'NA - NOT APPLICABLE', FUNCTIONAL_CLASS
'L - LOCAL IMPORTANT', OPENFORUSETO 'PUBLIC'), and verify-stac.py checks declared values
against DISTINCT in the data.

Register as a child of the live public-usfs bucket collection with patch_bucket_stac.py —
do NOT regenerate that collection from scratch or you will drop #585's four datasets.
"""
import json

BUCKET = "public-usfs"
DATASET = "roadcore-fs"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
SRC_ZIP = "https://data.fs.usda.gov/geodata/edw/edw_resources/shp/S_USA.RoadCore_FS.zip"
BBOX = [-149.981, 18.268, -65.730, 61.029]

TITLE = "National Forest System Roads (RoadCore)"

# Measured 2026-08-25 from s3://public-usfs/roadcore-fs.parquet
N_FEATURES = 367666
N_WITH_GEOM = 359462
N_NULL_GEOM = 8204
SEG_MILES = 368103
NULL_GEOM_MILES = 4745

ML_DEF = (
    "Operational maintenance level — the level to which the road is CURRENTLY maintained, given "
    "current needs, condition, budget and environmental concerns. This is the single most "
    "important column for any question about whether a road is usable, and level 1 is the trap: "
    "level 1 roads are closed to motor vehicle traffic and placed in storage between intermittent "
    "uses, so they are often impassable and frequently revegetated. They are 148,694 of the "
    "367,666 segments and 103,945 of the 368,103 miles — 28.2% of the system. Treating them as "
    "'existing roads' materially inflates any accessibility or road-proximity figure. Levels 3, 4 "
    "and 5 together (64,496 miles, 17.5%) are the roads maintained for standard passenger cars; "
    "level 2 alone (199,311 miles, 54.1%) is the high-clearance-vehicle network. Values: "
    "'1 - BASIC CUSTODIAL CARE (CLOSED)'=closed and stored, basic custodial maintenance only; "
    "'2 - HIGH CLEARANCE VEHICLES'=open to high-clearance vehicles; "
    "'3 - SUITABLE FOR PASSENGER CARS'=open and maintained for a prudent driver in a standard "
    "passenger car; '4 - MODERATE DEGREE OF USER COMFORT'=moderate comfort at moderate speed; "
    "'5 - HIGH DEGREE OF USER COMFORT'=high comfort and convenience; "
    "'0 - NOT MAINTAINED'=not maintained (39 segments, 18 miles); "
    "'NA - NOT APPLICABLE'=not applicable (40 segments, 29 miles). "
    "276 segments carry no value."
)

ML_VALUES = [
    "0 - NOT MAINTAINED",
    "1 - BASIC CUSTODIAL CARE (CLOSED)",
    "2 - HIGH CLEARANCE VEHICLES",
    "3 - SUITABLE FOR PASSENGER CARS",
    "4 - MODERATE DEGREE OF USER COMFORT",
    "5 - HIGH DEGREE OF USER COMFORT",
    "NA - NOT APPLICABLE",
]

OBJ_ML_VALUES = [
    "0 - NOT MAINTAINED", "1 - BASIC CUSTODIAL CARE (CLOSED)", "2 - HIGH CLEARANCE VEHICLES",
    "3 - SUITABLE FOR PASSENGER CARS", "4 - MODERATE DEGREE OF USER COMFORT",
    "5 - HIGH DEGREE OF USER COMFORT", "C - CONVERT USE", "D - DECOMMISSION",
    "NA - NOT APPLICABLE",
]

SURFACE_VALUES = [
    "AC - ASPHALT", "AGG - CRUSHED AGGREGATE OR GRAVEL", "AGG - LIMESTONE", "AGG - SCORIA",
    "BST - BITUMINOUS SURFACE TREATMENT", "CIN - CINDER SURFACE", "CSOIL - COMPACTED SOIL",
    "FSOIL - FROZEN SOIL", "GRA - GRASS (NAT)", "IMP - IMPROVED NATIVE MATERIAL",
    "NAT - NATIVE MATERIAL", "OTHER - OTHER", "P - PAVED", "PCC - PORTLAND CEMENT CONCRETE",
    "PIT - PIT RUN SHOT ROCK", "SOD - GRASS",
]

LOC_ERROR_VALUES = [
    "EMPTY ROUTE SHAPE", "MEASURE EXTENT OUT OF ROUTE MEASURE RANGE", "NO ERROR",
    "PARTIAL MATCH FOR THE FROM-MEASURE", "PARTIAL MATCH FOR THE FROM-MEASURE AND TO-MEASURE",
    "PARTIAL MATCH FOR THE TO-MEASURE", "ROUTE NOT FOUND", "ROUTE WITHOUT MEASURE",
    "ZERO LENGTH EXTENT",
]

LOC_ERROR_DEF = (
    "Diagnostic from the Forest Service's own linear-referencing step, which places each road "
    "record onto the route centerline network. This column explains every missing geometry in the "
    "layer: all 8,204 records with no geometry carry a failing value here, 7,430 of them "
    "'ROUTE NOT FOUND'. 328,420 records are 'NO ERROR'. Values: 'NO ERROR'=placed cleanly; "
    "'ROUTE NOT FOUND'=no matching route (7,430 records, all without geometry); "
    "'PARTIAL MATCH FOR THE TO-MEASURE' / 'PARTIAL MATCH FOR THE FROM-MEASURE' / "
    "'PARTIAL MATCH FOR THE FROM-MEASURE AND TO-MEASURE'=one or both endpoints only partially "
    "matched (mostly still placed); 'MEASURE EXTENT OUT OF ROUTE MEASURE RANGE'=extent outside "
    "the route's measure range; 'ROUTE WITHOUT MEASURE'=route carries no measure; "
    "'EMPTY ROUTE SHAPE'=route geometry empty; 'ZERO LENGTH EXTENT'=zero-length extent."
)

# name, type, description, values
COLUMNS = [
    ("_cng_fid", "int64",
     f"Stable per-feature identifier assigned during conversion, unique across all {N_FEATURES:,} "
     "source records. Use this as the feature key: NAME (161,472 distinct) and ID (249,414 "
     "distinct) both repeat across the segments of a single road, because one road is stored as "
     "many segments — each segment covering the stretch over which the attributes stay constant.",
     None),
    ("OGC_FID", "int64", "Sequential row identifier carried over from the source shapefile.", None),
    ("OPER_MAINT_LEVEL", "string", ML_DEF, ML_VALUES),
    ("OBJECTIVE_MAINT_LEVEL", "string",
     "Maintenance level the road is planned to be managed at in future, as distinct from the "
     "operational level it is maintained at today. Adds two codes beyond the operational scale: "
     "'C - CONVERT USE' (planned for conversion to another use) and 'D - DECOMMISSION' (planned "
     "for decommissioning). Do not use this column to judge current usability — use "
     "OPER_MAINT_LEVEL.", OBJ_ML_VALUES),
    ("SYSTEM", "string",
     "Travel-way system the route belongs to. Every record in this layer is "
     "'NFSR - NATIONAL FOREST SYSTEM ROAD': a forest road other than one authorized by a legally "
     "documented right-of-way held by a State, county or other local public road authority "
     "(36 CFR 212.1). This is why the layer alone cannot answer 'is this land near a road' — see "
     "the collection description.", ["NFSR - NATIONAL FOREST SYSTEM ROAD"]),
    ("JURISDICTION", "string",
     "Authority with the legal right to control or regulate use of the road. Every record is "
     "'FS - FOREST SERVICE'; roads under state, county or private jurisdiction are not in this "
     "layer.", ["FS - FOREST SERVICE"]),
    ("ROUTE_STATUS", "string",
     "Current physical state of the route segment. Every record is 'EX - EXISTING' — the layer "
     "contains only roads that physically exist, not planned or decommissioned alignments.",
     ["EX - EXISTING"]),
    ("FUNCTIONAL_CLASS", "string",
     "Grouping of roads by the character of service they provide. Values: 'A - ARTERIAL'=provides "
     "service to large land areas and connects with other arterial roads or public highways; "
     "'C - COLLECTOR'=collects traffic from local roads and connects to arterial roads; "
     "'L - LOCAL'=connects a terminal facility to collector or arterial roads, usually serving a "
     "single purpose; 'L - LOCAL IMPORTANT'=a local-class variant present in the data but not "
     "documented in the FGDC domain.",
     ["A - ARTERIAL", "C - COLLECTOR", "L - LOCAL", "L - LOCAL IMPORTANT"]),
    ("SURFACE_TYPE", "string",
     "Wearing course of the road. Note that three distinct aggregate descriptions share the 'AGG' "
     "prefix ('AGG - CRUSHED AGGREGATE OR GRAVEL', 'AGG - LIMESTONE', 'AGG - SCORIA') and two "
     "grass surfaces are coded differently ('SOD - GRASS', 'GRA - GRASS (NAT)'), so match on the "
     "full string rather than on the code prefix.", SURFACE_VALUES),
    ("OPENFORUSETO", "string",
     "Whether the segment is open to the public for motorized travel. Valid values: "
     "ALL=open for public motorized travel for at least part of the year; "
     "PUBLIC=open to the public (present in the data but not documented in the FGDC domain, "
     "which lists only All and Admin); "
     "ADMIN=open for Forest Service administrative use for at least part of the year and NOT "
     "open to public motorized use.", ["ADMIN", "ALL", "PUBLIC"]),
    ("SEG_LENGTH", "float64",
     f"Official length of the segment on record, in miles, derived from field measurements as "
     f"EMP minus BMP. This is the authoritative length: summing it over all {N_FEATURES:,} records "
     f"gives {SEG_MILES:,} miles, reproducing the Forest Service's published ~368,000-mile "
     "National Forest System road total. Differs from GIS_MILES, which is computed from the "
     f"drawn geometry. The {N_NULL_GEOM:,} records with no geometry still carry a real "
     f"SEG_LENGTH, totalling {NULL_GEOM_MILES:,} miles.", None),
    ("GIS_MILES", "float64",
     "Length of the drawn geometry in miles, computed by converting from decimal degrees. Sums to "
     "386,909 miles across the layer, about 5% above the official SEG_LENGTH total, and is 0 for "
     "every record without geometry. Prefer SEG_LENGTH for road-mileage accounting.", None),
    ("SHAPE_LEN", "float64",
     "Length of the segment geometry in the source projection's units.", None),
    ("BMP", "float64", "Beginning milepost of the segment along its route.", None),
    ("EMP", "float64", "Ending milepost of the segment along its route.", None),
    ("ID", "string",
     "Forest Service road number as signed and mapped, e.g. '12' or '3820-1A'. Not unique — "
     "249,414 distinct values across 367,666 segments, and road numbers repeat across forests.",
     None),
    ("NAME", "string",
     "Road name. 161,472 distinct values; one named road is normally split into many segments.",
     None),
    ("RTE_CN", "string",
     "Route control number — the Natural Resource Manager (NRM) internal identifier for the route "
     "the segment belongs to. Segments of one road share an RTE_CN, so this is the key for "
     "reassembling whole routes from segments.", None),
    ("LOC_ERROR", "string", LOC_ERROR_DEF, LOC_ERROR_VALUES),
    ("SYMBOL_CODE", "string",
     "Cartographic Feature File symbol code, derived by the Forest Service from SYSTEM, "
     "SURFACE_TYPE and OPER_MAINT_LEVEL. Valid values: "
     "106=road not maintained for passenger cars; 515=dirt road suitable for passenger car; "
     "517=paved road suitable for passenger car; 518=gravel road suitable for passenger car.",
     ["106", "515", "517", "518"]),
    ("SYMBOL_NAME", "string",
     "Human-readable form of SYMBOL_CODE.",
     ["Dirt Road, Suitable for Passenger Car", "Gravel Road, Suitable for Passenger Car",
      "Paved Road", "Road, Not Maintained for Passenger Car"]),
    ("IVM_SYMBOL", "string",
     "Integrated Visitor Map display label — the cartographic label text drawn against the "
     "segment on the rendered visitor map, typically the road number and name (e.g. "
     "'16934 - PUTT'). Effectively per-segment: 319,830 distinct strings across 367,666 "
     "records, so this is typography, not a controlled vocabulary.", None),
    ("LANES", "string",
     "Number of lanes. The source domain is inconsistent — three distinct strings all mean one "
     "lane — so normalise before grouping. Valid values: "
     "1 - SINGLE=one lane; 1 - SINGLE LANE=one lane, variant spelling; "
     "SINGLE=one lane, variant spelling; 2 - DOUBLE LANE=two lanes; 3 - THREE LANE=three lanes; "
     "4 - FOUR LANE=four lanes; 5 - FIVE LANE=five lanes.",
     ["1 - SINGLE", "1 - SINGLE LANE", "2 - DOUBLE LANE", "3 - THREE LANE", "4 - FOUR LANE",
      "5 - FIVE LANE", "SINGLE"]),
    ("SERVICE_LIFE", "string",
     "Intended service life of the road. As with LANES the source domain is inconsistent — "
     "'C- LONG TERM SERVICE' and 'C - LONG TERM SERVICE' differ only by a space.",
     ["C - LONG TERM SERVICE", "C- LONG TERM SERVICE", "I - INTERMITTENT TERM SERVICE",
      "IS - INTERMITTENT STORED SERVICE", "S - SHORT TERM SERVICE"]),
    ("LEVEL_OF_SERVICE", "string",
     "Traffic level of service, banded by average daily traffic (ADT) above or below 400.",
     ["A - FREE FLOW >400 ADT", "B - REASONABLY FREE FLOW >400 ADT",
      "C - FLOW INTERRUPTED,USE LIMITED>400 ADT", "D - SLOW FLOW, MAY BE BLOCKED >400 ADT",
      "E - UNSTABLE FLOW >400 ADT", "G - FREE FLOWING MIXED TRAFFIC <400 ADT",
      "H - CONGESTED WHEN HEAVY TRAFFIC<400 ADT", "I - FLOW INTERRUPTED,USE LIMITED<400 ADT",
      "J - SLOW FLOW OR MAY BE BLOCKED <400 ADT"]),
    ("PFSR_CLASSIFICATION", "string",
     "Public Forest Service Road classification under the Federal Lands Transportation Facility "
     "Inventory. Only two values are populated, both fiscal-year 2024 inventory labels.",
     ["FY24 FLTFI ROAD", "FY24 FLTFI ROAD - HUR-EG"]),
    ("PRIMARY_MAINTAINER", "string",
     "Entity primarily responsible for maintaining the segment (72 distinct values).", None),
    ("ADMIN_ORG", "string",
     "Forest Service administrative unit responsible for the road — a hierarchical organisation "
     "code (6 digits): region, then forest, then district (e.g. 011607 = region 01, forest 16, "
     "district 07). An identifier key rather than an enumerable class; 561 distinct values, some "
     "stored without leading zeros.", None),
    ("MANAGING_ORG", "string",
     "Forest Service organisation managing the road — the same hierarchical organisation code "
     "(6 digits) as ADMIN_ORG, and usually equal to it. An identifier key rather than an "
     "enumerable class; 551 distinct values.", None),
    ("COUNTY", "string", "County the segment lies in (741 distinct values).", None),
    ("CONGRESSIONAL_DISTRICT", "string",
     "Congressional district the segment lies in (206 distinct values).", None),
    ("SERVICE_LIFE_PLACEHOLDER", "string", "", None),  # removed below; keeps diffs honest
    ("SECURITY_ID", "string",
     "Forest Service data-security classification identifier (111 distinct values).", None),
    ("GLOBALID", "string", "Esri GlobalID assigned in the source geodatabase.", None),
]
COLUMNS = [c for c in COLUMNS if c[0] != "SERVICE_LIFE_PLACEHOLDER"]

H3_COLUMNS = [
    ("h8", "uint64",
     "H3 cell identifier at resolution 8 (native resolution for this layer, and the catalog's "
     "universal join key).", None),
    ("h0", "int64",
     "H3 cell identifier at resolution 0, used as the partition key for hive-partitioned reads.",
     None),
]

GEOM = ("geom", "geometry", "Road centerline geometry (GeoParquet), in EPSG:4326.", None)


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
    "One row per (road segment, resolution 8 cell) pair. Line features were hexed to H3 "
    "resolution 8 by buffering each segment by the H3 cell circumradius before polyfill.\n\n"
    "**Every per-segment length column — SEG_LENGTH, GIS_MILES, SHAPE_LEN — is repeated in full "
    "on every cell the segment touches.** Summing any of them over raw hex rows multiplies the "
    "road network. Deduplicate on `_cng_fid` first:\n\n"
    "```sql\n"
    "-- correct: official road miles\n"
    "SELECT SUM(SEG_LENGTH) FROM (SELECT DISTINCT _cng_fid, SEG_LENGTH\n"
    "                             FROM read_parquet('…/hex/h0=*/data_0.parquet'));\n"
    "-- correct: number of road segments\n"
    "SELECT COUNT(DISTINCT _cng_fid) FROM read_parquet('…/hex/h0=*/data_0.parquet');\n"
    "-- wrong: COUNT(*) counts (segment, cell) pairs, not segments\n"
    "-- wrong: SUM(SEG_LENGTH) over raw rows inflates the network several-fold\n"
    "```\n\n"
    "**Road density per cell must come from the H3 footprint, not from summing a repeated length "
    "column.** There is no per-cell length in this asset: a segment's length is not apportioned "
    "across the cells it crosses.\n\n"
    f"**This hex covers {N_WITH_GEOM:,} of {N_FEATURES:,} source records, and the shortfall is "
    f"legitimate.** The missing {N_NULL_GEOM:,} records have no geometry at all in the source — "
    "an upstream Forest Service linear-referencing failure flagged by the source's own LOC_ERROR "
    "column (7,430 of them 'ROUTE NOT FOUND') — so they cannot polyfill to any hex cell and are "
    "absent from the hex by necessity, not by a capped or failed build. They remain in the "
    f"GeoParquet with attributes intact, and carry {NULL_GEOM_MILES:,} official miles between "
    "them. For the same reason the five LOC_ERROR failure codes that always accompany a missing "
    "geometry never appear in this asset, though they are retained in the declared value set so "
    "the flat and hex schemas stay identical."
)

DESCRIPTION = (
    "Every existing road under Forest Service jurisdiction, as held in the Natural Resource "
    f"Manager (NRM) database and published through the Forest Service Enterprise Data Warehouse — "
    f"{N_FEATURES:,} segments totalling {SEG_MILES:,} official miles, national including Alaska "
    "and Puerto Rico. One record is one stretch of road over which the attributes stay constant, "
    "so a single road is normally many records; reassemble routes with RTE_CN.\n\n"
    "**Maintenance level is not optional detail — it decides what the layer means.** Level 1 "
    "roads are closed to motor vehicles and held in storage, often impassable and frequently "
    "revegetated, and they are 103,945 miles, 28.2% of the system. Any statement of the form "
    "'this land is near an existing road' changes substantially depending on whether level 1 is "
    "counted. Report road-proximity results broken out by OPER_MAINT_LEVEL, not only in "
    "aggregate. The maintenance-level split reproduces the Forest Service's own published "
    "figures: 64,496 miles (17.5%) at levels 3-5 accommodate standard passenger cars, and "
    "199,311 miles (54.1%) at level 2 are the high-clearance network.\n\n"
    "**This layer is Forest Service roads only, and that is a real limit.** SYSTEM is 'NFSR' and "
    "JURISDICTION is 'FS' on every record: state, county, and private roads are absent by "
    "construction. Inventoried roadless areas abut roads the Forest Service does not administer, "
    "so a proximity analysis run on this layer alone undercounts. The 2026 Roadless Rule Draft "
    "EIS buffered 'National Forest System roads and other authorized public roads' (Vol I fn. 10); "
    "the non-NFS half of that is published separately as Census TIGER/Line roads in "
    "public-census. Note also that 36 CFR 294.11 defines a road more broadly still — including "
    "unclassified and temporary roads — and the Forest Service maintains no national database of "
    "temporary roads (DEIS fn. 20), so no layer, including this one, can reproduce the regulatory "
    "definition at national scale.\n\n"
    f"**{N_NULL_GEOM:,} of the {N_FEATURES:,} records have no geometry** and carry "
    f"{NULL_GEOM_MILES:,} official miles between them. This is an upstream linear-referencing "
    "failure, flagged by the source's own LOC_ERROR column — 7,430 are 'ROUTE NOT FOUND'. Those "
    "records appear in the GeoParquet (attributes intact) but cannot appear in the hex or "
    "PMTiles, and cannot be buffered in a distance analysis by anyone, including the agency.\n\n"
    "**For distance and buffer work, use the GeoParquet, not the hex.** Resolution 8 cells are "
    "about 0.7 km2, which is coarser than the buffer distances that matter for road proximity "
    "(0.5 mile = 805 m), so hex adjacency is not a substitute for true geometry distance. The hex "
    "asset exists to join this layer against other catalog datasets on h8.\n\n"
    "The published date of the snapshot is 2025-05-11. The Forest Service makes no warranty as to "
    "accuracy or completeness, and these data are not legal documents: they may not be used to "
    "determine title, ownership, legal descriptions, boundaries or jurisdiction."
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
            "temporal": {"interval": [["2025-05-11T00:00:00Z", None]]},
        },
        "providers": [
            {"name": "USDA Forest Service, Natural Resource Manager (NRM)",
             "roles": ["producer", "licensor"],
             "url": "https://data.fs.usda.gov/geodata/edw/datasets.php"},
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
            {"rel": "via", "href": SRC_ZIP, "type": "application/zip",
             "title": "Source shapefile (Forest Service EDW)"},
            {"rel": "describedby", "href": f"{BASE}/raw/S_USA.RoadCore_FS.shp.xml",
             "type": "application/xml", "title": "FGDC metadata as published with the source"},
            {"rel": "related",
             "href": f"{BASE}/roadless-areas-2001/stac-collection.json",
             "type": "application/json",
             "title": "Inventoried Roadless Areas (2001 Roadless Rule)"},
            {"rel": "related",
             "href": "https://s3-west.nrp-nautilus.io/public-census/census-2025/roads/stac-collection.json",
             "type": "application/json",
             "title": "Census TIGER/Line roads 2025 — the non-NFS half of the road network"},
        ],
        "assets": {
            f"{DATASET}-parquet": {
                "href": f"{BASE}/{DATASET}.parquet",
                "type": "application/x-parquet",
                "title": f"{TITLE} {extent} — GeoParquet",
                "description":
                    f"One row per source record ({N_FEATURES:,} rows; {N_WITH_GEOM:,} carry "
                    "geometry). **This is the asset to use for distance, buffer and proximity "
                    "work** — it holds true centerline geometry, whereas the hex is a resolution-8 "
                    "approximation on ~0.7 km2 cells, coarser than the buffer distances road "
                    "proximity turns on. Buffer in an equal-area projection (EPSG:5070 for the "
                    "conterminous US, 3338 for Alaska, 32161 for Puerto Rico), not in degrees.",
                "roles": ["data"],
                "table:columns": flat_cols,
            },
            f"{DATASET}-pmtiles": {
                "href": f"{BASE}/{DATASET}.pmtiles",
                "type": "application/vnd.pmtiles",
                "title": f"{TITLE} {extent} — PMTiles",
                "description":
                    f"Vector tiles for web mapping, covering the {N_WITH_GEOM:,} records that have "
                    "geometry. Style on OPER_MAINT_LEVEL to distinguish the drivable network from "
                    "closed level-1 roads.",
                "roles": ["data", "visual"],
                "vector:layers": [DATASET],
                "table:columns": pm_cols,
            },
            f"{DATASET}-hex": {
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
    out = f"/tmp/{DATASET}-stac.json"
    with open(out, "w") as f:
        json.dump(dataset_collection(), f, indent=2)
        f.write("\n")
    print("wrote", out)
