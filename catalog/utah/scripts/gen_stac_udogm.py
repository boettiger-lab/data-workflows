#!/usr/bin/env python3
"""Generate the `udogm` STAC collection for public-utah (issue #480).

One collection ("Utah DNR / UDOGM — Permitted Mines, Wells & Oil-Gas Fields") with four
sub-layers, each carrying a GeoParquet + PMTiles + H3 hex asset (12 assets total):

  udogm-wells            oil & gas well surface locations (point, 40,344; res 10)
  udogm-mineral-mines    non-coal mineral mine permits    (point,  1,504; res 10)
  udogm-coal-permits     coal permit boundaries           (polygon,   32; res 10)
  udogm-oil-gas-fields   oil & gas producing fields        (polygon,  153; res 8)

Column authority is written IDENTICALLY on the flat GeoParquet and the hex (mcp-data-server
#303 dedups identical per-column text). PMTiles assets carry the lean name/type/values only.
Categorical `values` come from the ingested DISTINCT (verify-stac data check enforces the
match). Writes /tmp/udogm-stac-collection.json. STAC never lives in the repo — upload with
rclone and validate with scripts/verify-stac.py.

License: CC-BY-4.0 (Utah SGID / UGRC distribution; steward Utah DNR Division of Oil, Gas and
Mining), matching the UGS #479 sibling.
"""
import json

BASE = "https://s3-west.nrp-nautilus.io/public-utah"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
BUCKET_SELF = f"{BASE}/stac-collection.json"

GEOM = {"name": "geom", "type": "geometry",
        "description": "Feature geometry (GeoParquet, EPSG:4326 / OGC:CRS84)."}
CNG_FID = {"name": "_cng_fid", "type": "int64",
           "description": "Synthetic per-feature id (one per source feature, row-unique). "
                          "Dedup / COUNT(DISTINCT) key across the (feature, H3 cell) rows on the hex."}
OGC_FID = {"name": "OGC_FID", "type": "int64",
           "description": "GDAL feature id carried from conversion (provenance only; use "
                          "`_cng_fid` as the canonical per-feature dedup key)."}
YEAR = {"name": "year", "type": "int32",
        "description": "Derived integer year (see the collection/asset notes for the source "
                       "date field per layer); NULL where no reliable date exists."}


def hidx(res):
    """H3 index columns for a native resolution with parents down to h0."""
    cols = []
    ladder = {10: [10, 9, 8, 0], 8: [8, 0]}[res]
    for r in ladder:
        if r == 0:
            cols.append({"name": "h0", "type": "int64",
                         "description": "H3 cell ID at resolution 0; hive partition key."})
        else:
            role = "native resolution; one row per (feature, cell) pair" if r == ladder[0] \
                else f"parent rollup resolution"
            cols.append({"name": f"h{r}", "type": "uint64",
                         "description": f"H3 cell ID at resolution {r} ({role})."})
    return cols


# ----------------------------------------------------------------------------------------
# Per sub-layer column authority. `values` lists are the ingested DISTINCT (2026-07-23);
# verify-stac re-checks them against the live data.
# ----------------------------------------------------------------------------------------
def col(name, type_, desc, values=None):
    c = {"name": name, "type": type_, "description": desc}
    if values is not None:
        c["values"] = values
    return c


WELLSTATUS_VALUES = ["A", "APD", "DRL", "I", "LA", "NEW", "OPS", "P", "PA", "PAI",
                     "RET", "S", "SII", "TA", "TEST"]
WELLSTATUS_DESC = (
    "Most current DOGM status of the well or drilling permit. Values: "
    "NEW=New Application for Permit to Drill (APD) received, not yet approved; "
    "RET=APD returned to operator unapproved; "
    "APD=Approved Application for Permit to Drill; "
    "LA=Location Abandoned (approved APD for a new well rescinded, no site disturbance); "
    "DRL=Well spudded and/or currently drilling; "
    "OPS=Drilling operations suspended; "
    "P=Producing oil or gas well; "
    "S=Shut-in oil or gas well; "
    "TA=Temporarily-abandoned oil or gas well; "
    "PA=Plugged and Abandoned; "
    "PAI=Producing oil/gas zone AND active injection zone; "
    "SII=Shut-in oil/gas zone AND inactive injection zone; "
    "A=Active service well (injection/disposal/storage/source/test); "
    "I=Inactive service well; "
    "TEST=rare non-standard status value present in one record (not in the DOGM published list).")

WELLTYPE_VALUES = ["CD", "D", "GD", "GI", "GS", "GW", "GWD", "HE", "HS", "LI", "OGI",
                   "OGW", "OW", "OWD", "OWI", "PO", "TW", "WD", "WI", "WS", "tw"]
WELLTYPE_DESC = (
    "Most current DOGM well type. Values: "
    "OW=Oil Well; GW=Gas Well; OGW=Combined Oil and Gas Well; "
    "OWI=Combined Oil well / Water Injection well; OGI=Combined Oil well / Gas Injection well; "
    "OWD=Combined Oil well / Water Disposal well; GWD=Combined Gas well / Water Disposal well; "
    "D=Dry Hole; CD=Carbon Dioxide well; HE=Helium well; LI=Lithium well; PO=Potash well; "
    "WI=Water Injection well (service); GI=Gas Injection well (service); "
    "WD=Water Disposal well (service); WS=Water Source well (service); "
    "GS=Gas Storage well (service); TW=Test Well (service; strat/core test, monitor, etc.); "
    "tw=lowercase data-entry variant of TW (Test Well); "
    "GD, HS=rare codes present in the data but absent from the DOGM published well-type list "
    "(meaning not documented by the source).")

WORKTYPE_VALUES = ["DEEPEN", "DRILL", "REENTER"]
WORKTYPE_DESC = ("Most recent well work type. Values: DRILL=Drill a new well; "
                 "DEEPEN=Deepen an existing well; REENTER=Re-enter an existing wellbore.")

LEASETYPE_VALUES = ["Federal", "Fee", "Indian", "State", "Unknown"]
LEASETYPE_DESC = ("Current mineral lease type. Values: Federal=Federal lease; State=State lease; "
                  "Indian=Tribal/Indian lease; Fee=private fee lands; Unknown=not recorded.")

MM_STATUS_VALUES = ["APP", "NAP", "NPR", "RET"]
MM_STATUS_DESC = ("Mineral-mine permit/application status. Values: APP=Approved (active permit); "
                  "RET=Retired/terminated; NAP=Not a permit / no active permit; "
                  "NPR=No permit required (exempt).")

MM_MINESTATUS_VALUES = ["ABD", "ACT", "ARC", "FOR", "INA", "INS", "PRO", "REC", "RET", "SUS"]
MM_MINESTATUS_DESC = ("Operational mine status. Values: ACT=Active; INA=Inactive; "
                      "SUS=Suspended; PRO=Proposed; REC=Reclaimed; ABD=Abandoned; "
                      "ARC=Archived; RET=Retired; FOR=Forfeited; INS=Inspection/insufficient status.")

COAL_STATUS_VALUES = ["Abandoned", "Active", "Forfeiture", "Inactive",
                      "Relinquished Mine", "Temporary Cessation"]
COAL_STATUS_DESC = ("Coal permit status (self-describing): Active, Inactive, Abandoned, "
                    "Forfeiture, Relinquished Mine, Temporary Cessation.")

FIELDS_STATUS_VALUES = ["ACTIVE"]
FIELDS_STATUS_DESC = "Producing-field status. Values: ACTIVE=field is active/producing."


# per-sub-layer definitions
SUBS = {
    "wells": dict(
        seg="wells", key="udogm-wells", layer="wells", geom="point", res=10,
        title="Utah DNR / UDOGM — Oil & Gas Wells",
        count=40344,
        src="Utah Trust Lands / DOGM Energy_Wells_DOGM FeatureServer layer 4 "
            "(surface locations), native EPSG:26912 (UTM 12N), re-projected to EPSG:4326.",
        year_src="`origcompld` (original completion date), falling back to `eventdate` "
                 "(most recent well event); Esri epoch-ms dates converted to calendar year.",
        cols=[
            col("api", "string", "API well number (14-digit American Petroleum Institute identifier; "
                "digits 1-2 = 43 for Utah). Unique per wellbore event."),
            col("wellname", "string", "Well name (free-text)."),
            col("operator", "string", "Current well operator / company name (free-text)."),
            col("fieldname", "string", "Name of the oil & gas field the well is in (free-text; "
                "joins to udogm-oil-gas-fields FIELDNAME)."),
            col("county", "string", "County name."),
            col("leasetype", "string", LEASETYPE_DESC, LEASETYPE_VALUES),
            col("wellstatus", "string", WELLSTATUS_DESC, WELLSTATUS_VALUES),
            col("welltype", "string", WELLTYPE_DESC, WELLTYPE_VALUES),
            col("worktype", "string", WORKTYPE_DESC, WORKTYPE_VALUES),
            col("unitname", "string", "Name of the drilling/production unit, where applicable (free-text)."),
        ],
        hex_note=None,  # points: one cell per feature
    ),
    "mineral-mines": dict(
        seg="mineral-mines", key="udogm-mineral-mines", layer="mineral-mines",
        geom="point", res=10,
        title="Utah DNR / UDOGM — Mineral Mine Permits (non-coal)",
        count=1504,
        src="Utah DNR OGM Minerals_Permits_View_Layer FeatureServer layer 0 "
            "(vwMineralsPermitsSurvey123), re-projected to EPSG:4326.",
        year_src="`approved` (permit approval date; Esri epoch-ms) converted to calendar year.",
        cols=[
            col("Permit", "string", "Mineral-mine permit number/identifier."),
            col("Status", "string", MM_STATUS_DESC, MM_STATUS_VALUES),
            col("Mine_Name", "string", "Mine name (free-text)."),
            col("Mineral_Type", "string", "Commodity / mineral type mined (free-text; ~485 distinct "
                "descriptive values incl. combinations like 'GOLD, SILVER' and 'SAND AND GRAVEL' — "
                "an uncontrolled free-text vocabulary, not a coded enum)."),
            col("Company", "string", "Operator / company name (free-text)."),
            col("Mine_Status", "string", MM_MINESTATUS_DESC, MM_MINESTATUS_VALUES),
            col("County", "string", "County name."),
            col("Surface_Owner", "string", "Surface land ownership (free-text)."),
            col("app_acr", "int64", "Permitted / applied-for acreage of the mine operation (acres)."),
            col("Bond_Amount", "int64", "Reclamation bond amount posted for the permit (US dollars)."),
        ],
        hex_note=("`app_acr` and `Bond_Amount` are per-feature totals; each point maps to exactly "
                  "one h10 cell, so they are safe to SUM across distinct features at native "
                  "resolution, but at coarser rollups (h9/h8/h0) multiple mines can share a cell "
                  "— aggregate by COUNT/DISTINCT `_cng_fid`, not by re-summing per cell."),
    ),
    "coal-permits": dict(
        seg="coal-permits", key="udogm-coal-permits", layer="coal-permits",
        geom="polygon", res=10,
        title="Utah DNR / UDOGM — Coal Permit Boundaries",
        count=32,
        src="Utah DNR OGM Coalpermit FeatureServer layer 0 "
            "(CoalpermitAttributes_Updated_CopyFeatures), re-projected to EPSG:4326.",
        year_src="none — the source has no reliable permit-issue date (only GIS edit-tracking "
                 "timestamps), so `year` is NULL for every coal permit.",
        cols=[
            col("permit_no", "string", "Coal permit number/identifier (e.g. 'C/007/0011')."),
            col("status", "string", COAL_STATUS_DESC, COAL_STATUS_VALUES),
            col("company", "string", "Permittee company name (free-text)."),
            col("mine_name", "string", "Coal mine name (free-text)."),
            col("County", "string", "County name."),
            col("acres", "double", "Permit-area acreage as carried in the source attributes."),
            col("TotalPermitArea", "double", "Total permitted area (acres)."),
            col("TotalDisturbedArea", "double", "Total disturbed area within the permit (acres)."),
        ],
        hex_note=("`acres`, `TotalPermitArea` and `TotalDisturbedArea` are per-feature totals "
                  "repeated on every hex cell a permit polygon covers — never SUM them on the hex; "
                  "dedup by `_cng_fid` first (SELECT DISTINCT _cng_fid, acres). For permit ground "
                  "area from the H3 footprint see the h3-guide."),
    ),
    "oil-gas-fields": dict(
        seg="oil-gas-fields", key="udogm-oil-gas-fields", layer="oil-gas-fields",
        geom="polygon", res=8,
        title="Utah DNR / UDOGM — Oil & Gas Producing Fields",
        count=153,
        src="Utah SGID Oil & Gas Fields (steward Utah DNR OGM & UGRC), "
            "Oil_and_Gas_Fields FeatureServer layer 0 (OilGasFields_update), EPSG:4326.",
        year_src="`DATE` (discovery/establishment year, a 4-character year string) parsed to integer.",
        cols=[
            col("FIELDNUM", "int64", "Field number (unique field identifier)."),
            col("FIELDNAME", "string", "Producing-field name (free-text)."),
            col("STATUS", "string", FIELDS_STATUS_DESC, FIELDS_STATUS_VALUES),
            col("COUNTY", "string", "County FIPS code (Utah 3-digit / 2-digit county FIPS number)."),
            col("PROD_FORM_", "string", "Primary producing formation/reservoir abbreviation (free-text)."),
            col("DISC_WELL", "string", "Discovery well API number (identifier of the field's discovery well)."),
            col("COMMENTS", "string", "Free-text notes from the source."),
        ],
        hex_note=("Producing-field polygons expand across many h8 cells; count distinct fields with "
                  "COUNT(DISTINCT `_cng_fid`) (or DISTINCT FIELDNUM), never by counting hex rows. "
                  "For field ground area from the H3 footprint see the h3-guide."),
    ),
}


def build_assets(s):
    seg, key, layer = s["seg"], s["key"], s["layer"]
    flat_cols = s["cols"] + [YEAR, CNG_FID, OGC_FID, GEOM]
    hex_cols = s["cols"] + [YEAR, CNG_FID, OGC_FID] + hidx(s["res"])
    pm_cols = [{k: c[k] for k in ("name", "type", *(("values",) if "values" in c else ()))}
               for c in (s["cols"] + [YEAR, CNG_FID])]

    parents = {10: [9, 8, 0], 8: [0]}[s["res"]]
    geom_word = "point" if s["geom"] == "point" else "polygon"
    hex_desc = (f"H3 hex (native resolution {s['res']}, parents {parents}) of the "
                f"{s['count']:,} {geom_word} features. One row = one (feature, H3 cell) pair. ")
    if s["geom"] == "point":
        hex_desc += (f"Each point maps to exactly one h{s['res']} cell "
                     "(no reducer, no dedup; multiple points in a cell are not merged). ")
    if s["hex_note"]:
        hex_desc += s["hex_note"]

    return {
        f"{key}-parquet": {
            "href": f"{BASE}/udogm/{seg}.parquet",
            "type": "application/x-parquet",
            "title": f"{s['title']} (GeoParquet)",
            "roles": ["data"],
            "table:columns": flat_cols,
        },
        f"{key}-pmtiles": {
            "href": f"{BASE}/udogm/{seg}.pmtiles",
            "type": "application/vnd.pmtiles",
            "title": f"{s['title']} (PMTiles)",
            "roles": ["visual"],
            "vector:layers": [layer],
            "table:columns": pm_cols,
        },
        f"{key}-hex": {
            "href": f"{BASE}/udogm/{seg}/hex/h0=*/data_0.parquet",
            "type": "application/x-parquet",
            "title": f"{s['title']} (H3 hex, res {s['res']})",
            "roles": ["data"],
            "h3:native_resolution": s["res"],
            "h3:parent_resolutions": parents,
            "description": hex_desc,
            "table:columns": hex_cols,
        },
    }


def build_collection():
    assets = {}
    layer_lines = []
    for s in SUBS.values():
        assets.update(build_assets(s))
        layer_lines.append(f"{s['title']} ({s['count']:,} features, "
                           f"{'point' if s['geom']=='point' else 'polygon'}; source: {s['src']} "
                           f"year: {s['year_src']})")
    description = (
        "Utah DNR Division of Oil, Gas and Mining (UDOGM) operational data: the state authority "
        "on permitted extractive operations across ALL Utah lands (federal, state, and private) — "
        "the 'what is actually permitted, producing, and operating on the ground' complement to the "
        "geologic-occurrence layers (UGS mineral occurrences) and the federal legal-interest layers "
        "(BLM oil & gas leases, BLM mining claims). Four sub-layers, each with GeoParquet + PMTiles "
        "+ H3 hex. " + " ".join(layer_lines) +
        " Point layers (wells, mineral-mines) map each feature to one H3 cell at native resolution "
        "10; polygon layers (coal-permits res 10, oil-gas-fields res 8) are polyfilled — per-feature "
        "area/amount columns are repeated on every covered cell and must be deduped by `_cng_fid` "
        "before SUM (see each hex asset). A numeric `year` is derived per layer where a reliable "
        "date field exists, NULL otherwise (coal permits have no reliable date). Distributed through "
        "the Utah SGID; licensed CC-BY-4.0 (steward: Utah DNR Division of Oil, Gas and Mining; "
        "Utah Geospatial Resource Center).")
    return {
        "stac_version": "1.0.0",
        "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json"],
        "type": "Collection",
        "id": "udogm",
        "title": "Utah DNR / UDOGM — Permitted Mines, Wells & Oil-Gas Fields",
        "description": description,
        "license": "CC-BY-4.0",
        "keywords": ["Utah", "oil and gas", "wells", "mining", "coal", "minerals",
                     "producing fields", "UDOGM", "DOGM", "public lands", "energy"],
        "extent": {
            "spatial": {"bbox": [[-114.05, 36.99, -109.04, 42.0]]},
            "temporal": {"interval": [["1899-01-01T00:00:00Z", "2026-12-31T00:00:00Z"]]}},
        "providers": [
            {"name": "Utah DNR Division of Oil, Gas and Mining (UDOGM)",
             "roles": ["producer", "licensor"], "url": "https://ogm.utah.gov/"},
            {"name": "Utah Geospatial Resource Center (SGID)", "roles": ["host"],
             "url": "https://gis.utah.gov/"},
            {"name": "Boettiger Lab (cng-datasets processing)", "roles": ["processor"],
             "url": f"{BASE}/"}],
        "links": [
            {"rel": "self", "href": f"{BASE}/udogm/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": BUCKET_SELF, "type": "application/json"},
            {"rel": "license", "href": "https://gis.utah.gov/documentation/policy/aggregation-license/",
             "type": "text/html"}],
        "assets": assets,
    }


if __name__ == "__main__":
    doc = build_collection()
    path = "/tmp/udogm-stac-collection.json"
    json.dump(doc, open(path, "w"), indent=2)
    print(f"wrote {path}  ({len(doc['assets'])} assets)")
