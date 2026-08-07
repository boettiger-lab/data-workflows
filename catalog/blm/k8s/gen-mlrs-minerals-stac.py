#!/usr/bin/env python3
"""Generate STAC collections + READMEs for the seven BLM National MLRS mineral
case-record datasets (data-workflows #486).

⚠️ WRITES TO /tmp ONLY. STAC JSON and README files are NRP-S3-canonical and must never be
committed to this repo (AGENTS.md HARD BOUNDARY 1). This script is a generator, not an
artifact — the same arrangement as
`catalog/facts/k8s/common-attributes-2026-06/gen_stac.py`. Output goes to /tmp/486-stac/
for review, then `rclone copyto` to nrp:public-blm/<layer>/.

Why a generator rather than seven hand-written collections: AGENTS.md requires the flat
GeoParquet and the hex asset to carry the SAME per-column text (single authority), because
the mcp-data-server#303 renderer dedups identical descriptions across assets and would
silently drop a per-column note that differs between them. Seven hand-edits across two
schema variants guarantees drift; one table cannot drift. The PMTiles asset gets the LEAN
form (name + type + values, no prose).

Every `values` array is read from the INGESTED parquet, never from the upstream
FeatureServer — stage-raw collapses whitespace, maps empty to NULL and repairs U+00A0, so
the upstream DISTINCT set is not the ingested set, and `verify-stac.py` HARD-fails a
`values` array that is missing an ingested value.

    python3 catalog/blm/k8s/gen-mlrs-minerals-stac.py            # all seven + parent
    python3 catalog/blm/k8s/gen-mlrs-minerals-stac.py coal-cases # one layer
"""

import importlib.util
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = pathlib.Path("/tmp/486-stac")
BASE = "https://s3-west.nrp-nautilus.io/public-blm"
ROOT_CATALOG = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"

# Reuse verify-stac.py's MCP client so the `values` arrays and the extents come from the
# same source of truth the gate will check them against.
_spec = importlib.util.spec_from_file_location("vs", REPO / "scripts" / "verify-stac.py")
_vs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vs)

# Cardinality above which a column is documented as free text with NO `values` array.
# verify-stac.py's recall pass only nudges below 40, and an INCOMPLETE array is a HARD
# failure while no array is at most advisory — so a 108-value CMMDTY is better left open.
MAX_VALUES = 40

# --- the seven layers -------------------------------------------------------------------
from importlib.machinery import SourceFileLoader  # noqa: E402

_gen = SourceFileLoader("gen", str(HERE / "gen-mlrs-minerals.py")).load_module()
LAYERS = {s["name"]: s for s in _gen.LAYERS}

META = {
    "coal-cases": dict(
        title="BLM National Coal Cases",
        what="Federal coal leases, licenses, exploration licenses and logical mining units",
        detail="Coal is a *leasable* mineral under the Mineral Leasing Act of 1920: the "
               "government leases the right to mine rather than allowing it to be claimed. "
               "This layer is the federal coal estate's case record — every lease, "
               "preference-right lease, exploration license, logical mining unit and "
               "prospecting permit BLM administers, with its disposition and acreage. It is "
               "the layer to use for questions about coal near the Kaiparowits Plateau and "
               "the Grand Staircase-Escalante boundary changes.",
        keywords=["coal", "mineral leasing", "leasable minerals", "Kaiparowits"]),
    "geothermal-leases": dict(
        title="BLM National Geothermal Leases",
        what="Federal geothermal leases and utilization sites",
        detail="Geothermal is a leasable energy mineral under the Geothermal Steam Act of "
               "1970. Competitive and noncompetitive leases (pre- and post-2005 terms), "
               "converted mining-claimant leases, direct-use leases and utilization sites. "
               "Carries FRMTN (the producing formation) and a production status.",
        keywords=["geothermal", "renewable energy", "leasable minerals"]),
    "oil-shale-leases": dict(
        title="BLM National Oil Shale Leases",
        what="Federal oil shale RD&D leases, preference-right leases and exploration licenses",
        detail="The smallest MLRS mineral layer — 42 cases, concentrated in the Green River "
               "Formation of Colorado, Utah and Wyoming. Mostly research, development and "
               "demonstration (RD&D) leases issued under the Energy Policy Act of 2005.",
        keywords=["oil shale", "unconventional fuels", "Green River Formation"]),
    "non-energy-leasables": dict(
        title="BLM National Non-Energy Leasable Minerals",
        what="Federal leases for non-energy leasable minerals",
        detail="The non-fuel leasable estate: phosphate, sodium, potassium, sulfur, "
               "gilsonite, asphalt, and hardrock minerals on acquired lands (which are "
               "leased rather than claimed). Over 100 distinct commodities. Utah's "
               "gilsonite and potash cases and the Western phosphate field are here.",
        keywords=["phosphate", "potash", "sodium", "gilsonite", "leasable minerals"]),
    "mineral-materials": dict(
        title="BLM National Mineral Materials (Salable)",
        what="Federal sales and free-use permits for salable mineral materials",
        detail="The *salable* class — common-variety sand, gravel, stone, clay and fill, "
               "governed by the Materials Act of 1947. Unlike leasable and locatable "
               "minerals these are sold outright or permitted for free use, often to "
               "counties and other government subdivisions for road material. Includes "
               "community pits, common use areas and BLM quarries. The largest of the seven.",
        keywords=["sand and gravel", "salable minerals", "community pit", "quarry"]),
    "oil-gas-agreements": dict(
        title="BLM National Oil & Gas Agreements",
        what="Federal oil & gas unit and communitization agreements",
        detail="The administrative units that organize oil & gas development across lease "
               "boundaries: exploratory and secondary unit agreements, communitization "
               "agreements, development contracts, gas storage agreements and compensatory "
               "royalty agreements, including the Indian and NPR-A variants. These are the "
               "*agreements* that sit above the individual leases in #451, and are the "
               "companion to the participating areas in oil-gas-participating-areas.",
        keywords=["oil and gas", "unit agreement", "communitization", "NPR-A"]),
    "oil-gas-participating-areas": dict(
        title="BLM National Oil & Gas Participating Areas",
        what="Participating areas within federal oil & gas unit agreements",
        detail="A participating area is the portion of a unit agreement determined to be "
               "productive from a particular formation — the sub-area whose tracts actually "
               "share in production. Each carries its FRMTN (formation), so one unit may "
               "have several participating areas stacked on different reservoirs.",
        keywords=["oil and gas", "participating area", "unit agreement", "formation"]),
}

# --- column authority -------------------------------------------------------------------
# One description per column, written once and emitted IDENTICALLY to the flat GeoParquet
# and the hex asset (AGENTS.md single-authority rule). `RCRD_ACRS` is the sole exception
# and is handled below, because its correct guidance genuinely differs between the two.
COLS = {
    "CSE_NR": ("string", "BLM case serial number — the case's unique identifier (e.g. "
               "UTU0088556). The two-letter prefix is the administering state office."),
    "LEG_CSE_NR": ("string", "Legacy case number carried over from the pre-MLRS records "
                   "system, where one exists."),
    "CSE_NAME": ("string", "Case name as recorded by BLM — typically the lessee, operator, "
                 "unit or geographic feature. Free text; null where unnamed."),
    "CSE_TYPE_NR": ("string", "Internal MLRS case-type number backing BLM_PROD."),
    "BLM_PROD": ("string", "BLM case subtype — the specific authorization instrument."),
    "CSE_DISP": ("string", "Case disposition (status). This is the field to filter on for "
                 "active versus closed cases."),
    "CMMDTY": ("string", "Commodity the case covers."),
    "FRMTN": ("string", "Producing or target geologic formation. Free text as recorded by "
              "BLM; null where not specified."),
    "PRDCNG": ("string", "Production status — whether the case is held by production."),
    "SRC": ("string", "Provenance of the geometry: how the Legal Land Description was "
            "converted to a polygon (LLD = geocoded from the land description, "
            "LLD/CLS = land description plus cadastral survey, MIGRATE/BULK/Batch = "
            "bulk-loaded during the MLRS migration, PROTOOLS/EGMS = other BLM tooling)."),
    "ADMIN_STATE": ("string", "BLM administrative state office managing the case."),
    "GEO_STATE": ("string", "State the case is geographically located in. Differs from "
                  "ADMIN_STATE where one state office administers cases in another state."),
    "RCRD_ACRS": ("double", None),  # per-asset; see acres_desc()
    "EFF_DT": ("date", "Case effective date — when the lease, permit or agreement took "
               "effect. Sparse on the leasable/salable layers; see case_year."),
    "EXP_DT": ("date", "Case expiration date, where one is recorded."),
    "SALE_DT": ("date", "Sale date, where the case arose from a competitive sale. Sparse."),
    "CSE_DISP_DT": ("date", "Case disposition date — when the case reached its current "
                    "disposition (typically closure). Near-complete on this layer, which is "
                    "why it backs case_year where EFF_DT is absent."),
    "Created": ("date", "MLRS record-creation date. A record-management date from the "
                "digital migration window, NOT a date the case itself began."),
    "Modified": ("date", "MLRS record-last-modified date. A record-management date, not a "
                 "case milestone."),
    "CUST_NM_SEC": ("string", "Business account holding the interest — the lessee, permittee "
                    "or operator of record."),
    "PCT_INT_SEC": ("int32", "Percentage interest the business account holds in the case."),
    "INT_REL_SEC": ("string", "Interest relationship — the role in which the business "
                    "account holds its interest (e.g. lessee, operator, payor)."),
    "eff_year": ("int32", "Integer year of EFF_DT; null where EFF_DT is absent. Derived at "
                 "ingest. Years outside 1800–2100 are withheld (MLRS uses a year-3999 "
                 "'no known end' sentinel); the raw EFF_DT is retained verbatim."),
    "disp_year": ("int32", None),  # per-layer; see disp_year_desc()
    "case_year": ("int32", None),  # per-layer; see case_year_desc()
    "case_year_src": ("string", "Which date case_year came from: 'effective' (EFF_DT) or "
                      "'disposition' (CSE_DISP_DT). Null where case_year is null. Filter on "
                      "this to separate a case *start* year from a case *closure* year "
                      "rather than mixing them."),
    "OGC_FID": ("int64", "Sequential feature id added by the GDAL/OGR conversion. Use "
                "_cng_fid as the stable per-feature key."),
    "_cng_fid": ("int64", "Cloud-native feature ID, unique per source row. The dedup key "
                 "for hex aggregation."),
}

HEX_INDEX_COLS = [
    ("h10", "uint64", "H3 cell ID at resolution 10 (native; one row per (feature, h10) pair)."),
    ("h9", "uint64", "H3 cell ID at resolution 9."),
    ("h8", "uint64", "H3 cell ID at resolution 8 (catalog universal join key)."),
    ("h0", "int64", "H3 cell ID at resolution 0, used as the hive partition key."),
]

# Columns worth a `values` array when their cardinality is small enough.
CATEGORICAL = ("CSE_DISP", "CMMDTY", "BLM_PROD", "PRDCNG", "SRC",
               "ADMIN_STATE", "GEO_STATE", "INT_REL_SEC", "case_year_src")


# ADMIN_STATE / GEO_STATE are two-letter codes, so verify-stac.py requires an inline
# CODE=Definition list rather than a bare value enumeration. BLM administrative state
# offices use postal codes plus `ES` (Eastern States, the office covering all states east
# of the Mississippi); GEO_STATE uses ordinary postal codes.
STATE_NAMES = {
    "AK": "Alaska", "AL": "Alabama", "AR": "Arkansas", "AZ": "Arizona",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DC": "District of Columbia",
    "DE": "Delaware", "ES": "Eastern States (BLM office east of the Mississippi)",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "IA": "Iowa", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "MA": "Massachusetts", "MD": "Maryland", "ME": "Maine", "MI": "Michigan",
    "MN": "Minnesota", "MO": "Missouri", "MS": "Mississippi", "MT": "Montana",
    "NC": "North Carolina", "ND": "North Dakota", "NE": "Nebraska", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NV": "Nevada", "NY": "New York",
    "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "PR": "Puerto Rico", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VA": "Virginia", "VI": "U.S. Virgin Islands", "VT": "Vermont", "WA": "Washington",
    "WI": "Wisconsin", "WV": "West Virginia", "WY": "Wyoming",
}
STATE_COLS = ("ADMIN_STATE", "GEO_STATE")


# verify-stac.py treats a `values` array as self-documenting only when EVERY value is a
# human-readable label — it must contain whitespace, or contain a lowercase letter and be
# at least four characters. A single opaque all-caps token in an otherwise wordy enum
# (coal's CMMDTY is 'COAL, BITUMINOUS', 'Oil & Gas', … plus bare 'COBALT' and 'NONE')
# makes the whole column a "coded categorical" requiring an inline CODE=Definition list.
# Rather than gloss every value — noise when the value already IS its definition — we
# gloss only the opaque tokens and render the full list as VALUE=Definition when any are
# present. Unmapped opaque tokens raise rather than silently shipping a partial map.
OPAQUE_GLOSS = {
    "NONE": "No commodity recorded on the case",
    "COBALT": "Cobalt",
    # SRC — how the polygon was derived. (verify-stac.py exempts *src/*source columns from
    # the coded-categorical rule, but these codes are genuinely opaque, so gloss them.)
    "LLD": "Geocoded from the Legal Land Description",
    "LLD/CLS": "Geocoded from the Legal Land Description plus cadastral survey",
    "BULK": "Bulk-loaded during the MLRS migration",
    "BATCH": "Batch-loaded",
    "EGMS": "Loaded from the EGMS system",
    "MIGRATE": "Migrated from the pre-MLRS records system",
    "PROTOOLS": "Created with BLM ProTools",
    "MICA": "Mica",
    "SAND": "Sand",
    "TALC": "Talc",
    "ZINC": "Zinc",
    "GOLD": "Gold",
    "IRON": "Iron",
    "LEAD": "Lead",
    "PEAT": "Peat",
    "SALT": "Salt",
}


def is_self_describing(v):
    """Mirror verify-stac.py's rule so we only add glosses where they are required."""
    s = str(v)
    if any(ch.isspace() for ch in s):
        return True
    return any(ch.islower() for ch in s) and len(s) >= 4


def value_defs(col, vals):
    """Render `values` for a description. Plain list when every value speaks for itself;
    VALUE=Definition when any opaque token forces the coded-categorical rule."""
    opaque = [v for v in vals if not is_self_describing(v)]
    if not opaque:
        return ", ".join(vals)
    missing = [v for v in opaque if v not in OPAQUE_GLOSS]
    assert not missing, (
        f"column {col}: opaque value(s) {missing} need an entry in OPAQUE_GLOSS — "
        f"verify-stac.py requires an inline CODE=Definition list once any value in the "
        f"enum is not self-describing")
    return ", ".join(f"{v}={OPAQUE_GLOSS.get(v, v)}" for v in vals)


def state_defs(codes):
    unknown = [c for c in codes if c not in STATE_NAMES]
    assert not unknown, f"unmapped state code(s) {unknown} — add them to STATE_NAMES"
    return ", ".join(f"{c}={STATE_NAMES[c]}" for c in codes)


def acres_desc(hexed, upstream_dup):
    """`upstream_dup` is True when the SOURCE file already holds several rows per CSE_NR
    (axis 2). That changes the correct advice on the FLAT asset, where SUM is otherwise
    safe — getting this wrong is the #309 over-count class, so it is derived from the
    data (rows vs COUNT(DISTINCT CSE_NR)) rather than assumed per layer."""
    base = ("Recorded case acreage as carried in the BLM case record (source RCRD_ACRS). "
            "This is the *recorded* acreage of the case, not the area of the geocoded "
            "polygon — the LLD geocoder snaps to whole PLSS aliquots, so the polygon is "
            "often larger. ")
    if hexed:
        tail = ("Per-feature total repeated on every hex cell the case covers — never "
                "SUM(RCRD_ACRS) on the hex asset; dedup by _cng_fid first "
                "(SELECT DISTINCT _cng_fid, RCRD_ACRS).")
        if upstream_dup:
            tail += (" This layer ALSO has upstream row duplication, so to total by CASE "
                     "rather than by source row dedup on CSE_NR instead — _cng_fid is "
                     "unique per row and will not collapse it.")
        return base + tail
    if upstream_dup:
        return base + ("REPEATED — this layer holds several source rows per CSE_NR with "
                       "the value copied onto each, so a raw SUM(RCRD_ACRS) over-counts. "
                       "Dedup first: SELECT DISTINCT CSE_NR, RCRD_ACRS. Use "
                       "COUNT(DISTINCT CSE_NR) for the case count, not COUNT(*).")
    return base + "One row per case on the flat GeoParquet, so SUM is correct here."


def disp_year_desc(spec):
    if spec["variant"] == "leasable":
        return ("Integer year of CSE_DISP_DT; null where absent. Derived at ingest. Years "
                "outside 1800–2100 are withheld (the year-3999 sentinel).")
    return ("Always NULL on this layer — the MLRS energy services expose no CSE_DISP_DT. "
            "The column exists so all seven mineral case-record datasets share one column "
            "list; use case_year for the time slider.")


def case_year_desc(spec, pct):
    src = ("COALESCE(eff_year, disp_year)" if spec["variant"] == "leasable"
           else "eff_year (this layer has no CSE_DISP_DT to fall back to)")
    return (f"Uniform year column for time filtering and the app's year slider, common to "
            f"all seven BLM mineral case-record datasets: {src}. Populated on {pct} of "
            f"features here. Check case_year_src to see whether a given value is a case "
            f"*start* (effective) or *closure* (disposition) year — they are not "
            f"interchangeable for 'active cases in year X' questions.")


def q(mcp, sql):
    return mcp.query(sql)


def scalar(rows, key):
    return rows[0][key] if rows else None


def build(name, mcp):
    spec = LAYERS[name]
    meta = META[name]
    flat = f"s3://public-blm/{name}.parquet"
    hexp = f"s3://public-blm/{name}/hex/h0=*/data_0.parquet"
    leasable = spec["variant"] == "leasable"

    # --- facts from the ingested data ---
    stats = q(mcp, f"""
        SELECT COUNT(*) AS rows, COUNT(DISTINCT _cng_fid) AS fids,
               COUNT(DISTINCT CSE_NR) AS cases,
               COUNT(*) FILTER (WHERE geom IS NULL) AS null_geom,
               COUNT(case_year) AS cy,
               MIN(case_year) AS y0, MAX(case_year) AS y1,
               COUNT(*) FILTER (WHERE case_year_src='effective') AS n_eff,
               COUNT(*) FILTER (WHERE case_year_src='disposition') AS n_disp,
               ROUND(ST_XMin(ST_Extent_Agg(geom)),4) AS xmin,
               ROUND(ST_YMin(ST_Extent_Agg(geom)),4) AS ymin,
               ROUND(ST_XMax(ST_Extent_Agg(geom)),4) AS xmax,
               ROUND(ST_YMax(ST_Extent_Agg(geom)),4) AS ymax
        FROM read_parquet('{flat}')""")[0]
    n = int(stats["rows"])
    null_geom = int(stats["null_geom"])
    n_cases = int(stats["cases"])
    schema = {c["column_name"]: c["column_type"]
              for c in q(mcp, f"DESCRIBE SELECT * FROM read_parquet('{flat}')")}
    present = set(schema)
    # Temporal extent over the CASE dates only (not the MLRS record-management dates
    # Created/Modified, which would pin every layer's start to the migration window).
    # A date column that is 100% null converts to VARCHAR rather than DATE, so select on
    # the actual type instead of the variant -- e.g. oil-gas-participating-areas ships
    # SALE_DT and EXP_DT entirely empty.
    date_cols = [c for c in ("EFF_DT", "EXP_DT", "SALE_DT", "CSE_DISP_DT")
                 if schema.get(c) == "DATE"]
    assert date_cols, f"{name}: no DATE-typed case-date column to build a temporal extent"
    union = " UNION ALL ".join(
        f'SELECT "{c}" AS d FROM read_parquet(\'{flat}\')' for c in date_cols)
    dates = q(mcp, f"SELECT MIN(d) AS lo, MAX(d) AS hi FROM ({union}) "
                   f"WHERE d IS NOT NULL AND YEAR(d) BETWEEN 1800 AND 2100")[0]
    # The MCP `query` tool renders a DuckDB DATE as a full timestamp with
    # microseconds ("1974-03-01T00:00:00.000000"), NOT a bare "1974-03-01".
    # Slice to the date part before composing the RFC 3339 instant below --
    # appending to the raw value yields "…T00:00:00.000000T00:00:00Z", which
    # pystac (via dateutil.isoparse) rejects with "Unused components in ISO
    # string", making the whole collection unloadable for every MCP consumer.
    lo, hi = str(dates["lo"])[:10], str(dates["hi"])[:10]

    # --- categorical values, straight from the ingested parquet ---
    values = {}
    for col in CATEGORICAL:
        if col not in present:
            continue
        cnt = int(scalar(q(mcp, f'SELECT COUNT(DISTINCT "{col}") AS n '
                              f"FROM read_parquet('{flat}')"), "n"))
        if 0 < cnt <= MAX_VALUES:
            rows = q(mcp, f'SELECT DISTINCT "{col}" AS v FROM read_parquet(\'{flat}\') '
                          f'WHERE "{col}" IS NOT NULL AND trim(CAST("{col}" AS VARCHAR)) <> \'\' '
                          f"ORDER BY 1")
            values[col] = [str(r["v"]) for r in rows]

    pct = f"{100.0 * int(stats['cy']) / n:.0f}%"

    def col_entry(cname, hexed):
        typ, desc = COLS[cname]
        if cname == "RCRD_ACRS":
            desc = acres_desc(hexed, n_cases < n)
        elif cname == "disp_year":
            desc = disp_year_desc(spec)
        elif cname == "case_year":
            desc = case_year_desc(spec, pct)
        e = {"name": cname, "type": typ, "description": desc}
        if cname in values:
            if cname in STATE_COLS:
                e["description"] += " Values: " + state_defs(values[cname]) + "."
            else:
                e["description"] += " Values: " + value_defs(cname, values[cname]) + "."
            e["values"] = values[cname]
        return e

    order = [c for c in COLS if c in present]

    flat_cols = [col_entry(c, False) for c in order] + [
        {"name": "geom", "type": "geometry",
         "description": "Case polygon, geocoded from the Legal Land Description via the "
                        "PLSS (EPSG:4326). NULL where the geocoder could not place the "
                        "description."}]
    hex_cols = ([{"name": h, "type": t, "description": d} for h, t, d in HEX_INDEX_COLS]
                + [col_entry(c, True) for c in order]
                + [{"name": "bbox", "type": "struct",
                    "description": "Bounding box of the H3 cell."}])
    # LEAN PMTiles: name + type + values only, no prose (the definitions stay canonical on
    # the GeoParquet asset; duplicating them across three assets just bloats agent context).
    pm_cols = [{"name": c, "type": COLS[c][0],
                **({"values": values[c]} if c in values else {})}
               for c in order]

    ng = (f" {null_geom:,} of {n:,} cases ({100.0*null_geom/n:.1f}%) have no geometry — the "
          f"PLSS geocoder could not place their Legal Land Description. Those rows are "
          f"retained here in the GeoParquet with a NULL geom but are ABSENT from the PMTiles "
          f"and the H3 hex, so any area, extent or overlap computed from those two assets "
          f"omits them." if null_geom else " Every case is geocoded (no null geometries).")

    dup = ""
    if n_cases < n:
        dup = (f" NOTE — upstream row duplication: {n:,} rows cover only {n_cases:,} distinct "
               f"CSE_NR. To count or sum by CASE rather than by row, dedup on CSE_NR "
               f"(_cng_fid is unique per row and will not collapse this).")

    desc = (f"{meta['what']}, nationwide, from the Bureau of Land Management's National "
            f"MLRS / EGIS program — {n:,} polygon cases converted to cloud-native formats "
            f"(GeoParquet, PMTiles, H3 hex) with parcel-level H3 indexing at resolution 10. "
            f"{meta['detail']}{ng}{dup} Every case carries a uniform numeric `case_year` "
            f"({pct} populated) for time filtering, with `case_year_src` recording whether "
            f"that year is the case's effective date or its disposition date. Part of the "
            f"BLM National MLRS set alongside oil & gas leases, mining claims and "
            f"locatable-mineral operations.")

    hex_note = (f"One row per (case, H3 cell) pair at native resolution 10, with rollup "
                f"columns h9, h8 (the catalog's universal join key), and h0 (the hive "
                f"partition key). Every case attribute is repeated on every cell it covers: "
                f"never SUM per-feature totals (RCRD_ACRS) on the hex asset — dedup by "
                f"_cng_fid first (SELECT DISTINCT _cng_fid, RCRD_ACRS). H3 index columns, "
                f"_cng_fid and bbox are the only columns safe to aggregate directly.")
    if null_geom:
        hex_note += (f" The {null_geom:,} null-geometry cases "
                     f"({100.0*null_geom/n:.1f}% of this layer) are absent here.")
    if dup:
        hex_note += dup

    doc = {
        "stac_version": "1.0.0",
        "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json"],
        "type": "Collection",
        "id": name,
        "title": meta["title"],
        "description": desc,
        "license": "public-domain",
        "keywords": ["BLM", "public lands", "minerals", "MLRS", "United States",
                     *meta["keywords"]],
        "providers": [
            {"name": "U.S. Bureau of Land Management",
             "roles": ["producer", "licensor"],
             "url": "https://www.blm.gov/services/land-records/mlrs"},
            {"name": "Boettiger Lab", "roles": ["processor", "host"],
             "url": "https://boettiger-lab.github.io/"}],
        "extent": {
            "spatial": {"bbox": [[float(stats["xmin"]), float(stats["ymin"]),
                                  float(stats["xmax"]), float(stats["ymax"])]]},
            "temporal": {"interval": [[f"{lo}T00:00:00Z", f"{hi}T00:00:00Z"]]}},
        "links": [
            {"rel": "self", "href": f"{BASE}/{name}/stac-collection.json",
             "type": "application/json"},
            {"rel": "root", "href": ROOT_CATALOG, "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json",
             "type": "application/json"},
            {"rel": "describedby", "href": f"{BASE}/{name}/README.md",
             "type": "text/markdown"},
            {"rel": "about", "href": "https://www.blm.gov/services/land-records/mlrs"},
            {"rel": "license", "href": "https://www.usa.gov/government-works",
             "title": "U.S. Government Works (public domain)"}],
        "assets": {
            f"{name}-parquet": {
                "href": f"{BASE}/{name}.parquet",
                "type": "application/vnd.apache.parquet",
                "title": f"GeoParquet — {meta['title']}",
                "roles": ["data"],
                "description": (f"Flat GeoParquet, one row per source case record. "
                                f"{null_geom:,} rows have a NULL geom." if null_geom else
                                "Flat GeoParquet, one row per source case record."),
                "table:columns": flat_cols},
            f"{name}-pmtiles": {
                "href": f"{BASE}/{name}.pmtiles",
                "type": "application/vnd.pmtiles",
                "title": "PMTiles vector tiles for web map display",
                "roles": ["visual"],
                "vector:layers": [name],
                "table:columns": pm_cols},
            f"{name}-hex": {
                "href": f"{BASE}/{name}/hex/h0=*/data_0.parquet",
                "type": "application/vnd.apache.parquet",
                "title": f"H3 hexagonal index (native resolution 10) of {meta['title']}",
                "roles": ["data"],
                "h3:native_resolution": 10,
                "h3:parent_resolutions": [9, 8, 0],
                "description": hex_note,
                "table:columns": hex_cols}},
    }
    return doc, dict(n=n, null_geom=null_geom, cases=n_cases, pct=pct,
                     y0=stats["y0"], y1=stats["y1"], values=values,
                     n_eff=int(stats["n_eff"]), n_disp=int(stats["n_disp"]))


def readme(name, doc, f):
    meta, spec = META[name], LAYERS[name]
    ng = (f"\n> **{f['null_geom']:,} of {f['n']:,} cases ({100.0*f['null_geom']/f['n']:.1f}%) "
          f"have no geometry.** BLM geocodes these polygons from the Legal Land Description "
          f"via the PLSS; where that fails the case is kept in the GeoParquet with a NULL "
          f"`geom` but does not appear in the PMTiles or the H3 hex. Any acreage or overlap "
          f"computed from those two assets omits them.\n" if f["null_geom"] else "")
    dupw = (f"\n> **Upstream row duplication:** {f['n']:,} rows cover only {f['cases']:,} "
            f"distinct `CSE_NR`. Dedup on `CSE_NR` to count or sum by case; `_cng_fid` is "
            f"unique per row and will not collapse it.\n" if f["cases"] < f["n"] else "")
    return f"""# {meta['title']}

{doc['description']}

- **Source:** BLM National MLRS / EGIS — `{spec['service']}/FeatureServer/{spec['layer']}`
- **Extent:** national · **Features:** {f['n']:,} polygons · **License:** public domain (US federal work)
- **H3:** native resolution 10, parents 9, 8, 0 (joins the rest of the catalog at `h8`)
- **Tracked in:** [data-workflows #486](https://github.com/boettiger-lab/data-workflows/issues/486)
{ng}{dupw}
## Web map (MapLibre GL JS)

The PMTiles `source-layer` is **`{name}`** — the last segment of the dataset name. Using
anything else renders a blank layer with no error.

```js
map.addSource('{name}', {{
  type: 'vector',
  url: 'pmtiles://https://s3-west.nrp-nautilus.io/public-blm/{name}.pmtiles'
}});
map.addLayer({{
  id: '{name}-fill',
  type: 'fill',
  source: '{name}',
  'source-layer': '{name}',          // <-- must be exactly this
  paint: {{
    'fill-color': ['match', ['get', 'CSE_DISP'],
      'Authorized', '#E65100', 'Pending', '#FBC02D',
      'Interim', '#8D6E63', 'Closed', '#BDBDBD', '#888888'],
    'fill-opacity': 0.4
  }}
}});
```

## SQL (DuckDB)

```sql
INSTALL spatial; LOAD spatial;
INSTALL httpfs;  LOAD httpfs;

-- active cases by state
SELECT ADMIN_STATE, COUNT(*) AS cases, ROUND(SUM(RCRD_ACRS)) AS acres
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-blm/{name}.parquet')
WHERE CSE_DISP = 'Authorized'
GROUP BY 1 ORDER BY acres DESC;
```

### Time filtering

`case_year` is the uniform numeric year column ({f['pct']} populated here, range
{f['y0']}–{f['y1']}). `case_year_src` says where it came from —
`'effective'` ({f['n_eff']:,} cases) or `'disposition'` ({f['n_disp']:,}). They mean
different things: an effective year is when a case *started*, a disposition year is
usually when it *closed*. For "cases active in year X" use `case_year_src = 'effective'`
together with `CSE_DISP`.

```sql
SELECT case_year, COUNT(*) AS n
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-blm/{name}.parquet')
WHERE case_year IS NOT NULL AND case_year_src = 'effective'
GROUP BY 1 ORDER BY 1;
```

### H3 hex

One row per (case, H3 cell) at resolution 10. **Case attributes repeat on every cell**, so
dedup before summing a per-case total:

```sql
-- correct: acreage of authorized cases, deduped
SELECT SUM(RCRD_ACRS) FROM (
  SELECT DISTINCT _cng_fid, RCRD_ACRS
  FROM read_parquet('https://s3-west.nrp-nautilus.io/public-blm/{name}/hex/h0=*/data_0.parquet')
  WHERE CSE_DISP = 'Authorized');
```

Join to any other catalog dataset at `h8`.
"""


def update_parent(built):
    """Add a child link per new collection to the public-blm parent, and repair the
    existing locatable-operations link, which shipped with no `id` and no `title` — geo
    clients key on `id`, so an untitled child renders as a blank row. Read-modify-write
    against the LIVE parent so concurrent additions by other issues are preserved."""
    import urllib.request
    url = f"{BASE}/stac-collection.json"
    with urllib.request.urlopen(url, timeout=120) as r:
        doc = json.load(r)

    # Backfill id/title on any child link missing them, from the child's own collection.
    for link in doc["links"]:
        if link.get("rel") != "child" or (link.get("id") and link.get("title")):
            continue
        try:
            with urllib.request.urlopen(link["href"], timeout=120) as r:
                child = json.load(r)
            link["id"] = child["id"]
            link["title"] = child.get("title", child["id"])
            print(f"  repaired child link: {link['id']}")
        except Exception as e:                       # noqa: BLE001 - advisory only
            print(f"  WARN could not repair {link['href']}: {e}")

    have = {l.get("id") for l in doc["links"] if l.get("rel") == "child"}
    for name, (cdoc, _) in built.items():
        if name in have:
            doc["links"] = [l for l in doc["links"]
                            if not (l.get("rel") == "child" and l.get("id") == name)]
        doc["links"].append({
            "rel": "child", "id": name, "title": cdoc["title"],
            "href": f"{BASE}/{name}/stac-collection.json",
            "type": "application/json"})

    # The description still promised mining claims and APDs as future work; claims landed
    # in #477 and the mineral case records land here.
    doc["description"] = (
        "Bureau of Land Management public land-record datasets in cloud-native formats "
        "(GeoParquet, PMTiles, H3 hexagonal aggregations). Sourced from the BLM National "
        "MLRS / EGIS program. This collection is a grouping only — select a child "
        "collection to access data. Coverage spans the mineral estate (oil & gas leases "
        "and agreements, coal, geothermal, oil shale, non-energy leasables, salable "
        "mineral materials, mining claims and locatable-mineral operations) as well as "
        "land-use authorizations and tenure.")

    out = OUT / "parent-stac-collection.json"
    out.write_text(json.dumps(doc, indent=2) + "\n")
    kids = [l["id"] for l in doc["links"] if l.get("rel") == "child"]
    print(f"  parent now lists {len(kids)} children: {', '.join(sorted(kids))}")
    return out


def main():
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    names = only or list(LAYERS)
    mcp = _vs.MCPClient()
    mcp.initialize()
    OUT.mkdir(parents=True, exist_ok=True)
    built = {}
    for name in names:
        doc, f = build(name, mcp)
        d = OUT / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "stac-collection.json").write_text(json.dumps(doc, indent=2) + "\n")
        (d / "README.md").write_text(readme(name, doc, f))
        built[name] = (doc, f)
        vals = ", ".join(f"{k}={len(v)}" for k, v in f["values"].items())
        print(f"{name:30s} {f['n']:>7,} rows  {f['null_geom']:>5,} nullgeom  "
              f"case_year {f['pct']:>4} {f['y0']}-{f['y1']}  values[{vals}]")
    if not only:                 # only rewrite the parent on a full run
        update_parent(built)
    return built


if __name__ == "__main__":
    main()
