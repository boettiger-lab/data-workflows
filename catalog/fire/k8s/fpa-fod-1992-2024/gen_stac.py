#!/usr/bin/env python3
"""Generate stac-collection.json for FPA-FOD 7th edition, 1992-2024 (issue #587).

Source: Short, Karen C. 2026. *Spatial wildfire occurrence data for the United States,
1992-2024 [FPA_FOD_20260615]*, 7th Edition. Forest Service Research Data Archive.
DOI 10.2737/RDS-2013-0009.7

Column descriptions and coded domains come from `_codes.json`, which is generated from the
upstream `Data/_variable_descriptions.csv` shipped inside the source zip, plus the domains for
NWCG_GENERAL_CAUSE / OWNER_DESCR that upstream does NOT enumerate and which were therefore read
off the ingested data (never written from memory -- #294).

Writes /tmp/stac-collection.json. Then:
  scripts/verify-stac.py --no-data /tmp/stac-collection.json
  scripts/lint-stac-categorical.py /tmp/stac-collection.json
  scripts/lint-stac-pmtiles-fields.py /tmp/stac-collection.json
  rclone copyto /tmp/stac-collection.json nrp:public-fire/fpa-fod-1992-2024/stac-collection.json
"""
import json
import pathlib

HERE = pathlib.Path(__file__).parent
C = json.loads((HERE / "_codes.json").read_text())
B = C["build"]

BASE = "https://s3-west.nrp-nautilus.io/public-fire"
DS = "fpa-fod-1992-2024"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"

UP = C["descriptions"]        # upstream prose, keyed "Fires:COL" / "units:COL"
DOM = C["domains"]            # upstream-enumerated domains
LBL = C["domain_labels"]      # value -> label
DAT = C["data_domains"]       # domains discovered from the ingested data


def values_for(key):
    """Domain values for a column: upstream if enumerated, else discovered from data."""
    return DOM.get(key) or DAT.get(key)


def labelled(key):
    """'CODE=Definition, ...' suffix from the upstream domain labels, when we have them."""
    lab = LBL.get(key)
    if not lab:
        return ""
    return " Values: " + ", ".join(f"{k}={v}" for k, v in lab.items()) + "."


def enumerated(key):
    """'Values: a, b, c.' suffix for a domain read off the data (no upstream definitions)."""
    vals = DAT.get(key)
    return " Values: " + ", ".join(vals) + "." if vals else ""


# --- Fires layer: (name, duckdb_type, description, domain_key) ------------------------------
# Types read from the source GPKG via ogrinfo (fpa-fod-stage-raw schema probe).
def u(col, extra=""):
    return UP[f"Fires:{col}"] + extra


COLS = [
    ("_cng_fid", "BIGINT",
     "Synthetic unique row identifier assigned during conversion. One ignition record = one "
     "_cng_fid, and the same numbering is shared by the GeoParquet, PMTiles and hex assets, so "
     "it is the stable join key between them.", None),
    ("OBJECTID", "BIGINT", "Row identifier carried over from the source file. Unique within its own table, "
     "but not a stable upstream key -- cite FOD_ID to identify a fire, and use _cng_fid "
     "to join between the ignition assets.", None),
    ("FOD_ID", "INTEGER", u("FOD_ID") + " This is the upstream record key; it is stable across "
     "editions for a given fire report and is the id to cite when referring to one fire.", None),
    ("FPA_ID", "VARCHAR", u("FPA_ID") + " Because it encodes the contributing source system, it "
     "is the best available proxy for how a record's coordinates were obtained, and therefore "
     "for its positional precision (see the collection description).", None),
    ("SOURCE_SYSTEM_TYPE", "VARCHAR", u("SOURCE_SYSTEM_TYPE") + labelled("Fires:SOURCE_SYSTEM_TYPE"),
     "Fires:SOURCE_SYSTEM_TYPE"),
    ("SOURCE_SYSTEM", "VARCHAR", u("SOURCE_SYSTEM"), None),
    ("NWCG_REPORTING_AGENCY", "VARCHAR", u("NWCG_REPORTING_AGENCY")
     + labelled("Fires:NWCG_REPORTING_AGENCY"), "Fires:NWCG_REPORTING_AGENCY"),
    ("NWCG_REPORTING_UNIT_ID", "VARCHAR", u("NWCG_REPORTING_UNIT_ID")
     + " Joins to UnitId in the companion NWCG unit table, which resolves the unit to its "
       "department, agency and geographic area.", None),
    ("NWCG_REPORTING_UNIT_NAME", "VARCHAR", u("NWCG_REPORTING_UNIT_NAME")
     + " For selecting a class of units (all National Forest System units, say), join on "
       "NWCG_REPORTING_UNIT_ID rather than matching this free text.", None),
    ("SOURCE_REPORTING_UNIT", "VARCHAR", u("SOURCE_REPORTING_UNIT")
     + " Carried verbatim across contributing agencies with no harmonisation, so each source "
       "system uses its own coding and the value set is heterogeneous rather than a controlled "
       "vocabulary. Use NWCG_REPORTING_UNIT_ID for a harmonised unit key.", None),
    ("SOURCE_REPORTING_UNIT_NAME", "VARCHAR", u("SOURCE_REPORTING_UNIT_NAME")
     + " Carried verbatim across contributing agencies with no harmonisation, so spellings and "
       "abbreviations vary between source systems. Use NWCG_REPORTING_UNIT_NAME for the "
       "harmonised name.", None),
    ("LOCAL_FIRE_REPORT_ID", "VARCHAR", u("LOCAL_FIRE_REPORT_ID"), None),
    ("LOCAL_INCIDENT_ID", "VARCHAR", u("LOCAL_INCIDENT_ID"), None),
    ("FIRE_CODE", "VARCHAR", "Interagency firecode used to track emergency fire-suppression "
     "expenditures; joins to the interagency firecode system at https://www.firecode.gov/. A "
     "per-incident accounting key rather than a thematic class, so it is not enumerated here.",
     None),
    ("FIRE_NAME", "VARCHAR", u("FIRE_NAME"), None),
    ("ICS_209_PLUS_INCIDENT_JOIN_ID", "VARCHAR", u("ICS_209_PLUS_INCIDENT_JOIN_ID"), None),
    ("ICS_209_PLUS_COMPLEX_JOIN_ID", "VARCHAR", u("ICS_209_PLUS_COMPLEX_JOIN_ID"), None),
    ("MTBS_ID", "VARCHAR", u("MTBS_ID")
     + " Populated only for fires large enough to have an MTBS perimeter, so it is a join key "
       "to the MTBS collections in this bucket, not a completeness indicator.", None),
    ("MTBS_FIRE_NAME", "VARCHAR", u("MTBS_FIRE_NAME"), None),
    ("COMPLEX_NAME", "VARCHAR", u("COMPLEX_NAME"), None),
    ("FIRE_YEAR", "SMALLINT", u("FIRE_YEAR")
     + f" Ranges {B['fire_year_min']}-{B['fire_year_max']} in this edition.", None),
    ("DISCOVERY_DATE", "TIMESTAMPTZ", u("DISCOVERY_DATE"), None),
    ("DISCOVERY_DOY", "INTEGER", u("DISCOVERY_DOY"), None),
    ("DISCOVERY_TIME", "VARCHAR", u("DISCOVERY_TIME")
     + " Stored as a 4-character hhmm string, not a time type; frequently blank.", None),
    ("NWCG_CAUSE_CLASSIFICATION", "VARCHAR", u("NWCG_CAUSE_CLASSIFICATION") + "."
     + labelled("Fires:NWCG_CAUSE_CLASSIFICATION")
     + " This is the coarse human/natural split; NWCG_GENERAL_CAUSE gives the specific cause.",
     "Fires:NWCG_CAUSE_CLASSIFICATION"),
    ("NWCG_GENERAL_CAUSE", "VARCHAR", u("NWCG_GENERAL_CAUSE")
     + " Follows the NWCG wildfire-cause standard approved in August 2020."
     + enumerated("Fires:NWCG_GENERAL_CAUSE")
     + " Upstream metadata does not enumerate this field, so these values were read from the "
       "ingested data.", "Fires:NWCG_GENERAL_CAUSE"),
    ("NWCG_CAUSE_AGE_CATEGORY", "VARCHAR", u("NWCG_CAUSE_AGE_CATEGORY")
     + " Set to Minor where the cause was attributed to a child (0-12) or adolescent (13-17), "
       "and null otherwise, so a null is 'not attributed to a minor', not missing data. "
       "Minor is the only value stored; upstream metadata also lists Null, which denotes the "
       "absent case rather than a value found in the column.",
     "Fires:NWCG_CAUSE_AGE_CATEGORY"),
    ("CONT_DATE", "TIMESTAMPTZ", u("CONT_DATE"), None),
    ("CONT_DOY", "INTEGER", u("CONT_DOY"), None),
    ("CONT_TIME", "VARCHAR", u("CONT_TIME"), None),
    ("FIRE_SIZE", "DOUBLE", u("FIRE_SIZE")
     + " Acres. This is the size of the whole fire, recorded on its point of origin; it is not "
       "an area within the hex cell holding the point.", None),
    ("FIRE_SIZE_CLASS", "VARCHAR", u("FIRE_SIZE_CLASS") + labelled("Fires:FIRE_SIZE_CLASS"),
     "Fires:FIRE_SIZE_CLASS"),
    ("LATITUDE", "DOUBLE", u("LATITUDE"), None),
    ("LONGITUDE", "DOUBLE", u("LONGITUDE"), None),
    ("OWNER_DESCR", "VARCHAR", u("OWNER_DESCR")
     + " Values: USFS=USDA Forest Service, BLM=Bureau of Land Management, NPS=National Park "
       "Service, FWS=US Fish and Wildlife Service, BIA=Bureau of Indian Affairs, BOR=Bureau of "
       "Reclamation, OTHER FEDERAL=another federal agency, UNDEFINED FEDERAL=federal but agency "
       "not recorded, STATE=state government, COUNTY=county government, MUNICIPAL/LOCAL="
       "municipal or other local government, STATE OR PRIVATE=state or private, not "
       "distinguished in the report, TRIBAL=tribal land, PRIVATE=private ownership, "
       "Private=private ownership (a lowercase variant of PRIVATE appearing on 2 records), "
       "FOREIGN=outside the United States, MISSING/NOT SPECIFIED=not recorded."
     + " Upstream metadata does not enumerate this field, so these values were read from the "
       "ingested data. Note that PRIVATE and Private both occur, so compare case-insensitively.",
     "Fires:OWNER_DESCR"),
    ("STATE", "VARCHAR", u("STATE")
     + " This is a two-letter US state/territory postal abbreviation. Values follow the postal "
       "standard, with one upstream inconsistency: Oklahoma appears as both OK and lowercase ok, "
       "so compare case-insensitively.", None),
    ("COUNTY", "VARCHAR", u("COUNTY"), None),
    ("FIPS_CODE", "VARCHAR", "County FIPS code (5 digits), from Federal Information Processing "
     "Standards publication 6-4, based on the nominal designation in the fire report rather than "
     "a spatial overlay. An identifier for a county, not a thematic class, so it is not "
     "enumerated here.", None),
    ("FIPS_NAME", "VARCHAR", u("FIPS_NAME"), None),
    ("Shape", "GEOMETRY", "Point location of the fire's origin (GeoParquet geometry), "
     "reprojected from the source NAD83 (EPSG:4269) to EPSG:4326. The column keeps the name it "
     "has in the source GeoPackage.", None),
]

TYPE_MAP = {
    "BIGINT": "int64", "INTEGER": "int32", "SMALLINT": "int16",
    "DOUBLE": "double", "VARCHAR": "string", "TIMESTAMP": "timestamp",
    "TIMESTAMPTZ": "timestamp", "GEOMETRY": "geometry",
}

H3_COLS = [
    {"name": "h10", "type": "uint64",
     "description": "H3 cell identifier at resolution 10, the native resolution of this hex asset."},
    {"name": "h9", "type": "uint64",
     "description": "H3 cell identifier at resolution 9, a parent rollup of h10."},
    {"name": "h8", "type": "uint64",
     "description": "H3 cell identifier at resolution 8, a parent rollup and the resolution most "
                    "other collections in this catalog can be joined at."},
    {"name": "h0", "type": "int64",
     "description": "H3 cell identifier at resolution 0, used as the hive partition key for the "
                    "hex dataset."},
]


# tippecanoe coarsens attribute types, so a timestamp arrives in the tiles as a string.
PMTILES_TYPE_MAP = {"timestamp": "string"}


def col_entry(name, dtype, desc, dom_key, lean=False):
    t = TYPE_MAP[dtype]
    if lean:
        t = PMTILES_TYPE_MAP.get(t, t)
    e = {"name": name, "type": t}
    if not lean:
        e["description"] = desc
    vals = values_for(dom_key) if dom_key else None
    if vals:
        e["values"] = vals
    return e


geoparquet_cols = [col_entry(*c) for c in COLS]
# Hex: same columns and the SAME per-column prose (the renderer folds identical text across
# assets and silently drops divergent text), minus geometry, plus the H3 index columns.
hex_cols = [col_entry(*c) for c in COLS if c[0] != "Shape"] + H3_COLS
# PMTiles: MIRROR the GeoParquet schema, in lean form (name/type/values, no prose -- the prose
# stays canonical on the GeoParquet asset). Verified against the published tile footer: tippecanoe
# keeps every attribute column, so the tile field set is exactly the GeoParquet columns minus the
# geometry. Hand-curating a subset here would hide stylable fields from MapLibre authors and the
# geo-agent, which is the defect #283/#320 exist to prevent.
pmtiles_cols = [col_entry(*c, lean=True) for c in COLS if c[0] != "Shape"]

# --- companion non-spatial NWCG unit lookup -------------------------------------------------
UNIT_COLS = [
    ("OBJECTID", "BIGINT", "Row identifier carried over from the source file. Unique within its own table, "
     "but not a stable upstream key -- cite FOD_ID to identify a fire, and use _cng_fid "
     "to join between the ignition assets.", None),
    ("UnitId", "VARCHAR", "NWCG unit identifier. Joins to NWCG_REPORTING_UNIT_ID on the ignition "
     "records.", None),
    ("GeographicArea", "VARCHAR", UP["units:GeographicArea"] + labelled("units:GeographicArea"),
     "units:GeographicArea"),
    ("GACC", "VARCHAR", UP["units:GACC"] + labelled("units:GACC"), "units:GACC"),
    ("WildlandRole", "VARCHAR", UP["units:WildlandRole"]
     + enumerated("units:WildlandRole"), "units:WildlandRole"),
    ("UnitType", "VARCHAR", UP["units:UnitType"]
     + enumerated("units:UnitType"), "units:UnitType"),
    ("Department", "VARCHAR", UP["units:Department"] + labelled("units:Department"),
     "units:Department"),
    ("Agency", "VARCHAR", UP["units:Agency"] + labelled("units:Agency"), "units:Agency"),
    ("Country", "VARCHAR", UP["units:Country"] + labelled("units:Country"), "units:Country"),
    ("State", "VARCHAR", UP["units:State"]
     + " A two-letter US state/territory postal abbreviation.", None),
    ("Code", "VARCHAR", UP["units:Code"]
     + " A per-unit identifier that joins to the agency's own unit records, not a thematic "
       "class, so it is not enumerated here.", None),
    ("Name", "VARCHAR", UP["units:Name"], None),
]
unit_cols = [col_entry(*c) for c in UNIT_COLS]

N = B["feature_count"]

DESCRIPTION = f"""\
**Every wildfire ignition reported in the United States from 1992 to 2024** -- {N:,} georeferenced
records, each a point at a fire's origin, compiled by the USDA Forest Service from the reporting
systems of federal, state and local fire organizations. This is the Fire Program Analysis
fire-occurrence database (FPA FOD), 7th edition, and it represents about 209 million acres burned
over the 33-year period.

Its purpose is counting and locating **ignitions**: how many fires started, where, when, and what
started them. `NWCG_GENERAL_CAUSE` and `NWCG_CAUSE_CLASSIFICATION` carry the cause attribution,
which is what makes the dataset usable for questions about human versus natural ignition.

**This is the ignition census for this catalog.** The MTBS collections in this bucket record
burned area and severity for fires above a size threshold, so they answer "how much burned and how
badly" but cannot answer "how many fires started" -- counting MTBS perimeters undercounts
ignitions badly, because the great majority of fires here are small. The two link per fire through
`MTBS_ID`: take counts from this collection and burned extent or severity from MTBS.

**Positional precision -- the main way to over-claim from this dataset.** A record was included if
it had a point location at least as precise as a Public Land Survey System section, which is a
1-square-mile (about 1.6 km) grid cell. Some coordinates are therefore only accurate to roughly
1.6 km, and the dataset carries no per-record precision flag. Two consequences:

- Distance bands finer than about 1 km cannot be resolved for the imprecise subset, so a
  distance-to-road or distance-to-boundary curve at that resolution is not defensible without
  either restricting to high-precision records or stating the smoothing applied.
- `FPA_ID` encodes the contributing source system and is the best available proxy for how a
  coordinate was obtained; grouping by it is the practical way to isolate a
  higher-precision subset.

**Coverage.** National, including Alaska, Hawaii, Puerto Rico and Pacific territories. The 7th
edition added records from states and territories that were previously underrepresented, Guam
among them, so counts for years before 2021 differ from earlier editions -- this edition is not
simply four more years appended to the 6th.

**Nominal versus spatial geography.** `STATE`, `COUNTY`, `FIPS_CODE` and `FIPS_NAME` come from the
fire report as filed, not from a spatial overlay on the point. Where the two disagree, a spatial
join against a boundary layer is authoritative and these fields are not.

**Provenance.** Downloaded {B['accessed']} from the Forest Service Research Data Archive,
DOI 10.2737/RDS-2013-0009.7, as `{B['source_zip']}`
({B['source_zip_bytes']:,} bytes, sha256 `{B['source_zip_sha256']}`), staged at
`s3://public-fire/raw/{B['inner_gpkg']}`. Built from the `{B['layers']['fires']}` layer;
geometry reprojected from NAD83 to EPSG:4326.
"""

HEX_DESCRIPTION = f"""\
Hive-partitioned H3 hex parquet, partitioned by `h0`. Point observations were hexed to H3
resolution 10, so each fire resolves to exactly one cell of about 15,000 m2 and one row. Multiple
fires falling in the same cell are not deduplicated -- several rows can share an `h10` value, and
that is the intended representation, since each row is a distinct ignition.

Because one point produces exactly one cell, per-fire values are not replicated across cells the
way polygon attributes are. Counting and summing over cells therefore behave as expected:
`COUNT(*)` grouped by a cell is the number of ignitions in it, and `SUM(FIRE_SIZE)` is the total
final size of the fires that started there. Note that `FIRE_SIZE` is the whole fire's acreage
recorded at its origin, not burned area inside the cell -- for burned extent use the MTBS
collections.

Ignition density is the ratio a stratified comparison wants: join to a boundary layer at `h8`,
count ignitions per stratum, and divide by the stratum's H3 footprint area.
"""

collection = {
    "type": "Collection",
    "stac_version": "1.0.0",
    "stac_extensions": [
        "https://stac-extensions.github.io/table/v1.2.0/schema.json",
        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
        "https://stac-extensions.github.io/version/v1.2.0/schema.json",
    ],
    "id": DS,
    "title": "FPA FOD: US wildfire ignition points, 1992-2024 (7th edition)",
    "description": DESCRIPTION,
    "license": "public-domain",
    "version": "7",
    "keywords": ["wildfire", "fire occurrence", "ignitions", "fire cause", "FPA FOD",
                 "USFS", "United States", "points"],
    "providers": [
        {"name": "USDA Forest Service, Rocky Mountain Research Station",
         "roles": ["producer", "licensor"],
         "url": "https://www.fs.usda.gov/rds/archive/products/RDS-2013-0009.7"},
        {"name": "Karen C. Short", "roles": ["producer"],
         "url": "https://orcid.org/0000-0002-3383-0460"},
        {"name": "Boettiger Lab / cirrus", "roles": ["processor", "host"],
         "url": "https://s3-west.nrp-nautilus.io/public-fire/"},
    ],
    "sci:doi": "10.2737/RDS-2013-0009.7",
    "sci:citation": (
        "Short, Karen C. 2026. Spatial wildfire occurrence data for the United States, 1992-2024 "
        "[FPA_FOD_20260615], 7th Edition. Fort Collins, CO: Forest Service Research Data Archive. "
        f"https://doi.org/10.2737/RDS-2013-0009.7 (accessed {B['accessed']})."
    ),
    "extent": {
        # Overall bbox is antimeridian-crossing: the record set runs from Guam eastward across the
        # Pacific to Puerto Rico, so the west edge has a LARGER longitude than the east edge, per
        # the GeoJSON/STAC convention. Regional boxes follow for consumers that want a tight
        # extent per area. Values measured from the ingested data.
        "spatial": {"bbox": [
            # Overall extent CROSSES THE ANTIMERIDIAN, so the west edge (Guam, +144.639) has a
            # larger longitude than the east edge (US Virgin Islands, -64.7677), per the
            # GeoJSON/STAC convention. Writing it as -178.8 -> +144.9 instead would claim 324
            # degrees of longitude for a record set that spans about 151.
            B["bbox_overall_antimeridian"],
            B["bbox_western_hemisphere"],   # CONUS, Alaska, Hawaii, Puerto Rico, US Virgin Islands
            B["bbox_guam"],                 # Guam, added in the 7th edition
        ]},
        "temporal": {"interval": [[f"{B['fire_year_min']}-01-01T00:00:00Z",
                                   f"{B['fire_year_max']}-12-31T00:00:00Z"]]},
    },
    "links": [
        {"rel": "self", "href": f"{BASE}/{DS}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": ROOT, "type": "application/json"},
        {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
        {"rel": "license", "href": "https://www.usa.gov/government-works", "type": "text/html",
         "title": "US Government work -- public domain"},
        {"rel": "about", "href": "https://doi.org/10.2737/RDS-2013-0009.7", "type": "text/html",
         "title": "FPA FOD 7th edition -- Forest Service Research Data Archive"},
        {"rel": "cite-as", "href": "https://doi.org/10.2737/RDS-2013-0009.7"},
    ],
    "assets": {
        f"{DS}-parquet": {
            "href": f"{BASE}/{DS}.parquet",
            "type": "application/x-parquet",
            "title": "FPA FOD ignition points, 1992-2024 -- GeoParquet",
            "roles": ["data"],
            "description": (
                f"Flat GeoParquet, {N:,} rows, one row per wildfire ignition record. The full "
                "attribute set including cause, dates, final fire size and reporting unit."
            ),
            "table:primary_geometry": "Shape",
            "table:columns": geoparquet_cols,
        },
        f"{DS}-pmtiles": {
            "href": f"{BASE}/{DS}.pmtiles",
            "type": "application/vnd.pmtiles",
            "title": "FPA FOD ignition points, 1992-2024 -- PMTiles (web map)",
            "roles": ["visual"],
            "description": (
                f"Vector tiles for MapLibre GL JS. The MapLibre source-layer id is '{DS}'. "
                "Good default fields for styling are NWCG_CAUSE_CLASSIFICATION or "
                "NWCG_GENERAL_CAUSE for cause, FIRE_SIZE_CLASS or FIRE_SIZE for magnitude, and "
                "FIRE_YEAR for time filtering. The tiles carry every attribute column, so any "
                "field listed below can be styled or filtered directly; the column definitions "
                "are on the GeoParquet asset."
            ),
            "vector:layers": [DS],
            "table:columns": pmtiles_cols,
        },
        f"{DS}-hex": {
            "href": f"{BASE}/{DS}/hex/h0=*/data_0.parquet",
            "type": "application/x-parquet",
            "title": "FPA FOD ignition points, 1992-2024 -- H3 hex (resolution 10)",
            "roles": ["data"],
            "description": HEX_DESCRIPTION,
            "h3:native_resolution": 10,
            "h3:parent_resolutions": [9, 8, 0],
            "table:columns": hex_cols,
        },
        f"{DS}-nwcg-units": {
            "href": f"{BASE}/{DS}-nwcg-units.parquet",
            "type": "application/x-parquet",
            "title": "NWCG reporting-unit lookup (non-spatial)",
            "roles": ["metadata"],
            "description": (
                "Non-spatial lookup table shipped with the source (5,971 units), resolving an "
                "NWCG unit identifier to its department, agency, wildland role, geographic area "
                "and coordination centre. Join UnitId to NWCG_REPORTING_UNIT_ID on the ignition "
                "records to select a class of reporting units. Forest Service units carry "
                "Agency = 'FS', which is how the National Forest System stratum is defined "
                "without matching unit-name text:\n\n"
                "```sql\n"
                "SELECT f.NWCG_GENERAL_CAUSE, COUNT(*) AS ignitions\n"
                f"FROM read_parquet('s3://public-fire/{DS}.parquet') f\n"
                f"JOIN read_parquet('s3://public-fire/{DS}-nwcg-units.parquet') u\n"
                "  ON f.NWCG_REPORTING_UNIT_ID = u.UnitId\n"
                "WHERE u.Agency = 'FS'\n"
                "GROUP BY 1 ORDER BY 2 DESC;\n"
                "```\n\n"
                "The unit is the organisation that filed the report, which is not always the "
                "landowner at the point of origin -- OWNER_DESCR on the ignition records carries "
                "that, and the two can disagree."
            ),
            "table:columns": unit_cols,
        },
    },
}

if __name__ == "__main__":
    import sys
    if collection["extent"]["spatial"]["bbox"] is None:
        sys.exit("bbox is unset: measure it from the ingested data and fill BBOX in before "
                 "publishing (see the comment on extent.spatial).")
    out = pathlib.Path("/tmp/stac-collection.json")
    out.write_text(json.dumps(collection, indent=2))
    print(f"wrote {out}")
    print(f"  geoparquet cols: {len(geoparquet_cols)}")
    print(f"  hex cols:        {len(hex_cols)}")
    print(f"  pmtiles cols:    {len(pmtiles_cols)}")
    print(f"  unit cols:       {len(unit_cols)}")
