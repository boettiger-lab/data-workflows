#!/usr/bin/env python3
"""Emit the invest-peru-2019 carbon collection, the invest-peru-2019/habitat-quality collection
(provisional) and their READMEs, and the public-ncp bucket collection patched with a child link
to each, to an output directory for upload (AGENTS.md Hard Boundary 1: this repo never contains
STAC JSON or README files). Scope: data-workflows #882.

    gen_stac.py <out_dir> <objects.json> <parent_collection.json>

objects.json is `rclone lsjson --hash -R nrp:public-ncp/invest-peru-2019/ nrp:public-ncp/raw/`
merged by the publish job, so sizes, checksums and created times are read from the objects,
not transcribed (#417). parent_collection.json is the live public-ncp collection; it is
PATCHED (one child link appended if absent), never rewritten.

Measured, 2026-11-10 (carbon) and 2026-11-12 (habitat quality):
- Hex row counts and value ranges from the parquet footers (row-group statistics) of the four
  h0 partitions of each layer: 10,769,285 rows each, no nulls; total 0 to 230.3, biomass 0 to
  176.2 Mg C/ha.
- Peru totals, pixel count and cocoa pixel count from the step 2 job log and report.json
  (s3://public-ncp/raw/derived/invest-peru-2019/carbon/report.json).
- Habitat quality hex (MCP): 10,769,285 rows per layer, no nulls; quality 0 to 1 (median 0.999),
  degradation 0 to 0.599 (median 0, 90th pct 0.128, 99th pct 0.283). The 100 m degradation COG
  reaches 0.7218 and k = 0.36092 (hq-1-invest report.json).
"""
import copy
import json
import os
import sys

BUCKET = "public-ncp"
DATASET = "invest-peru-2019"
S3 = "https://s3-west.nrp-nautilus.io"
BASE = f"{S3}/{BUCKET}"
ROOT = f"{S3}/public-data/stac/catalog.json"
PARENT = f"{BASE}/stac-collection.json"
SELF = f"{BASE}/{DATASET}/stac-collection.json"
TITLE = "InVEST carbon storage, Peru"

# COG extent (gdalinfo), = the GAUL 2015 Peru footprint on the CGLS-LC100 grid.
BBOX = [-81.3879, -18.4147, -68.6171, 0.0466]
H0 = [578290339652042751, 578923658349641727, 578994027093819391, 579627345791418367]
HEX_ROWS = 10_769_285
NATCAP_INVEST = "3.20.2"
PIXELS = 108_199_227
COCOA_PIXELS = 268_804

CGLS = f"{S3}/public-land-cover/cgls-lc100-2019/stac-collection.json"
FDAP = f"{S3}/public-commodities/fdap-2025b/cocoa-peru-2024/stac-collection.json"
GEZ_LANDING = "https://data.apps.fao.org/catalog/dataset/2fb209d0-fd34-4e5e-a3d8-a13c241eb61b"
GEZ_ACCESS = "2026-11-06"
INVEST = "https://naturalcapitalalliance.stanford.edu/invest/carbon"
CITE_INVEST = (f"Natural Capital Alliance (Stanford University). InVEST {NATCAP_INVEST}: "
               "Carbon Storage and Sequestration model. https://github.com/natcap/invest")
CITE_IPCC = ("IPCC (2019). 2019 Refinement to the 2006 IPCC Guidelines for National Greenhouse "
             "Gas Inventories, Volume 4: Agriculture, Forestry and Other Land Use; and IPCC "
             "(2006), 2006 IPCC Guidelines, Volume 4.")
CITE_CGLS = ("Buchhorn, M., Lesiv, M., Tsendbazar, N-E., Herold, M., Bertels, L., Smets, B. "
             "(2020). Copernicus Global Land Cover Layers — Collection 2. Remote Sensing 12(6), "
             "1044. doi:10.3390/rs12061044")
CITE_FDAP = ("Forest Data Partnership (2026). Community models 2025b, cocoa 2024. Produced by "
             "Google for the Forest Data Partnership.")
CITE_GEZ = "FAO (2012). Global Ecological Zones, second edition (2010). FAO Map Catalog."

MEAN_NOTE = (
    "Each value is a carbon density in megagrams of carbon per hectare (Mg C/ha), the "
    "area-weighted mean of the 100 m model pixels in the cell. Summing it across cells has no "
    "meaning: average it weighted by cell area, or multiply by cell area to get a stock.")

LAYERS = {
    "carbon-total": {
        "col": "total_carbon", "vmax": 230.3, "total_tg": 18764.4,
        "title": "Total carbon storage",
        "render": {"colormap_name": "ylgn", "rescale": [[0, 230]]},
        "about": ("Total carbon stored per hectare: above-ground biomass, below-ground "
                  "biomass, dead organic matter and soil organic carbon (0–30 cm)."),
        "col_desc": ("Total carbon density in the cell, in Mg C/ha: above-ground and "
                     "below-ground biomass, dead organic matter and soil organic carbon "
                     "(0–30 cm), the area-weighted mean of the 100 m model pixels."),
    },
    "carbon-biomass": {
        "col": "biomass_carbon", "vmax": 176.2, "total_tg": 12777.3,
        "title": "Biomass carbon storage",
        "render": {"colormap_name": "ylgn", "rescale": [[0, 180]]},
        "about": ("Carbon stored per hectare in living biomass only: above-ground plus "
                  "below-ground. Soil and dead organic matter are left out, so soil "
                  "assumptions do not drive comparisons between places."),
        "col_desc": ("Living biomass carbon density in the cell, in Mg C/ha: above-ground plus "
                     "below-ground biomass, without soil or dead organic matter, the "
                     "area-weighted mean of the 100 m model pixels."),
    },
}

H3_COLS = [
    {"name": "h9", "type": "uint64",
     "description": "H3 cell ID at resolution 9, the native resolution; one row per cell."},
    {"name": "h8", "type": "uint64", "description": "H3 cell ID at resolution 8, parent of h9."},
    {"name": "h0", "type": "uint64",
     "description": "H3 cell ID at resolution 0, used as the partition key for "
                    "hive-partitioned reads."},
]


def objects(path):
    return {r["Path"]: r for r in json.load(open(path)) if not r.get("IsDir")}


def created(objs, key):
    return objs[key]["ModTime"][:19] + "Z"


def build_collection(objs):
    gez = objs["raw/fao-gez-2010/gez2010.zip"]
    pools_key = f"{DATASET}/carbon_pools.csv"
    assets, renders, dictionary = {}, {}, []
    for key, L in LAYERS.items():
        cog = f"{DATASET}/{key}-cog.tif"
        assets[f"{key}-cog"] = {
            "href": f"{BASE}/{cog}",
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "title": f"{L['title']}, Peru: WGS84 COG (100 m)",
            "description": (f"{L['about']} WGS84 cloud-optimized GeoTIFF on the CGLS-LC100 "
                            f"100 m grid, clipped to Peru, values 0 to {L['vmax']:g} Mg C/ha. "
                            f"Nodata is −9999 (outside Peru)."),
            "roles": ["data"],
            "created": created(objs, cog),
            "raster:bands": [{"name": L["col"], "data_type": "float32", "nodata": -9999,
                              "spatial_resolution": 100, "unit": "Mg C/ha"}],
        }
        renders[key] = {"title": f"{L['title']} (Mg C/ha)", "assets": [f"{key}-cog"],
                        **L["render"]}
        col = {"name": L["col"], "type": "double", "description": L["col_desc"]}
        first_hex = min(k for k in objs if k.startswith(f"{DATASET}/{key}/hex/"))
        assets[f"{key}-hex"] = {
            "href": f"{BASE}/{DATASET}/{key}/hex/h0=*/data_0.parquet",
            "type": "application/x-parquet",
            "title": f"{L['title']}, Peru: H3 hex (resolution 9)",
            "description": (f"{L['about']} H3 hex parquet at native resolution 9 with parents "
                            f"8 and 0: one row per cell in Peru ({HEX_ROWS:,} rows), values 0 "
                            f"to {L['vmax']:g} Mg C/ha. {MEAN_NOTE}"),
            "roles": ["data"],
            "created": created(objs, first_hex),
            "h3:native_resolution": 9,
            "h3:parent_resolutions": [8, 0],
            "table:columns": [{"name": c["name"], "type": c["type"]} for c in [col] + H3_COLS],
        }
        for c in [col] + H3_COLS:
            if c["name"] not in {d["name"] for d in dictionary}:
                dictionary.append(c)

    assets["carbon-pools-table"] = {
        "href": f"{BASE}/{pools_key}",
        "type": "text/csv",
        "title": "Carbon pools table used by the model (CSV)",
        "description": (
            "The carbon pools table passed to InVEST: one row per land-use code, with "
            "above-ground (c_above), below-ground (c_below), soil (c_soil) and dead organic "
            "matter (c_dead) carbon in Mg C/ha. Each code is the ecological zone times 1000 "
            "plus the land-cover class: zones 11 tropical rainforest, 12 tropical moist forest, "
            "13 tropical dry forest, 14 tropical shrubland, 15 tropical desert, 16 tropical "
            "mountain system; classes are CGLS-LC100 codes, plus 250 for cocoa. For example "
            "11112 is closed evergreen broadleaf forest in the rainforest zone and 16250 is "
            "cocoa in the mountain zone."),
        "roles": ["metadata"],
        "created": created(objs, pools_key),
    }

    description = f"""Carbon stored on the land across Peru, modelled with the InVEST Carbon Storage and Sequestration model ({NATCAP_INVEST}) at 100 m. Built for cocoa supply-chain decision support: finding areas where carbon could be gained, for example by shaded agroforestry, and screening candidate areas for further study.

Two layers, each as a WGS84 cloud-optimized GeoTIFF and as H3 hex parquet at native resolution 9 with parents 8 and 0:

- **Total carbon** (`total_carbon`): above-ground and below-ground biomass, dead organic matter and soil organic carbon (0–30 cm), 0 to 230.3 Mg C/ha. Peru total about {LAYERS['carbon-total']['total_tg'] / 1000:.1f} Pg C.
- **Biomass carbon** (`biomass_carbon`): above-ground plus below-ground living biomass only, 0 to 176.2 Mg C/ha. Peru total about {LAYERS['carbon-biomass']['total_tg'] / 1000:.1f} Pg C. Use this layer to compare places without soil assumptions dominating.

Values are densities in megagrams of carbon per hectare (Mg C/ha). To turn them into a stock, multiply by area; never add densities across cells.

**Use these as screening layers.** They rank areas against each other. They are not farm-level estimates: a smallholder cocoa farm covers only a few 100 m pixels, and every pixel of a land-cover class in an ecological zone receives the same default value. Confirm any site-level claim with field measurement.

**Absolute totals are likely high.** Land cover does not say which forest is primary, so every closed-forest pixel takes the default stock for primary forest and every open-forest pixel the stock for secondary forest older than 20 years. Where closed forest is degraded or young, the true stock is lower. Comparisons between places are more reliable than the national totals.

**Footprint.** All of Peru, inside the FAO GAUL 2015 country boundary (the boundary the cocoa layer uses), {PIXELS:,} land pixels. The model ran on land cover extended 5 km beyond the border and was then clipped to it.

**How the model was set up.**
- **Land cover:** Copernicus Global Land Cover CGLS-LC100 v3.0.1 for 2019, 100 m. Cocoa from the Forest Data Partnership model 2025b for 2024 (10 m probabilities) was added as its own class: a 100 m pixel became cocoa when more than half of its 10 m sub-pixels had a cocoa probability of 0.5 or more ({COCOA_PIXELS:,} pixels, about 3,240 km²). Scattered cocoa plots smaller than half a pixel are not counted, so the layer holds about 64% of the 10 m cocoa area. The pixels holding the other 36% keep their Copernicus class, mostly forest, so carbon is somewhat overstated in cocoa landscapes. Land cover is from 2019 and cocoa from 2024.
- **Carbon values:** IPCC Tier 1 defaults (2006 Guidelines and 2019 Refinement) for each land-cover class and FAO Global Ecological Zone, listed in the carbon pools table asset. Biomass is converted to carbon with the default fraction 0.47.

**Assumptions.**
- Closed forest is treated as primary forest, open forest as secondary forest older than 20 years.
- Soil carbon uses one soil class per ecological zone: low-activity clay in rainforest, high-activity clay in the mountain, shrubland and dry forest zones, sandy soil in the desert zone. No soil map was used.
- Andean grassland (puna), shrubs, herbaceous wetland and moss take the IPCC tropical grassland values; Tier 1 has no montane or shrub row.
- Cropland holds 5.0 Mg C/ha of biomass, the IPCC stock one year after conversion, used as the standing stock.
- Forest in the desert zone takes dry-forest values.
- Cocoa holds 24.0 Mg C/ha above ground (the average over a 20-year cycle for tropical shaded perennial agroforestry) and none below ground, because IPCC gives no root ratio for perennial crops. The land cover cannot separate full-sun from shaded cocoa; these values are the conservative case.
- Two pixels at the border fall in the tropical moist forest zone and take the rainforest values.
- Built-up land, bare ground, snow and ice, and water hold no carbon.

**Licence and attribution.** CC BY 4.0. These are model outputs built from CC BY 4.0 inputs; credit them as follows.
- {CITE_CGLS}
- {CITE_FDAP}
- {CITE_GEZ}
- {CITE_IPCC}
- {CITE_INVEST}

**Provenance.** Land cover and cocoa were read from this catalog's copies (`public-land-cover/cgls-lc100-2019`, `public-commodities/fdap-2025b/cocoa-peru-2024`). The FAO Global Ecological Zones zip was retrieved {GEZ_ACCESS} from the FAO Map Catalog and staged as `raw/fao-gez-2010/gez2010.zip` ({gez['Size']:,} bytes, MD5 {gez['Hashes']['md5']}). Model run with natcap.invest {NATCAP_INVEST} on 2026-11-10."""

    return {
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
            "https://stac-extensions.github.io/render/v2.0.0/schema.json",
        ],
        "type": "Collection",
        "id": DATASET,
        "title": TITLE,
        "description": description,
        "license": "CC-BY-4.0",
        "sci:citation": (f"Boettiger Lab, UC Berkeley (2026). {TITLE}: InVEST {NATCAP_INVEST} "
                         f"Carbon model outputs, 2019 land cover with 2024 cocoa. {SELF}"),
        "keywords": ["carbon", "carbon storage", "biomass", "InVEST", "cocoa", "cacao",
                     "Peru", "IPCC Tier 1", "ecosystem services", "H3"],
        "extent": {
            "spatial": {"bbox": [BBOX]},
            "temporal": {"interval": [["2019-01-01T00:00:00Z", "2024-12-31T23:59:59Z"]]},
        },
        "created": min(a["created"] for a in assets.values()),
        "updated": max(a["created"] for a in assets.values()),
        "providers": [
            {"name": "Boettiger Lab, UC Berkeley", "roles": ["producer", "processor", "host"],
             "url": f"{BASE}/{DATASET}/"},
            {"name": "Copernicus Global Land Service", "roles": ["licensor"],
             "url": "https://land.copernicus.eu/global/products/lc"},
            {"name": "Forest Data Partnership", "roles": ["licensor"],
             "url": "https://github.com/google/forest-data-partnership"},
            {"name": "FAO", "roles": ["licensor"], "url": GEZ_LANDING},
        ],
        "links": [
            {"rel": "self", "href": SELF, "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": PARENT, "type": "application/json"},
            {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/",
             "type": "text/html", "title": "Creative Commons Attribution 4.0 International"},
            {"rel": "describedby", "href": f"{BASE}/{DATASET}/README.md",
             "type": "text/markdown", "title": "README"},
            {"rel": "about", "href": INVEST, "type": "text/html",
             "title": "InVEST Carbon Storage and Sequestration model"},
            {"rel": "derived_from", "href": CGLS, "type": "application/json",
             "title": "Copernicus Global Land Cover 100 m, 2019"},
            {"rel": "derived_from", "href": FDAP, "type": "application/json",
             "title": "Cocoa probability, Peru 2024 (Forest Data Partnership)"},
            {"rel": "derived_from", "href": GEZ_LANDING, "type": "text/html",
             "title": "FAO Global Ecological Zones, second edition (2010)"},
        ],
        "table:columns": dictionary,
        "renders": renders,
        "assets": assets,
    }


# --- Habitat Quality: its own collection, so "provisional" applies to these layers only -------
# (scope agreed 2026-11-12). Values measured from the hex parquet footers and report.json,
# 2026-11-12; see the module docstring.
HQ_DIR = f"{DATASET}/habitat-quality"
HQ_ID = f"{DATASET}-habitat-quality"
HQ_SELF = f"{BASE}/{HQ_DIR}/stac-collection.json"
HQ_TITLE = "InVEST habitat quality, Peru (provisional)"
HQ_K = 0.36092
HQ_DMAX = 0.7218
HQ_HEX_ROWS = 10_769_285
INVEST_HQ = "https://naturalcapitalalliance.stanford.edu/invest/habitat-quality"
CITE_INVEST_HQ = (f"Natural Capital Alliance (Stanford University). InVEST {NATCAP_INVEST}: "
                  "Habitat Quality model. https://github.com/natcap/invest")
HQ_RUN = "2026-11-12"

HQ_LAYERS = {
    "habitat-quality": {
        "col": "habitat_quality", "vmax": 1.0, "hex_max": 1.0, "title": "Habitat quality",
        "render": {"colormap_name": "bugn", "rescale": [[0, 1]]},
        "about": ("Habitat quality score from 0 to 1: how suitable the land is as habitat, "
                  "lowered by nearby threats. 0 where the land is not habitat (cropland, "
                  "built-up land, bare ground, snow, water)."),
        "col_desc": ("Habitat quality score in the cell, from 0 (not habitat) to 1 (fully "
                     "suitable habitat with no nearby threats), the area-weighted mean of the "
                     "100 m model pixels. A relative score without units."),
    },
    "habitat-degradation": {
        "col": "habitat_degradation", "vmax": HQ_DMAX, "hex_max": 0.599, "title": "Habitat degradation",
        # 99% of hex cells are at or below 0.283; the colour range stops at 0.3 so the gradient
        # around threats stays visible.
        "render": {"colormap_name": "ylorrd", "rescale": [[0, 0.3]]},
        "about": ("Habitat degradation score: the combined pressure that nearby urban land, "
                  "cropland and cocoa put on habitat, weighted by distance and by how "
                  "sensitive each habitat is. 0 where no threat is within reach or the land "
                  "is not habitat."),
        "col_desc": ("Habitat degradation score in the cell, from 0 (no threat within reach) "
                     "upwards, the area-weighted mean of the "
                     "100 m model pixels. A relative score without units, comparable only "
                     "within this collection."),
    },
}

HQ_MEAN_NOTE = (
    "Each value is the area-weighted mean of the 100 m model pixels in the cell. These are "
    "relative scores, so summing them across cells has no meaning: average them, weighted by "
    "cell area, to summarise an area.")


def build_hq_collection(objs):
    assets, renders, dictionary = {}, {}, []
    for key, L in HQ_LAYERS.items():
        cog = f"{DATASET}/{key}-cog.tif"
        assets[f"{key}-cog"] = {
            "href": f"{BASE}/{cog}",
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "title": f"{L['title']}, Peru (provisional): WGS84 COG (100 m)",
            "description": (f"{L['about']} WGS84 cloud-optimized GeoTIFF on the CGLS-LC100 "
                            f"100 m grid, clipped to Peru, values 0 to {L['vmax']:g}. "
                            "Nodata is −9999 (outside Peru)."),
            "roles": ["data"],
            "created": created(objs, cog),
            "raster:bands": [{"name": L["col"], "data_type": "float32", "nodata": -9999,
                              "spatial_resolution": 100}],
        }
        renders[key] = {"title": f"{L['title']} (provisional)", "assets": [f"{key}-cog"],
                        **L["render"]}
        col = {"name": L["col"], "type": "double", "description": L["col_desc"]}
        first_hex = min(k for k in objs if k.startswith(f"{DATASET}/{key}/hex/"))
        assets[f"{key}-hex"] = {
            "href": f"{BASE}/{DATASET}/{key}/hex/h0=*/data_0.parquet",
            "type": "application/x-parquet",
            "title": f"{L['title']}, Peru (provisional): H3 hex (resolution 9)",
            "description": (f"{L['about']} H3 hex parquet at native resolution 9 with parents "
                            f"8 and 0: one row per cell in Peru ({HQ_HEX_ROWS:,} rows), values 0 "
                            f"to {L['hex_max']:g}. {HQ_MEAN_NOTE}"),
            "roles": ["data"],
            "created": created(objs, first_hex),
            "h3:native_resolution": 9,
            "h3:parent_resolutions": [8, 0],
            "table:columns": [{"name": c["name"], "type": c["type"]} for c in [col] + H3_COLS],
        }
        for c in [col] + H3_COLS:
            if c["name"] not in {d["name"] for d in dictionary}:
                dictionary.append(c)
    for key, fname, title, about in (
        ("threats-table", "threats.csv", "Threats table used by the model (CSV)",
         "The threats table passed to InVEST: each threat's maximum distance in metres, its "
         "weight, and how its effect decays with distance."),
        ("sensitivity-table", "sensitivity.csv",
         "Habitat and sensitivity table used by the model (CSV)",
         "The habitat and sensitivity table passed to InVEST: one row per land-use code, with "
         "its habitat suitability (habitat) and its sensitivity to each threat (urban, "
         "cropland, cocoa), all from 0 to 1. Each code is the ecological zone times 1000 plus "
         "the land-cover class, as in the carbon collection; the values depend on the class "
         "only, with 250 for cocoa."),
    ):
        k = f"{HQ_DIR}/{fname}"
        assets[key] = {"href": f"{BASE}/{k}", "type": "text/csv", "title": title,
                       "description": about, "roles": ["metadata"], "created": created(objs, k)}

    description = f"""**Provisional: threat and sensitivity values are judgment calls pending expert review.** The layers will be re-run if the review changes them.

Habitat quality across Peru, modelled with the InVEST Habitat Quality model ({NATCAP_INVEST}) at 100 m. Built for cocoa supply-chain decision support: comparing places by how intact their habitat is and how much pressure nearby land use puts on it. It is a general habitat score, not a map of any one species.

Two layers, each as a WGS84 cloud-optimized GeoTIFF and as H3 hex parquet at native resolution 9 with parents 8 and 0:

- **Habitat quality** (`habitat_quality`), 0 to 1: how suitable the land is as habitat, lowered by nearby threats. 0 where the land is not habitat.
- **Habitat degradation** (`habitat_degradation`), 0 to {HQ_DMAX}: the combined pressure from nearby threats. 0 where no threat is within reach.

Both are relative scores without units. Compare places with them; do not read them as a probability or a measured quantity. To summarise an area, average them weighted by area; never add them up.

**Use these as screening layers.** They rank areas against each other. They are not farm-level estimates: a smallholder cocoa farm covers only a few 100 m pixels, and every pixel of a land-cover class gets the same habitat and sensitivity values. Confirm any site-level claim in the field.

**Footprint.** All of Peru, inside the FAO GAUL 2015 country boundary (the boundary the cocoa layer uses), {PIXELS:,} land pixels. The model ran on land cover extended 5 km beyond the border, the farthest a threat reaches, so threats just across the border are counted; the outputs were then clipped to the border.

**How the model was set up.**
- **Land cover:** the same land cover as the InVEST carbon storage collection: Copernicus Global Land Cover CGLS-LC100 v3.0.1 for 2019, 100 m, with cocoa from the Forest Data Partnership model 2025b for 2024 added as its own class where more than half of a 100 m pixel's 10 m sub-pixels had a cocoa probability of 0.5 or more ({COCOA_PIXELS:,} pixels in Peru). That keeps about 64% of the 10 m cocoa area. The pixels holding the other 36% keep their Copernicus class, mostly forest, so habitat is somewhat overstated and the cocoa threat understated in cocoa landscapes. Land cover is from 2019 and cocoa from 2024.
- **Threats,** each present or absent in a pixel: urban land (Copernicus built-up class), reaching 5 km with weight 1.0 and exponential decay; cropland (Copernicus cultivated class), 3 km, weight 0.7, linear decay; cocoa, 1 km, weight 0.4, linear decay. Roads are not included.
- **Habitat suitability:** closed forest 1.0; open forest and herbaceous wetland 0.9; shrubs 0.7; herbaceous vegetation, including Andean grassland, 0.6; moss and lichen 0.5; cocoa 0.3; cropland, built-up land, bare ground, snow and water 0. Each class's sensitivity to each threat is in the sensitivity table asset.
- **Half-saturation constant:** {HQ_K:.3f}, half the highest degradation score, as the InVEST guide recommends. Scenarios run on this landscape use the same constant, so their scores stay comparable.

**Licence and attribution.** CC BY 4.0. These are model outputs built from CC BY 4.0 inputs; credit them as follows.
- {CITE_CGLS}
- {CITE_FDAP}
- {CITE_INVEST_HQ}

**Provenance.** Land cover and cocoa were read from this catalog's copies (`public-land-cover/cgls-lc100-2019`, `public-commodities/fdap-2025b/cocoa-peru-2024`). Model run with natcap.invest {NATCAP_INVEST} on {HQ_RUN}."""

    return {
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
            "https://stac-extensions.github.io/render/v2.0.0/schema.json",
        ],
        "type": "Collection",
        "id": HQ_ID,
        "title": HQ_TITLE,
        "description": description,
        "license": "CC-BY-4.0",
        "sci:citation": (f"Boettiger Lab, UC Berkeley (2026). {HQ_TITLE}: InVEST {NATCAP_INVEST} "
                         f"Habitat Quality model outputs, 2019 land cover with 2024 cocoa. "
                         f"{HQ_SELF}"),
        "keywords": ["habitat quality", "habitat degradation", "biodiversity", "InVEST",
                     "cocoa", "cacao", "Peru", "ecosystem services", "provisional", "H3"],
        "extent": {
            "spatial": {"bbox": [BBOX]},
            "temporal": {"interval": [["2019-01-01T00:00:00Z", "2024-12-31T23:59:59Z"]]},
        },
        "created": min(a["created"] for a in assets.values()),
        "updated": max(a["created"] for a in assets.values()),
        "providers": [
            {"name": "Boettiger Lab, UC Berkeley", "roles": ["producer", "processor", "host"],
             "url": f"{BASE}/{HQ_DIR}/"},
            {"name": "Copernicus Global Land Service", "roles": ["licensor"],
             "url": "https://land.copernicus.eu/global/products/lc"},
            {"name": "Forest Data Partnership", "roles": ["licensor"],
             "url": "https://github.com/google/forest-data-partnership"},
        ],
        "links": [
            {"rel": "self", "href": HQ_SELF, "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": PARENT, "type": "application/json"},
            {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/",
             "type": "text/html", "title": "Creative Commons Attribution 4.0 International"},
            {"rel": "describedby", "href": f"{BASE}/{HQ_DIR}/README.md",
             "type": "text/markdown", "title": "README"},
            {"rel": "about", "href": INVEST_HQ, "type": "text/html",
             "title": "InVEST Habitat Quality model"},
            {"rel": "related", "href": SELF, "type": "application/json",
             "title": "InVEST carbon storage, Peru (same land cover)"},
            {"rel": "derived_from", "href": CGLS, "type": "application/json",
             "title": "Copernicus Global Land Cover 100 m, 2019"},
            {"rel": "derived_from", "href": FDAP, "type": "application/json",
             "title": "Cocoa probability, Peru 2024 (Forest Data Partnership)"},
        ],
        "table:columns": dictionary,
        "renders": renders,
        "assets": assets,
    }


def hq_readme(coll):
    rows = "\n".join(
        f"| {L['title']} | `{L['col']}` | [COG]({BASE}/{DATASET}/{k}-cog.tif) "
        f"| `{BASE}/{DATASET}/{k}/hex/h0=*/data_0.parquet` |" for k, L in HQ_LAYERS.items())
    r = HQ_LAYERS["habitat-quality"]["render"]
    return f"""# {HQ_TITLE}

{coll['description']}

## Layers

| layer | column | COG | hex parquet |
|---|---|---|---|
{rows}

The tables the model used: [threats.csv]({BASE}/{HQ_DIR}/threats.csv) and
[sensitivity.csv]({BASE}/{HQ_DIR}/sensitivity.csv).

## Query with DuckDB

```sql
INSTALL h3 FROM community; LOAD h3; INSTALL httpfs; LOAD httpfs;
-- Area-weighted mean habitat quality under likely cocoa (FDAP 2024 probability >= 0.5)
SELECT SUM(q.habitat_quality * h3_cell_area(q.h9, 'km^2')) / SUM(h3_cell_area(q.h9, 'km^2'))
       AS mean_habitat_quality
FROM read_parquet('{BASE}/{DATASET}/habitat-quality/hex/h0=*/data_0.parquet') q
JOIN read_parquet('{S3}/public-commodities/fdap-2025b/cocoa-peru-2024/hex/h0=*/data_0.parquet') c
  USING (h9)
WHERE c.probability >= 0.5;
```

## Map with MapLibre GL JS

These are rasters, so there is no vector `source-layer`; serve the COG through a tile server
such as titiler:

```js
map.addSource('peru-habitat-quality', {{
  type: 'raster',
  tiles: ['https://titiler.nrp-nautilus.io/cog/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png'
        + '?url={BASE}/{DATASET}/habitat-quality-cog.tif&rescale={r['rescale'][0][0]},{r['rescale'][0][1]}&colormap_name={r['colormap_name']}'],
  tileSize: 256
}});
map.addLayer({{ id: 'peru-habitat-quality', type: 'raster', source: 'peru-habitat-quality' }});
```
"""


def patch_parent(parent):
    parent = copy.deepcopy(parent)
    for href, cid, title in ((SELF, DATASET, TITLE), (HQ_SELF, HQ_ID, HQ_TITLE)):
        if not any(l.get("href") == href for l in parent["links"]):
            parent["links"].append({"rel": "child", "id": cid, "href": href,
                                    "type": "application/json", "title": title})
    return parent


def readme(coll):
    rows = "\n".join(
        f"| {L['title']} | `{L['col']}` | [COG]({BASE}/{DATASET}/{k}-cog.tif) "
        f"| `{BASE}/{DATASET}/{k}/hex/h0=*/data_0.parquet` |" for k, L in LAYERS.items())
    return f"""# {TITLE}

{coll['description']}

## Layers

| layer | column | COG | hex parquet |
|---|---|---|---|
{rows}

The carbon pools table the model used: [{DATASET}/carbon_pools.csv]({BASE}/{DATASET}/carbon_pools.csv).

## Query with DuckDB

```sql
INSTALL h3 FROM community; LOAD h3; INSTALL httpfs; LOAD httpfs;
-- Biomass carbon stock in Peru, in teragrams of carbon (density × area; 1 km² = 100 ha)
SELECT SUM(biomass_carbon * h3_cell_area(h9, 'km^2') * 100) / 1e6 AS Tg_C
FROM read_parquet('{BASE}/{DATASET}/carbon-biomass/hex/h0=*/data_0.parquet');

-- Mean biomass carbon under likely cocoa (FDAP 2024 probability >= 0.5)
SELECT AVG(b.biomass_carbon) AS mean_Mg_C_per_ha
FROM read_parquet('{BASE}/{DATASET}/carbon-biomass/hex/h0=*/data_0.parquet') b
JOIN read_parquet('{S3}/public-commodities/fdap-2025b/cocoa-peru-2024/hex/h0=*/data_0.parquet') c
  USING (h9)
WHERE c.probability >= 0.5;
```

## Map with MapLibre GL JS

These are rasters, so there is no vector `source-layer`; serve the COG through a tile server
such as titiler:

```js
map.addSource('peru-biomass-carbon', {{
  type: 'raster',
  tiles: ['https://titiler.nrp-nautilus.io/cog/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png'
        + '?url={BASE}/{DATASET}/carbon-biomass-cog.tif&rescale=0,180&colormap_name=ylgn'],
  tileSize: 256
}});
map.addLayer({{ id: 'peru-biomass-carbon', type: 'raster', source: 'peru-biomass-carbon' }});
```
"""


def main():
    out, objs_path, parent_path = sys.argv[1:4]
    objs = objects(objs_path)
    coll = build_collection(objs)
    os.makedirs(f"{out}/{DATASET}", exist_ok=True)
    json.dump(coll, open(f"{out}/{DATASET}/stac-collection.json", "w"), indent=2,
              ensure_ascii=False)
    open(f"{out}/{DATASET}/README.md", "w").write(readme(coll))
    hq = build_hq_collection(objs)
    os.makedirs(f"{out}/{HQ_DIR}", exist_ok=True)
    json.dump(hq, open(f"{out}/{HQ_DIR}/stac-collection.json", "w"), indent=2, ensure_ascii=False)
    open(f"{out}/{HQ_DIR}/README.md", "w").write(hq_readme(hq))
    json.dump(patch_parent(json.load(open(parent_path))),
              open(f"{out}/stac-collection.json", "w"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
