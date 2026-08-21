#!/usr/bin/env python3
"""Emit the four whp-2023 dataset collections and the patched public-fire bucket
collection to /tmp for rclone upload (AGENTS.md Hard Boundary 1 — this repo never
contains STAC JSON or README files).

Four collections, not one, because the WHP classification is DOMAIN-RELATIVE: the
class breaks for Alaska and CONUS are different numbers (a CONUS "Very High" is
index > 1,985; an Alaska "Very High" is > 8,912). A single mosaicked classified
layer would invite a pooled GROUP BY across two incompatible scales, which is
exactly the arithmetic that produces a wrong headline number. Splitting the
domains makes the pooling impossible to do by accident, and the res-8 `h8` key on
all four means they still join to each other and to roadless-areas-2001 cell for
cell — which is what H3 is for.

The bucket collection is FETCHED and PATCHED rather than rewritten, so fields this
script does not know about survive.
"""
import copy
import json
import urllib.request

BUCKET = "public-fire"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"

ARCHIVE = "https://www.fs.usda.gov/rds/archive/products/RDS-2015-0047-4"
PRODUCT_PAGE = ("https://research.fs.usda.gov/firelab/products/dataandtools/"
                "wildfire-hazard-potential")

# ── Official class labels, verbatim from the source value attribute table ──────
# whp2023_cls_{conus,ak}.tif.vat.dbf, column `class_desc`. Transcribed rather than
# written from memory (#294). The source ships NO color table on either the
# classified GeoTIFF or the file geodatabase, so no palette is asserted here.
CLASS_DESC = {
    1: "Very Low",
    2: "Low",
    3: "Moderate",
    4: "High",
    5: "Very High",
    6: "Non-burnable",
    7: "Water",
}

CLASS_LIST = ", ".join(f"{k}={v}" for k, v in sorted(CLASS_DESC.items()))

# Class breaks on the continuous WHP index, per domain (Dillon 2023). These are the
# reason the domains are published separately.
BREAKS = {
    "conus": {1: "≤ 61", 2: "62–178", 3: "179–489", 4: "490–1,985", 5: "> 1,985"},
    "ak":    {1: "≤ 83", 2: "84–624", 3: "625–2,922", 4: "2,923–8,912", 5: "> 8,912"},
}

HAZARD_NOT_RISK = (
    "**Hazard, not risk.** Wildfire Hazard Potential describes the likelihood and intensity "
    "of wildfire at a location given its fuels, topography and weather. It says nothing about "
    "what is there to lose. A remote wilderness ridge can carry Very High hazard with no "
    "exposed assets; a subdivision can sit in Moderate hazard and still dominate a risk "
    "ranking. Do not read this layer as a map of communities in danger — for that, use "
    "Wildfire Risk to Communities, which combines hazard with exposure and susceptibility."
)

NON_BURNABLE_NOTE = (
    "Classes 6 (Non-burnable) and 7 (Water) are not hazard levels — they are the absence of "
    "burnable fuel. They are part of the mapped land base and are NOT excluded from any total "
    "here. Whether to exclude them is the consumer's decision and it changes every "
    "\"share of X that is high hazard\" figure materially: they are 27.0% of CONUS cells and "
    "24.4% of Alaska cells. State which convention a published percentage uses."
)


def domain_note(domain):
    other = "ak" if domain == "conus" else "conus"
    dom_name = "CONUS" if domain == "conus" else "Alaska"
    other_name = "Alaska" if domain == "conus" else "CONUS"
    return (
        f"**The class breaks are specific to {dom_name} and are not comparable to "
        f"{other_name}.** Dillon (2023) classifies each domain against its own distribution of "
        f"the continuous WHP index, so identical class labels mean different absolute hazard in "
        f"each domain:\n\n"
        f"| Class | {dom_name} index | {other_name} index |\n|---|---|---|\n"
        + "".join(
            f"| {k}: {CLASS_DESC[k]} | {BREAKS[domain][k]} | {BREAKS[other][k]} |\n"
            for k in (1, 2, 3, 4, 5)
        )
        + f"\nA {dom_name} \"Very High\" cell and an {other_name} \"Very High\" cell differ by "
        f"roughly 4.5× in underlying index. Never GROUP BY class across the two collections. "
        f"For any cross-domain comparison use the continuous collections "
        f"(`whp-2023-continuous-{domain}` / `whp-2023-continuous-{other}`), whose raw index "
        f"means the same thing everywhere."
    )


AREA_TRUTH = (
    "**Area truth comes from the source grid, not from pixel counts on the COG.** The source "
    "is an equal-area Albers grid; the WGS84 COG published alongside is geographic and therefore "
    "is not equal-area, so counting COG pixels is not an area measurement. H3 cells at a given "
    "resolution are near-equal-area, so cell counts on the hex asset ARE a valid area proxy — "
    "and they reproduce the source's equal-area class shares to within 0.6 percentage points on "
    "every class in both domains."
)

# `bbox` is the MEASURED footprint of the populated H3 cells, not the COG rectangle and
# not the gdalwarp clip box. The COG carries a nodata margin (and the Alaska clip box
# reaches 2.4° south of any Alaska data), so declaring either would overstate the extent
# — which verify-stac.py flags as title-names-state-but-bbox-exceeds-it (#528).
DATASETS = {
    "whp-2023-classified-conus": {
        "domain": "conus",
        "kind": "classified",
        "title": "Wildfire Hazard Potential 2023 — classified, CONUS",
        "bbox": [-124.864, 24.467, -66.940, 49.387],
        "cog": "whp-2023-classified-conus-cog.tif",
        "native": 9,
        "parents": [8, 0],
        "reducer": "mode",
        "column": "whp_class",
        "coltype": "uint8",
        "nodata": 255,
        "rows": 74428571,
        "h0_count": 6,
        "src_tif": "whp2023_cls_conus.tif",
        "eff_pixel": "about 250 m × 324 m at 40°N",
    },
    "whp-2023-classified-ak": {
        "domain": "ak",
        "kind": "classified",
        "title": "Wildfire Hazard Potential 2023 — classified, Alaska",
        "bbox": [-173.190, 54.653, -129.988, 71.370],
        "cog": "whp-2023-classified-ak-cog.tif",
        "native": 9,
        "parents": [8, 0],
        "reducer": "mode",
        "column": "whp_class",
        "coltype": "uint8",
        "nodata": 255,
        "rows": 16540214,
        "h0_count": 3,
        "src_tif": "whp2023_cls_ak.tif",
        "eff_pixel": "about 169 m × 337 m at 60°N",
    },
    "whp-2023-continuous-conus": {
        "domain": "conus",
        "kind": "continuous",
        "title": "Wildfire Hazard Potential 2023 — continuous index, CONUS",
        "bbox": [-124.868, 24.467, -66.940, 49.387],
        "cog": "whp-2023-continuous-conus-cog.tif",
        "native": 8,
        "parents": [0],
        "reducer": "mean",
        "column": "whp_index",
        "coltype": "double",
        "nodata": 2147483647,
        "rows": 10641399,
        "h0_count": 6,
        "src_tif": "whp2023_cnt_conus.tif",
        "eff_pixel": "about 250 m × 324 m at 40°N",
    },
    "whp-2023-continuous-ak": {
        "domain": "ak",
        "kind": "continuous",
        "title": "Wildfire Hazard Potential 2023 — continuous index, Alaska",
        "bbox": [-173.188, 54.654, -129.984, 71.371],
        "cog": "whp-2023-continuous-ak-cog.tif",
        "native": 8,
        "parents": [0],
        "reducer": "mean",
        "column": "whp_index",
        "coltype": "double",
        "nodata": 2147483647,
        "rows": 2369388,
        "h0_count": 3,
        "src_tif": "whp2023_cnt_ak.tif",
        "eff_pixel": "about 169 m × 337 m at 60°N",
    },
}


H3_DESC = {
    9: "H3 cell identifier at resolution 9.",
    8: ("H3 cell identifier at resolution 8. This is the shared join key across the catalog "
        "(AGENTS.md) — use it to join this layer to roadless-areas-2001 and to the other three "
        "whp-2023 collections."),
    0: ("H3 cell identifier at resolution 0, used as the partition key for hive-partitioned "
        "reads."),
}


def hex_columns(cfg):
    """Column list for the hex asset: the value column plus its H3 keys."""
    if cfg["kind"] == "classified":
        value = {
            "name": cfg["column"],
            "type": cfg["coltype"],
            "description": (
                "Classified Wildfire Hazard Potential, the majority (`mode`) source class within "
                "the cell. Values 1–5 are hazard levels on a domain-relative scale; 6 and 7 are "
                "non-burnable land and water, not hazard levels. Labels are verbatim from the "
                "source value attribute table. Source nodata (255) is dropped rather than stored, "
                "so this column is never null. Valid values: "
                + CLASS_LIST + "."
            ),
            "values": [1, 2, 3, 4, 5, 6, 7],
        }
    else:
        value = {
            "name": cfg["column"],
            "type": cfg["coltype"],
            "description": (
                "Continuous Wildfire Hazard Potential index, the area-weighted `mean` of the "
                "source pixels within the cell. Unitless and monotonic — higher means greater "
                "hazard potential — and, unlike the classified product, comparable between CONUS "
                "and Alaska. Averaging is meaningful here because the index is a continuous "
                "quantity; do not average the classified codes instead. Source nodata "
                "(2147483647) is dropped rather than stored, so this column is never null."
            ),
        }
    res = [cfg["native"]] + cfg["parents"]
    return [value] + [
        {"name": f"h{r}", "type": "int64" if r == 0 else "uint64", "description": H3_DESC[r]}
        for r in res
    ]


def dataset_collection(name, cfg):
    dom = cfg["domain"]
    dom_name = "CONUS" if dom == "conus" else "Alaska"
    is_cls = cfg["kind"] == "classified"

    rows = f"{cfg['rows']:,}" if cfg["rows"] else "see the hex asset"
    parts = [
        f"Wildfire Hazard Potential (WHP) version 2023 for {dom_name}, at the source resolution "
        f"of 270 m, published as a WGS84 cloud-optimized GeoTIFF and as H3 hex parquet at native "
        f"resolution {cfg['native']}"
        + (f" with parents {', '.join(str(p) for p in cfg['parents'])}." if cfg["parents"] else "."),
        HAZARD_NOT_RISK,
    ]

    if is_cls:
        parts += [domain_note(dom), NON_BURNABLE_NOTE]
    else:
        parts.append(
            "**This is the cross-domain-comparable product.** The raw WHP index means the same "
            "thing in Alaska as in CONUS, whereas the classified product's breaks are computed "
            "per domain. Any CONUS-vs-Alaska comparison should be built on this collection, not "
            "on `whp-2023-classified-*`."
        )

    parts.append(AREA_TRUTH)

    parts.append(
        f"**Effective resolution.** Native H3 resolution is {cfg['native']}, but the source pixel "
        f"is 270 m in the equal-area projection, which after reprojection is {cfg['eff_pixel']}. "
        + (
            "At resolution 9 that is roughly 1.3–1.9 source pixels per cell, so the hex carries "
            "slightly finer geometry than the source actually resolves. Resolution 9 was chosen "
            "deliberately over 8: the deliverable is a class-share statistic inside polygon "
            "boundaries, and at ~9 pixels per cell a `mode` vote is winner-take-all — a cell that "
            "is 4/9 Very High and 5/9 Moderate becomes entirely Moderate, biasing exactly the "
            "statistic being measured. Do not read resolution-9 cells as resolution-9 information."
            if is_cls else
            "At resolution 8 that is roughly 9–13 source pixels per cell, which is what an "
            "area-weighted `mean` wants; resolution 9 would multiply the row count for no added "
            "information."
        )
    )

    if dom == "ak":
        parts.append(
            "**Alaska extent.** Clipped to 180°W–129°W, 48.8°N–71.6°N, which drops the "
            "far-western Aleutians (roughly 157°E–180°) where the source grid wraps the "
            "antimeridian. No National Forest System land lies in the dropped area — the Alaska "
            "units are the Tongass and Chugach, far to the east — so nothing relevant to Forest "
            "Service analysis is lost, but the collection is not a complete Alaska mosaic and "
            "should not be described as one."
        )

    parts.append(
        "Hawaii is published by the source as a third domain with its own class breaks and is not "
        "ingested here; the raw source raster covering it is retained under "
        f"`{BASE}/raw/whp-2023/`."
    )

    description = "\n\n".join(parts)

    assets = {
        f"{name}-cog": {
            "href": f"{BASE}/{cfg['cog']}",
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "title": f"{cfg['title']} — WGS84 COG",
            "description": (
                "Reprojected from the source equal-area Albers grid to EPSG:4326 with nearest-"
                "neighbour resampling"
                + (" — required, since the values are class codes and any other resampling "
                   "invents classes that do not exist in the source." if is_cls else
                   " — matching the classified product so the two grids align cell for cell.")
                + " Geographic, therefore NOT equal-area: use the hex asset for area statistics."
            ),
            "roles": ["data"],
            "raster:bands": [{
                "data_type": "uint8" if is_cls else "int32",
                "nodata": cfg["nodata"],
                "spatial_resolution": 270,
                "unit": "class code" if is_cls else "WHP index (unitless)",
            }],
        },
        f"{name}-hex": {
            "href": f"{BASE}/{name}/hex/h0=*/data_0.parquet",
            "type": "application/x-parquet",
            "title": f"{cfg['title']} — H3 hex (resolution {cfg['native']})",
            "description": (
                f"One row per populated H3 resolution-{cfg['native']} cell ({rows} rows across "
                f"{cfg['h0_count']} h0 partitions). Reducer is `{cfg['reducer']}`"
                + (", correct for class codes — a majority vote preserves values that exist in "
                   "the source, where a mean would fabricate ones that do not."
                   if is_cls else
                   ", correct for a continuous index.")
                + " There is no per-feature attribute repeated across cells here, so unlike a "
                  "vector hex asset `COUNT(*)` is meaningful: it counts cells, and cells are a "
                  "valid area proxy."
            ),
            "roles": ["data"],
            "h3:native_resolution": cfg["native"],
            "h3:parent_resolutions": cfg["parents"],
            "table:columns": hex_columns(cfg),
        },
    }

    if is_cls:
        assets[f"{name}-hex"]["classification:classes"] = [
            {"value": v, "description": d} for v, d in sorted(CLASS_DESC.items())
        ]

    return {
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/classification/v1.1.0/schema.json",
        ] if is_cls else [
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
        ],
        "type": "Collection",
        "id": name,
        "title": cfg["title"],
        "description": description,
        "license": "public-domain",
        "keywords": ["wildfire", "hazard", "fuels", "WHP", "H3", dom_name,
                     "USDA Forest Service", "Fire Sciences Laboratory"],
        "extent": {
            "spatial": {"bbox": [cfg["bbox"]]},
            "temporal": {"interval": [["2023-01-01T00:00:00Z", "2023-12-31T23:59:59Z"]]},
        },
        "providers": [
            {"name": "Gregory K. Dillon, USDA Forest Service Rocky Mountain Research Station, "
                     "Fire Sciences Laboratory",
             "roles": ["producer", "licensor"], "url": PRODUCT_PAGE},
            {"name": "USDA Forest Service Research Data Archive",
             "roles": ["licensor", "host"], "url": ARCHIVE},
            {"name": "Boettiger Lab / cirrus", "roles": ["processor", "host"], "url": f"{BASE}/"},
        ],
        "links": [
            {"rel": "self", "href": f"{BASE}/{name}/stac-collection.json",
             "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json",
             "type": "application/json"},
            {"rel": "license", "href": "https://www.usa.gov/government-works",
             "type": "text/html", "title": "US Government work — public domain"},
            {"rel": "cite-as", "href": "https://doi.org/10.2737/RDS-2015-0047-4",
             "title": "Dillon, G.K. 2023. Wildfire Hazard Potential for the United States "
                      "(270-m), version 2023. 4th Edition. Fort Collins, CO: Forest Service "
                      "Research Data Archive."},
            {"rel": "via", "href": f"{ARCHIVE}/RDS-2015-0047-4_Data.zip",
             "type": "application/zip", "title": "Source data package (Research Data Archive)"},
            {"rel": "about", "href": PRODUCT_PAGE, "type": "text/html",
             "title": "Wildfire Hazard Potential product page"},
            {"rel": "describedby",
             "href": f"{BASE}/raw/whp-2023/unpacked/Data/whp2023_GeoTIF/{cfg['src_tif']}.xml",
             "type": "application/xml",
             "title": "FGDC metadata as published with the source"},
        ],
        "assets": assets,
    }


BUCKET_TITLE = "Wildfire: hazard potential and fire perimeters"

BUCKET_DESCRIPTION = (
    "Wildfire datasets published as cloud-native GeoParquet, PMTiles and H3 hex parquet. Two "
    "kinds of layer live here and they answer different questions. Fire perimeters (CAL FIRE "
    "FRAP, USGS Combined) record where fire HAS burned. Wildfire Hazard Potential records where "
    "fire is LIKELY to burn and how intensely, given fuels, topography and weather — it is a "
    "modelled surface, not an observation, and it is hazard rather than risk: it does not account "
    "for what is exposed to loss.\n\n"
    "Licenses differ by dataset — the CAL FIRE and USGS perimeter collections are CC-BY-4.0, the "
    "Forest Service hazard products are US Government works in the public domain. Each child "
    "collection carries its own license; check there rather than assuming a bucket-wide term."
)


def patch_bucket_collection():
    """Fetch the published bucket collection and add the four whp-2023 children.

    Patched rather than rewritten so fields this script does not model are preserved.
    Three edits beyond the child links:

    1. title/description — the published ones say "Fire Perimeters", which stops being
       true once a modelled hazard raster lives in the bucket.
    2. license CC-BY-4.0 → various — the perimeter children are CC-BY-4.0 and the WHP
       children are public-domain, so no single bucket-level term is honest. A
       meta-collection (one with child links) may use `various` with no license link;
       the real licenses live on and are gated per child (stac-authoring SKILL.md,
       verify-stac.py check_license).
    3. the bucket-level CC-BY-4.0 license LINK is dropped for the same reason — left in
       place it would assert CC-BY over public-domain children.

    The `id` (`fire-perimeters`) is deliberately NOT changed: it is consumer-visible and
    renaming it is out of scope for this issue.
    """
    with urllib.request.urlopen(f"{BASE}/stac-collection.json", timeout=60) as r:
        doc = json.load(r)

    doc["title"] = BUCKET_TITLE
    doc["description"] = BUCKET_DESCRIPTION
    doc["license"] = "various"

    links = [
        l for l in doc.get("links", [])
        if not (l.get("rel") == "license"
                and "creativecommons.org" in l.get("href", ""))
    ]

    have = {l.get("href") for l in links if l.get("rel") == "child"}
    for name, cfg in DATASETS.items():
        href = f"{BASE}/{name}/stac-collection.json"
        if href not in have:
            links.append({"rel": "child", "href": href, "type": "application/json",
                          "title": cfg["title"]})
    doc["links"] = links

    # widen the temporal interval to cover the 2023 hazard vintage if needed
    extent = doc.setdefault("extent", {}).setdefault("temporal", {})
    interval = extent.get("interval") or [[None, None]]
    start, end = interval[0][0], interval[0][1]
    if end and end < "2023-12-31T23:59:59Z":
        interval[0][1] = "2023-12-31T23:59:59Z"
        extent["interval"] = interval

    kw = doc.setdefault("keywords", [])
    for k in ("wildfire hazard potential", "WHP", "fuels", "H3"):
        if k not in kw:
            kw.append(k)

    return doc


WHP_README_SECTION = f"""
## Wildfire Hazard Potential 2023 (`whp-2023-*`) — modelled hazard, not perimeters

Four collections, because the source classifies each geographic domain against its own
distribution of the continuous index. **The class breaks are different numbers in CONUS and
Alaska** — a CONUS "Very High" is index > 1,985, an Alaska "Very High" is > 8,912, 4.5× apart —
so a pooled `GROUP BY class` across domains is meaningless arithmetic.

| Collection | Native H3 | Reducer | Column |
|---|---|---|---|
| [`whp-2023-classified-conus`]({BASE}/whp-2023-classified-conus/stac-collection.json) | 9 (parents 8, 0) | `mode` | `whp_class` |
| [`whp-2023-classified-ak`]({BASE}/whp-2023-classified-ak/stac-collection.json) | 9 (parents 8, 0) | `mode` | `whp_class` |
| [`whp-2023-continuous-conus`]({BASE}/whp-2023-continuous-conus/stac-collection.json) | 8 (parent 0) | `mean` | `whp_index` |
| [`whp-2023-continuous-ak`]({BASE}/whp-2023-continuous-ak/stac-collection.json) | 8 (parent 0) | `mean` | `whp_index` |

Classes: {CLASS_LIST}. Classes 6 and 7 are the absence of burnable fuel, not hazard levels.

**Hazard is not risk.** WHP describes how likely and intense fire is given fuels, topography and
weather. It says nothing about what is exposed to loss. A remote wilderness ridge can be Very
High with nothing at stake; a subdivision can be Moderate and still top a risk ranking.

**For any CONUS-vs-Alaska comparison use the continuous collections** — the raw index means the
same thing everywhere.

### DuckDB

```sql
INSTALL httpfs; LOAD httpfs;

-- high + very high share of CONUS, by H3 cell area (cells are near-equal-area)
SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE whp_class IN (4,5)) / COUNT(*), 2) AS pct_high
FROM read_parquet('{BASE}/whp-2023-classified-conus/hex/h0=*/data_0.parquet');
-- 12.47

-- hazard inside inventoried roadless areas: join on the shared h8 key
SELECT w.whp_class, COUNT(DISTINCT w.h8) AS cells
FROM read_parquet('{BASE}/whp-2023-classified-conus/hex/h0=*/data_0.parquet') w
JOIN (SELECT DISTINCT h8 FROM read_parquet(
        'https://s3-west.nrp-nautilus.io/public-usfs/roadless-areas-2001/hex/h0=*/data_0.parquet')) r
  USING (h8)
GROUP BY w.whp_class ORDER BY w.whp_class;
```

⚠️ Area statistics belong on the hex asset, not the COG. The COG is geographic and therefore not
equal-area — counting its pixels is not an area measurement. The source Albers grid is the area
truth, and the hex reproduces its class shares to within 0.6 percentage points.
"""


def patch_readme():
    """Fetch the published bucket README and add the WHP section.

    Two of the intro's claims stop being true once a modelled hazard raster lives in the
    bucket: that it holds fire *perimeter* datasets, and that all datasets are polygon
    geometries. Both are rewritten; the per-dataset sections are left untouched.
    """
    with urllib.request.urlopen(f"{BASE}/README.md", timeout=60) as r:
        text = r.read().decode("utf-8")

    old_intro = "This bucket contains CAL FIRE and USGS fire perimeter datasets:"
    new_intro = (
        "This bucket contains two kinds of wildfire layer. **Fire perimeters** record where fire "
        "has burned. **Wildfire Hazard Potential** is a modelled surface describing where fire is "
        "likely to burn and how intensely — not an observation, and not a map of risk to people "
        "or property.\n\nContents:"
    )
    assert old_intro in text, "README intro anchor not found"
    text = text.replace(old_intro, new_intro)

    old_all = ("All datasets are polygon geometries processed into GeoParquet, PMTiles, and H3 "
               "hex Parquet (resolution 10).")
    new_all = ("The perimeter datasets are polygon geometries processed into GeoParquet, PMTiles "
               "and H3 hex Parquet (resolution 10). Wildfire Hazard Potential is raster, "
               "published as a WGS84 COG plus H3 hex Parquet (resolution 9 classified, 8 "
               "continuous).")
    assert old_all in text, "README 'all datasets' anchor not found"
    text = text.replace(old_all, new_all)

    perimeter_bullet = ("- **USGS Wildland Fire Combined Dataset** — National wildfire perimeters "
                        "1878\u20132021 (`usgs-fires-2021/combined`)")
    assert perimeter_bullet in text, "README bullet anchor not found"
    text = text.replace(
        perimeter_bullet,
        perimeter_bullet + "\n- **Wildfire Hazard Potential 2023** \u2014 modelled 270 m hazard "
        "surface, CONUS and Alaska, classified and continuous (`whp-2023-*`)",
    )

    # WHP section immediately before the Citation section
    assert "\n## Citation\n" in text, "README citation anchor not found"
    text = text.replace("\n## Citation\n", WHP_README_SECTION + "\n---\n\n## Citation\n", 1)

    text = text.rstrip("\n") + (
        "\n\n**Wildfire Hazard Potential:**\n"
        "Dillon, G.K. 2023. Wildfire Hazard Potential for the United States (270-m), version "
        "2023, 4th Edition. Fort Collins, CO: Forest Service Research Data Archive. "
        "https://doi.org/10.2737/RDS-2015-0047-4\n"
    )
    return text


if __name__ == "__main__":
    written = []
    for name, cfg in DATASETS.items():
        path = f"/tmp/{name}-stac.json"
        with open(path, "w") as f:
            json.dump(dataset_collection(name, cfg), f, indent=2)
            f.write("\n")
        written.append(path)

    with open("/tmp/fire-bucket-stac.json", "w") as f:
        json.dump(patch_bucket_collection(), f, indent=2)
        f.write("\n")
    written.append("/tmp/fire-bucket-stac.json")

    with open("/tmp/fire-README.md", "w") as f:
        f.write(patch_readme())
    written.append("/tmp/fire-README.md")

    print("wrote:")
    for p in written:
        print(" ", p)
