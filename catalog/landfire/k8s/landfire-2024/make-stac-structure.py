#!/usr/bin/env python3
"""STAC for the seven LANDFIRE 2024 structure/fuels collections (data-workflows #515).

Two shapes in one tranche, and they need opposite treatment:

  CONTINUOUS (cbd, cbh, cc, ch) -- linearly scaled physical quantities. The pixel is NOT
  the value: the shipped CSV gives the decode (KGM3 = VALUE/100, METERS = VALUE/10,
  CC_PERCENT = VALUE). Reducer is `mean`, and `0 = Non-Forested` is a CATEGORY among the
  measurements, excluded at hex along with the fill codes -- so these cover forest only.
  No classification:classes: a continuous surface has no class list, and anything listed
  there gets painted.

  CATEGORICAL (fbfm13, fvc, fvh) -- class codes. Reducer is `mode`. classification:classes
  comes from the shipped legend with fill codes REMOVED (#628: that list becomes a render
  colormap, so a fill code in it paints over real ground).

Every range, mean and `values` array here is MEASURED from the published hex, never taken
from upstream documentation (#518). Class legends come from the CSV shipped in each product
zip, staged beside the raw.

Writes to /tmp only -- this repo never contains STAC JSON (AGENTS.md Hard Boundary 1).
"""
import argparse, csv, io, json, pathlib, urllib.request

BUCKET = "public-landfire"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
LANDING = "https://landfire.gov/data/FullExtentDownloads"
EDITION = "LF 2024 (2.5.0)"
ACCESSED = "2026-09-07"
BBOX = [-128.3873, 22.4283, -64.0541, 52.4816]
TEMPORAL = ["2024-01-01T00:00:00Z", "2024-12-31T23:59:59Z"]
FILL = [-9999, 32767]

# measured from the published hex (see #515) -- cells, min, max, mean of the RAW pixel value
MEASURED = {
    "cbd":    dict(cells=267118010, lo=1,  hi=45,          mean=7.1656),
    "cbh":    dict(cells=267118010, lo=2,  hi=100,         mean=47.7073),
    "cc":     dict(cells=267118010, lo=15, hi=95,          mean=53.7778),
    "ch":     dict(cells=267118010, lo=30, hi=509.3253167, mean=165.3252),
    "fbfm13": dict(cells=566661014, lo=2,  hi=99,          mean=None),
    "fvc":    dict(cells=566661014, lo=11, hi=129,         mean=None),
    "fvh":    dict(cells=566661014, lo=11, hi=651,         mean=None),
    "fvt":    dict(cells=566661014, lo=11, hi=2969,        mean=None),
}

RAW = {  # staged pristine upstream zip: bytes + sha256 recomputed from the object
    "cbd":    (1932453529, "bbfcc165a5932ec159138f2b932f7557091a63b4dc1822cdfceaadb4aff89a2d"),
    "cbh":    (2388285120, "7641958cb179f4345485ad3ef95961d19bd1c05947a5e363f8e4e31dfb737019"),
    "cc":     (1986573231, "694b88a888f340d5924d8730f42b071ff3bcc23810a21d58f3b6c16be704bf12"),
    "ch":     (1909386732, "d1b050a124ad07959a64eae04ae2e42259e69a466a14fa3f410100c9c00f27b8"),
    "fbfm13": (2552370712, "cc02ff3f5e87c3cff312f24e2c691ea1e07572e994a387372e446b2712c099ef"),
    "fvc":    (4146626612, "e75bccdbc26d6d46ab5088e662ff10ee3371892f0beb22b7a37fb67355a07c0f"),
    "fvh":    (3535211143, "e77136958c99d4da8729565bc928a55203d2add2f109057f8903d201fbb2207d"),
    "fvt":    (3719631490, "11413880c3642d951756f5bcaaabf19362838611f051db8a27884c27563b6fa5"),
}

COG_CREATED = {  # object mtime on S3 -- which conversion produced which asset (#549)
    "cbd": "2026-09-07T18:43:20Z", "cbh": "2026-09-07T18:43:32Z",
    "cc":  "2026-09-07T18:52:12Z", "ch":  "2026-09-07T18:53:28Z",
    "fbfm13": "2026-09-07T19:06:37Z", "fvc": "2026-09-07T18:44:30Z",
    "fvh": "2026-09-07T18:44:06Z", "fvt": "2026-09-07T18:45:00Z",
}
COG_BYTES = {"cbd":2089104183,"cbh":2605634917,"cc":2087722356,"ch":1998245444,
             "fbfm13":2657139827,"fvc":4322553564,"fvh":3744772364,"fvt":4009625884}

# values actually present in the published hex (measured, not from the legend)
PRESENT = {
    "fbfm13": [2,3,4,5,6,7,8,9,10,11,12,13,91,92,93,98,99],
    "fvc": [11,12,13,14,15,16,17,22,23,24,25,31,32,61,63,64,65,68,69,82,
            100,101,102,103,104,105,106,107,108,109,111,112,113,114,115,116,117,118,119,
            121,122,123,124,125,126,127,128,129],
    "fvh": [11,12,13,14,15,16,17,22,23,24,25,31,32,61,63,64,65,68,69,82,
            100,425,475,499,502,507,520,530,603,607,611,615,619,623,627,631,635,639,643,651],
}

PRESENT["fvt"] = [int(v) for v in
    pathlib.Path("/tmp/fvt-present-list.txt").read_text().strip().split(",")]

CONT = {
    "cbd": dict(
        code="CBD", csv="LF2024_CBD.csv", name_col="KGM3",
        title="LANDFIRE 2024 Forest Canopy Bulk Density (CONUS, 30 m)",
        short="Forest Canopy Bulk Density", unit="kilograms per cubic metre",
        scale=0.01, scale_text="divide the stored value by 100",
        domain="0.01 to 0.45 kilograms per cubic metre",
        blurb=("Forest Canopy Bulk Density is the mass of available canopy fuel per unit of canopy "
               "volume that would burn in a crown fire. It is one of the two canopy inputs, with "
               "canopy base height, that determine whether a surface fire can transition into the "
               "crown and sustain itself there.")),
    "cbh": dict(
        code="CBH", csv="LF2024_CBH.csv", name_col="METERS",
        title="LANDFIRE 2024 Forest Canopy Base Height (CONUS, 30 m)",
        short="Forest Canopy Base Height", unit="metres",
        scale=0.1, scale_text="divide the stored value by 10",
        domain="0.2 to 10.0 metres",
        blurb=("Forest Canopy Base Height is the height above the ground of the lowest canopy fuel "
               "capable of carrying fire vertically. A low canopy base height makes a crown fire "
               "easier to initiate from a surface fire.")),
    "cc": dict(
        code="CC", csv="LF2024_CC.csv", name_col="CC_PERCENT",
        title="LANDFIRE 2024 Forest Canopy Cover (CONUS, 30 m)",
        short="Forest Canopy Cover", unit="percent",
        scale=1.0, scale_text="the stored value is already a percentage",
        domain="15 to 95 percent",
        blurb=("Forest Canopy Cover is the percentage of ground covered by the vertical projection "
               "of tree canopy. It drives how much of a fire's heat is retained beneath the canopy "
               "and how much wind reaches the surface.")),
    "ch": dict(
        code="CH", csv="LF2024_CH.csv", name_col="METERS",
        title="LANDFIRE 2024 Forest Canopy Height (CONUS, 30 m)",
        short="Forest Canopy Height", unit="metres",
        scale=0.1, scale_text="divide the stored value by 10",
        domain="3.0 to 50.9 metres",
        blurb=("Forest Canopy Height is the average height of the top of the tree canopy for a "
               "stand. With canopy base height it describes the vertical extent of the crown fuel "
               "layer.")),
}

CAT = {
    "fbfm13": dict(
        code="FBFM13", csv="LF2024_FBFM13.csv", name_col="FBFM13",
        title="LANDFIRE 2024 13 Anderson Fire Behavior Fuel Models (CONUS, 30 m)",
        short="13 Anderson Fire Behavior Fuel Models",
        blurb=("The 13 Anderson Fire Behavior Fuel Models classify surface fuels into thirteen "
               "types that fire behaviour models use to predict rate of spread and flame length. "
               "Codes 91 to 99 mark land that does not carry a surface fire: urban, snow and ice, "
               "agriculture, open water and barren ground.")),
    "fvc": dict(
        code="FVC", csv="LF2024_FVC.csv", name_col="CLASSNAMES",
        title="LANDFIRE 2024 Fuel Vegetation Cover (CONUS, 30 m)",
        short="Fuel Vegetation Cover",
        blurb=("Fuel Vegetation Cover gives the canopy cover of the vegetation used to assign fuel "
               "models, banded by life form. Tree, shrub and herb cover occupy separate code "
               "ranges, and further codes mark water, snow and ice, developed land, barren ground "
               "and agriculture.")),
    "fvt": dict(
        code="FVT", csv="LF2024_FVT.csv", name_col="EVT_FUEL_N",
        title="LANDFIRE 2024 Fuel Vegetation Type (CONUS, 30 m)",
        short="Fuel Vegetation Type",
        blurb=("Fuel Vegetation Type is the vegetation classification used to assign fuel models, "
               "naming what is growing rather than how much of it there is. With fuel vegetation "
               "cover and fuel vegetation height it forms the set that describes the fuel-bearing "
               "vegetation: what it is, how much ground it covers and how tall it stands. Classes "
               "carry a life-form prefix, and further codes mark open water, snow and ice, "
               "developed land, barren ground and agriculture. The national legend lists 906 "
               "classes, of which 565 occur in the conterminous United States.")),
    "fvh": dict(
        code="FVH", csv="LF2024_FVH.csv", name_col="CLASSNAMES",
        title="LANDFIRE 2024 Fuel Vegetation Height (CONUS, 30 m)",
        short="Fuel Vegetation Height",
        blurb=("Fuel Vegetation Height gives the height of the vegetation used to assign fuel "
               "models, banded by life form. Tree, shrub and herb heights occupy separate code "
               "ranges, and further codes mark water, snow and ice, developed land, barren ground "
               "and agriculture.")),
}

HEX_COLS = [
    ("h10", "uint64", "H3 cell ID at resolution 10 (native resolution; one row per cell)."),
    ("h9",  "uint64", "H3 cell ID at resolution 9 (parent)."),
    ("h8",  "uint64", "H3 cell ID at resolution 8 (parent; catalog universal join key)."),
    ("h0",  "int64",  "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."),
]


def legend(code, csvname, name_col, legends_dir):
    path = pathlib.Path(legends_dir) / code / csvname
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    out = {}
    for r in rows:
        v = r.get("VALUE", "").strip()
        if not v.lstrip("-").isdigit():
            continue
        iv = int(v)
        if iv in FILL:
            continue
        rgb = "".join(f"{int(r[c]):02X}" for c in ("R", "G", "B")) if r.get("R") else "808080"
        out[iv] = (r.get(name_col, "").strip() or f"Class {iv}", rgb)
    return out


def nav(dsid):
    return [
        {"rel": "self", "href": f"{BASE}/{dsid}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": ROOT, "type": "application/json"},
        {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
        {"rel": "license", "href": LANDING, "type": "text/html",
         "title": "LANDFIRE data access and use"},
        {"rel": "about", "href": LANDING, "type": "text/html",
         "title": "LANDFIRE Full Extent Downloads"},
    ]


def provenance(layer):
    b, sha = RAW[layer]
    code = (CONT.get(layer) or CAT[layer])["code"]
    return (f"Source edition {EDITION}, accessed {ACCESSED} from the LANDFIRE Full Extent Downloads "
            f"page. The pristine upstream archive is retained at "
            f"s3://{BUCKET}/raw/LF2024_{code}_CONUS.zip ({b:,} bytes, "
            f"sha256 {sha}), and the shipped class table at "
            f"s3://{BUCKET}/raw/landfire-2024/{code}/{code and ''}{(CONT.get(layer) or CAT[layer])['csv']}.")


def common(layer, dsid, cfg, description, assets):
    return {
        "type": "Collection", "stac_version": "1.0.0", "id": dsid,
        "stac_extensions": [
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
        ],
        "title": cfg["title"], "description": description,
        "license": "public-domain",
        "sci:citation": (f"LANDFIRE {EDITION}, {cfg['short']}, conterminous United States. "
                         f"US Geological Survey and US Department of Agriculture Forest Service. "
                         f"Accessed {ACCESSED}."),
        "extent": {"spatial": {"bbox": [BBOX]}, "temporal": {"interval": [TEMPORAL]}},
        "providers": [
            {"name": "LANDFIRE (USGS / USDA Forest Service)", "roles": ["producer", "licensor"],
             "url": LANDING},
            {"name": "Carl Boettiger Lab, UC Berkeley", "roles": ["processor", "host"],
             "url": f"{BASE}/"},
        ],
        "links": nav(dsid),
        "assets": assets,
    }


def build_continuous(layer, legends_dir):
    cfg, m = CONT[layer], MEASURED[layer]
    dsid = f"landfire-2024-{layer}"
    lg = legend(cfg["code"], cfg["csv"], cfg["name_col"], legends_dir)

    forest_note = (
        "Pixel value 0 marks land that is not forested. It is a category rather than a "
        "measurement, and it covers roughly 69 percent of valid pixels, so it is excluded from "
        "the hex table along with the fill codes. Every cell in the hex table therefore describes "
        "forested ground, and a mean taken over it is a mean over forest, not over all land. A "
        "statistic across a whole region needs that denominator stated, or the region's non-forest "
        "area brought in from another layer.")

    # cc stores a percentage directly, so the "value is not the quantity" framing is wrong
    # for it and produced a garbled sentence. Branch rather than force one template.
    if cfg["scale"] == 1.0:
        decode = (f"The stored value is already in {cfg['unit']} and needs no conversion. "
                  f"The published range is {cfg['domain']}.")
    else:
        decode = (f"The stored value is not the physical quantity: {cfg['scale_text']} to obtain "
                  f"{cfg['unit']}. The published range is {cfg['domain']}.")

    extra = ""
    if layer == "cbh":
        extra = (" The top class, stored as 100, means 10 metres or greater and is not an exact "
                 "height; it holds about 19 percent of cells, so a mean over this layer is pulled "
                 "toward that ceiling and understates the tallest canopy bases.")
    if layer == "cc":
        extra = (" The lowest class covers 10 to under 20 percent cover, stored as 15. There is no "
                 "class below 10 percent: ground with sparse tree cover falls into the "
                 "non-forested value 0 and is therefore absent from this table, so this layer "
                 "cannot distinguish open woodland from treeless ground.")
    if layer in ("ch", "cc"):
        extra += (" Classes are stored as the midpoint of a range rather than an exact measurement, "
                  "so an averaged cell carries the discretisation of those bands.")

    desc = (f"{cfg['blurb']} {decode}{extra} {forest_note} Published as a cloud-optimized GeoTIFF "
            f"at 30 metres and as an H3 hex table at resolution 10 covering the conterminous "
            f"United States. {provenance(layer)}")

    hex_desc = (
        f"Area-weighted mean (mean reducer) H3 hex of LANDFIRE 2024 {cfg['short']} at resolution "
        f"10, one row per cell, hive-partitioned by h0. Each cell carries the mean of the source "
        f"pixels falling in it, so the value is already an average and combining cells means "
        f"averaging again rather than summing. "
        + (f"Values are in {cfg['unit']}. " if cfg["scale"] == 1.0
           else f"{cfg['scale_text'].capitalize()} to obtain {cfg['unit']}. ")
        + f"Cells whose pixels are all non-forested or fill are not written, so this "
        f"table covers forested ground only and partitions are sparse. "
        f"Fill codes {', '.join(str(f) for f in FILL)} and the non-forested value 0 are excluded.")

    col_desc = (f"LANDFIRE 2024 {cfg['short']} as an area-weighted mean of the source pixels in the "
                f"cell. {decode}")

    cog_desc = (f"LANDFIRE 2024 {cfg['short']}, conterminous United States, 30 metres, reprojected "
                f"to WGS84. Unlike the hex table this retains every pixel, including the "
                f"non-forested value 0 and the fill codes {', '.join(str(f) for f in FILL)}, so a "
                f"consumer reading the raster directly must exclude them. {decode}")

    assets = {
        f"{layer}-cog": {
            "href": f"{BASE}/{dsid}/{dsid}-cog.tif", "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "title": f"{cfg['short']} 2024, cloud-optimized GeoTIFF, 30 m", "roles": ["data"],
            "description": cog_desc, "created": COG_CREATED[layer],
            "file:size": COG_BYTES[layer],
            "raster:bands": [{"name": layer, "data_type": "int16", "nodata": -9999,
                              "unit": cfg["unit"], "scale": cfg["scale"]}],
        },
        f"{layer}-hex": {
            "href": f"{BASE}/{dsid}/hex/h0=*/data_0.parquet", "type": "application/x-parquet",
            "title": f"{cfg['short']} 2024, H3 resolution 10, area-weighted mean", "roles": ["data"],
            "description": hex_desc,
            "h3:native_resolution": 10, "h3:parent_resolutions": [9, 8, 0],
            "table:columns": [{"name": layer, "type": "double", "description": col_desc}]
                             + [{"name": n, "type": t, "description": d} for n, t, d in HEX_COLS],
        },
    }
    coll = common(layer, dsid, cfg, desc, assets)
    return coll, len(lg)


def build_categorical(layer, legends_dir):
    cfg, m = CAT[layer], MEASURED[layer]
    dsid = f"landfire-2024-{layer}"
    lg = legend(cfg["code"], cfg["csv"], cfg["name_col"], legends_dir)
    present = PRESENT[layer]
    missing = [v for v in present if v not in lg]
    if missing:
        raise SystemExit(f"{layer}: ingested codes absent from the shipped legend: {missing}")

    desc = (f"{cfg['blurb']} Published as a cloud-optimized GeoTIFF at 30 metres and as an H3 hex "
            f"table at resolution 10 covering the conterminous United States. Fill codes "
            f"{', '.join(str(f) for f in FILL)} are excluded from the hex table; the raster retains "
            f"them. {provenance(layer)}")

    hex_desc = (
        f"Dominant-class (mode reducer) H3 hex of LANDFIRE 2024 {cfg['short']} at resolution 10, "
        f"one row per cell, hive-partitioned by h0. Each cell takes the class covering the largest "
        f"share of it, so the mix within a cell is not preserved and the value is a class code "
        f"rather than a quantity: averaging or summing this column is not meaningful. Cells with no "
        f"valid source pixel are not written, so partitions are sparse. Fill codes "
        f"{', '.join(str(f) for f in FILL)} are excluded.")

    defs = ", ".join(f"{v}={lg[v][0]}" for v in present)
    col_desc = (f"LANDFIRE 2024 {cfg['short']} class code, the class covering the largest share of "
                f"the cell. Values: {defs}")

    classes = [{"value": v, "name": lg[v][0],
                "description": f"{cfg['short']} class {v}: {lg[v][0]}.",
                "color_hint": lg[v][1]}
               for v in sorted(lg)]

    assets = {
        f"{layer}-cog": {
            "href": f"{BASE}/{dsid}/{dsid}-cog.tif", "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "title": f"{cfg['short']} 2024, cloud-optimized GeoTIFF, 30 m", "roles": ["data"],
            "description": (f"LANDFIRE 2024 {cfg['short']}, conterminous United States, 30 metres, "
                            f"reprojected to WGS84. Retains the fill codes "
                            f"{', '.join(str(f) for f in FILL)}, which the hex table excludes."),
            "created": COG_CREATED[layer], "file:size": COG_BYTES[layer],
            "raster:bands": [{"name": layer, "data_type": "int16", "nodata": -9999,
                              "classification:classes": classes}],
        },
        f"{layer}-hex": {
            "href": f"{BASE}/{dsid}/hex/h0=*/data_0.parquet", "type": "application/x-parquet",
            "title": f"{cfg['short']} 2024, H3 resolution 10, dominant class", "roles": ["data"],
            "description": hex_desc,
            "h3:native_resolution": 10, "h3:parent_resolutions": [9, 8, 0],
            "table:columns": [{"name": layer, "type": "int16", "description": col_desc,
                               "values": present}]
                             + [{"name": n, "type": t, "description": d} for n, t, d in HEX_COLS],
        },
    }
    coll = common(layer, dsid, cfg, desc, assets)
    coll["stac_extensions"].append(
        "https://stac-extensions.github.io/classification/v2.0.0/schema.json")
    return coll, len(classes)


# ---------------------------------------------------------------------------
# Bucket collection
# ---------------------------------------------------------------------------
# SINGLE OWNER. make-stac.py also has a bucket_collection(), written when only vcc and
# evt existed; it is superseded and must not be run against public-landfire/stac-collection.json
# any more, or it will drop the seven collections below. Two generators for one file is
# how the fractions claim drifted the first time.
PUBLISHED_ALL = [
    ("landfire-2024-vcc",    "LANDFIRE 2024 Vegetation Condition Class (CONUS, 30 m)"),
    ("landfire-2024-evt",    "LANDFIRE 2024 Existing Vegetation Type (CONUS, 30 m)"),
    ("landfire-2024-cbd",    "LANDFIRE 2024 Forest Canopy Bulk Density (CONUS, 30 m)"),
    ("landfire-2024-cbh",    "LANDFIRE 2024 Forest Canopy Base Height (CONUS, 30 m)"),
    ("landfire-2024-cc",     "LANDFIRE 2024 Forest Canopy Cover (CONUS, 30 m)"),
    ("landfire-2024-ch",     "LANDFIRE 2024 Forest Canopy Height (CONUS, 30 m)"),
    ("landfire-2024-fbfm13", "LANDFIRE 2024 13 Anderson Fire Behavior Fuel Models (CONUS, 30 m)"),
    ("landfire-2024-fvc",    "LANDFIRE 2024 Fuel Vegetation Cover (CONUS, 30 m)"),
    ("landfire-2024-fvh",    "LANDFIRE 2024 Fuel Vegetation Height (CONUS, 30 m)"),
    ("landfire-2024-fvt",    "LANDFIRE 2024 Fuel Vegetation Type (CONUS, 30 m)"),
]


def bucket_collection():
    return {
        "type": "Collection", "stac_version": "1.0.0", "id": "landfire",
        "title": "LANDFIRE",
        "description": (
            "LANDFIRE is a shared program of the US Geological Survey and the USDA Forest Service "
            "that maps vegetation, fuel and fire regime conditions across the United States at 30 "
            "metre resolution. This catalog holds the LANDFIRE 2024 Update (version 2.5.0) for the "
            "conterminous United States: vegetation condition class and existing vegetation type; "
            "the four forest canopy layers used as crown fire inputs, which are bulk density, base "
            "height, cover and height; and three fuel layers, the 13 Anderson fire behaviour fuel "
            "models with fuel vegetation cover and height. Each is published as a cloud-optimized "
            "GeoTIFF and as an H3 hex table at resolution 10. The four canopy layers describe "
            "forested ground only, because the value marking non-forested land is excluded from "
            "their hex tables; the other five cover all mapped land. Existing vegetation cover, "
            "existing vegetation height and the 40 Scott and Burgan fire behaviour fuel models are "
            "not yet published."),
        "license": "public-domain",
        "extent": {"spatial": {"bbox": [BBOX]}, "temporal": {"interval": [TEMPORAL]}},
        "links": [
            {"rel": "self", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": ROOT, "type": "application/json"},
            {"rel": "license", "href": LANDING, "type": "text/html",
             "title": "LANDFIRE data access and use"},
        ] + [
            {"rel": "child", "id": i, "href": f"{BASE}/{i}/stac-collection.json",
             "type": "application/json", "title": t}
            for i, t in PUBLISHED_ALL
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--legends", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for layer in list(CONT) + list(CAT):
        coll, n = (build_continuous if layer in CONT else build_categorical)(layer, a.legends)
        p = out / f"landfire-2024-{layer}.json"
        p.write_text(json.dumps(coll, indent=2))
        kind = "continuous" if layer in CONT else f"{n} classes"
        print(f"  {p.name}  {kind}  {p.stat().st_size/1024:.0f} KiB")
    b = out / "landfire-bucket.json"
    b.write_text(json.dumps(bucket_collection(), indent=2))
    print(f"  {b.name}  {len(PUBLISHED_ALL)} children")


if __name__ == "__main__":
    main()
