#!/usr/bin/env python3
"""Generate the public-utah monument-boundary STAC collections (issue #450).

One leaf collection per monument (`benm-boundaries`, `gsenm-boundaries`), each with one
PMTiles asset per era (the app's GLEN `versions` dropdown swaps whole PMTiles assets) plus
one combined GeoParquet + one combined H3 hex (all eras, `era` column) for SQL / zonal work.
Also emits the `public-utah` bucket meta-collection that links both monuments.

Writes to /tmp; upload with rclone (STAC never lives in this repo). License = public-domain
(US federal proclamations + Utah SGID). Verified by scripts/verify-stac.py.
"""
import json

BASE = "https://s3-west.nrp-nautilus.io/public-utah"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
BUCKET_SELF = f"{BASE}/stac-collection.json"

# ---- shared column authority (identical text on flat + hex, per mcp-data-server#303) ----
def cols_common(era_values):
    return {
        "_cng_fid": {"name": "_cng_fid", "type": "int64",
            "description": "Synthetic per-feature id (one per source boundary feature, row-unique). "
                           "Dedup / COUNT(DISTINCT) key across the (feature, H3 cell) rows on the hex."},
        "name": {"name": "name", "type": "string",
            "description": "Monument display name (tooltip title)."},
        "monument": {"name": "monument", "type": "string",
            "description": "Monument key the app filters on.",
            "values": None},  # filled per-collection
        "unit": {"name": "unit", "type": "string",
            "description": "Named sub-unit where an era's boundary is split into units "
                           "(e.g. Grand Staircase-Escalante's 2026 units); the monument name for "
                           "whole-monument eras; null for an unnamed unit."},
        "era": {"name": "era", "type": "string",
            "description": "Redesignation era this boundary represents (the GLEN `versions` label).",
            "values": era_values},
        "status": {"name": "status", "type": "string",
            "description": "Designation-change type: original (as first proclaimed), reduced "
                           "(shrunk by proclamation), restored (re-expanded by proclamation).",
            "values": ["original", "reduced", "restored"]},
        "acres": {"name": "acres", "type": "number",
            "description": "Official published proclamation / legal acreage for this era (the headline "
                           "figure the timeline is about). Differs a few % from the GIS-measured "
                           "`gis_acres` (boundary digitization; the PAD-US-sourced 2021 restored "
                           "boundaries measure larger than the proclamation figure). For Grand "
                           "Staircase-Escalante's 2026 units this is the per-unit acreage."},
        "gis_acres": {"name": "gis_acres", "type": "number",
            "description": "Geodesic area in acres computed from the boundary polygon "
                           "(EPSG:5070 equal-area). Transparency companion to the published `acres`."},
    }

GEOM_COL = {"name": "geom", "type": "geometry",
            "description": "Feature geometry (GeoParquet, EPSG:4326 / OGC:CRS84)."}
H8_COL = {"name": "h8", "type": "uint64",
          "description": "H3 cell ID at resolution 8 (native resolution; one row per (feature, h8) pair)."}
H0_COL = {"name": "h0", "type": "int64",
          "description": "H3 cell ID at resolution 0; hive partition key."}

# per-monument config
MONUMENTS = [
    dict(seg="bears-ears", pfx="benm", cid="benm-boundaries", layer="benm",
         disp="Bears Ears National Monument", mon="Bears Ears", color="#8B4513",
         eras=[("2016", "2016 original"), ("2017", "2017 reduced"),
               ("2021", "2021 restored"), ("2026", "2026 reduced")],
         default_version="2026 reduced",
         bbox=[-110.529, 37.154, -109.449, 38.469],
         temporal=["2016-12-28T00:00:00Z", "2026-12-31T00:00:00Z"]),
    dict(seg="grand-staircase-escalante", pfx="gsenm", cid="gsenm-boundaries", layer="gsenm",
         disp="Grand Staircase-Escalante National Monument", mon="Grand Staircase-Escalante",
         color="#00695C",
         eras=[("1996", "1996 original"), ("2017", "2017 reduced"),
               ("2021", "2021 restored"), ("2026", "2026 reduced")],
         default_version="2026 reduced",
         bbox=[-112.468, 37.001, -110.973, 38.017],
         temporal=["1996-09-18T00:00:00Z", "2026-12-31T00:00:00Z"]),
]


def build_collection(m):
    seg, pfx, layer = m["seg"], m["pfx"], m["layer"]
    era_values = [label for _tok, label in m["eras"]]
    cc = cols_common(era_values)
    cc["monument"]["values"] = [m["mon"]]

    # flat GeoParquet columns (full authority + geometry)
    flat_cols = [cc["_cng_fid"], cc["name"], cc["monument"], cc["unit"],
                 cc["era"], cc["status"], cc["acres"], cc["gis_acres"], GEOM_COL]
    # hex columns (full authority minus geometry + H3 index columns)
    hex_cols = [cc["_cng_fid"], cc["name"], cc["monument"], cc["unit"],
                cc["era"], cc["status"], cc["acres"], cc["gis_acres"], H8_COL, H0_COL]
    # PMTiles columns (lean: name+type only; each PMTiles holds one era's rows)
    pm_cols = [{"name": c["name"], "type": c["type"]}
               for c in (cc["_cng_fid"], cc["name"], cc["monument"], cc["unit"],
                         cc["era"], cc["status"], cc["acres"], cc["gis_acres"])]

    assets = {}
    # one PMTiles per era
    for tok, label in m["eras"]:
        assets[f"{pfx}-{tok}"] = {
            "href": f"{BASE}/{seg}/{pfx}-{tok}.pmtiles",
            "type": "application/vnd.pmtiles",
            "title": f"{m['disp']} — {label} (PMTiles)",
            "roles": ["visual"],
            "vector:layers": [layer],
            "table:columns": pm_cols,
        }
    # combined GeoParquet
    assets[f"{pfx}-parquet"] = {
        "href": f"{BASE}/{seg}/{pfx}.parquet",
        "type": "application/x-parquet",
        "title": f"{m['disp']} — all eras (GeoParquet)",
        "roles": ["data"],
        "table:columns": flat_cols,
    }
    # combined H3 hex
    assets[f"{pfx}-hex"] = {
        "href": f"{BASE}/{seg}/{pfx}/hex/h0=*/data_0.parquet",
        "type": "application/x-parquet",
        "title": f"{m['disp']} — all eras (H3 hex, res 8)",
        "roles": ["data"],
        "h3:native_resolution": 8,
        "h3:parent_resolutions": [0],
        "description": (
            "H3 hex (native resolution 8, parent 0) of the per-era boundaries. One row = one "
            "(feature, H3 cell) pair, so `acres` and `gis_acres` are per-feature totals repeated "
            "on every cell a feature covers — never SUM them on the hex; dedup by `_cng_fid` "
            "(or _cng_fid, era) first, e.g. SELECT DISTINCT _cng_fid, era, acres. For per-cell "
            "ground area use the H3 cell footprint (see the h3-guide)."),
        "table:columns": hex_cols,
    }

    return {
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/table/v1.2.0/schema.json"],
        "type": "Collection",
        "id": m["cid"],
        "title": f"{m['disp']} — boundaries by era (2016–2026)",
        "description": (
            f"{m['disp']} boundary as it changed across each presidential redesignation, one "
            f"asset per era for the Utah Public Lands app's era dropdown (GLEN `versions`). Eras: "
            + ", ".join(era_values) + ". Each era has its own PMTiles layer (source-layer "
            f"`{layer}`); a combined GeoParquet and H3 hex (res 8) carry all eras with an `era` "
            "column for SQL and zonal comparison. `acres` is the official published proclamation "
            "acreage; `gis_acres` is the geodesic area measured from the boundary polygon. Sources: "
            "Utah SGID BLM Monuments & NCAs Historic (originals), PAD-US 2.1 (2017 reduction), "
            "PAD-US 4.1 (2021 restoration), and the 2026 proposed-reduction boundaries. "
            "US federal / Utah SGID public domain."),
        "license": "public-domain",
        "keywords": ["national monument", "Bears Ears", "Grand Staircase-Escalante", "Utah",
                     "public lands", "boundaries", "BLM", "PAD-US", "time series"],
        "extent": {
            "spatial": {"bbox": [m["bbox"]]},
            "temporal": {"interval": [m["temporal"]]}},
        "providers": [
            {"name": "US BLM / Utah SGID / USGS PAD-US", "roles": ["producer", "licensor"],
             "url": "https://gis.utah.gov/data/boundaries/"},
            {"name": "Boettiger Lab (cng-datasets processing)", "roles": ["processor"],
             "url": f"{BASE}/"}],
        "links": [
            {"rel": "self", "href": f"{BASE}/{seg}/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": BUCKET_SELF, "type": "application/json"},
            {"rel": "license",
             "href": "https://www.usa.gov/government-works", "type": "text/html"}],
        # app-wiring hints (non-STAC-core, harmless extras the app reads)
        "boundaries:default_version": m["default_version"],
        "boundaries:color": m["color"],
        "assets": assets,
    }


def build_bucket():
    children = [
        {"rel": "child", "href": f"{BASE}/{m['seg']}/stac-collection.json",
         "type": "application/json", "title": m["disp"]}
        for m in MONUMENTS]
    return {
        "stac_version": "1.0.0",
        "type": "Collection",
        "id": "public-utah",
        "title": "Utah Public Lands",
        "description": ("Utah-focused geospatial datasets for the Utah Public Lands app. "
                        "Currently: per-era Bears Ears and Grand Staircase-Escalante National "
                        "Monument boundaries (2016–2026)."),
        "license": "public-domain",
        "keywords": ["Utah", "public lands", "national monuments"],
        "extent": {
            "spatial": {"bbox": [[-114.05, 36.99, -109.04, 42.00]]},
            "temporal": {"interval": [["1996-09-18T00:00:00Z", "2026-12-31T00:00:00Z"]]}},
        "links": [
            {"rel": "self", "href": BUCKET_SELF, "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": ROOT, "type": "application/json"},
            *children],
        "assets": {},
    }


if __name__ == "__main__":
    for m in MONUMENTS:
        doc = build_collection(m)
        path = f"/tmp/{m['seg']}-stac-collection.json"
        json.dump(doc, open(path, "w"), indent=2)
        print(f"wrote {path}  ({len(doc['assets'])} assets)")
    bucket = build_bucket()
    json.dump(bucket, open("/tmp/public-utah-stac-collection.json", "w"), indent=2)
    print("wrote /tmp/public-utah-stac-collection.json  (bucket meta-collection)")
