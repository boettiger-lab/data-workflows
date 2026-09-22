#!/usr/bin/env python3
"""Generate the `ugs-uranium` STAC collection for public-utah (issue #708).

One collection with five sub-layers, each carrying a GeoParquet + PMTiles + H3 hex asset
(15 assets total):

  districts        uranium districts, interpretive           (polygon,  58; native res 8)
  area-boundaries  Colorado Plateau uranium areas            (polygon,  15; native res 8)
  past-producers   past uranium producers, USGS CRIB schema  (point,  748; native res 8)
  permitted-mines  permitted uranium/vanadium mines          (point,   25; native res 8)
  mills            uranium/vanadium processing mills         (point,    2; native res 8)

Column authority is written IDENTICALLY on the flat GeoParquet and the hex (mcp-data-server
#303 dedups identical per-column text, first-seen wins). PMTiles assets carry the lean
name/type/values only. Categorical `values` come from the ingested DISTINCT measured
2026-09-22 against the published parquet (the verify-stac data check re-enforces the match).

Writes /tmp/ugs-uranium-stac-collection.json. STAC never lives in the repo (AGENTS.md Hard
Boundary 1) -- upload with rclone and validate with scripts/verify-stac.py.

License: CC-BY-4.0, stated verbatim in the `licenseInfo` of all five AGOL items (verified
2026-09-22), distributed by UGRC/SGID.
"""
import json

BASE = "https://s3-west.nrp-nautilus.io/public-utah"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
BUCKET_SELF = f"{BASE}/stac-collection.json"
SELF = f"{BASE}/ugs-uranium/stac-collection.json"
ACCESSED = "2026-09-22"

# ---------------------------------------------------------------------------------------
# Shared column authority -- identical text everywhere the column appears (#303 fold).
# ---------------------------------------------------------------------------------------
GEOM = {"name": "geom", "type": "geometry",
        "description": "Feature geometry (GeoParquet, EPSG:4326 / OGC:CRS84)."}
CNG_FID = {"name": "_cng_fid", "type": "int64",
           "description": "Synthetic per-feature id (one per source feature, row-unique). "
                          "Dedup / COUNT(DISTINCT) key across the (feature, H3 cell) rows "
                          "on the hex."}
OGC_FID = {"name": "OGC_FID", "type": "int64",
           "description": "GDAL feature id carried through conversion (provenance only; "
                          "use `_cng_fid` as the canonical per-feature dedup key)."}

# Shared between districts and area-boundaries, so the text must stay grain-neutral.
NAME_SHARED = ("Feature name as published by the Utah Geological Survey. Not unique: on the "
               "districts layer the La Sal district is published as two polygons sharing the "
               "name. Use `_cng_fid` to count features.")
ID_SHARED = ("Upstream integer identifier. Largely unpopulated (0 for 50 of 58 districts and "
             "13 of 15 areas) and not a usable key or join column; kept for fidelity with the "
             "source. Use `_cng_fid` instead.")


def hidx(native=8):
    """H3 index columns: native resolution plus the h0 partition key."""
    return [
        {"name": f"h{native}", "type": "uint64",
         "description": f"H3 cell ID at resolution {native} (native resolution; one row per "
                        f"(feature, cell) pair)."},
        {"name": "h0", "type": "int64",
         "description": "H3 cell ID at resolution 0; hive partition key."},
    ]


def col(name, type_, desc, values=None, codes=None):
    """One column entry.

    `codes` is a list of (code, definition) pairs: it renders an inline
    "Values: CODE=Definition, ..." clause onto the description AND supplies the `values`
    array, so the two can never drift apart. `values` alone is for columns whose value
    text is its own definition (geographic names), where an inline map would be noise.
    """
    if codes is not None:
        desc = desc + " Values: " + ", ".join(f"{c}={d}" for c, d in codes) + "."
        values = [c for c, _ in codes]
    c = {"name": name, "type": type_, "description": desc}
    if values is not None:
        c["values"] = values
    return c


UNDEF = "not defined by the publisher"


# ---------------------------------------------------------------------------------------
# Column names that appear on MORE THAN ONE sub-layer must carry ONE text collection-wide:
# the mcp-data-server #303 fold keeps the first-seen text per column NAME and drops the
# rest, and verify-stac HARD-fails divergence. So these texts span every layer they appear
# on, and layer-specific grain lives in the asset `description`. `values` is checked
# per-asset against that asset's own parquet, so it still varies by layer.
# ---------------------------------------------------------------------------------------
SHARED = {
    "NAME": NAME_SHARED,
    "ID": ID_SHARED,
    "COUNTY": "Utah county names, as published upstream in upper case. Past producers also carries one compound value, EMERY (GRAND), on 3 records that straddle the county line.",
    "OPERATOR": "Operating company as published upstream. Historical: reflects the operator "
                "recorded at the time of the source compilation, not present-day ownership.",
    "TOWNSHIP": "Public Land Survey System township of the site, as published upstream. "
                "Formatting is not consistent between layers (for example 'S37' on permitted "
                "mines, '36S' on mills), so it is a label rather than a join key.",
    "RANGE": "Public Land Survey System range of the site, as published upstream. Formatting "
             "is not consistent between layers (for example 'E24' on permitted mines, '22E' "
             "on mills), so it is a label rather than a join key.",
    "SECTION": "Public Land Survey System section number of the site, as published upstream.",
    "UTM_N": "UTM northing recorded in the source compilation, in metres. Provenance only: "
             "use `geom` for position. On past producers this is 0 for the 26 records that "
             "carry geometry but no attributes.",
    "UTM_E": "UTM easting recorded in the source compilation, in metres. Provenance only: "
             "use `geom` for position. On past producers this is 0 for the 26 records that "
             "carry geometry but no attributes.",
    "MERIDIAN": "Public Land Survey System meridian of the site, as published upstream. "
                "Values: S=Salt Lake meridian.",
    "STATUS": "Status code, with a different meaning on each layer it appears on. On "
              "permitted mines it is the mine permit status published by the Utah Division "
              "of Oil, Gas and Mining (ACT = active, SUS = suspended). On past producers it "
              "is the USGS CRIB 'status of exploration or development' item (A20), an "
              "integer whose code-to-category mapping could not be established: CRIB "
              "Circular 755-B publishes four development categories while this layer carries "
              "eight distinct values, and 0 marks the 26 records that have geometry but no "
              "attributes. Treat the past-producer integers as opaque rather than ordered. "
              "Values: ACT=active permit, SUS=suspended permit, 0=record carries geometry "
              "but no attributes, 1=undefined by the publisher, 2=undefined by the "
              "publisher, 3=undefined by the publisher, 4=undefined by the publisher, "
              "6=undefined by the publisher, 7=undefined by the publisher, 8=undefined by "
              "the publisher.",
}

# ---------------------------------------------------------------------------------------
# districts / area-boundaries
# ---------------------------------------------------------------------------------------
POTENTIAL_DESC = (
    "Uranium potential class assigned to the district by the Utah Geological Survey: "
    "High, Moderate, Low, or None. 'None' is a substantive assessment meaning no uranium "
    "potential was assigned, not a missing value; three districts (Castle Peaks Draw, "
    "Oljeto Mesa and Comb Ridge) are genuinely unclassified and are NULL. The criteria "
    "behind the classes are not documented by the publisher: they are absent from the "
    "ArcGIS Online item metadata, from the FGDC record (which lists the field with no "
    "attribute definition), from the UGRC product page, and from UGS Map 215, the source "
    "map, whose legend carries no potential classification. Use the classes as the "
    "publisher's qualitative judgement and do not infer thresholds from them."
)
NUMBER_DESC = (
    "Map label number for the district, ranging 1 to 17. Applied only to the districts "
    "rated High (1 to 5) and Moderate (6 to 17); every district rated Low or None, and "
    "every unclassified district, carries 0. Numbers repeat where one district is drawn as "
    "several polygons, and two differently named districts share the number 3, so this is "
    "a cartographic label rather than a key or a rank."
)

DISTRICTS_COLS = [
    CNG_FID, OGC_FID,
    col("ID", "int32", SHARED["ID"]),
    col("NAME", "string", SHARED["NAME"]),
    col("POTENTIAL", "string", POTENTIAL_DESC,
        codes=[("High", "high uranium potential"),
               ("Moderate", "moderate uranium potential"),
               ("Low", "low uranium potential"),
               ("None", "no uranium potential assigned (an assessment, not a missing "
                        "value)")]),
    col("NUMBER", "int32", NUMBER_DESC),
]

AREAS_COLS = [
    CNG_FID, OGC_FID,
    col("ID", "int32", SHARED["ID"]),
    col("NAME", "string", SHARED["NAME"]),
]

# ---------------------------------------------------------------------------------------
# mills / permitted-mines
# ---------------------------------------------------------------------------------------
MILLS_COLS = [
    CNG_FID, OGC_FID,
    col("MILL_ID", "string", "Mill identifier assigned by the Utah Division of Oil, Gas and "
                             "Mining."),
    col("NAME", "string", SHARED["NAME"]),
    col("OPERATOR", "string", SHARED["OPERATOR"]),
    col("TOWNSHIP", "string", SHARED["TOWNSHIP"]),
    col("RANGE", "string", SHARED["RANGE"]),
    col("SECTION", "int32", SHARED["SECTION"]),
    col("UTM_N", "int32", SHARED["UTM_N"]),
    col("UTM_E", "int32", SHARED["UTM_E"]),
    col("COUNTY", "string", SHARED["COUNTY"], values=["GARFIELD", "SAN JUAN"]),
]

MINES_COLS = [
    CNG_FID, OGC_FID,
    col("MINEID", "string", "Mine identifier assigned by the Utah Division of Oil, Gas and "
                            "Mining."),
    col("COUNTY", "string", SHARED["COUNTY"], values=["SAN JUAN", "GARFIELD"]),
    col("TYPE", "string", "Single-letter mine class code. It is always the first character "
                          "of `MINEID` (true for all 25 records) and moves exactly with "
                          "`MIN_TYPE` (S with BM, M with EM). The publisher does not define "
                          "what the letters stand for, so treat them as opaque class labels.",
        codes=[("S", UNDEF), ("M", UNDEF)]),
    col("NUM", "string", "Permit sequence number within the mine identifier. Populated for "
                         "7 of 25 records."),
    col("STATUS", "string", SHARED["STATUS"], values=["ACT", "SUS"]),
    col("NAME", "string", SHARED["NAME"]),
    col("OPERATOR", "string", SHARED["OPERATOR"]),
    col("PRODUCT", "string", "Commodities covered by the permit.",
        codes=[("URANIUM", "uranium only"),
               ("URANIUM, VANADIUM", "uranium and vanadium")]),
    col("MIN_TYPE", "string", "Two-letter mine class code. It moves exactly with `TYPE` "
                              "(BM with S, EM with M), partitioning the layer 14 / 11. The "
                              "publisher does not define what the codes stand for, so treat "
                              "them as opaque class labels.",
        codes=[("BM", UNDEF), ("EM", UNDEF)]),
    col("PERM_STAT", "string", "Permit application status, populated on 7 of 25 records.",
        codes=[("APP", "approved")]),
    col("MSU", "string", "Mineral surface use code, populated on 7 of 25 records.",
        codes=[("U", UNDEF), ("S", UNDEF)]),
    col("SURF_OWN", "string", "Surface owner, populated on 7 of 25 records "
                              "(BLM = Bureau of Land Management).", values=["BLM"]),
    col("MIN_OWN", "string", "Mineral estate owner, populated on 7 of 25 records "
                             "(BLM = Bureau of Land Management, FEE = private fee estate).",
        values=["BLM", "FEE"]),
    col("CONTACT", "string", "Permit contact person recorded by the permitting authority, "
                             "populated on 7 of 25 records."),
    col("OPER_ID", "int32", "Operator identifier assigned by the permitting authority; 0 "
                            "where not assigned (18 of 25 records)."),
    col("ACR_REL", "int32", "Acres released from the permit. 0 on every record in this "
                            "layer, so it carries no information here."),
    col("EASTING", "int32", "UTM easting recorded on the permit, in metres. Provenance "
                            "only: use `geom` for position."),
    col("NORTHING", "int32", "UTM northing recorded on the permit, in metres. Provenance "
                             "only: use `geom` for position."),
    col("MERIDIAN", "string", SHARED["MERIDIAN"], values=["S"]),  # inline map in SHARED
    col("TOWNSHIP", "string", SHARED["TOWNSHIP"]),
    col("RANGE", "string", SHARED["RANGE"]),
    col("SECTION", "string", SHARED["SECTION"]),
]


# ---------------------------------------------------------------------------------------
# past-producers: the USGS CRIB record. Field meanings follow Keefer, E.K. and Calkins,
# J.A., 1978, "Description of individual data items and codes in CRIB": USGS Circular
# 755-B (https://doi.org/10.3133/cir755B); CRIB item labels are given in brackets so a
# reader can look any field up in that document.
#
# The production and reserve tables are the trap on this layer. Circular 755-B defines
# five separate tables, and RESERVES AND POTENTIAL RESOURCES is the WHOLE of which
# RESERVES ONLY and POTENTIAL RESOURCES are the two parts -- so adding all three double
# counts a deposit. On top of that each amount is a packed list, in thousands of units.
# ---------------------------------------------------------------------------------------
SEP = "ý"

PACKED = (
    " Packed multi-value field: several entries are stored in one string separated by the "
    "character U+00FD ('ý'), positionally parallel to the other packed fields of the "
    "same table."
)

AMT_DESC = (
    "Amount reported in the {table} table [CRIB {labels}], expressed in THOUSANDS of the "
    "unit named in the matching entry of `{u}` -- Circular 755-B: \"the figure given must "
    "be multiplied by 1,000 to obtain the production figures in single units\"."
    + PACKED +
    " Stored as text, and not summable as it stands: units differ between entries of a "
    "single record (one record mixes LB and ST), unit spellings differ between records "
    "(LB, LBS, ST, TONS), the entries cover different commodities per `{item}` (uranium, "
    "vanadium, ore, concentrate), and the entry counts of the amount, unit and item fields "
    "disagree in 30 records, so the three cannot always be zipped positionally. Parse all "
    "three fields together and normalise before any arithmetic."
)

BLOCKS = [
    ("AP",  "ANNUAL PRODUCTION (ore and commodities)", "D1-D7",
     "production in a single named year"),
    ("CP",  "CUMULATIVE PRODUCTION (ore, commodities, concentrates)", "G7-G15",
     "production summed over a range of years"),
    ("RPR", "RESERVES AND POTENTIAL RESOURCES", "E1-E6",
     "the TOTAL current resources of the deposit -- reserves plus potential resources "
     "together, so this is the whole of which `R_AMT` and `PR_AMT` are the two parts"),
    ("R",   "RESERVES ONLY", "H1-H6",
     "the reserves portion of the total resources"),
    ("PR",  "POTENTIAL RESOURCES (exclusive of reserves)", "J1-J6",
     "the non-reserve portion of the total resources"),
]

DOUBLE_COUNT = (
    " Reserves are reported in three overlapping tables: `RPR_*` is the total, `R_*` is its "
    "reserves part and `PR_*` its potential-resources part, so adding all three counts the "
    "same material twice."
)


def crib_block(prefix, table, labels, meaning):
    """The six-to-eight parallel fields CRIB writes for one production/reserve table."""
    cols = [
        col(f"{prefix}_ITEM", "string",
            f"Commodity reported in the {table} table [CRIB {labels}] -- {meaning}. "
            f"Commodity codes from Circular 755-B list E, with qualifiers such as ACC "
            f"(accumulated), EST (estimated), ORE and CON (concentrate)." + PACKED),
        col(f"{prefix}_ACC", "string",
            f"Accuracy qualifier for the matching entry of `{prefix}_AMT` in the {table} "
            f"table [CRIB {labels}]: whether the figure is accurate, estimated or averaged, "
            f"or where no figure was available whether the amount was small, medium or "
            f"large." + PACKED),
        col(f"{prefix}_AMT", "string",
            AMT_DESC.format(table=table, labels=labels, u=f"{prefix}_U",
                            item=f"{prefix}_ITEM")
            + (DOUBLE_COUNT if prefix in ("RPR", "R", "PR") else "")),
        col(f"{prefix}_U", "string",
            f"Unit for the matching entry of `{prefix}_AMT` in the {table} table [CRIB "
            f"{labels}]. Spellings are inconsistent across records (LB, LBS, ST, TONS). "
            f"Circular 755-B also allows a scale word here -- a unit of MIL TONS means the "
            f"amount is in millions rather than thousands." + PACKED),
        col(f"{prefix}_YEAR", "string",
            f"Year, or year range, of the matching entry of `{prefix}_AMT` in the {table} "
            f"table [CRIB {labels}]." + PACKED),
        col(f"{prefix}_GRADE", "string",
            f"Grade, or use, of the matching entry of `{prefix}_AMT` in the {table} table "
            f"[CRIB {labels}]." + PACKED),
    ]
    return cols


CRIB_HEAD = [
    col("ZID", "string", "Upstream record key carried from the UGS compilation. Empty on "
                         "the 26 records that have geometry but no attributes."),
    col("REC_NO", "string", "CRIB record number [CRIB B10], the identifier of the record in "
                            "the USGS Computerized Resources Information Bank."),
    col("REC_TYPE", "string", "CRIB record type [CRIB B20]. Circular 755-B marks the "
                              "record-type code list (list A) as discontinued and gives no "
                              "definitions, so these codes are opaque.",
        codes=[("X1N", UNDEF), ("X1M", UNDEF), ("X1B", UNDEF), ("X1", UNDEF),
               ("X2B", UNDEF)]),
    col("DEP_NUM", "string", "Deposit number [CRIB B40]."),
    col("REP_DATE", "string", "Date the record was reported or last updated [CRIB G1/G3], "
                              "as published (year and month, not a parseable date type)."),
    col("INFO_SRC", "string", "Primary source file when the record was drawn from another "
                              "compilation [CRIB B30]. Populated on 14 records."),
    col("FIL_LINK", "string", "File link identifier, naming another file holding more "
                              "information on this locality [CRIB B50]."),
    col("REP", "string", "Name of the reporter who compiled the record [CRIB G2]."),
    col("REP_AFF", "string", "Affiliation of the reporter [CRIB G4]."),
    col("SYN", "string", "Synonym name(s) for the deposit [CRIB A11]."),
    col("DIST", "string", "Mining district, area or subdistrict containing the site [CRIB "
                          "A30]. 132 distinct values. These are CRIB district names and do "
                          "not correspond to the `districts` layer of this collection, "
                          "which has 58 polygons under different names; there is no shared "
                          "key between them."),
    col("COUNTY", "string", SHARED["COUNTY"],
        values=["BEAVER", "EMERY", "EMERY (GRAND)", "GARFIELD", "GRAND", "JUAB", "KANE",
                "PIUTE", "SALT LAKE", "SAN JUAN", "SEVIER", "UINTAH", "UTAH", "WASHINGTON",
                "WAYNE"]),
    col("STATE", "string", "State code [CRIB A50], on every record that carries "
                           "attributes.", codes=[("UT", "Utah")]),
    col("COUNTRY", "string", "Country code [CRIB A40].",
        codes=[("US", "United States")]),
    col("PHYS", "string", "Physiographic province [CRIB A63]."),
    col("DRAIN", "string", "Drainage area [CRIB A62]."),
    col("LAND_ST", "string", "Land classification or ownership status recorded at the time "
                             "of compilation [CRIB A64]. Historical: not a current land "
                             "status."),
    col("QUAD1", "string", "Primary topographic quadrangle name [CRIB A90]."),
    col("Q1_SCALE", "string", "Scale of the primary quadrangle [CRIB A100]."),
    col("QUAD2", "string", "Secondary topographic quadrangle name [CRIB A92]."),
    col("Q2_SCALE", "int32", "Scale of the secondary quadrangle [CRIB A91]; 0 where absent."),
    col("ELEV", "string", "Altitude of the site as published [CRIB A101]."),
    col("UTM_N", "int32", SHARED["UTM_N"]),
    col("UTM_E", "int32", SHARED["UTM_E"]),
    col("UTM_Z", "int32", "UTM zone of `UTM_N` / `UTM_E` [CRIB A110]; 0 for the 26 records "
                          "that carry geometry but no attributes."),
    col("ACC", "string", "Accuracy of the recorded position [CRIB, list G]."),
    col("TOWNSHIP", "string", SHARED["TOWNSHIP"]),
    col("RANGE", "string", SHARED["RANGE"]),
    col("SECTION", "string", SHARED["SECTION"]),
    col("SECT_FRACT", "string", "Fractional part of the section locating the site within it. "
                                "Populated on 9 records."),
    col("MERIDIAN", "string", SHARED["MERIDIAN"]),
    col("POSITION", "string", "Position relative to the nearest prominent locality [CRIB "
                              "A82]."),
    col("LOCATION", "string", "Free-text location comments [CRIB A83]."),
    col("SITE_NAME", "string", "Deposit or site name [CRIB A10]."),
    col("LAT", "string", "Latitude as published in the source compilation, in "
                         "degrees-minutes-seconds text [CRIB A70]. Provenance only: use "
                         "`geom` for position."),
    col("LONG", "string", "Longitude as published in the source compilation, in "
                          "degrees-minutes-seconds text [CRIB A80]. Provenance only: use "
                          "`geom` for position."),
]


CRIB_BODY = [
    col("COMMOD", "string", "Commodities present at the site [CRIB C10], as commodity codes "
                            "from Circular 755-B list E. 31 distinct combinations."),
    col("ORE_MAT", "string", "Ore materials: the minerals or rocks carrying the commodity "
                             "[CRIB C30]."),
    col("COM_SUB", "string", "Commodity subtype or use notes [CRIB C41]. Free text, "
                             "populated on 3 records."),
    col("GEN_ANAL", "string", "General analytical data for the site [CRIB C43]."),
    col("COM_INFO", "string", "Commodity comments [CRIB C50]. Populated on 20 records."),
    col("MAJOR", "string", "Commodities present as a MAJOR constituent [CRIB C15 "
                           "significance]."),
    col("MINOR", "string", "Commodities present as a MINOR constituent [CRIB C15 "
                           "significance]."),
    col("POTEN", "string", "Commodities present as a POTENTIAL resource [CRIB C15 "
                           "significance]. This is a commodity-significance field and is "
                           "unrelated to the `POTENTIAL` column on the districts layer, "
                           "which is a district-level uranium potential class; the two "
                           "share no values and must not be joined."),
    col("OCCUR", "string", "Commodities present only as an OCCURRENCE [CRIB C15 "
                           "significance]."),
    col("NP_MAIN", "string", "Main non-producing commodity noted for the site. Populated on "
                             "6 records."),
    col("NP_MINOR", "string", "Minor non-producing commodity noted for the site. Populated "
                              "on 4 records."),
    col("PROD", "string",
        "Whether the site has produced [CRIB PROD]. Values: Y=production has occurred, "
        "N=no production past or present as of the reported date, L=large production, "
        "M=medium production, S=small production, U=not defined in Circular 755-B "
        "(2 records). Circular 755-B notes the reporter judged large, medium and small "
        "subjectively, so L, M and S are not a measured scale and carry no thresholds.",
        values=["S", "M", "L", "N", "Y", "U"]),
    col("LOCAL_STRU", "string", "Local structural setting of the deposit [CRIB, local "
                                "geology]."),
    col("STATUS", "int32", SHARED["STATUS"],
        values=["0", "1", "2", "3", "4", "6", "7", "8"]),  # inline map in SHARED
    col("DISC", "string", "Who made the discovery [CRIB L20]. Populated on 67 records."),
    col("YR_DISC", "string", "Year of discovery [CRIB L10], as published text. Populated on "
                             "159 records, spanning 1893 to 1972."),
    col("NAT_DISC", "string", "Nature of the discovery [CRIB L30]."),
    col("YR_1ST_PRO", "string", "Year of first production [CRIB L40], as published text. "
                                "Populated on 55 records, spanning 1894 to 1977."),
    col("YR_LAST_PR", "string", "Year of last production. Populated on 1 record."),
    col("OWNER", "string", "Present or last owner at the time of compilation [CRIB A12]. "
                           "Historical: not present-day ownership."),
    col("OPER", "string", "Present or last operator at the time of compilation [CRIB A13]. "
                          "Historical: not a present-day operator."),
    col("EXPL_COM", "string", "Exploration and development comments [CRIB L110]."),
    col("DEP_TYPE", "string", "Deposit type [CRIB C40]."),
    col("DEP_FORM", "string", "Form or shape of the deposit [CRIB M10]."),
    col("DEPTH_TOP", "string", "Depth to the top of the deposit, in the unit given by "
                               "`DEP_T_U`."),
    col("DEP_T_U", "string", "Unit for `DEPTH_TOP`."),
    col("DEPTH_BOT", "string", "Depth to the bottom of the deposit, in the unit given by "
                               "`DEP_B_U`."),
    col("DEP_B_U", "string", "Unit for `DEPTH_BOT`."),
    col("MAX_LEN", "string", "Maximum length of the deposit, in the unit given by `M_L_U`."),
    col("M_L_U", "string", "Unit for `MAX_LEN`."),
    col("MAX_WID", "string", "Maximum width of the deposit, in the unit given by `M_W_U`."),
    col("M_W_U", "string", "Unit for `MAX_WID`."),
    col("MAX_THICK", "string", "Maximum thickness of the deposit, in the unit given by "
                               "`M_T_U`."),
    col("M_T_U", "string", "Unit for `MAX_THICK`."),
    col("DEP_SIZE", "string",
        "Size class of the deposit [CRIB, size-of-deposit categories]. The same three "
        "classes appear under two spellings in the source and were left as received, so a "
        "filter must match both forms.",
        codes=[("SMALL", "small deposit, 337 records"),
               ("SML", "small deposit, alternative spelling, 27 records"),
               ("MEDIUM", "medium deposit, 203 records"),
               ("LARGE", "large deposit, 92 records"),
               ("LGE", "large deposit, alternative spelling, 18 records")]),
    col("STRIKE", "string", "Strike of the orebody in degrees [CRIB M20]."),
    col("DIP", "string", "Dip of the orebody."),
    col("PLUNGE_DIR", "string", "Direction of plunge of the orebody [CRIB M40]. Populated on "
                                "49 records."),
    col("PLUNGE", "string", "Plunge of the orebody [CRIB M30]. Populated on 50 records."),
    col("DEP_DESC_C", "string", "Narrative description of the deposit [CRIB M110]."),
    col("DEPTH_WK", "string", "Depth of the workings below surface, in the unit given by "
                              "`D_WK_U` [CRIB M160]."),
    col("D_WK_U", "string", "Unit for `DEPTH_WK` [CRIB M161]."),
    col("LEN_WK", "string", "Length of the workings, in the unit given by `L_WK_U` [CRIB "
                            "M170]."),
    col("L_WK_U", "string", "Unit for `LEN_WK` [CRIB M171]."),
    col("OV_LEN_WK", "string", "Overall length of the mined area, in the unit given by "
                               "`O_L_U` [CRIB M190]."),
    col("O_L_U", "string", "Unit for `OV_LEN_WK` [CRIB M191]."),
    col("OV_WID_WK", "string", "Overall width of the mined area, in the unit given by "
                               "`O_W_U` [CRIB M200]."),
    col("O_W_U", "string", "Unit for `OV_WID_WK` [CRIB M201]."),
    col("OV_AREA_WK", "string", "Overall area of the mined area, in the unit given by "
                                "`O_A_U` [CRIB M210]."),
    col("O_A_U", "string", "Unit for `OV_AREA_WK` [CRIB M211]."),
    col("DESC_WORK_", "string", "Comments describing the workings [CRIB M220]."),
    col("HR_AGE", "string", "Age of the host rock."),
    col("HR_TYPE", "string", "Type of the host rock."),
    col("IG_AGE", "string", "Age of associated igneous rocks [CRIB K2]. Populated on 28 "
                            "records."),
    col("IG_TYPE", "string", "Type of associated igneous rocks [CRIB K2]. Populated on 17 "
                             "records."),
    col("MIN_AGE", "string", "Age of mineralisation."),
    col("NON_ORE_MI", "string", "Non-ore minerals present."),
    col("ORE_CNTL", "string", "Ore control: the feature localising the ore."),
    col("TECT_SET", "string", "Tectonic setting [CRIB N15]."),
    col("REG_STRUCT", "string", "Major regional structures [CRIB N5]."),
    col("ALTER_", "string", "Alteration observed at the site."),
    col("CONC", "string", "Concentration process or tenor notes."),
    col("FORM_AGE", "string", "Age of the host formation." + PACKED),
    col("FORM_NAME", "string", "Name of the host formation." + PACKED),
    col("FORM2_AGE", "string", "Age of a second host formation. Empty on every record in "
                               "this layer."),
    col("FORM2_NAME", "string", "Name of a second host formation. Empty on every record in "
                                "this layer."),
    col("IG_UNIT_AG", "string", "Age of the associated igneous unit. Populated on 31 "
                                "records." + PACKED),
    col("IG_UNIT_NA", "string", "Name of the associated igneous unit. Populated on 31 "
                                "records." + PACKED),
    col("IG2_UNIT_A", "string", "Age of a second associated igneous unit. Empty on every "
                                "record in this layer."),
    col("IG2_UNIT_N", "string", "Name of a second associated igneous unit. Empty on every "
                                "record in this layer."),
    col("GEOL_COM", "string", "Geological descriptive notes [CRIB K6]. Populated on 90 "
                              "records."),
    col("GEN_COM", "string", "General comments. Populated on 12 records."),
    col("RF1", "string", "General reference 1 [CRIB F1]."),
    col("RF2", "string", "General reference 2 [CRIB F2]."),
    col("RF3", "string", "General reference 3 [CRIB F3]."),
    col("RF4", "string", "General reference 4 [CRIB F4]."),
    col("DESC_WORK", "string", "Type of workings at the site (surface, underground, or "
                               "both) [CRIB M130]."),
]

PROD_TAIL = [
    col("P_SOURCE", "string", "Source of the production information [CRIB D9]."),
    col("P_COM", "string", "Production comments [CRIB D10]. Populated on 69 records."),
]

RES_TAIL = {
    "RPR": [col("RPR_SOURCE", "string", "Source of the reserves and potential resources "
                                        "information [CRIB E7]."),
            col("RPR_COM", "string", "Comments on the reserves and potential resources "
                                     "[CRIB E8].")],
    "R":   [col("R_SOURCE", "string", "Source of the reserves information [CRIB H8]."),
            col("R_COM", "string", "Comments on the reserves [CRIB H7].")],
    "PR":  [col("PR_SOURCE", "string", "Source of the potential resources information "
                                       "[CRIB J8]."),
            col("PR_COM", "string", "Comments on the potential resources [CRIB J7].")],
}

PP_COLS = [CNG_FID, OGC_FID] + CRIB_HEAD + CRIB_BODY
for _p, _t, _l, _m in BLOCKS:
    PP_COLS += crib_block(_p, _t, _l, _m)
    if _p == "CP":
        PP_COLS += PROD_TAIL
    if _p in RES_TAIL:
        PP_COLS += RES_TAIL[_p]
PP_COLS += [col("REF", "int32", "Reference counter carried from the source compilation. 0 on "
                                "every record in this layer, so it carries no information "
                                "here.")]


# ---------------------------------------------------------------------------------------
# Sub-layer definitions. Counts, checksums and cell counts measured 2026-09-22 against the
# published objects.
# ---------------------------------------------------------------------------------------
LAYERS = [
    {
        "key": "districts", "title": "Uranium Districts", "geom": "polygon",
        "n": 58, "cols": DISTRICTS_COLS,
        "cells": "13,431 (feature, cell) rows over 13,423 distinct resolution-8 cells",
        "sha": "d236c2f9919757aed2e67311dd5799af9b3077c931f25b2b1b071dcd87d4bc7b",
        "raw_size": 451808,
        "blurb": "58 uranium districts delineated by the Utah Geological Survey, each "
                 "carrying the survey's uranium potential class (High, Moderate, Low or "
                 "None). Interpretive boundaries at district scale, not mapped deposit "
                 "outlines.",
    },
    {
        "key": "area-boundaries", "title": "Uranium Area Boundaries", "geom": "polygon",
        "n": 15, "cols": AREAS_COLS,
        "cells": "57,045 (feature, cell) rows over 57,026 distinct resolution-8 cells",
        "sha": "bcd6cab751f6d8d401a0defde91061b0aab3ae1e846926b9cc35364f9060fca1",
        "raw_size": 358579,
        "blurb": "15 broad uranium areas of the Colorado Plateau in Utah, as drawn on UGS "
                 "Map 215. Regional envelopes roughly four times the total area of the "
                 "districts layer.",
    },
    {
        "key": "past-producers", "title": "Uranium Past Producers", "geom": "point",
        "n": 748, "cols": PP_COLS,
        "cells": "748 points over 551 distinct resolution-8 cells",
        "sha": "a9f397422f1f1124b547a4390ebd441572bf30970002f3f05212a93b80e32e45",
        "raw_size": 2637065,
        "blurb": "748 sites in Utah that have produced uranium, described in the full USGS "
                 "CRIB record: location, commodity, deposit geometry and geology, "
                 "production, reserves and potential resources.",
    },
    {
        "key": "permitted-mines", "title": "Permitted Uranium Mines", "geom": "point",
        "n": 25, "cols": MINES_COLS,
        "cells": "25 points over 22 distinct resolution-8 cells",
        "sha": "4ed55d3585c27f13190134a0669988753d267d73f029b4cfd80d9f2674229394",
        "raw_size": 13723,
        "blurb": "25 uranium and uranium-vanadium mines permitted through the Utah Division "
                 "of Oil, Gas and Mining, with operator, permit status and ownership.",
    },
    {
        "key": "mills", "title": "Uranium Mills", "geom": "point",
        "n": 2, "cols": MILLS_COLS,
        "cells": "2 points over 2 distinct resolution-8 cells",
        "sha": "d38f3507945c4d213283274f6ee4f5516558a711db02a67d15dd2c2a395b62c5",
        "raw_size": 773,
        "blurb": "The two uranium and vanadium processing mills in Utah: the White Mesa "
                 "Mill in San Juan County and the Shootaring Canyon Mill in Garfield "
                 "County.",
    },
]

HEX_NOTE = (
    " One row per (feature, resolution-8 cell) pair, so every attribute of a feature is "
    "repeated on every cell that feature covers. Dedup on `_cng_fid` before counting or "
    "summing any attribute:\n"
    "```sql\n"
    "-- correct: one row per feature before aggregating\n"
    "SELECT COUNT(DISTINCT _cng_fid) FROM read_parquet('s3://.../hex/h0=*/data_0.parquet');\n"
    "-- wrong: COUNT(*) counts cells, not features\n"
    "```"
)

POINT_NOTE = (
    " Point layer: each point was mapped to exactly one H3 cell at resolution 8 (about "
    "0.74 km2 per cell). Points sharing a cell are not deduplicated, so {cells}."
)


def lean(cols):
    """PMTiles columns: name/type/values only, no geometry, prose stays on the GeoParquet."""
    out = []
    for c in cols:
        if c["name"] == "geom":
            continue
        lc = {"name": c["name"], "type": c["type"]}
        if "values" in c:
            lc["values"] = c["values"]
        out.append(lc)
    return out


def assets_for(layer):
    k, title, n = layer["key"], layer["title"], layer["n"]
    pretty = f"Utah Geological Survey — {title}"
    flat_cols = layer["cols"] + [GEOM]
    hex_cols = layer["cols"] + hidx(8)
    is_point = layer["geom"] == "point"

    hex_desc = (f"{pretty}: {n:,} features indexed to H3 resolution 8 for spatial joins and "
                f"aggregation.")
    if is_point:
        hex_desc += POINT_NOTE.format(cells=layer["cells"])
    else:
        hex_desc += HEX_NOTE
    if k == "past-producers":
        hex_desc += (" The production and reserve columns are packed text and are not "
                     "summable even after deduplication; see their column descriptions.")

    return {
        f"ugs-uranium-{k}-parquet": {
            "href": f"{BASE}/ugs-uranium/{k}.parquet",
            "type": "application/x-parquet",
            "title": f"{pretty} (GeoParquet)",
            "description": f"{pretty}: {layer['blurb']} {n:,} features, EPSG:4326.",
            "roles": ["data"],
            "created": f"{ACCESSED}T00:00:00Z",
            "table:columns": flat_cols,
        },
        f"ugs-uranium-{k}-pmtiles": {
            "href": f"{BASE}/ugs-uranium/{k}.pmtiles",
            "type": "application/vnd.pmtiles",
            "title": f"{pretty} (PMTiles)",
            "description": f"{pretty}: vector tiles for web maps. MapLibre source-layer "
                           f"is `{k}`.",
            "roles": ["visual"],
            "created": f"{ACCESSED}T00:00:00Z",
            "vector:layers": [k],
            "table:columns": lean(layer["cols"]),
        },
        f"ugs-uranium-{k}-hex": {
            "href": f"{BASE}/ugs-uranium/{k}/hex/h0=*/data_0.parquet",
            "type": "application/x-parquet",
            "title": f"{pretty} (H3 hex, resolution 8)",
            "description": hex_desc,
            "roles": ["data"],
            "created": f"{ACCESSED}T00:00:00Z",
            "h3:native_resolution": 8,
            "h3:parent_resolutions": [0],
            "table:columns": hex_cols,
        },
    }


DESCRIPTION = """\
Utah's uranium geology and mining history from the Utah Geological Survey (UGS) and the \
Utah Division of Oil, Gas and Mining (UDOGM), distributed through the Utah Geospatial \
Resource Center (UGRC/SGID). Five layers: 58 uranium districts carrying the survey's \
uranium potential class, 15 broad uranium areas of the Colorado Plateau, 748 past \
producing sites in the full USGS CRIB record, 25 permitted uranium and uranium-vanadium \
mines, and Utah's 2 uranium processing mills. Utah statewide; all five are Utah-only state \
products and the data reaches no further than the state line.

How the two polygon layers relate. There is no shared key between districts and areas and \
no name in common, so they can only be related spatially, and the relationship is not a \
clean hierarchy. The areas are regional envelopes totalling about 46,400 km2; the \
districts are finer units totalling about 10,900 km2 and covering roughly a fifth of the \
areas. 47 of the 58 districts fall entirely inside a single area and 4 more fall 93 to 98 \
per cent inside one, the remainder being slivers where the two were digitised \
independently. The other 7 districts (Spor Mountain, Honeycomb Hills, East Erickson, Blawn \
Mountain, Silver Reef, Marysvale and Newton) lie outside every area, because the 15 areas \
cover the Colorado Plateau while those districts are in western Utah. Rolling districts up \
to areas therefore drops those 7.

Counting across layers. The layers overlap each other and overlap the sibling collections \
`ugs-mineral-occurrences` and `usgs-mrds` with no shared identifier, so counts from \
different layers cannot be added: a single mine may appear as a past producer, as a \
permitted mine and as a mineral occurrence. Count within one layer, using \
COUNT(DISTINCT _cng_fid).

Production and reserve figures on the past-producers layer. These follow the USGS CRIB \
record format and need parsing before any arithmetic. Each amount column holds several \
entries packed into one string separated by U+00FD, each entry is in THOUSANDS of the unit \
named in the parallel unit column, and the entries may cover different commodities and \
carry different units within the same record. Reserves are also reported in three \
overlapping tables, where RPR is the total and R and PR are its two parts, so adding all \
three double counts. The columns are published as text exactly as received; see the column \
descriptions on the past-producers assets before using them.

Provenance. Retrieved 2026-09-22 from five ArcGIS Online feature services published by \
UGRC under the SGID Energy theme. The services are live and unversioned: the publisher \
states no edition or release, so the access date is the only edition marker, and a later \
retrieval may differ. The retrieved snapshot is staged at s3://public-utah/raw/ as \
ugs-uranium-districts.geojson (451,808 bytes, sha256 \
d236c2f9919757aed2e67311dd5799af9b3077c931f25b2b1b071dcd87d4bc7b), \
ugs-uranium-area-boundaries.geojson (358,579 bytes, sha256 \
bcd6cab751f6d8d401a0defde91061b0aab3ae1e846926b9cc35364f9060fca1), \
ugs-uranium-past-producers.geojson (2,637,065 bytes, sha256 \
a9f397422f1f1124b547a4390ebd441572bf30970002f3f05212a93b80e32e45), \
ugs-uranium-permitted-mines.geojson (13,723 bytes, sha256 \
4ed55d3585c27f13190134a0669988753d267d73f029b4cfd80d9f2674229394) and \
ugs-uranium-mills.geojson (773 bytes, sha256 \
d38f3507945c4d213283274f6ee4f5516558a711db02a67d15dd2c2a395b62c5).

Known gaps in the source. 26 of the 748 past producers carry valid coordinates but no \
attributes at all, so a count of described past producers is 722. Three districts have no \
uranium potential class. The criteria behind the potential classes are not published \
anywhere by the publisher. String fields arrive space-padded from the SGID extract and \
were trimmed, with empty-after-trimming values stored as NULL; nothing else was altered.\
"""

collection = {
    "stac_version": "1.0.0",
    "stac_extensions": [
        "https://stac-extensions.github.io/table/v1.2.0/schema.json",
        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
    ],
    "type": "Collection",
    "id": "ugs-uranium",
    "title": "Utah Geological Survey — Uranium Districts, Areas, Past Producers, "
             "Permitted Mines & Mills",
    "description": DESCRIPTION,
    "license": "CC-BY-4.0",
    "keywords": ["uranium", "vanadium", "mining", "mineral resources", "geology",
                 "Utah", "Colorado Plateau", "UGS", "UDOGM", "SGID", "CRIB"],
    "extent": {
        "spatial": {"bbox": [[-113.6237, 36.9958, -109.0390, 40.8033]]},
        "temporal": {"interval": [["1893-01-01T00:00:00Z", None]]},
    },
    "sci:citation": (
        "Utah Geological Survey and Utah Division of Oil, Gas and Mining, Utah uranium "
        "districts, area boundaries, past producers, permitted mines and mills: "
        "distributed by the Utah Geospatial Resource Center (SGID Energy), ArcGIS Online "
        f"feature services, accessed {ACCESSED}. Underlying compilation published as Utah "
        "Geological Survey Map 215, Uranium and Vanadium Map of Utah (Gloyn, R.W., Bon, "
        "R.L., Wakefield, S., and Krahulec, K., 2005). Past-producer attributes follow the "
        "USGS Computerized Resources Information Bank (CRIB) record format described in "
        "Keefer, E.K., and Calkins, J.A., 1978, Description of individual data items and "
        "codes in CRIB: U.S. Geological Survey Circular 755-B, "
        "https://doi.org/10.3133/cir755B."
    ),
    "created": f"{ACCESSED}T00:00:00Z",
    "updated": f"{ACCESSED}T00:00:00Z",
    "providers": [
        {"name": "Utah Geological Survey (UGS)",
         "roles": ["producer", "licensor"], "url": "https://geology.utah.gov/"},
        {"name": "Utah Division of Oil, Gas and Mining (UDOGM)",
         "roles": ["producer"], "url": "https://ogm.utah.gov/"},
        {"name": "Utah Geospatial Resource Center (UGRC/SGID)",
         "roles": ["host"], "url": "https://gis.utah.gov/products/sgid/energy/"},
        {"name": "Boettiger Lab (cng-datasets processing)",
         "roles": ["processor"], "url": f"{BASE}/"},
    ],
    "links": [
        {"rel": "self", "href": SELF, "type": "application/json"},
        {"rel": "root", "href": ROOT, "type": "application/json"},
        {"rel": "parent", "href": BUCKET_SELF, "type": "application/json"},
        {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/",
         "type": "text/html",
         "title": "Creative Commons Attribution 4.0 International"},
        {"rel": "about", "href": "https://gis.utah.gov/products/sgid/energy/",
         "type": "text/html",
         "title": "UGRC SGID Energy theme (publisher landing page)"},
    ],
    "assets": {},
}

for _layer in LAYERS:
    collection["assets"].update(assets_for(_layer))

if __name__ == "__main__":
    out = "/tmp/ugs-uranium-stac-collection.json"
    with open(out, "w") as fh:
        json.dump(collection, fh, indent=2, ensure_ascii=False)
    n_cols = sum(len(a.get("table:columns", [])) for a in collection["assets"].values())
    print(f"wrote {out}: {len(collection['assets'])} assets, {n_cols} column entries")
