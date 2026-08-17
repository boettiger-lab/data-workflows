#!/usr/bin/env python3
"""#509 metadata fix for the 3 cpad collections: move the collection-level table:columns
onto the flat GeoParquet asset (reconciled to the actual schema), give the hex asset the
full self-describing schema, add the per-feature-duplication note to the hex description,
and drop the collection-level table:columns. Writes corrected STACs to /tmp for validation
before any S3 write."""
import json, urllib.request, os, tempfile

OUT = os.environ.get("CPAD_OUT", os.path.join(tempfile.gettempdir(), "cpad-out"))
os.makedirs(OUT, exist_ok=True)

# actual parquet schemas (name::duckdbtype), captured from the MCP DESCRIBE and pinned in
# cpad-schemas.txt so the flat/hex table:columns match the data exactly (#534).
SCHEMAS = {}
SCHEMA_RAW = open(os.path.join(os.path.dirname(__file__), "cpad-schemas.txt")).read().strip().splitlines()
for line in SCHEMA_RAW:
    key, cols = line.split("\t", 1)
    SCHEMAS[key] = [c.split("::", 1) for c in cols.split("|")]

DUCK2STAC = {"VARCHAR": "string", "BIGINT": "int64", "INTEGER": "int32", "DOUBLE": "double",
             "DATE": "date", "UBIGINT": "uint64", "BOOLEAN": "boolean"}
def stac_type(dt):
    if dt.startswith("STRUCT"): return "object"
    if dt.startswith("GEOMETRY"): return "geometry"
    return DUCK2STAC.get(dt, dt.lower())

# Coded categoricals needing an explicit CODE=Definition list + values array. Codes are
# the DISTINCT values actually present in the data (nan is a missing-value artifact,
# excluded per #511); definitions are the IUCN protected-area category standard.
CODED = {
    "iucncat": ("IUCN protected-area management category. Values: Ib=Wilderness Area, "
                "IV=Habitat/Species Management Area, V=Protected Landscape/Seascape, "
                "N/A=No IUCN category assigned. Most easements are unclassified.",
                ["N/A", "V", "IV", "Ib"]),
}

SPECIAL = {
    "_cng_fid": "Synthetic per-feature row id assigned by cng-datasets at conversion — one per input feature, row-unique. The universal key for dedup and COUNT(DISTINCT) across assets.",
    "geom": "Feature geometry (GeoParquet).",
    "bbox": "Per-row bounding box (xmin, ymin, xmax, ymax) for spatial pre-filtering.",
    "h0": "H3 cell ID at resolution 0, used as the hive partition key for partitioned reads.",
    "h8": "H3 cell ID at resolution 8.",
    "h9": "H3 cell ID at resolution 9.",
    "h10": "H3 cell ID at resolution 10 (native resolution; one row per (feature, h10) pair).",
}

# collection stac url -> (flat_asset_key, hex_asset_key, flat_schema_key, hex_schema_key,
#                         per-feature total columns for the dedup note)
COLLS = {
    "https://s3-west.nrp-nautilus.io/public-cpad/cpad-holdings-stac-collection.json":
        ("holdings-parquet", "holdings-hex", "cpad-holdings-flat", "cpad-holdings-hex",
         "cpad-holdings-stac-collection.json"),
    "https://s3-west.nrp-nautilus.io/public-cpad/cced-stac-collection.json":
        ("cced-parquet", "cced-hex", "cced-flat", "cced-hex", "cced-stac-collection.json"),
    "https://s3-west.nrp-nautilus.io/public-cpad/cpad-units-stac-collection.json":
        ("units-parquet", "units-hex", "cpad-units-flat", "cpad-units-hex",
         "cpad-units-stac-collection.json"),
}

AREA_HINT = ("ACRES", "GAP1_acres", "GAP2_acres", "GAP3_acres", "GAP4_acres", "GAP_tot_ac",
             "gis_acres")

# Measured sub-cell shortfall (hex COUNT(DISTINCT _cng_fid) < flat COUNT(*)): small
# parcels/slivers below one resolution-10 cell (~3.7 acres) polyfill to zero cells. Keyed
# by hex schema key -> (features_missing, flat_total). Documented so the #535 gate accepts
# it (a legitimate footprint shortfall, not a dropped build).
COVERAGE = {
    "cpad-holdings-hex": (33571, 160522),
    "cced-hex": (6032, 21717),
    "cpad-units-hex": (4286, 17239),
}

def coldef(name, dtype, topmap, hexmap):
    """Build a table:columns entry, preferring an existing description (top-level or the
    hex asset's own), else a standard one for the structural columns."""
    if name.lower() in CODED:
        desc, vals = CODED[name.lower()]
        return {"name": name, "type": stac_type(dtype), "description": desc, "values": vals}
    src = topmap.get(name.lower()) or hexmap.get(name.lower())
    d = {"name": name, "type": stac_type(dtype)}
    if src and src.get("description"):
        d["description"] = src["description"]
    elif name.lower() in SPECIAL:
        d["description"] = SPECIAL[name.lower()]
    else:
        d["description"] = name  # fallback: at least name (no fabricated semantics)
    if src and src.get("values"):
        d["values"] = src["values"]
    if src and src.get("type"):
        d["type"] = src["type"]  # keep an already-declared STAC type verbatim
    return d

for url, (fkey, hkey, fsk, hsk, outname) in COLLS.items():
    doc = json.loads(urllib.request.urlopen(url, timeout=30).read())
    top = doc.pop("table:columns", [])
    topmap = {c["name"].lower(): c for c in top if c.get("name")}
    assets = doc["assets"]
    hexmap = {c["name"].lower(): c for c in assets[hkey].get("table:columns", []) if c.get("name")}

    assets[fkey]["table:columns"] = [coldef(n, t, topmap, hexmap) for n, t in SCHEMAS[fsk]]
    assets[hkey]["table:columns"] = [coldef(n, t, topmap, hexmap) for n, t in SCHEMAS[hsk]]

    # per-feature duplication note on the hex asset description
    areas = [n for n, _ in SCHEMAS[hsk] if n in AREA_HINT]
    note = (" Each hex row is one (feature, H3 cell) pair; the per-feature area columns ("
            + ", ".join(areas) + ") are repeated on every cell a feature covers — dedup by "
            "_cng_fid before summing (SELECT DISTINCT _cng_fid, <col>). For area from the H3 "
            "footprint see the h3-guide.")
    base = assets[hkey].get("description", "") or ""
    if "repeated on every cell" not in base:
        base = base + note
    if hsk in COVERAGE and "smaller than one" not in base:
        nmiss, total = COVERAGE[hsk]
        base += (f" {nmiss:,} of the {total:,} features are smaller than one resolution-10 "
                 "cell (thin parcels/slivers, median well under one acre) and polyfill to "
                 "zero cells, so they are absent from the hex; query the flat GeoParquet for "
                 "complete feature coverage.")
    assets[hkey]["description"] = base

    open(os.path.join(OUT, outname), "w").write(json.dumps(doc, indent=2))
    print(f"{outname}: flat={len(assets[fkey]['table:columns'])} cols, "
          f"hex={len(assets[hkey]['table:columns'])} cols, top-level removed, area-cols={areas}")
