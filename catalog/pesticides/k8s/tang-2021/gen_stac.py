#!/usr/bin/env python3
"""Emit the tang-2021 collection, the new public-pesticides bucket collection, their READMEs
and the patched root catalog to an output directory for upload (AGENTS.md Hard Boundary 1:
this repo never contains STAC JSON or README files). Scope: data-workflows #865.

    gen_stac.py <out_dir> <objects.json> <root_catalog.json> <access_date>

objects.json is `rclone lsjson --hash -R nrp:public-pesticides/`, taken in the publish job,
so sizes, checksums and created times are read from the objects, not transcribed (#417).
root_catalog.json is the live root catalog; it is PATCHED (one child link appended if absent),
never rewritten, so fields this script does not know about survive.

Row counts and value ranges below were measured on the published hex with the duckdb-geo MCP
after the build (2026-11-06) and are stated as measurements.
"""
import copy
import json
import os
import sys

BUCKET = "public-pesticides"
DATASET = "tang-2021"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
PARENT = f"{BASE}/stac-collection.json"
SELF = f"{BASE}/{DATASET}/stac-collection.json"

DATA_DOI = "https://doi.org/10.6084/m9.figshare.10302218"
PAPER_DOI = "https://doi.org/10.1038/s41561-021-00712-5"
FIGSHARE_API = "https://api.figshare.com/v2/articles/10302218"
CITE_DATA = ("Tang, F.H.M., Lenzen, M., McBratney, A. & Maggi, F. (2021). Global pesticide "
             "pollution risk data sets. Figshare, version 1. "
             "https://doi.org/10.6084/m9.figshare.10302218")
CITE_PAPER = ("Tang, F.H.M., Lenzen, M., McBratney, A. & Maggi, F. (2021). Risk of pesticide "
              "pollution at the global scale. Nature Geoscience 14, 206–210. "
              "https://doi.org/10.1038/s41561-021-00712-5")

# Source grid, from gdalinfo on every upstream file (identical across the five).
BBOX = [-178.9167, -56.0425, 179.9167, 84.0408]

COMMON_CELLS = 377_432  # risk, active-ingredient, regions-of-concern, certainty: identical cell sets

NOT_FARMLAND = (
    "Only agricultural land carries a value. Upstream codes non-agricultural land as −1 and "
    "water or missing data as −2; both are nodata here, so a cell with no row is water, "
    "non-agricultural land or missing data, not a place with zero risk."
)

# key -> per-layer facts. `cells` / `vmin` / `vmax` are measured on the published hex.
LAYERS = {
    "risk-score": {
        "file": "Global_pesticide_risk_scores.tif",
        "col": "risk_score", "reducer": "mean", "dtype": "float64",
        "title": "Pesticide pollution risk score",
        "unit": "unitless",
        "cells": COMMON_CELLS, "vmin": 0.0, "vmax": 5.992,
        "col_desc": (
            "Pesticide pollution risk score of the agricultural land in the cell, unitless, "
            "the area-weighted mean of the source pixels (source range 0 to 6.1). It describes "
            "how far environmental residues of 92 active ingredients exceed their no-effect "
            "concentrations; higher means greater risk."),
        "about": ("Risk score of agricultural land to pesticide pollution from 92 active "
                  "ingredients."),
    },
    "active-ingredient-count": {
        "file": "Global_active_ingredient_counts.tif",
        "col": "active_ingredient_count", "reducer": "max", "dtype": "float32",
        "title": "Number of active ingredients posing pollution risk",
        "unit": "count of active ingredients",
        "cells": COMMON_CELLS, "vmin": 0.0, "vmax": 43.0,
        "col_desc": (
            "Number of pesticide active ingredients posing a pollution risk in the cell, the "
            "largest count among the source pixels in the cell (source range 0 to 43). A whole "
            "number stored as a double. It measures exposure to pesticide mixtures."),
        "about": ("Number of active ingredients posing a pollution risk to agricultural land, "
                  "a measure of exposure to pesticide mixtures."),
    },
    "regions-of-concern": {
        "file": "Global_regions_of_concern.tif",
        "col": "concern_level", "reducer": "mode", "dtype": "float64",
        "title": "Regions of concern",
        "unit": "concern level",
        "cells": COMMON_CELLS, "vmin": 1.0, "vmax": 4.0,
        "col_desc": (
            "Concern level, the most common source class in the cell. Values: 1=highest "
            "concern, 2=concern level 2, 3=concern level 3, 4=no concern. Upstream defines "
            "only the two ends of the scale; levels 2 and 3 lie between them in order. Codes "
            "are stored as doubles."),
        "values": [1, 2, 3, 4],
        "about": ("Regions of concern, combining pesticide pollution risk with water scarcity "
                  "and biodiversity, on a four-level scale from 1 (highest concern) to 4 "
                  "(no concern)."),
    },
    "quality-index": {
        "file": "Quality_index.tif",
        "col": "quality_index", "reducer": "mean", "dtype": "float32",
        "title": "Data quality index",
        "unit": "unitless index, 0 to 1",
        # Masked rebuild: a subset of the common cells, less 14 with no upstream quality value.
        "cells": 377_418, "vmin": 0.403, "vmax": 0.889,
        "col_desc": (
            "Data quality index of the estimates in the cell, from 0 (low quality) to 1 (high "
            "quality), the area-weighted mean of the source pixels."),
        "about": "Quality of the estimates, from 0 (low) to 1 (high).",
    },
    "certainty-index": {
        "file": "Certainty_index.tif",
        "col": "certainty_index", "reducer": "mean", "dtype": "float32",
        "title": "Data certainty index",
        "unit": "unitless index, 0 to 1",
        "cells": COMMON_CELLS, "vmin": 0.322, "vmax": 1.0,
        "col_desc": (
            "Data certainty index from the parameter sensitivity analysis, from 0 (low "
            "certainty) to 1 (high certainty), the area-weighted mean of the source pixels."),
        "about": "Certainty of the estimates from a parameter sensitivity analysis, 0 to 1.",
    },
}

REDUCER_NOTE = {
    "mean": ("Each value is the area-weighted mean of the source pixels in the cell, so it is "
             "a per-area quantity; summing it across cells has no meaning. Average it, "
             "weighted by cell area, to combine cells."),
    "max": ("Each value is the largest source pixel value in the cell (the `max` reducer), so "
            "local peaks are kept. To roll up to a coarser cell take MAX again; averaging or "
            "summing counts of active ingredients double-counts ingredients shared between "
            "cells."),
    "mode": ("Each value is the most common source class in the cell (the `mode` reducer); the "
             "mix of classes within the cell is not kept. Count cells per class to compare "
             "areas; never average the codes."),
}

COLORS = {1: "B2182B", 2: "EF8A62", 3: "FDDBC7", 4: "D1E5F0"}
CLASSES = [
    {"value": 1, "name": "Highest concern", "description": "Area of highest concern.",
     "color_hint": COLORS[1]},
    {"value": 2, "name": "Concern level 2",
     "description": "Second level of concern, between highest concern and no concern.",
     "color_hint": COLORS[2]},
    {"value": 3, "name": "Concern level 3",
     "description": "Third level of concern, between highest concern and no concern.",
     "color_hint": COLORS[3]},
    {"value": 4, "name": "No concern", "description": "Area of no concern.",
     "color_hint": COLORS[4]},
]


def objects(path):
    rows = json.load(open(path))
    return {r["Path"]: r for r in rows if not r.get("IsDir")}


def created(objs, key):
    t = objs[key]["ModTime"]
    return t[:19] + "Z"


def h3_cols(native):
    return [
        {"name": f"h{native}", "type": "uint64",
         "description": f"H3 cell ID at resolution {native}, the native resolution; one row "
                        f"per cell."},
        {"name": "h0", "type": "int64",
         "description": "H3 cell ID at resolution 0, used as the partition key for "
                        "hive-partitioned reads."},
    ]


def build_collection(objs, access_date):
    raw = []
    for name in ["Global_pesticide_risk_scores.tif", "Global_active_ingredient_counts.tif",
                 "Global_regions_of_concern.tif", "Quality_index.tif", "Certainty_index.tif",
                 "Metadata.pdf", "Code.zip"]:
        o = objs[f"raw/{name}"]
        raw.append(f"`raw/{name}` ({o['Size']:,} bytes, MD5 {o['Hashes']['md5']})")
    masked = objs["raw/derived/Quality_index_masked.tif"]

    assets = {}
    for key, L in LAYERS.items():
        cog_key = f"{DATASET}/{key}-cog.tif"
        band = {"name": L["col"], "data_type": L["dtype"], "nodata": -2,
                "spatial_resolution": 9265, "unit": L["unit"]}
        cog_desc = (f"{L['about']} WGS84 cloud-optimized GeoTIFF on the source grid "
                    f"(5 arc-minutes, about 9 km at the equator); pixel values are unchanged "
                    f"from upstream. Nodata is −2: upstream's −1 (non-agricultural land) "
                    f"and −2 (water or no data) are both stored as −2 here.")
        if L["reducer"] == "mode":
            band["classification:classes"] = CLASSES
            cog_desc += (" Overviews use the most common class, so zoomed-out views show "
                         "real classes. Upstream publishes no palette; the colours here run "
                         "from red (highest concern) to pale blue (no concern).")
        else:
            cog_desc += " Overviews are averaged, so zoomed-out views smooth local peaks."
        if key == "quality-index":
            cog_desc += QUALITY_MASK_NOTE
        assets[f"{DATASET}-{key}-cog"] = {
            "href": f"{BASE}/{cog_key}",
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "title": f"{L['title']}: WGS84 COG",
            "description": cog_desc,
            "roles": ["data"],
            "created": created(objs, cog_key),
            "raster:bands": [band],
        }

        hex_desc = (
            f"{L['about']} H3 hex parquet at native resolution 5 with parent 0: one row per "
            f"cell that holds agricultural land ({L['cells']:,} rows), values "
            f"{L['vmin']:g} to {L['vmax']:g}. {REDUCER_NOTE[L['reducer']]} There is no "
            f"resolution 8 (`h8`) column: the source pixel is about 9 km, coarser than a "
            f"resolution 8 cell, so resolution 5 is the finest the data supports. To join "
            f"finer catalog data, roll it up to `h5` (for example with "
            f"`h3_cell_to_parent(h8, 5)`). {NOT_FARMLAND}")
        if key == "quality-index":
            hex_desc += QUALITY_MASK_NOTE
        col = {"name": L["col"], "type": "double", "description": L["col_desc"]}
        if "values" in L:
            col["values"] = L["values"]
        first_hex = min(k for k in objs if k.startswith(f"{DATASET}/{key}/hex/"))
        assets[f"{DATASET}-{key}-hex"] = {
            "href": f"{BASE}/{DATASET}/{key}/hex/h0=*/data_0.parquet",
            "type": "application/x-parquet",
            "title": f"{L['title']}: H3 hex (resolution 5)",
            "description": hex_desc,
            "roles": ["data"],
            "created": created(objs, first_hex),
            "h3:native_resolution": 5,
            "h3:parent_resolutions": [0],
            "table:columns": [col] + h3_cols(5),
        }

    assets[f"{DATASET}-metadata"] = {
        "href": f"{BASE}/{DATASET}/Metadata.pdf",
        "type": "application/pdf",
        "title": "Upstream metadata sheet (Metadata.pdf)",
        "description": ("The authors' one-page metadata sheet for the five maps: units, value "
                        "ranges, the meaning of −1 and −2, the recommended citation and the "
                        "use agreement. Copied unchanged from the Figshare record."),
        "roles": ["metadata"],
    }

    description = f"""Global maps of the risk of pesticide pollution on agricultural land, from Tang, Lenzen, McBratney and Maggi (2021, Nature Geoscience). The authors combined a global database of pesticide applications with a spatially explicit environmental model to estimate where residues of 92 active ingredients exceed their no-effect concentrations. They found 64% of global agricultural land at risk of pollution by more than one active ingredient.

Five layers, each published as a WGS84 cloud-optimized GeoTIFF on the source grid and as H3 hex parquet at native resolution 5 with parent 0:

- **Risk score** (`risk_score`): unitless risk of pollution, 0 to 6.1.
- **Active ingredient count** (`active_ingredient_count`): how many active ingredients pose a risk, 0 to 43.
- **Regions of concern** (`concern_level`): 1 = highest concern to 4 = no concern, combining pollution risk with water scarcity and biodiversity.
- **Data quality index** (`quality_index`) and **data certainty index** (`certainty_index`), each 0 to 1, describe how much to trust the estimates.

**Coverage.** Global agricultural land, 56°S to 84°N, at 5 arc-minutes (about 9 km at the equator). {NOT_FARMLAND} The risk score, active ingredient count, regions of concern and certainty layers cover exactly the same {COMMON_CELLS:,} cells, so they join on `h5` one to one.

**Resolution.** Native H3 resolution is 5, matched to the 9 km source pixel. There is no resolution 8 (`h8`) column, because the data is coarser than resolution 8. Join finer catalog layers by rolling them up to `h5`.

**Reference year.** The public metadata and the paper's abstract do not state the year the maps represent, so no temporal extent is asserted here. The paper draws on pesticide application rates from PEST-CHEMGRIDS (Maggi et al. 2019).

**Data quality index cleaning.** {QUALITY_MASK_NOTE.strip()}

**Licence and citation.** Released under CC BY 4.0 on Figshare. The authors' use agreement asks that the data be cited appropriately. Cite both the paper and the data set:

- {CITE_PAPER}
- {CITE_DATA}

**Provenance.** Figshare article 10302218, version 1 (published 2021-03-08), retrieved {access_date}. The staged upstream files in `s3://{BUCKET}/raw/`, each matching the MD5 Figshare publishes: {"; ".join(raw)}. The masked quality index used for the build is `raw/derived/Quality_index_masked.tif` ({masked['Size']:,} bytes, MD5 {masked['Hashes']['md5']})."""

    return {
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/classification/v2.0.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
            "https://stac-extensions.github.io/version/v1.2.0/schema.json",
        ],
        "type": "Collection",
        "id": DATASET,
        "title": "Global pesticide pollution risk (Tang et al. 2021)",
        "description": description,
        "license": "CC-BY-4.0",
        "version": "1",
        "sci:doi": "10.6084/m9.figshare.10302218",
        "sci:citation": f"{CITE_DATA} Accessed {access_date}.",
        "sci:publications": [{"doi": "10.1038/s41561-021-00712-5", "citation": CITE_PAPER}],
        "keywords": ["pesticides", "pollution", "agriculture", "risk", "active ingredients",
                     "water scarcity", "biodiversity", "global", "H3"],
        "extent": {
            "spatial": {"bbox": [BBOX]},
            "temporal": {"interval": [[None, None]]},
        },
        "created": min(a["created"] for a in assets.values() if "created" in a),
        "updated": max(a["created"] for a in assets.values() if "created" in a),
        "providers": [
            {"name": "Fiona H.M. Tang, Manfred Lenzen, Alexander McBratney and Federico Maggi, "
                     "The University of Sydney",
             "roles": ["producer", "licensor"], "url": PAPER_DOI},
            {"name": "Figshare", "roles": ["host"], "url": DATA_DOI},
            {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"],
             "url": f"{BASE}/"},
        ],
        "links": [
            {"rel": "self", "href": SELF, "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": PARENT, "type": "application/json"},
            {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/",
             "type": "text/html", "title": "Creative Commons Attribution 4.0 International"},
            {"rel": "cite-as", "href": DATA_DOI, "title": CITE_DATA},
            {"rel": "describedby", "href": PAPER_DOI, "type": "text/html", "title": CITE_PAPER},
            {"rel": "about", "href": DATA_DOI, "type": "text/html",
             "title": "Figshare landing page"},
            {"rel": "via", "href": FIGSHARE_API, "type": "application/json",
             "title": "Figshare record (file list, checksums, licence)"},
        ],
        "assets": assets,
    }


QUALITY_MASK_NOTE = (
    " The upstream quality index documents a range of 0 to 1 but contains 2,408 pixels "
    "valued −1.12 to −1.31, all of them water or no data in the other four layers; those "
    "pixels are treated as nodata here. A further 49 agricultural pixels have no quality "
    "value upstream, so a few cells carry the other layers but not this one.")


def build_parent(objs):
    return {
        "stac_version": "1.0.0",
        "type": "Collection",
        "id": "public-pesticides",
        "title": "Pesticides",
        "description": ("Data sets on pesticide use and pesticide pollution, published as "
                        "cloud-optimized GeoTIFF and H3 hex parquet. Each child collection "
                        "carries its own licence; check there rather than assuming a "
                        "bucket-wide term."),
        "license": "various",
        "keywords": ["pesticides", "pollution", "agriculture"],
        "extent": {"spatial": {"bbox": [BBOX]}, "temporal": {"interval": [[None, None]]}},
        "providers": [{"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"],
                       "url": f"{BASE}/"}],
        "links": [
            {"rel": "self", "href": PARENT, "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": ROOT, "type": "application/json"},
            {"rel": "child", "id": DATASET, "href": SELF, "type": "application/json",
             "title": "Global pesticide pollution risk (Tang et al. 2021)"},
        ],
    }


def patch_root(root):
    root = copy.deepcopy(root)
    if not any(l.get("href") == PARENT for l in root["links"]):
        root["links"].append({"rel": "child", "id": "public-pesticides", "href": PARENT,
                              "type": "application/json", "title": "Pesticides"})
    return root


def readme(coll):
    rows = "\n".join(
        f"| `{k}` | `{L['col']}` | `{L['reducer']}` | [COG]({BASE}/{DATASET}/{k}-cog.tif) "
        f"| `{BASE}/{DATASET}/{k}/hex/h0=*/data_0.parquet` |"
        for k, L in LAYERS.items())
    return f"""# Global pesticide pollution risk (Tang et al. 2021)

{coll['description']}

## Layers

| layer | column | H3 reducer | COG | hex parquet |
|---|---|---|---|---|
{rows}

## Query with DuckDB

```sql
INSTALL h3 FROM community; LOAD h3; INSTALL httpfs; LOAD httpfs;
-- Share of agricultural cells in each concern level
SELECT concern_level, COUNT(*) AS cells,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM read_parquet('{BASE}/{DATASET}/regions-of-concern/hex/h0=*/data_0.parquet')
GROUP BY concern_level ORDER BY concern_level;

-- Join two layers on the resolution 5 cell
SELECT r.h5, r.risk_score, a.active_ingredient_count
FROM read_parquet('{BASE}/{DATASET}/risk-score/hex/h0=*/data_0.parquet') r
JOIN read_parquet('{BASE}/{DATASET}/active-ingredient-count/hex/h0=*/data_0.parquet') a USING (h5)
ORDER BY r.risk_score DESC LIMIT 10;
```

## Map with MapLibre GL JS

These are rasters, so there is no vector `source-layer`; serve the COG through a tile server
such as titiler:

```js
map.addSource('pesticide-risk', {{
  type: 'raster',
  tiles: ['https://titiler.nrp-nautilus.io/cog/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png'
        + '?url={BASE}/{DATASET}/risk-score-cog.tif&rescale=0,6&colormap_name=magma'],
  tileSize: 256
}});
map.addLayer({{ id: 'pesticide-risk', type: 'raster', source: 'pesticide-risk' }});
```

## Licence and citation

CC BY 4.0. Cite both:

- {CITE_PAPER}
- {CITE_DATA}
"""


def main():
    out, objs_path, root_path, access_date = sys.argv[1:5]
    objs = objects(objs_path)
    coll = build_collection(objs, access_date)
    os.makedirs(f"{out}/{DATASET}", exist_ok=True)
    json.dump(coll, open(f"{out}/{DATASET}/stac-collection.json", "w"), indent=2,
              ensure_ascii=False)
    open(f"{out}/{DATASET}/README.md", "w").write(readme(coll))
    json.dump(build_parent(objs), open(f"{out}/stac-collection.json", "w"), indent=2,
              ensure_ascii=False)
    open(f"{out}/README.md", "w").write(
        "# Pesticides\n\nPesticide use and pollution data sets. Collections:\n\n"
        f"- [Global pesticide pollution risk (Tang et al. 2021)]({BASE}/{DATASET}/README.md)\n")
    root = json.load(open(root_path))
    json.dump(patch_root(root), open(f"{out}/catalog.json", "w"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
