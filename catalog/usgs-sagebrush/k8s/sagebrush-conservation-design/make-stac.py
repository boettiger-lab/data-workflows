#!/usr/bin/env python3
"""Write the usgs-sagebrush-conservation-design STAC collection and the public-usgs-sagebrush
bucket-level collection (#770).

Measured inputs (see BUILD.md): the raw fingerprint and class histograms from the
stage-raw job, the WGS84 footprint read from the published COGs (gdalinfo over HTTP
range reads; header only), and the hex column types from the published parquet.

Usage:  make-stac.py --out /tmp/sagebrush-stac
Writes to the --out directory only -- this repo never contains STAC JSON
(AGENTS.md Hard Boundary 1). Publish with rclone copyto.
"""
import argparse, json, pathlib, subprocess

BUCKET = "public-usgs-sagebrush"
DS = "sagebrush-conservation-design"
CID = "usgs-sagebrush-conservation-design"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
LANDING = "https://www.sciencebase.gov/catalog/item/62d57e89d34e87fffb2dda62"
DOI = "https://doi.org/10.5066/P94Y5CDV"
OFR = "https://doi.org/10.3133/ofr20221081"
LICENSE_URL = "https://www.usa.gov/government-works"
ACCESSED = "2026-10-10"
# Data footprint (classes 1-3), measured from the published hex: min/max of resolution-10
# cell centres, padded by ~one cell. Matches the ScienceBase item bbox. The COG grids are
# larger (the full Albers rectangle, value 0 outside the biome).
BBOX = [-122.118, 34.29, -102.272, 49.003]

PERIODS = [
    # key, upstream layer, start, end, label
    ("1998-2001", "SEI_1998_2001_30_Current", "1998-01-01", "2001-12-31", "1998–2001"),
    ("2003-2006", "SEI_2003_2006_30_Current", "2003-01-01", "2006-12-31", "2003–2006"),
    ("2008-2011", "SEI_2008_2011_30_Current", "2008-01-01", "2011-12-31", "2008–2011"),
    ("2013-2016", "SEI_2013_2016_30_Current", "2013-01-01", "2016-12-31", "2013–2016"),
    ("2017-2020", "SEI_2017_2020_30_Current", "2017-01-01", "2020-12-31", "2017–2020"),
    ("2030-2060-rcp85", "SEI_2017_2020_30_ClimateOnly_RCP85_2030-2060_median",
     "2030-01-01", "2060-12-31", "2030–2060 projection (RCP8.5, climate only, median)"),
]

CLASSES = [
    {"value": 1, "name": "Core Sagebrush Area",
     "description": "Core Sagebrush Areas: the highest-integrity sagebrush ecosystems, with abundant big sagebrush and perennial grass and forb cover, little annual grass, few conifers and little human modification. The design's priority for protection.",
     "color_hint": "1A9850"},
    {"value": 2, "name": "Growth Opportunity Area",
     "description": "Growth Opportunity Areas: sagebrush ecosystems of intermediate integrity, often next to core areas, where restoration and threat reduction could grow core habitat.",
     "color_hint": "FDAE61"},
    {"value": 3, "name": "Other Rangeland Area",
     "description": "Other Rangeland Areas: rangeland within the sagebrush biome with lower ecological integrity for sagebrush.",
     "color_hint": "BDBDBD"},
]
CLASS_TEXT = ("Sagebrush ecological integrity class. Values: 1=Core Sagebrush Area, "
              "2=Growth Opportunity Area, 3=Other Rangeland Area.")

# Source pixel counts per class, measured over the full 55301 x 59852 EPSG:5070 source grid
# by the stage-raw job (code 0 = 2,168,872,732-747 px in every layer).
HIST = {
    "1998-2001": (247823495, 416483292, 476695933),
    "2003-2006": (275091904, 406901947, 459008854),
    "2008-2011": (253090075, 482635115, 405277515),
    "2013-2016": (193432960, 374442183, 573127562),
    "2017-2020": (154246183, 386944578, 599811959),
    "2030-2060-rcp85": (162057159, 322459606, 656485955),
}
RAW_ZIP = dict(path=f"s3://{BUCKET}/raw/Raster_Data.zip", size="898,795,900",
               md5="4174fee8ddf8a7d44d5203051b57b806",
               sha256="b7cbbccbd214892b68e7904c0cee0cd588a7f0b5bfb2a2d867ab90293f170a09")


def cog_info(key):
    url = f"/vsicurl/{BASE}/{DS}/{DS}-{key}-cog.tif"
    j = json.loads(subprocess.run(["gdalinfo", "-json", url], check=True,
                                  capture_output=True, text=True).stdout)
    cc = j["cornerCoordinates"]
    bbox = [cc["upperLeft"][0], cc["lowerLeft"][1], cc["lowerRight"][0], cc["upperLeft"][1]]
    b = j["bands"][0]
    return bbox, b["type"].lower(), b.get("noDataValue"), j["size"], j["geoTransform"][1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--hex-value-type", default="uint8",
                    help="sei_class parquet type, read from the published hex")
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)

    assets, bboxes = {}, []
    for key, layer, start, end, label in PERIODS:
        bbox, dtype, nodata, size, px = cog_info(key)
        bboxes.append(bbox)
        projection = key.endswith("rcp85")
        what = ("a projection of the 2017–2020 classes forward under future climate "
                "(RCP8.5, climate change only, median across climate models)"
                if projection else f"the {label} period")
        assets[f"{DS}-{key}-cog"] = {
            "href": f"{BASE}/{DS}/{DS}-{key}-cog.tif",
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "title": f"Sagebrush Conservation Design classes, {label} (COG)",
            "description": (
                f"Sagebrush ecological integrity class for {what}, at 30 m, reprojected from "
                f"NAD83 / CONUS Albers to WGS84 with nearest-neighbour resampling so class codes "
                f"are unchanged. Upstream layer {layer}. Pixel value 0 marks land outside the "
                f"analysis (non-sagebrush areas and the area beyond the biome) and is the "
                f"no-data value."),
            "roles": ["data"],
            "created": None,
            "raster:bands": [{
                "name": "sei_class", "data_type": dtype, "nodata": 0,
                "spatial_resolution": px, "unit": "class",
                "classification:classes": CLASSES,
            }],
        }
    bbox = BBOX

    period_vals = [p[0] for p in PERIODS]
    hex_cols = [
        {"name": "sei_class", "type": a.hex_value_type, "description": CLASS_TEXT,
         "values": [1, 2, 3]},
        {"name": "h10", "type": "uint64", "description": "H3 cell ID at resolution 10."},
        {"name": "h9", "type": "uint64", "description": "H3 cell ID at resolution 9."},
        {"name": "h8", "type": "uint64", "description": "H3 cell ID at resolution 8."},
        {"name": "h0", "type": "int64", "description": "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."},
        {"name": "period", "type": "string",
         "description": ("Time period of the classification, from the hive partition. Values: "
                         "1998-2001=years 1998 to 2001, 2003-2006=years 2003 to 2006, "
                         "2008-2011=years 2008 to 2011, 2013-2016=years 2013 to 2016, "
                         "2017-2020=years 2017 to 2020, 2030-2060-rcp85=projection for 2030 to 2060 "
                         "under RCP8.5 climate change alone (a scenario, not an observation)."),
         "values": period_vals},
    ]
    assets[f"{DS}-hex"] = {
        "href": f"{BASE}/{DS}/hex/period=*/h0=*/data_0.parquet",
        "type": "application/x-parquet",
        "title": "Sagebrush Conservation Design classes, H3 resolution 10, all periods",
        "description": (
            "The dominant sagebrush ecological integrity class in each H3 resolution 10 cell, "
            "for all six periods in one table, with parent cells at resolutions 9, 8 and 0. "
            "One row per (period, cell). Each cell takes the most common class among the 30 m "
            "pixels it covers that lie inside the analysis; pixels outside it (value 0 in the "
            "source) are ignored, and cells with none are absent. Because only the dominant "
            "class is kept, and a cell on the edge of the analysis area takes its class from "
            "the few in-analysis pixels it holds, adding up cell areas by class approximates "
            "class area rather than measuring it: it runs high for Other Rangeland Areas, which "
            "dominate that edge, and low for Core Sagebrush Areas. For exact class areas use "
            "the pixel counts in the collection description. Pick one period, or compare "
            "periods by joining on the cell:\n"
            "```sql\n"
            "-- cells that were Core Sagebrush Area in 1998-2001 but not in 2017-2020\n"
            "SELECT a.h10, a.h0, b.sei_class AS class_2017_2020 FROM read_parquet('<this asset>') a\n"
            "JOIN read_parquet('<this asset>') b USING (h10, h0)\n"
            "WHERE a.period = '1998-2001' AND b.period = '2017-2020'\n"
            "  AND a.sei_class = 1 AND b.sei_class <> 1;\n"
            "```\n"
            "The 2030-2060-rcp85 period is a projection; keep it out of comparisons between "
            "observed periods unless that is the intent."),
        "roles": ["data"],
        "h3:native_resolution": 10,
        "h3:parent_resolutions": [9, 8, 0],
        "table:columns": hex_cols,
    }

    hist_lines = "; ".join(
        f"{k}: {c[0]:,} / {c[1]:,} / {c[2]:,}" for k, c in HIST.items())
    desc = (
        "The USGS Sagebrush Conservation Design classifies the entire sagebrush biome of the "
        "western United States by sagebrush ecological integrity, at 30 m: Core Sagebrush "
        "Areas (highest integrity, the priority for protection), Growth Opportunity Areas "
        "(intermediate integrity, the best places to grow core habitat through restoration) "
        "and Other Rangeland Areas. Integrity is modelled from satellite-derived cover of big "
        "sagebrush, perennial and annual grasses and forbs, and conifers, together with human "
        "modification, with relationships tuned regionally by experts across the biome "
        "(Doherty et al. 2022).\n\n"
        "Coverage is the full sagebrush biome as published, across the western United States, "
        "not clipped to any one state. Five observed periods are included (1998–2001, "
        "2003–2006, 2008–2011, 2013–2016, 2017–2020), plus one projection of the 2017–2020 "
        "classes to 2030–2060 under RCP8.5 climate change alone (median across models), which "
        "is a scenario rather than an observation.\n\n"
        "Assets: one cloud-optimized GeoTIFF per period, and one H3 table holding every period "
        "with a `period` column. In the GeoTIFFs, 0 marks land outside the analysis and is the "
        "no-data value; the H3 table contains classes 1–3 only.\n\n"
        f"Source: USGS ScienceBase item 62d57e89d34e87fffb2dda62 ({DOI}), published 2022-08-26, "
        f"metadata revised 2024-11-25; upstream publishes no edition label. Accessed {ACCESSED}. "
        f"Staged raw: {RAW_ZIP['path']}, {RAW_ZIP['size']} bytes, MD5 {RAW_ZIP['md5']} "
        f"(matches ScienceBase), SHA256 {RAW_ZIP['sha256']}. Source pixel counts of classes "
        f"1 / 2 / 3 per period over the full 55,301 × 59,852 source grid: {hist_lines}.\n\n"
        "U.S. Government work in the public domain. Please cite: Doherty, K., Theobald, D.M., "
        "Holdrege, M.C., Wiechman, L.A., and Bradford, J.B., 2022, Biome-wide sagebrush core "
        f"habitat and growth areas estimated from a threat-based conservation design: U.S. "
        f"Geological Survey data release, {DOI}.")

    coll = {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/classification/v2.0.0/schema.json",
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
        ],
        "id": CID,
        "title": "USGS Sagebrush Conservation Design: core and growth areas across the sagebrush biome, 1998–2020 and a 2030–2060 projection",
        "description": desc,
        "license": "public-domain",
        "keywords": ["sagebrush", "sagebrush ecological integrity", "Core Sagebrush Areas",
                     "Growth Opportunity Areas", "rangeland", "conservation design", "USGS",
                     "sage-grouse habitat", "western United States", "H3", "time series"],
        "sci:doi": "10.5066/P94Y5CDV",
        "sci:citation": (
            "Doherty, K., Theobald, D.M., Holdrege, M.C., Wiechman, L.A., and Bradford, J.B., "
            "2022, Biome-wide sagebrush core habitat and growth areas estimated from a "
            "threat-based conservation design: U.S. Geological Survey data release, "
            f"{DOI}. Accessed {ACCESSED}."),
        "sci:publications": [{"doi": "10.3133/ofr20221081", "citation": (
            "Doherty, K., Theobald, D.M., Bradford, J.B., Wiechman, L.A., et al., 2022, A "
            "sagebrush conservation design to proactively restore America's sagebrush biome: "
            "U.S. Geological Survey Open-File Report 2022–1081, 38 p.")}],
        "providers": [
            {"name": "U.S. Geological Survey", "roles": ["producer", "licensor"], "url": LANDING},
            {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"],
             "url": "https://github.com/boettiger-lab/data-workflows"},
        ],
        "extent": {
            "spatial": {"bbox": [bbox]},
            "temporal": {"interval": [["1998-01-01T00:00:00Z", "2060-12-31T23:59:59Z"]]},
        },
        "links": [
            {"rel": "self", "href": f"{BASE}/{DS}/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "about", "href": LANDING, "type": "text/html", "title": "USGS ScienceBase data release"},
            {"rel": "cite-as", "href": DOI, "title": "Data release DOI"},
            {"rel": "describedby", "href": OFR, "title": "USGS Open-File Report 2022-1081"},
            {"rel": "license", "href": LICENSE_URL, "type": "text/html", "title": "U.S. Government Works"},
        ],
        "assets": assets,
    }
    # per-asset created: measured from the objects at publish time
    for k, v in assets.items():
        v.pop("created", None)
    (out / "stac-collection.json").write_text(json.dumps(coll, indent=2, ensure_ascii=False) + "\n")

    parent = {
        "type": "Collection",
        "stac_version": "1.0.0",
        "id": "usgs-sagebrush",
        "title": "USGS sagebrush biome data",
        "description": ("Sagebrush biome datasets published by the U.S. Geological Survey, "
                        "starting with the Sagebrush Conservation Design (core sagebrush areas "
                        "and growth opportunity areas across the biome)."),
        "license": "public-domain",
        "extent": coll["extent"],
        "providers": coll["providers"],
        "links": [
            {"rel": "self", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": ROOT, "type": "application/json"},
            {"rel": "child", "href": f"{BASE}/{DS}/stac-collection.json", "type": "application/json",
             "title": coll["title"]},
            {"rel": "license", "href": LICENSE_URL, "type": "text/html", "title": "U.S. Government Works"},
        ],
    }
    (out / "parent-stac-collection.json").write_text(json.dumps(parent, indent=2, ensure_ascii=False) + "\n")
    print("bbox", bbox)


if __name__ == "__main__":
    main()
