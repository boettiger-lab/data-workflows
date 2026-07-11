#!/usr/bin/env python3
"""Generate stac-collection.json for FACTS Common Attributes (issue #299).

Writes to /tmp/stac-collection.json. Lint with:
  scripts/lint-stac-categorical.py /tmp/stac-collection.json
  scripts/lint-stac-pmtiles-fields.py /tmp/stac-collection.json
"""
import json, pathlib

HERE = pathlib.Path(__file__).parent
CODES = json.loads((HERE / "_codes.json").read_text())

BASE = "https://s3-west.nrp-nautilus.io/public-facts"
DS = "common-attributes-2026-06"

TYPE_MAP = {
    "BIGINT": "int64", "SMALLINT": "int16", "INTEGER": "int32",
    "DOUBLE": "double", "VARCHAR": "string",
    "TIMESTAMP WITH TIME ZONE": "timestamp", "GEOMETRY": "geometry",
    "UBIGINT": "uint64",
}

# Per-feature total columns: repeated on every hex cell -> never SUM on hex.
PER_FEATURE_TOTAL = {
    "SITE_NBR_OF_UNITS", "GIS_ACRES", "COST_PER_UNIT",
    "NBR_UNITS_PLANNED", "NBR_UNITS_ACCOMPLISHED", "KV_NBR_UNITS_FUNDED",
}

DEDUP_NOTE = (
    " **Per-feature value repeated on every hex row the activity covers — "
    "never SUM this on the hex asset. Dedup on _cng_fid first "
    "(e.g. SELECT DISTINCT _cng_fid, <col> ...) before aggregating.**"
)

# (name, duckdb_type, description, values_key_or_None)
COLS = [
    ("_cng_fid", "BIGINT", "Synthetic unique row identifier assigned during conversion. Stable join key between the GeoParquet and the hex asset (one feature = one _cng_fid).", None),
    ("id", "BIGINT", "Original GeoPackage feature identifier (FID) from the source layer; not guaranteed unique across the 9 merged regions — use _cng_fid as the stable key.", None),
    ("SU_SECURITY_ID", "VARCHAR", "FACTS spatial-unit security identifier.", None),
    ("AU_ORG", "VARCHAR", "Accounting-unit organization identifier (administering org).", None),
    ("SUID", "VARCHAR", "19-character FACTS spatial-unit identifier locating the activity subunit down to a specific parcel.", None),
    ("FACTS_ID", "VARCHAR", "10-character FACTS activity-unit identifier for the geographic area where activities occur.", None),
    ("SUBUNIT", "VARCHAR", "Subunit identifier within the activity unit.", None),
    ("AU_NAME", "VARCHAR", "Accounting-unit name.", None),
    ("NAME", "VARCHAR", "Activity unit name.", None),
    ("FEATURE_TYPE", "VARCHAR", "Native feature geometry type recorded in FACTS. Values: A=Area, L=Line, P=Point. All features are stored as polygons in this layer (line/point activities were represented as polygons).", "FEATURE_TYPE"),
    ("SITE_NBR_OF_UNITS", "DOUBLE", "Total size of the activity site, in the unit given by UOM (typically acres).", None),
    ("GIS_ACRES", "DOUBLE", "Feature area in acres, computed by the Forest Service in NAD83 Albers Equal Area.", None),
    ("UOM", "VARCHAR", "Unit of measure for the NBR_UNITS_* and SITE_NBR_OF_UNITS fields. Values: ACRES=Acres, EACH=Each (count), MILES=Miles, PLOTS=Plots, STRUCTURES=Structures, 'PAOT DAYS'=People-at-one-time days.", "UOM"),
    ("ACTIVITY_CODE", "VARCHAR", "FACTS activity identifier (4-digit). The human-readable label for each value is carried in the paired ACTIVITY column. Examples: 4310=Silvicultural Stand Examination, 4341=Stocking Survey, 4301=Photo Stand Delineation, 2510=Invasives - Pesticide Application, 4431=Plant Trees, 1130=Burning of Piled Material. First digit groups the activity family (1xxx=Fire/Fuels, 2xxx=Range/Invasives, 3xxx=Vegetation, 4xxx=Silviculture/Timber, 5xxx=Wildlife/TES, 6xxx=Recreation/Watershed, 7xxx=Lands, 8xxx=Minerals, 9xxx=Other).", "ACTIVITY_CODE"),
    ("ACTIVITY", "VARCHAR", "Human-readable activity description (textual label for the activity identifier; e.g. 'Silvicultural Stand Examination').", None),
    ("LOCAL_QUALIFIER", "VARCHAR", "Local qualifier text further describing the activity.", None),
    ("METHOD_CODE", "VARCHAR", "FACTS method identifier. The human-readable label for each value is carried in the paired METHOD column. Examples: 100=Manual, 200=Mechanical, 300=Prescribed Burn, 420=Tractor Logging, 933=Quick Plot Exams, 000=Not Applicable.", "METHOD_CODE"),
    ("METHOD", "VARCHAR", "Human-readable method description (textual label for the method identifier; e.g. 'Prescribed Burn').", None),
    ("EQUIPMENT_CODE", "VARCHAR", "FACTS equipment identifier. The human-readable label for each value is carried in the paired EQUIPMENT column. Examples: 111=Chain Saw, 302=Drip torch, 100=Hand Work, 721=Mobile ground sprayer, 712=Backpack sprayer, 000=NA.", "EQUIPMENT_CODE"),
    ("EQUIPMENT", "VARCHAR", "Human-readable equipment description (textual label for the equipment identifier; e.g. 'Chain Saw').", None),
    ("FUND_CODES", "VARCHAR", "Funding-source identifiers applied to the activity (may list several).", None),
    ("COST_PER_UNIT", "DOUBLE", "Recorded cost per unit of the activity.", None),
    ("WORKFORCE_CODE", "VARCHAR", "Workforce identifier (FACTS workforce lookup).", None),
    ("FISCAL_YEAR_PLANNED", "SMALLINT", "Fiscal year the activity was planned.", None),
    ("FISCAL_YEAR_AWARDED", "SMALLINT", "Fiscal year the activity was awarded.", None),
    ("DATE_AWARDED", "TIMESTAMP WITH TIME ZONE", "Date the activity was awarded.", None),
    ("FISCAL_YEAR_COMPLETED", "SMALLINT", "Fiscal year the activity work was physically completed.", None),
    ("DATE_COMPLETED", "TIMESTAMP WITH TIME ZONE", "Date the activity work was physically completed.", None),
    ("NBR_UNITS_PLANNED", "DOUBLE", "Number of units (per UOM) planned for the activity.", None),
    ("NBR_UNITS_ACCOMPLISHED", "DOUBLE", "Number of units (per UOM) accomplished/completed by the activity.", None),
    ("EXCLUDE_ACCOMPLISHMENT", "VARCHAR", "Whether the record is excluded from accomplishment reporting. Values: Y=Excluded (not reported as accomplishment), N=Not excluded (reported).", "YN"),
    ("TREATMENT_NAME", "VARCHAR", "Treatment name.", None),
    ("FUELS_KEYPOINT_AREA", "VARCHAR", "NFPORS fuels keypoint-area grouping. Values: 0=Not a fuels keypoint area (none), 2=Post Wildfire Restoration Activities, 3=Primary Fuels Reduction Treatments, 6=Secondary Fuels Reduction Treatments.", "FUELS_KEYPOINT_AREA"),
    ("ISWUI", "VARCHAR", "Whether the activity is within the Wildland-Urban Interface. Values: Y=Yes, N=No.", "YN"),
    ("FIREREGIME", "INTEGER", "Historic fire-regime group (integer 1-5) for the activity location.", None),
    ("CWPP", "VARCHAR", "Community Wildfire Protection Plan name associated with the activity, if any.", None),
    ("BIOMASS_UTILIZATION", "VARCHAR", "Whether biomass was utilized. Values: Y=Yes (biomass utilized), N=No, U=Unknown.", "YNU"),
    ("NFPORS_CATEGORY", "VARCHAR", "NFPORS treatment grouping (free-text, e.g. 'Fuels Management').", None),
    ("NFPORS_TREATMENT", "VARCHAR", "NFPORS treatment type (free-text).", None),
    ("PURPOSE_CODE", "VARCHAR", "Activity purpose. Values: FUEL=Fuels, TMBR=Timber Management, TSI=Timber Stand Improvement, RF=Reforestation, FIRE=Fire, FTI=Fuel Treatment Initial, FTM=Fuel Treatment Maintenance, FTF=Fuel Treatment Final, WILD=Wildlife, INV=Invasive Species, INS=Insects, DIS=Disease, REC=Recreation, SOIL=Soil, TES=Threatened/Endangered Species, RNGE=Range, ANML=Animal Damage, BOT=Botany, WA=Watershed/Air, AIR=Air, SS=Special Status, ENG=Engineering, CLTR=Cultural, BD=Brush Disposal, FE=Forest Health. See the FACTS data dictionary for authoritative definitions.", "PURPOSE_CODE"),
    ("SALE_NAME", "VARCHAR", "Timber sale name, if the activity is tied to a sale.", None),
    ("SALE_NUMBER", "VARCHAR", "Timber sale number/identifier.", None),
    ("SALE_CATEGORY", "VARCHAR", "Timber sale grouping flag from FACTS. Observed values: C, H, M, P (definitions per the FACTS data dictionary).", None),
    ("UNIT_ID", "VARCHAR", "Sale/contract unit identifier.", None),
    ("PURCHASER_NAME", "VARCHAR", "Timber sale purchaser name.", None),
    ("CONTRACT_PLANNED_TERM", "TIMESTAMP WITH TIME ZONE", "Planned contract termination date.", None),
    ("AWARD_DATE", "TIMESTAMP WITH TIME ZONE", "Contract award date.", None),
    ("SALE_CLOSURE_DATE", "TIMESTAMP WITH TIME ZONE", "Sale closure date.", None),
    ("BASE_YEAR", "VARCHAR", "Contract base year flag.", None),
    ("KV_NBR_UNITS_FUNDED", "DOUBLE", "Knutson-Vandenberg (K-V) number of units funded.", None),
    ("PERCENT_FUNDED", "VARCHAR", "Percent funded flag.", None),
    ("NEEDS", "VARCHAR", "Reforestation/TSI needs flag.", None),
    ("CAUSAL_AGENT", "VARCHAR", "Causal agent associated with a need (e.g. fire, insects).", None),
    ("REFORESTATION_STATUS", "VARCHAR", "Reforestation status flag.", None),
    ("EXAM_NBR", "SMALLINT", "Stand exam number.", None),
    ("NEEDS_ADJUSTMENT", "VARCHAR", "Needs-adjustment flag.", None),
    ("TSI", "VARCHAR", "Timber stand improvement flag.", None),
    ("EVENT_YEAR", "SMALLINT", "Event year.", None),
    ("IMPLEMENTATION_PROJECT", "VARCHAR", "Implementation project name (NEPA/PALS).", None),
    ("IMPL_PROJECT_NBR", "VARCHAR", "Implementation project number/identifier.", None),
    ("IMPL_PROJECT_TYPE", "VARCHAR", "Implementation project type (free-text).", None),
    ("NEPA_DOC_NBR", "VARCHAR", "NEPA document number uniquely identifying the NEPA decision in FACTS or PALS.", None),
    ("NEPA_DOC_TYPE", "VARCHAR", "NEPA document type (e.g. CE, EA, EIS).", None),
    ("NEPA_PROJECT_NAME", "VARCHAR", "NEPA project name.", None),
    ("NEPA_HFI", "VARCHAR", "Whether the project is a Healthy Forests Initiative project. Values: Y=Yes, N=No.", "YN"),
    ("NEPA_HFRA", "VARCHAR", "Whether the project is a Healthy Forests Restoration Act project. Values: Y=Yes, N=No.", "YN"),
    ("NEPA_SIGNED_DATE", "TIMESTAMP WITH TIME ZONE", "Date the NEPA decision was signed.", None),
    ("ADMIN_REGION", "VARCHAR", "USFS administrative Region that administers the land. Values: 01=Northern, 02=Rocky Mountain, 03=Southwestern, 04=Intermountain, 05=Pacific Southwest, 06=Pacific Northwest, 08=Southern, 09=Eastern, 10=Alaska. This is the canonical region field for filtering/aggregating by USFS region (exactly one value per source region file).", "ADMIN_REGION"),
    ("ADMIN_FOREST", "VARCHAR", "Administrative forest identifier (2-digit, within the region).", None),
    ("ADMIN_DISTRICT", "VARCHAR", "Administrative ranger-district identifier (2-digit, within the forest).", None),
    ("AU_REGION", "VARCHAR", "Accounting-unit Region identifier.", None),
    ("AU_FOREST", "VARCHAR", "Accounting-unit forest identifier.", None),
    ("AU_DISTRICT", "VARCHAR", "Accounting-unit district identifier.", None),
    ("PROC_FOREST", "VARCHAR", "Proclaimed forest identifier.", None),
    ("OWNERSHIP", "VARCHAR", "Land ownership description (free-text, e.g. 'FS - Forest Service').", None),
    ("STATE_ABBR", "VARCHAR", "Two-letter US state/territory postal abbreviation.", None),
    ("PRODUCTIVITY_CLASS", "VARCHAR", "Site productivity classification identifier (FACTS PRODUCTIVITY_CLASS lookup; numeric site-quality rank). See the FACTS data dictionary.", None),
    ("LAND_SUITABILITY_CODE", "VARCHAR", "Land suitability identifier (FACTS lookup).", None),
    ("COUNTY_NAME", "VARCHAR", "County name.", None),
    ("CONG_DIST_NAME", "VARCHAR", "Congressional district name.", None),
    ("LATITUDE", "DOUBLE", "Representative latitude of the activity (decimal degrees).", None),
    ("LONGITUDE", "DOUBLE", "Representative longitude of the activity (decimal degrees).", None),
    ("LEGAL_LOCATION", "VARCHAR", "Public Land Survey System legal location description.", None),
    ("ASPECT", "VARCHAR", "Slope aspect (compass direction) of the site.", None),
    ("SLOPE", "SMALLINT", "Slope percent of the site.", None),
    ("ELEVATION", "DOUBLE", "Elevation of the site (feet).", None),
    ("WATERSHED_CODE", "VARCHAR", "Hydrologic Unit (HUC) watershed identifier.", None),
    ("MGT_AREA_CODE", "VARCHAR", "Forest-plan management-area identifier (varies by forest).", None),
    ("MGT_PRESCRIPTION_CODE", "VARCHAR", "Forest-plan management-prescription identifier (varies by forest).", None),
    ("ACTIVITY_SITE_REMARKS", "VARCHAR", "Free-text remarks about the activity site.", None),
    ("ACTIVITY_REMARKS", "VARCHAR", "Free-text remarks about the activity.", None),
    ("SU_CREATED_BY", "VARCHAR", "User who created the spatial-unit record.", None),
    ("SU_CREATED_DATE", "TIMESTAMP WITH TIME ZONE", "Date the spatial-unit record was created.", None),
    ("SU_MODIFIED_BY", "VARCHAR", "User who last modified the spatial-unit record.", None),
    ("SU_MODIFIED_DATE", "TIMESTAMP WITH TIME ZONE", "Date the spatial-unit record was last modified.", None),
    ("ACT_CREATED_BY", "VARCHAR", "User who created the activity record.", None),
    ("ACT_CREATED_DATE", "TIMESTAMP WITH TIME ZONE", "Date the activity record was created.", None),
    ("ACT_MODIFIED_BY", "VARCHAR", "User who last modified the activity record.", None),
    ("ACT_MODIFIED_DATE", "TIMESTAMP WITH TIME ZONE", "Date the activity record was last modified.", None),
    ("ACTIVITY_UNIT_CN", "VARCHAR", "FACTS control-number (CN) identifier for the activity unit.", None),
    ("LU_CN", "VARCHAR", "FACTS control-number identifier for the land unit.", None),
    ("SUID_CN", "VARCHAR", "FACTS control-number identifier for the SUID.", None),
    ("EVENT_CN", "VARCHAR", "FACTS control-number identifier for the event.", None),
    ("NEPA_PROJECT_CN", "VARCHAR", "FACTS control-number identifier for the NEPA project.", None),
    ("PALS_PROJECT_CN", "VARCHAR", "PALS control-number identifier for the project.", None),
    ("SALE_CN", "VARCHAR", "FACTS control-number identifier for the sale.", None),
    ("IMPLEMENTATION_PROJECT_CN", "VARCHAR", "FACTS control-number identifier for the implementation project.", None),
    ("UKCN", "VARCHAR", "FACTS unique-key control number.", None),
    ("FS_UNIT_ID", "VARCHAR", "Forest Service organizational unit identifier.", None),
    ("CRC_VALUE", "VARCHAR", "Cyclic-redundancy-check value used by FACTS for change detection.", None),
    ("EVENT_NAME", "VARCHAR", "Event name.", None),
    ("geom", "GEOMETRY", "Feature geometry (GeoParquet, EPSG:4326). Polygon/MultiPolygon. ~17% of source records are aspatial (NULL geometry) and are absent from the hex/PMTiles assets.", None),
]

# Y/N shared values + other small enums not in _codes.json.
# Value sets are the ACTUAL ingested distinct values (verify-stac requires declared >= ingested).
CODES["YN"] = ["Y", "N"]
CODES["YNU"] = ["Y", "N", "U"]
CODES["FUELS_KEYPOINT_AREA"] = ["0", "2", "3", "6"]

def col_entry(name, dtype, desc, vkey, *, on_hex=False):
    e = {"name": name, "type": TYPE_MAP[dtype], "description": desc}
    if on_hex and name in PER_FEATURE_TOTAL:
        e["description"] = desc + DEDUP_NOTE
    if vkey:
        e["values"] = CODES[vkey]
    return e

# GeoParquet asset: all columns incl geom
geoparquet_cols = [col_entry(n, t, d, v) for (n, t, d, v) in COLS]

# Hex asset: all columns except geom, plus H3 columns; dedup notes on per-feature totals.
hex_cols = [col_entry(n, t, d, v, on_hex=True) for (n, t, d, v) in COLS if n != "geom"]
hex_cols += [
    {"name": "h10", "type": "uint64", "description": "H3 cell ID at resolution 10 (native resolution; one row per (feature, h10) pair)."},
    {"name": "h9", "type": "uint64", "description": "H3 cell ID at resolution 9 (parent rollup)."},
    {"name": "h8", "type": "uint64", "description": "H3 cell ID at resolution 8 (parent rollup)."},
    {"name": "h0", "type": "int64", "description": "H3 cell ID at resolution 0; hive partition key for the hex dataset."},
]

# PMTiles tile fields (the -select subset baked at tile-build time, #283).
pmtiles_cols = [
    {"name": "_cng_fid", "type": "int64", "description": "Synthetic feature id; join key back to the full GeoParquet (110 attribute columns)."},
    {"name": "ADMIN_REGION", "type": "string", "description": "USFS Region (01..10). Primary field for filtering/styling by region.", "values": CODES["ADMIN_REGION"]},
    {"name": "ADMIN_FOREST", "type": "string", "description": "Administrative forest identifier."},
    {"name": "STATE_ABBR", "type": "string", "description": "Two-letter state/territory abbreviation."},
    {"name": "COUNTY_NAME", "type": "string", "description": "County name."},
    {"name": "ACTIVITY_CODE", "type": "string", "description": "FACTS activity identifier (label in ACTIVITY).", "values": CODES["ACTIVITY_CODE"]},
    {"name": "ACTIVITY", "type": "string", "description": "Human-readable activity description. Good default field for categorical styling."},
    {"name": "METHOD", "type": "string", "description": "Human-readable method description."},
    {"name": "EQUIPMENT", "type": "string", "description": "Human-readable equipment description."},
    {"name": "NFPORS_CATEGORY", "type": "string", "description": "NFPORS treatment category."},
    {"name": "NFPORS_TREATMENT", "type": "string", "description": "NFPORS treatment type."},
    {"name": "PURPOSE_CODE", "type": "string", "description": "Activity purpose (see GeoParquet asset for value definitions).", "values": CODES["PURPOSE_CODE"]},
    {"name": "FISCAL_YEAR_PLANNED", "type": "int16", "description": "Fiscal year planned."},
    {"name": "FISCAL_YEAR_COMPLETED", "type": "int16", "description": "Fiscal year completed. Good field for time filtering/styling."},
    {"name": "DATE_COMPLETED", "type": "string", "description": "Completion date (ISO-8601 string in tiles)."},
    {"name": "GIS_ACRES", "type": "double", "description": "Feature area in acres. Good field for graduated styling."},
    {"name": "NBR_UNITS_ACCOMPLISHED", "type": "double", "description": "Units accomplished (per UOM)."},
    {"name": "UOM", "type": "string", "description": "Unit of measure for NBR_UNITS_ACCOMPLISHED.", "values": CODES["UOM"]},
    {"name": "NAME", "type": "string", "description": "Activity unit name (label field)."},
    {"name": "TREATMENT_NAME", "type": "string", "description": "Treatment name (label field)."},
    {"name": "NEPA_PROJECT_NAME", "type": "string", "description": "NEPA project name (label field)."},
]

collection = {
    "type": "Collection",
    "stac_version": "1.0.0",
    "stac_extensions": [
        "https://stac-extensions.github.io/table/v1.2.0/schema.json",
    ],
    "id": "facts-common-attributes-2026-06",
    "title": "USFS FACTS Common Attributes (National, 2026-06)",
    "description": (
        "US Forest Service **FACTS Common Attributes** — the comprehensive all-activities "
        "record from the Forest Service Activity Tracking System (FACTS), covering planned, "
        "accomplished, and completed management activities (fire/fuels, silviculture, timber, "
        "range, invasive species, watershed, recreation, and more) on National Forest System "
        "lands.\n\n"
        "This is a **single national dataset** merged from all 9 USFS regions "
        "(01-06, 08, 09, 10; there is no Region 07), downloaded from the FS Enterprise Data "
        "Warehouse (EDW) on 2026-06-24. **7,324,720 activity records**; geometry reprojected "
        "from NAD83 (EPSG:4269) to EPSG:4326.\n\n"
        "**Region field:** use `ADMIN_REGION` (values 01..10) to filter/aggregate by USFS region.\n\n"
        "**Aspatial records:** ~17% of records (1,267,056) have NULL geometry — these are FACTS "
        "activities recorded without a mapped spatial unit. They are present in the GeoParquet "
        "but absent from the hex and PMTiles assets (which require geometry). Filter "
        "`WHERE geom IS NOT NULL` to restrict to mapped features (6,057,664).\n\n"
        "**Upstream data quality:** FACTS contains a small number of data-entry errors — "
        "~35 features have erroneous coordinates outside the US, and ~1,271 records have "
        "implausible fiscal years (e.g. 1820, 2050). These are preserved as-is from the source.\n\n"
        "**Hex aggregation:** activity polygons were indexed to H3 resolution 10 "
        "(parents 9, 8, 0). One hex row = one (feature, cell) pair; attributes are repeated on "
        "every cell a feature covers. Never SUM per-feature totals (GIS_ACRES, NBR_UNITS_*, "
        "COST_PER_UNIT, etc.) on the hex asset without first deduplicating on `_cng_fid`. "
        "To estimate area from hex, use COUNT(DISTINCT h10) x cell_area_at_resolution_10."
    ),
    "license": "public-domain",
    "keywords": ["forestry", "USFS", "FACTS", "land management", "fuels", "silviculture",
                 "timber", "wildfire", "United States"],
    "providers": [
        {"name": "USDA Forest Service", "roles": ["producer", "licensor"],
         "url": "https://data.fs.usda.gov/geodata/edw/datasets.php?xmlKeyword=FACTS"},
        {"name": "Boettiger Lab / cirrus", "roles": ["processor", "host"],
         "url": "https://s3-west.nrp-nautilus.io/public-facts/"},
    ],
    "extent": {
        "spatial": {"bbox": [[-151.6, 17.6, -65.0, 64.3]]},
        "temporal": {"interval": [["1950-01-01T00:00:00Z", "2026-12-31T00:00:00Z"]]},
    },
    "links": [
        {"rel": "self", "href": f"{BASE}/{DS}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json"},
        {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
        {"rel": "license", "href": "https://www.usa.gov/government-works", "type": "text/html",
         "title": "US Government work — public domain"},
    ],
    "assets": {
        f"{DS}-parquet": {
            "href": f"{BASE}/{DS}.parquet",
            "type": "application/x-parquet",
            "title": "FACTS Common Attributes — national GeoParquet",
            "roles": ["data"],
            "description": "Merged national GeoParquet (7,324,720 rows, all 9 regions). One row per FACTS activity record; includes aspatial records (NULL geom).",
            "table:primary_geometry": "geom",
            "table:columns": geoparquet_cols,
        },
        f"{DS}-pmtiles": {
            "href": f"{BASE}/{DS}.pmtiles",
            "type": "application/vnd.pmtiles",
            "title": "FACTS Common Attributes — PMTiles (web map)",
            "roles": ["visual"],
            "description": ("Vector tiles for MapLibre. MapLibre source-layer id = "
                            f"'{DS}'. Tiles carry a curated subset of fields (below); "
                            "join on _cng_fid to the GeoParquet for the full attribute set. "
                            "Aspatial records are not included."),
            "vector:layers": [DS],
            "table:columns": pmtiles_cols,
        },
        f"{DS}-hex": {
            "href": f"{BASE}/{DS}/hex/h0=*/data_0.parquet",
            "type": "application/x-parquet",
            "title": "FACTS Common Attributes — H3 hex (res 10)",
            "roles": ["data"],
            "description": ("Hive-partitioned H3 hex parquet (partition key h0). One row per "
                            "(feature, h10 cell); 96,883,698 rows over ~21.7M distinct res-10 cells "
                            "for the 6,057,664 mapped features. Per-feature attributes are repeated "
                            "on every cell — never SUM per-feature totals here without deduplicating "
                            "on _cng_fid; estimate area via COUNT(DISTINCT h10) x cell_area."),
            "h3:native_resolution": 10,
            "h3:parent_resolutions": [9, 8, 0],
            "table:columns": hex_cols,
        },
    },
}

out = pathlib.Path("/tmp/stac-collection.json")
out.write_text(json.dumps(collection, indent=2))
print(f"wrote {out} ({len(geoparquet_cols)} geoparquet cols, {len(hex_cols)} hex cols, {len(pmtiles_cols)} pmtiles cols)")
