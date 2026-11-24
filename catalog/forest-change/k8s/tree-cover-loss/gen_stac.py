#!/usr/bin/env python3
"""Emit the tree-cover-loss collection and README, the new public-forest-change bucket catalog
that links it, to an output directory for upload (AGENTS.md Hard Boundary 1: this repo never
contains STAC JSON or README files). Scope: data-workflows #434.

    gen_stac.py <out_dir> <objects.json>

objects.json is `rclone lsjson -R nrp:public-forest-change/tree-cover-loss/` with each Path made
bucket-relative by the publish job, so sizes and created times are read from the objects, not
transcribed (#417).

Measured 2026-11-16 (MCP over the published hex; class counts from the cogs.yaml checks):
- Loss-year hex: 81 h0 partitions, loss_year in {0..25, 254, 255}, frac in (0, 1], frac sums to
  1 per cell (h0 578994027093819391: 1,290,400 cells, min = max = 1). Rows with frac down to
  ~1e-27 are exactextract rounding residue. Area per year, SUM(frac * h3_cell_area(h8)), agrees
  with the per-year pixel counts x pixel area to within 1% for every year (2001: 152,055 vs
  151,159 km2; 2024: 383,289 vs 384,227 km2); no-loss land 122.5M km2, permanent water 26.3M km2,
  total loss 2001-2025 6.45M km2.
- Tree-cover hex: 80 h0 partitions, 175,879,377 rows, one per cell, 0 to 100, mean 25.0, no
  nulls or NaN. The one loss-year partition it lacks (h0 580155111372750847, South Atlantic) holds
  only permanent water and unmapped area.
- Raw staging manifest: 1,288 files (lossyear 280 / 9,191,150,013 B; treecover2000 504 /
  58,875,497,056 B; datamask 504 / 8,382,109,151 B); the 12 parts concatenated and sorted have
  MD5 2c2a4a7684b5c2c82c11c53239970240.
"""
import json
import os
import sys
from datetime import datetime, timezone


def v2_classes(doc):
    """Classification v2 (#761): a class's label goes to `title` and `name` becomes its slug,
    with `-<value>` added where a label repeats. Same rule as
    catalog/portolan/k8s/classes-761/fix_classes.py, so a rebuild keeps the published names."""
    import re, unicodedata

    def slug(s):
        s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
        return re.sub(r"[^0-9a-z]+", "-", s.lower()).strip("-")

    def fix(classes):
        todo = [c for c in classes if isinstance(c, dict) and "title" not in c
                and (c.get("name") or c.get("description"))]
        taken = {c["name"] for c in classes if isinstance(c, dict) and "title" in c and c.get("name")}
        labels = [c.get("name") or c["description"] for c in todo]
        slugs = [slug(x) for x in labels]
        for c, label, s in zip(todo, labels, slugs):
            if not s or slugs.count(s) > 1 or s in taken:
                s = f"{s}-{re.sub(r'[^0-9A-Za-z_-]', '-', str(c.get('value')))}".strip("-")
            taken.add(s)
            c["title"], c["name"] = label, s

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "classification:classes" and isinstance(v, list):
                    fix(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(doc)
    return doc

BUCKET = "public-forest-change"
DATASET = "tree-cover-loss"
S3 = "https://s3-west.nrp-nautilus.io"
BASE = f"{S3}/{BUCKET}"
ROOT = f"{S3}/public-data/stac/catalog.json"
PARENT = f"{BASE}/stac-collection.json"
SELF = f"{BASE}/{DATASET}/stac-collection.json"
LANDING = "https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/download.html"
EDITION = "GFC-2025-v1.13"
ACCESSED = "2026-11-13"
BBOX = [-180.0, -60.0, 180.0, 80.0]  # COG extent (gdalinfo): origin -180, 80; 1440000 x 560000 at 0.00025

CITATION = (
    "Hansen, M. C., P. V. Potapov, R. Moore, M. Hancher, S. A. Turubanova, A. Tyukavina, "
    "D. Thau, S. V. Stehman, S. J. Goetz, T. R. Loveland, A. Kommareddy, A. Egorov, L. Chini, "
    "C. O. Justice, and J. R. G. Townshend. 2013. High-Resolution Global Maps of 21st-Century "
    "Forest Cover Change. Science 342 (15 November): 850-53. Data: Hansen/UMD/Google/USGS/NASA, "
    f"Global Forest Change 2000-2025, version {EDITION}, accessed {ACCESSED}."
)

# Loss-year colours: light yellow (2001) to dark red (2025), interpolated along ColorBrewer YlOrRd.
STOPS = [(0xFF, 0xFF, 0xB2), (0xFE, 0xCC, 0x5C), (0xFD, 0x8D, 0x3C), (0xF0, 0x3B, 0x20),
         (0xBD, 0x00, 0x26), (0x80, 0x00, 0x26)]


def ramp(i, n=25):
    t = i / (n - 1) * (len(STOPS) - 1)
    k = min(int(t), len(STOPS) - 2)
    f = t - k
    return "".join(f"{round(a + (b - a) * f):02X}" for a, b in zip(STOPS[k], STOPS[k + 1]))


YEAR_COLOURS = {y: ramp(y - 1) for y in range(1, 26)}

LOSS_CODES = ("Values: 0=No loss 2001-2025, " +
              ", ".join(f"{y}={2000 + y}" for y in range(1, 26)) +
              ", 254=Permanent water, 255=No data (outside the mapped area).")

COLUMNS = [
    {"name": "loss_year", "type": "int32",
     "description": "Year in which tree cover was lost, as a code. " + LOSS_CODES +
     " These are codes, not quantities: do not sum or average them.",
     "values": [0] + list(range(1, 26)) + [254, 255]},
    {"name": "frac", "type": "double",
     "description": "Share, between 0 and 1, of the H3 cell's area that falls in this loss_year "
     "class. For each cell the frac values add up to 1."},
    {"name": "tree_cover_2000", "type": "double",
     "description": "Tree canopy cover in 2000, in percent (0 to 100): the share of ground covered "
     "by vegetation taller than 5 metres, averaged over the mapped land in the cell. Water and "
     "unmapped area are left out of the average. It is a percentage, so average it weighted by "
     "area; do not add it up."},
    {"name": "h8", "type": "uint64",
     "description": "H3 cell ID at resolution 8, the native resolution of this dataset and the "
     "resolution most datasets in this catalog share for joins."},
    {"name": "h0", "type": "int64",
     "description": "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."},
]

DESCRIPTION = f"""Where and when tree cover was lost worldwide from 2001 to 2025, and how much tree cover there was in 2000, mapped at 30 metres. From the Hansen Global Forest Change dataset (University of Maryland), version {EDITION}.

Here a tree is any vegetation taller than 5 metres. Loss means the tree canopy in a 30 metre pixel was removed or killed outright, for any reason: clearing for farming, logging, fire, storms or disease. Loss is not the same as deforestation. It includes loss in plantations and in forest that later regrows, and this dataset does not record regrowth.

Two layers, each published as a 30 metre cloud-optimised GeoTIFF and as H3 hexagons at resolution 8:

- **Loss year**: the year, if any, that each pixel lost its tree cover. The hexagons give the share of each cell lost in each year, so they answer "how much was lost, and when".
- **Tree cover 2000**: canopy cover in 2000, in percent.

**Comparing years.** The producers reprocessed 2011 onward with an improved method but have not reprocessed 2001 to 2010, so loss before and after 2011 is not fully consistent. Treat trends that span 2011 with caution, and compare recent years with each other rather than with the 2000s.

**Coverage.** Land between 80 degrees north and 60 degrees south. Every pixel uses the producers' data mask: mapped land keeps its value, permanent water is its own class (254) in the loss-year layer and is left out of tree cover, and anything the mask marks as no data is left empty (255 in both layers).

**Source.** Downloaded on {ACCESSED} from the {EDITION} release ({LANDING}). The 1,288 source tiles are kept in s3://{BUCKET}/raw/hansen-gfc-2025-v1.13/: lossyear (280 tiles, 9.19 GB), treecover2000 (504 tiles, 58.88 GB) and datamask (504 tiles, 8.38 GB). Each was checked against the MD5 (or, for a few tiles, CRC32C) that Google Cloud Storage reports. The size, MD5 and download date of every tile are listed in raw/hansen-gfc-2025-v1.13/manifest/part-00.txt to part-11.txt; the twelve parts combined and sorted have MD5 2c2a4a7684b5c2c82c11c53239970240.

**Licence and credit.** Creative Commons Attribution 4.0. Cite: {CITATION} Changes made here: tiles masked by the data mask, permanent water given its own class, tiles joined into one global map per layer, and summarised to H3 hexagons."""

LOSS_HEX_DESC = (
    "H3 hexagons at resolution 8, hive-partitioned by h0. One row per (cell, loss_year class "
    "present in the cell), not one row per cell: frac is the share of the cell's area in that "
    "class, and per cell the frac values add up to 1, with 255 as the share outside the mapped "
    "area. To get the area lost per year, weight each row's frac by its own cell's ground area "
    "and sum by loss_year, keeping codes 1 to 25; take the cell area from the H3 area recipe in "
    "the h3-guide rather than a nominal per-resolution constant. Some rows have a frac as small "
    "as 1e-27: that is rounding residue and adds nothing to a sum.\n\n"
    "```sql\n"
    "-- area lost each year, km2\n"
    "SELECT 2000 + loss_year AS year, SUM(frac * <cell area of h8 in km2>) AS loss_km2\n"
    "FROM read_parquet('<this asset>') WHERE loss_year BETWEEN 1 AND 25 GROUP BY 1 ORDER BY 1\n"
    "```\n\n"
    "Resolution 8 cells are about 0.7 square kilometres, coarser than the 30 metre pixels, so a "
    "cell holds roughly 800 pixels and the shares come from all of them."
)

TREE_HEX_DESC = (
    "H3 hexagons at resolution 8, hive-partitioned by h0. One row per cell: tree_cover_2000 is "
    "the mean canopy cover over the cell's mapped land pixels (about 800 pixels per cell). Cells "
    "with no mapped land, such as open water, are absent. To summarise an area, average the "
    "values weighted by cell area; do not add them up."
)


def obj_index(objects):
    return {o["Path"]: o for o in objects}


def created(o):
    t = o["ModTime"]
    return datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(timezone.utc) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")


def hex_created(objects, layer):
    ts = [created(o) for o in objects
          if o["Path"].startswith(f"{DATASET}/{layer}/hex/") and o["Path"].endswith(".parquet")]
    assert len(ts) in (80, 81), (layer, len(ts))
    return max(ts)


def collection(objects):
    idx = obj_index(objects)
    ly, tc = idx[f"{DATASET}/loss-year-cog.tif"], idx[f"{DATASET}/tree-cover-2000-cog.tif"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    classes = [{"value": 0, "name": "No loss 2001-2025",
                "description": "Mapped land with no tree cover loss detected from 2001 to 2025, "
                               "including land that had no trees.",
                "color_hint": "EDEDED"}]
    classes += [{"value": y, "name": f"Lost in {2000 + y}",
                 "description": f"Tree cover lost in {2000 + y}.", "color_hint": YEAR_COLOURS[y]}
                for y in range(1, 26)]
    classes += [{"value": 254, "name": "Permanent water",
                 "description": "Permanent water according to the producers' data mask.",
                 "color_hint": "A6CEE3"}]
    return {
        "type": "Collection",
        "stac_version": "1.1.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/classification/v2.0.0/schema.json",
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
            "https://stac-extensions.github.io/render/v2.0.0/schema.json",
            "https://stac-extensions.github.io/version/v1.2.0/schema.json",
        ],
        "id": DATASET,
        "title": "Tree cover loss 2001-2025 and tree cover 2000 (Hansen Global Forest Change v1.13)",
        "description": DESCRIPTION,
        "keywords": ["forest", "tree cover", "tree cover loss", "deforestation", "Hansen",
                     "Global Forest Change", "Landsat", "raster", "H3"],
        "license": "CC-BY-4.0",
        "version": EDITION,
        "sci:doi": "10.1126/science.1244693",
        "sci:citation": CITATION,
        "created": now,
        "updated": now,
        "providers": [
            {"name": "University of Maryland, Department of Geographical Sciences (Hansen et al.)",
             "roles": ["producer", "licensor"], "url": LANDING},
            {"name": "Google", "roles": ["host"],
             "url": "https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/"},
            {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"],
             "url": "https://github.com/boettiger-lab/data-workflows"},
        ],
        "extent": {
            "spatial": {"bbox": [BBOX]},
            "temporal": {"interval": [["2000-01-01T00:00:00Z", "2025-12-31T23:59:59Z"]]},
        },
        "table:columns": COLUMNS,
        "renders": {
            "tree-cover-2000": {
                "title": "Tree canopy cover in 2000 (percent)",
                "assets": ["tree-cover-2000-cog"], "nodata": 255,
                "colormap_name": "greens", "rescale": [[0, 100]],
            },
            "loss-year": {
                "title": "Year of tree cover loss, 2001 (yellow) to 2025 (dark red)",
                "assets": ["loss-year-cog"], "resampling": "nearest", "nodata": 255,
                "colormap": {str(y): f"#{c}" for y, c in YEAR_COLOURS.items()},
            },
        },
        "assets": {
            "loss-year-cog": {
                "href": f"{BASE}/{DATASET}/loss-year-cog.tif",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "title": "Loss year, 30 m cloud-optimised GeoTIFF (EPSG:4326)",
                "description": "Year each 30 metre pixel lost its tree cover, as a code: 0 for no "
                    "loss, 1 to 25 for 2001 to 2025, 254 for permanent water and 255 for no data. "
                    "Overviews use nearest-neighbour resampling, so zoomed-out views show real codes. "
                    "The default render colours only the loss years and leaves no-loss land and "
                    "water clear; the class colours run from light yellow (2001) to dark red (2025) "
                    "along the ColorBrewer yellow-orange-red ramp, chosen here.",
                "roles": ["data"],
                "created": created(ly),
                "file:size": ly["Size"],
                "raster:bands": [{"name": "loss_year", "data_type": "uint8", "nodata": 255,
                                  "spatial_resolution": 30, "classification:classes": classes}],
            },
            "loss-year-hex": {
                "href": f"{BASE}/{DATASET}/loss-year/hex/h0=*/data_0.parquet",
                "type": "application/vnd.apache.parquet",
                "title": "Loss year, H3 hexagons (share of each cell lost per year, resolution 8)",
                "description": LOSS_HEX_DESC,
                "roles": ["data"],
                "created": hex_created(objects, "loss-year"),
                "h3:native_resolution": 8,
                "h3:parent_resolutions": [0],
                "table:columns": [{"name": "loss_year", "type": "int32"},
                                  {"name": "frac", "type": "double"},
                                  {"name": "h8", "type": "uint64"},
                                  {"name": "h0", "type": "int64"}],
            },
            "tree-cover-2000-cog": {
                "href": f"{BASE}/{DATASET}/tree-cover-2000-cog.tif",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "title": "Tree cover 2000, 30 m cloud-optimised GeoTIFF (EPSG:4326)",
                "description": "Tree canopy cover in 2000, in percent (0 to 100), for each 30 metre "
                    "pixel of mapped land; 255 for water and no data. Overviews use average "
                    "resampling.",
                "roles": ["data"],
                "created": created(tc),
                "file:size": tc["Size"],
                "raster:bands": [{"name": "tree_cover_2000", "data_type": "uint8", "nodata": 255,
                                  "unit": "percent", "spatial_resolution": 30}],
            },
            "tree-cover-2000-hex": {
                "href": f"{BASE}/{DATASET}/tree-cover-2000/hex/h0=*/data_0.parquet",
                "type": "application/vnd.apache.parquet",
                "title": "Tree cover 2000, H3 hexagons (mean percent, resolution 8)",
                "description": TREE_HEX_DESC,
                "roles": ["data"],
                "created": hex_created(objects, "tree-cover-2000"),
                "h3:native_resolution": 8,
                "h3:parent_resolutions": [0],
                "table:columns": [{"name": "tree_cover_2000", "type": "double"},
                                  {"name": "h8", "type": "uint64"},
                                  {"name": "h0", "type": "int64"}],
            },
            # Drawn by scripts/thumbnail.py from the tree-cover-2000 render (the loss-year render
            # is too sparse to read at 512 px) and uploaded by the publish job.
            "thumbnail": {
                "href": f"{BASE}/{DATASET}/thumbnail.png",
                "type": "image/png",
                "roles": ["thumbnail"],
                "title": "Thumbnail",
                "description": "Preview drawn from the collection's render tree-cover-2000.",
            },
        },
        "links": [
            {"rel": "self", "href": SELF, "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": PARENT, "type": "application/json"},
            {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/",
             "type": "text/html", "title": "Creative Commons Attribution 4.0"},
            {"rel": "about", "href": LANDING, "type": "text/html",
             "title": f"Global Forest Change {EDITION} (download page and user notes)"},
            {"rel": "cite-as", "href": "https://doi.org/10.1126/science.1244693",
             "type": "text/html"},
            {"rel": "describedby", "href": f"{BASE}/{DATASET}/README.md", "type": "text/markdown"},
        ],
    }


def bucket_catalog():
    return {
        "type": "Catalog",
        "stac_version": "1.1.0",
        "id": "forest-change",
        "title": "Forest change",
        "description": "Global forest change layers republished by the Boettiger Lab. Child "
                       "collections: tree cover loss 2001-2025 and tree cover 2000 from Hansen "
                       "Global Forest Change (`tree-cover-loss`). See each child for its licence.",
        "keywords": ["forest", "tree cover", "tree cover loss", "deforestation"],
        "links": [
            {"rel": "self", "href": PARENT, "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": ROOT, "type": "application/json"},
            {"rel": "child", "href": SELF, "type": "application/json",
             "title": "Tree cover loss 2001-2025 and tree cover 2000 (Hansen Global Forest Change v1.13)"},
        ],
    }


README = f"""# Tree cover loss 2001-2025 and tree cover 2000 (Hansen Global Forest Change v1.13)

{DESCRIPTION}

## Files

| file | what |
|---|---|
| `{BASE}/{DATASET}/loss-year-cog.tif` | loss year, 30 m COG (0 no loss, 1-25 = 2001-2025, 254 water, 255 no data) |
| `{BASE}/{DATASET}/tree-cover-2000-cog.tif` | tree cover 2000, 30 m COG (percent, 255 no data) |
| `s3://{BUCKET}/{DATASET}/loss-year/hex/h0=*/data_0.parquet` | loss year, H3 resolution 8: one row per (cell, class) with `frac` |
| `s3://{BUCKET}/{DATASET}/tree-cover-2000/hex/h0=*/data_0.parquet` | tree cover 2000, H3 resolution 8: one row per cell |

## DuckDB: tree cover loss per year in one area

```sql
INSTALL h3 FROM community; LOAD h3; INSTALL httpfs; LOAD httpfs;
SET s3_endpoint = 's3-west.nrp-nautilus.io'; SET s3_url_style = 'path';

-- area lost each year (km2) in the resolution-0 cell over central Peru
SELECT 2000 + loss_year AS year,
       SUM(frac * h3_cell_area(h8, 'km^2')) AS loss_km2
FROM read_parquet('s3://{BUCKET}/{DATASET}/loss-year/hex/h0=*/data_0.parquet', hive_partitioning = true)
WHERE h0 = 578994027093819391 AND loss_year BETWEEN 1 AND 25
GROUP BY 1 ORDER BY 1;
```

## Map tiles (TiTiler)

```
https://titiler.nrp-nautilus.io/cog/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png?url={BASE}/{DATASET}/tree-cover-2000-cog.tif&colormap_name=greens&rescale=0,100
```
"""


def main():
    out, objects_path = sys.argv[1:3]
    objects = json.load(open(objects_path))
    os.makedirs(f"{out}/{DATASET}", exist_ok=True)
    with open(f"{out}/{DATASET}/stac-collection.json", "w") as f:
        json.dump(v2_classes(collection(objects)), f, indent=2, ensure_ascii=False)
    with open(f"{out}/{DATASET}/README.md", "w") as f:
        f.write(README)
    with open(f"{out}/stac-collection.json", "w") as f:
        json.dump(bucket_catalog(), f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
