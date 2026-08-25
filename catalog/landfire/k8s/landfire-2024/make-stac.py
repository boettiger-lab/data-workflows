#!/usr/bin/env python3
"""Generate the four landfire-2024-* STAC collections plus the public-landfire
bucket-level collection.

Class legends come from the CSV that LANDFIRE ships inside each product zip
(the authoritative code -> name/description/RGB map). The `values` arrays come
from the exact value histogram measured over each source raster by the
landfire-2024-stage-raw job -- the ingest, not the documentation (#294).

Inputs, both staged by that job:
    rclone copy nrp:public-landfire/raw/landfire-2024/ <legends-dir>/
    ... plus the per-layer histogram CSVs written from the stage-raw logs

Usage:
    make-stac.py --legends <dir> --hist <dir> --out /tmp/landfire-stac

Writes to /tmp only -- this repo never contains STAC JSON (AGENTS.md Hard Boundary 1).
"""
import argparse, csv, json, pathlib, sys

BUCKET = "public-landfire"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
LANDING = "https://landfire.gov/data/FullExtentDownloads"
EDITION = "LF 2024 (2.5.0)"
ACCESSED = "2026-08-25"
# WGS84 footprint of the warped COGs, measured from the gdalwarp output grid.
BBOX = [-128.0021, 22.6293, -64.6605, 52.4816]
TEMPORAL = ["2024-01-01T00:00:00Z", "2024-12-31T23:59:59Z"]

# Fill codes measured per layer (see BUILD.md). -9999 is the COG's declared
# NoData; the rest remain real pixel values in the COG and are excluded at the
# hex step, which accepts a comma list.
FILL = {
    "vcc":    [-9999, -1111, 32767],
    "evt":    [-9999, 32767],
    "evc":    [-9999, 32767],
    "fbfm40": [-9999, 32767],
}
PRIMARY_NODATA = -9999

LAYERS = {
    "vcc": dict(
        prod="VCC", csv="LF2024_VCC.csv", name_col="CLASS", desc_col="DESCRIPTION",
        title="LANDFIRE 2024 Vegetation Condition Class (CONUS, 30 m)",
        short="Vegetation Condition Class",
        blurb=(
            "Vegetation Condition Class measures how far current vegetation has departed from its "
            "estimated historical reference condition, on a six-step ordinal scale from Class I.A "
            "(0-16% departure) to Class III.B (84-100% departure). It is the LANDFIRE product that "
            "speaks to claims about stands being overgrown or out of their natural condition. "
            "Five additional codes mark land that is not rated for departure at all: 111 water, "
            "112 snow and ice, 120 developed, 132 barren or sparsely vegetated, and 180 "
            "agriculture. Exclude those from the denominator of any 'share of land that is "
            "departed' statistic."),
    ),
    "evt": dict(
        prod="EVT", csv="LF2024_EVT.csv", name_col="EVT_NAME", desc_col=None,
        title="LANDFIRE 2024 Existing Vegetation Type (CONUS, 30 m)",
        short="Existing Vegetation Type",
        blurb=(
            "Existing Vegetation Type names the plant community currently occupying each 30 metre "
            "pixel, drawn from a national vocabulary of roughly 1,070 ecological system and land "
            "use types. The shipped legend also carries lifeform and physiognomy groupings "
            "(EVT_LF, EVT_PHYS) that let many types be rolled up to tree, shrub, herb or "
            "non-vegetated before analysis."),
    ),
    "evc": dict(
        prod="EVC", csv="LF2024_EVC.csv", name_col="CLASSNAMES", desc_col=None,
        title="LANDFIRE 2024 Existing Vegetation Cover (CONUS, 30 m)",
        short="Existing Vegetation Cover",
        blurb=(
            "Existing Vegetation Cover records canopy cover as a combined lifeform and percentage "
            "code, not as a plain percentage. Codes 110 to 199 are tree cover, where the percentage "
            "is the value minus 100; codes 210 to 299 are shrub cover, value minus 200; codes 310 "
            "to 399 are herb cover, value minus 300. Code 100 is sparse vegetation and carries no "
            "percentage, and codes 11 to 32 and 61 to 82 are water, snow and ice, developed land, "
            "barren land, quarries and agriculture. Because a code combines lifeform with "
            "percentage, the codes are categories and cannot be averaged: decode the lifeform and "
            "the percentage into separate values first.\n\n"
            "```sql\n"
            "-- correct: decode, then average within one lifeform\n"
            "SELECT AVG(evc - 100) FROM ... WHERE evc BETWEEN 110 AND 199   -- mean tree cover %\n"
            "-- wrong: AVG(evc) mixes lifeforms; the mean of a 15% tree code and a 15% shrub\n"
            "-- code is 165, which decodes as tree cover 65%\n"
            "```"),
    ),
    "fbfm40": dict(
        prod="FBFM40", csv="LF2024_FBFM40.csv", name_col="FBFM40", desc_col=None,
        title="LANDFIRE 2024 Fire Behavior Fuel Model 40 (CONUS, 30 m)",
        short="40 Scott and Burgan Fire Behavior Fuel Models",
        blurb=(
            "Fire Behavior Fuel Model 40 assigns each pixel one of the 40 Scott and Burgan surface "
            "fuel models used by fire behaviour models such as FARSITE and FlamMap. Codes 91, 92, "
            "93, 98 and 99 are the non-burnable models NB1, NB2, NB3, NB8 and NB9 -- urban, snow "
            "and ice, agriculture, open water and bare ground. Exclude them from any statistic "
            "about fuel conditions on burnable land."),
    ),
}

HEX_COLS = [
    ("h10", "uint64", "H3 cell ID at resolution 10 (native resolution)."),
    ("h9",  "uint64", "H3 cell ID at resolution 9 (parent)."),
    ("h8",  "uint64", "H3 cell ID at resolution 8 (parent; catalog universal join key)."),
    ("h0",  "int64",  "H3 cell ID at resolution 0 (hive partition key)."),
]


def read_legend(path, name_col, desc_col):
    """code -> (name, description, color_hint) from the shipped LANDFIRE CSV."""
    out = {}
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.DictReader(fh):
            try:
                v = int(row["VALUE"])
            except (KeyError, TypeError, ValueError):
                continue
            name = (row.get(name_col) or "").strip()
            desc = (row.get(desc_col) or "").strip() if desc_col else ""
            try:
                color = "%02X%02X%02X" % (int(row["R"]), int(row["G"]), int(row["B"]))
            except (KeyError, TypeError, ValueError):
                color = "808080"
            out[v] = (name or f"Class {v}", desc or name or f"Class {v}", color)
    return out


def read_hist(path):
    """Value -> pixel count, from the measured full-raster histogram."""
    out = {}
    with open(path, newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 2 or not row[0].lstrip("-").isdigit():
                continue
            out[int(row[0])] = int(row[1])
    return out


def build(layer, cfg, legends_dir, hist_dir):
    prod = cfg["prod"]
    legend = read_legend(pathlib.Path(legends_dir) / prod / cfg["csv"],
                         cfg["name_col"], cfg["desc_col"])
    hist = read_hist(pathlib.Path(hist_dir) / f"hist-{prod}.csv")
    fill = set(FILL[layer])
    present = sorted(v for v in hist if v not in fill)
    missing_from_legend = [v for v in present if v not in legend]
    if missing_from_legend:
        sys.exit(f"{layer}: {len(missing_from_legend)} ingested codes absent from the shipped "
                 f"legend: {missing_from_legend[:20]} -- resolve before publishing")

    ds = f"landfire-2024-{layer}"
    # classification:classes covers everything a consumer can meet in the COG:
    # the real classes plus every fill code that survives as a pixel value. 32767
    # is NOT in the shipped CSV, so it is declared explicitly here.
    classes = []
    for v in sorted(set(present) | fill):
        if v in legend:
            n, d, c = legend[v]
        elif v == 32767:
            n, d, c = ("Fill - NoData (band sentinel)",
                       "Unmapped fill carried in the source raster and declared as the source "
                       "band NoData value. Excluded from the H3 hex.", "FFFFFF")
        else:
            n, d, c = (f"Class {v}", f"Class {v}", "808080")
        classes.append({"value": v, "name": n, "color_hint": c, "description": d})

    fill_note = (
        f"Fill codes {', '.join(str(f) for f in sorted(fill))} are excluded from the H3 hex "
        f"assets; {PRIMARY_NODATA} is the declared NoData of this COG and the others remain "
        f"pixel values here.")

    value_desc = (
        f"LANDFIRE 2024 {cfg['short']} class code. Definitions, names and the published colour "
        f"for every code are in the classification classes on the COG asset of this collection. "
        f"Fill codes are excluded from these hex assets.")

    def cols(with_frac):
        c = [{"name": layer, "type": "int16", "description": value_desc, "values": present}]
        if with_frac:
            c.append({"name": "frac", "type": "double", "description":
                      "Areal fraction (0 to 1) of the H3 cell covered by this class. One row per "
                      "(cell, class); the fractions within a cell sum to 1 or less, the shortfall "
                      "being the part of the cell with no valid source pixel."})
        return c + [{"name": n, "type": t, "description": d} for n, t, d in HEX_COLS]

    hex_desc = (
        f"Dominant-class (mode reducer) H3 hex of LANDFIRE 2024 {cfg['short']} at resolution 10, "
        f"one row per cell, hive-partitioned by h0. Each cell takes the class covering the largest "
        f"share of it, so the mix within a cell is not preserved; for the area held by each class "
        f"use the fractional-coverage asset instead. Cells with no valid source pixel are not "
        f"written, so partitions are sparse. {fill_note}")

    frac_desc = (
        f"Per-class fractional-coverage H3 hex of LANDFIRE 2024 {cfg['short']} at resolution 10, "
        f"hive-partitioned by h0. Long format: one row per (cell, class), with frac giving that "
        f"class's share of the cell. This is the asset to use for area accounting: filter to a "
        f"class, then weight frac by the ground area of each cell (see the catalog h3-guide for "
        f"the area method; do not use a nominal per-resolution constant). {fill_note}")

    coll = {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/classification/v2.0.0/schema.json",
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
            "https://stac-extensions.github.io/version/v1.2.0/schema.json",
        ],
        "id": ds,
        "title": cfg["title"],
        "version": EDITION,
        "description": (
            f"{cfg['blurb']}\n\n"
            f"This is the LANDFIRE 2024 Update, version 2.5.0, covering the conterminous United "
            f"States at 30 metre resolution on a NAD83 Albers grid, reprojected here to WGS84. "
            f"LANDFIRE 2024 is the most recent release that carries Vegetation Condition Class; "
            f"the 2025 release (version 2.6.0) does not. Wildfire Hazard Potential 2023, published "
            f"separately in this catalog, is built from LANDFIRE 2020 version 2.2.0 fuels, three "
            f"updates older than this data -- the two are not the same vintage and should not be "
            f"combined as though they were.\n\n"
            f"Source archive s3://{BUCKET}/raw/LF2024_{prod}_CONUS.zip, retrieved from "
            f"landfire.gov on {ACCESSED}; the size and SHA-256 of that staged copy are recorded in "
            f"the build notes. Fill codes were measured from the full source raster rather than "
            f"read from its metadata, because the shipped metadata understates them: every layer "
            f"carries {', '.join(str(f) for f in sorted(fill))} as fill.\n\n"
            f"Available as a cloud-optimized GeoTIFF and as two H3 hex tables at resolution 10: a "
            f"dominant-class table and a per-class fractional-coverage table. Use the fractional "
            f"table for any question about how much area a class holds."),
        "license": "public-domain",
        "keywords": ["LANDFIRE", "fire", "fuels", "vegetation", "wildfire", "CONUS",
                     cfg["short"]],
        "extent": {"spatial": {"bbox": [BBOX]},
                   "temporal": {"interval": [TEMPORAL]}},
        "sci:citation": (
            f"LANDFIRE, 2026, {cfg['short']} Layer, LANDFIRE 2024 (2.5.0), U.S. Department of the "
            f"Interior, Geological Survey, and U.S. Department of Agriculture, Forest Service. "
            f"Accessed {ACCESSED} at {LANDING}."),
        "providers": [
            {"name": "LANDFIRE (USGS EROS and USDA Forest Service)",
             "roles": ["producer", "licensor"], "url": "https://landfire.gov"},
            {"name": "Boettiger Lab (cng-datasets H3 processing)",
             "roles": ["processor"], "url": f"{BASE}/{ds}/"},
        ],
        "links": [
            {"rel": "self", "href": f"{BASE}/{ds}/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "about", "href": LANDING, "type": "text/html",
             "title": "LANDFIRE full-extent downloads (product landing page)"},
            {"rel": "license", "href": "https://landfire.gov/data/citation", "type": "text/html",
             "title": "LANDFIRE data citation and use"},
        ],
        "assets": {
            f"{layer}-cog": {
                "href": f"{BASE}/{ds}/{ds}-cog.tif",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "title": f"{cfg['title']} (WGS84 COG)",
                "roles": ["data"],
                "raster:bands": [{
                    "name": layer, "data_type": "int16", "nodata": PRIMARY_NODATA,
                    "classification:classes": classes,
                }],
            },
            f"{layer}-hex": {
                "href": f"{BASE}/{ds}/hex/h0=*/data_0.parquet",
                "type": "application/x-parquet",
                "title": f"{cfg['short']} 2024, H3 resolution 10, dominant class",
                "roles": ["data"],
                "h3:native_resolution": 10,
                "h3:parent_resolutions": [9, 8, 0],
                "description": hex_desc,
                "table:columns": cols(False),
            },
            f"{layer}-hex-fractions": {
                "href": f"{BASE}/{ds}/hex-fractions/h0=*/data_0.parquet",
                "type": "application/x-parquet",
                "title": f"{cfg['short']} 2024, H3 resolution 10, per-class fractional coverage",
                "roles": ["data"],
                "h3:native_resolution": 10,
                "h3:parent_resolutions": [9, 8, 0],
                "description": frac_desc,
                "table:columns": cols(True),
            },
        },
    }
    return coll, len(present), len(classes)


def bucket_collection():
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "id": "landfire",
        "title": "LANDFIRE",
        "description": (
            "LANDFIRE is a shared program of the US Geological Survey and the USDA Forest Service "
            "that maps vegetation, fuel and fire regime conditions across the United States at 30 "
            "metre resolution. This catalog holds the LANDFIRE 2024 Update (version 2.5.0) for the "
            "conterminous United States: vegetation condition class, existing vegetation type, "
            "existing vegetation cover and the 40 Scott and Burgan fire behaviour fuel models. "
            "Each product is published as a cloud-optimized GeoTIFF and as H3 hex tables at "
            "resolution 10, in both dominant-class and per-class fractional-coverage form."),
        "license": "public-domain",
        "extent": {"spatial": {"bbox": [BBOX]},
                   "temporal": {"interval": [TEMPORAL]}},
        "links": [
            {"rel": "self", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": ROOT, "type": "application/json"},
        ] + [
            {"rel": "child", "id": f"landfire-2024-{k}",
             "href": f"{BASE}/landfire-2024-{k}/stac-collection.json",
             "type": "application/json", "title": v["title"]}
            for k, v in LAYERS.items()
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--legends", required=True)
    ap.add_argument("--hist", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for layer, cfg in LAYERS.items():
        coll, n_vals, n_cls = build(layer, cfg, a.legends, a.hist)
        p = out / f"landfire-2024-{layer}.json"
        p.write_text(json.dumps(coll, indent=2))
        print(f"{p}  values={n_vals}  classes={n_cls}  {p.stat().st_size/1024:.0f} KiB")
    p = out / "landfire-bucket.json"
    p.write_text(json.dumps(bucket_collection(), indent=2))
    print(f"{p}")


if __name__ == "__main__":
    main()
