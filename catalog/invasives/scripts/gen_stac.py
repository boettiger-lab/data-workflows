#!/usr/bin/env python3
"""Generate the public-invasives STAC for USGS INHABIT v4.0 (data-workflows #610).

Writes two files to /tmp:
  /tmp/invasives-bucket-stac.json    -> s3://public-invasives/stac-collection.json
  /tmp/inhabit-v4-2024-stac.json     -> s3://public-invasives/inhabit-v4-2024/stac-collection.json

One collection, `inhabit-v4-2024`, holding one COG asset and one hex asset per
(species x product) -- the 12 species share a grid, license, method and citation, so they
do not warrant separate collections.

Phase control -- so the collection can be published truthfully while the res-10 hex fan-out is
still running, instead of advertising hex assets that partly 404. COG assets are ALWAYS emitted
(all 48 COGs are built and grid-verified); READY_LAYERS gates only the hex assets:

  unset            every hex asset -- use only once the fan-out is 72/72 and the h0 coverage
                   gate has passed
  "NONE"           no hex assets (COG-only interim)
  "a|b,c|d"        hex assets for exactly those "<species>|<product>" keys
"""
import json
import os

BUCKET = "public-invasives"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
COLL = f"{BASE}/inhabit-v4-2024"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"

DOI = "10.5066/P14HNEJF"
CITE = ("Jarnevich, C.S., Engelstad, P., Williams, D.A., Shadwell, K.S., Reimer, C.J., "
        "Henderson, G.C., Prevey, J.S., and Pearse, I.S., 2024, INHABIT species potential "
        "distribution across the contiguous United States (ver. 4.0, June 2024): U.S. "
        "Geological Survey data release, https://doi.org/10.5066/P14HNEJF. Method: Jarnevich "
        "et al. 2024, NeoBiota 96:261-278, https://doi.org/10.3897/neobiota.96.134842.")
SRC = f"Source: USGS INHABIT v4.0 (June 2024), doi:{DOI}."

# ── The 12 in-scope species. Order and ScienceBase child-item ids are pinned; the ids were
# re-verified against the v4 parent listing (663926f0d34e2537768ce951) on 2026-08-26 and are
# the provenance a reader needs to re-fetch exactly this input.
SPECIES = [
    ("bromus_tectorum",               "Bromus tectorum",               "cheatgrass",          "66a14c62d34ec831f2c2b1cc"),
    ("bromus_rubens",                 "Bromus rubens",                 "red brome",           "66a14559d34ef32deb7ee1a2"),
    ("bromus_japonicus",              "Bromus japonicus",              "Japanese brome",      "66a14239d34ef32deb7ede9c"),
    ("bromus_arvensis",               "Bromus arvensis",               "field brome",         "669fd2e7d34eef99d5abc5eb"),
    ("taeniatherum_caput_medusae",    "Taeniatherum caput-medusae",    "medusahead",          "66bb7a6ad34e033882814282"),
    ("ventenata_dubia",               "Ventenata dubia",               "ventenata",           "66c3adebd34e03388287af28"),
    ("aegilops_cylindrica",           "Aegilops cylindrica",           "jointed goatgrass",   "669ee0dcd34eef99d5abbb3b"),
    ("agropyron_cristatum",           "Agropyron cristatum",           "crested wheatgrass",  "669ee8e0d34eef99d5abbb50"),
    ("salsola_tragus",                "Salsola tragus",                "Russian thistle",     "66c3c389d34e03388287bba9"),
    ("tamarix_chinensis_ramosissima", "Tamarix chinensis/ramosissima",  "tamarisk",            "66bb7eccd34e033882814498"),
    ("elaeagnus_angustifolia",        "Elaeagnus angustifolia",        "Russian olive",       "66a68b88d34ea6469c870807"),
    ("cenchrus_ciliaris",             "Cenchrus ciliaris",             "buffelgrass",         "66a29430d34ec831f2c2d2d7"),
]

# ── All nine products. `masked` = restricted to the MESS training envelope (the stated IRA
# default, because roadless country is disproportionately outside that envelope).
#
# Phase 1 is the four products the IRA tabulation actually reads; phase 2 is the other five.
# The split is a build-order convenience only: same collection, same pinned 4326 grid, additive.
MODEL_GROUP = {
    "occurrence":     "occurrence",
    "abundance":      "abundance (>=5% cover)",
    "high-abundance": "high abundance (>=25% cover)",
}
# threshold key -> (percentile label, where it sits in the inclusive..targeted gradient)
THRESHOLD = {
    "first": ("0.01", "the most inclusive (comprehensive) of the three"),
    "fifth": ("0.05", "**the canonical threshold for this collection**"),
    "tenth": ("0.10", "the most restrictive (targeted) of the three"),
}
CONTINUOUS = ["occurrence", "abundance", "high-abundance"]
PHASE1 = ["occurrence-masked", "abundance-masked", "high-abundance-masked",
          "integrated-binary-fifth"]
PHASE2 = ["occurrence", "abundance", "high-abundance",
          "integrated-binary-first", "integrated-binary-tenth"]
ALL_PRODUCTS = PHASE1 + PHASE2


def group_of(product):
    """Model group for a continuous product, masked or not."""
    return MODEL_GROUP[product[:-len("-masked")] if product.endswith("-masked") else product]


def is_masked(product):
    return product.endswith("-masked")


def is_class(product):
    return product.startswith("integrated-binary")

# ── gHM (Global Human Modification) importance, measured from each species'
# variableImportance.csv: mean AUCdiff per predictor, negatives clipped to 0, expressed as a
# share of the positive total, with gHM's rank among that species' predictors. Two columns:
# pooled over all four model types, and restricted to the OCCURRENCE models -- which is the
# subset a distance-to-road gradient actually leans on. gHM is built substantially from roads,
# so a high share makes "suitability rises near roads" partly the model restating a predictor.
# (species: (all_share, all_rank, all_n, occ_share, occ_rank, occ_n, occurrence backgrounds))
GHM = {
    "aegilops_cylindrica":           (22.0,  1, 25, 25.0,  1, 24, "KDE,target"),
    "agropyron_cristatum":           ( 5.0,  7, 28,  7.2,  3, 26, "KDE,target"),
    "bromus_arvensis":               ( 5.0,  7, 29,  8.0,  4, 27, "KDE,target"),
    "bromus_japonicus":              ( 3.5,  8, 26,  6.3,  6, 26, "KDE,target"),
    "bromus_rubens":                 ( 2.2,  8, 24,  4.0,  8, 22, "KDE,target"),
    "bromus_tectorum":               ( 1.2, 12, 25,  2.0,  6, 23, "target"),
    "cenchrus_ciliaris":             (13.9,  3, 24, 22.4,  1, 23, "KDE,target"),
    "elaeagnus_angustifolia":        (11.3,  3, 28, 17.6,  3, 27, "KDE,target"),
    "salsola_tragus":                ( 6.1,  3, 25, 12.9,  2, 22, "KDE,target"),
    "taeniatherum_caput_medusae":    ( 3.4,  7, 26,  3.1, 10, 26, "KDE,target"),
    "tamarix_chinensis_ramosissima": (16.4,  2, 26, 17.1,  3, 25, "KDE,target"),
    "ventenata_dubia":               ( 5.7,  6, 26,  6.0,  7, 26, "KDE,target"),
}
# -- MEASURED source facts (exact full-raster bincount, value-census job, 2026-08-26;
# all 108 layers, 12 species x 9 products). Not copied from FGDC: the FGDC rdommax of 98 is a
# per-file figure and understates the 0-100 family scale the paper specifies ("we rescaled the
# mapped values for each model between 0 and 100"). min/max/data_px are over the SOURCE Albers
# raster; gdalwarp with -srcnodata excludes nodata from interpolation, so the warp cannot move
# a value outside [min, max]. Keys are "<species>|<product>".
MEASURED = {
  "aegilops_cylindrica|occurrence": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 96, "data_px": 786932647, "nodata_px": 572375402},
  "aegilops_cylindrica|abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 98, "data_px": 787285901, "nodata_px": 572022148},
  "aegilops_cylindrica|high-abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 99, "data_px": 787324241, "nodata_px": 571983808},
  "aegilops_cylindrica|occurrence-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 96, "data_px": 727416706, "nodata_px": 631891343},
  "aegilops_cylindrica|abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 98, "data_px": 787285901, "nodata_px": 572022148},
  "aegilops_cylindrica|high-abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 99, "data_px": 758686878, "nodata_px": 600621171},
  "aegilops_cylindrica|integrated-binary-first": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 52758462, 0: 198766120, 1: 141252797, 2: 147593475, 3: 246984292}},
  "aegilops_cylindrica|integrated-binary-fifth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 57930517, 0: 391847400, 1: 197680156, 2: 88100038, 3: 51797035}},
  "aegilops_cylindrica|integrated-binary-tenth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 59665571, 0: 525424175, 1: 163308672, 2: 19806699, 3: 19150029}},
  "agropyron_cristatum|occurrence": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 94, "data_px": 786381246, "nodata_px": 572926803},
  "agropyron_cristatum|abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 786041508, "nodata_px": 573266541},
  "agropyron_cristatum|high-abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 786672515, "nodata_px": 572635534},
  "agropyron_cristatum|occurrence-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 94, "data_px": 684552911, "nodata_px": 674755138},
  "agropyron_cristatum|abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 689660872, "nodata_px": 669647177},
  "agropyron_cristatum|high-abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 687390291, "nodata_px": 671917758},
  "agropyron_cristatum|integrated-binary-first": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 91517791, 0: 317913435, 1: 53749864, 2: 12182329, 3: 311991727}},
  "agropyron_cristatum|integrated-binary-fifth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 96230905, 0: 423953925, 1: 47791502, 2: 12663660, 3: 206715154}},
  "agropyron_cristatum|integrated-binary-tenth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 97592240, 0: 464986343, 1: 46690837, 2: 7808189, 3: 170277537}},
  "bromus_arvensis|occurrence": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 97, "data_px": 786803391, "nodata_px": 572504658},
  "bromus_arvensis|abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 787274597, "nodata_px": 572033452},
  "bromus_arvensis|high-abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 784693775, "nodata_px": 574614274},
  "bromus_arvensis|occurrence-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 97, "data_px": 742132306, "nodata_px": 617175743},
  "bromus_arvensis|abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 766315922, "nodata_px": 592992127},
  "bromus_arvensis|high-abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 763836585, "nodata_px": 595471464},
  "bromus_arvensis|integrated-binary-first": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 25872331, 0: 85916747, 1: 257904639, 2: 90010151, 3: 327651278}},
  "bromus_arvensis|integrated-binary-fifth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 33469349, 0: 252321824, 1: 201569792, 2: 36012431, 3: 263981750}},
  "bromus_arvensis|integrated-binary-tenth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 38627780, 0: 417898847, 1: 108454968, 2: 20077847, 3: 202295704}},
  "bromus_japonicus|occurrence": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 787271338, "nodata_px": 572036711},
  "bromus_japonicus|abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 98, "data_px": 787322271, "nodata_px": 571985778},
  "bromus_japonicus|high-abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 787263708, "nodata_px": 572044341},
  "bromus_japonicus|occurrence-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 764981374, "nodata_px": 594326675},
  "bromus_japonicus|abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 98, "data_px": 773137047, "nodata_px": 586171002},
  "bromus_japonicus|high-abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 773078484, "nodata_px": 586229565},
  "bromus_japonicus|integrated-binary-first": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 17229753, 0: 143772823, 1: 143606461, 2: 32280362, 3: 450465747}},
  "bromus_japonicus|integrated-binary-fifth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 20464051, 0: 347793096, 1: 112292409, 2: 37289263, 3: 269516327}},
  "bromus_japonicus|integrated-binary-tenth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 21505760, 0: 465296628, 1: 75072376, 2: 35477322, 3: 190003060}},
  "bromus_rubens|occurrence": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 787188817, "nodata_px": 572119232},
  "bromus_rubens|abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 786674582, "nodata_px": 572633467},
  "bromus_rubens|high-abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 98, "data_px": 787296231, "nodata_px": 572011818},
  "bromus_rubens|occurrence-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 405349680, "nodata_px": 953958369},
  "bromus_rubens|abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 626258242, "nodata_px": 733049807},
  "bromus_rubens|high-abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 98, "data_px": 626879891, "nodata_px": 732428158},
  "bromus_rubens|integrated-binary-first": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 379204213, 0: 212161826, 1: 32780417, 2: 21171702, 3: 142036988}},
  "bromus_rubens|integrated-binary-fifth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 381452798, 0: 313995157, 1: 5890663, 2: 4930957, 3: 81085571}},
  "bromus_rubens|integrated-binary-tenth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 381821716, 0: 344355843, 1: 4615836, 2: 1656264, 3: 54905487}},
  "bromus_tectorum|occurrence": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 787296518, "nodata_px": 572011531},
  "bromus_tectorum|abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 97, "data_px": 787285900, "nodata_px": 572022149},
  "bromus_tectorum|high-abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 95, "data_px": 787292530, "nodata_px": 572015519},
  "bromus_tectorum|occurrence-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 748943939, "nodata_px": 610364110},
  "bromus_tectorum|abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 97, "data_px": 748478249, "nodata_px": 610829800},
  "bromus_tectorum|high-abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 95, "data_px": 748484879, "nodata_px": 610823170},
  "bromus_tectorum|integrated-binary-first": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 38162079, 0: 344705305, 1: 88630388, 2: 38874620, 3: 276982754}},
  "bromus_tectorum|integrated-binary-fifth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 38329816, 0: 447915693, 1: 90394262, 2: 17513279, 3: 193202096}},
  "bromus_tectorum|integrated-binary-tenth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 38368578, 0: 542781474, 1: 40955455, 2: 12856456, 3: 152393183}},
  "cenchrus_ciliaris|occurrence": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 98, "data_px": 786932515, "nodata_px": 572375534},
  "cenchrus_ciliaris|abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 98, "data_px": 787285901, "nodata_px": 572022148},
  "cenchrus_ciliaris|high-abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 97, "data_px": 786932515, "nodata_px": 572375534},
  "cenchrus_ciliaris|occurrence-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 98, "data_px": 444982994, "nodata_px": 914325055},
  "cenchrus_ciliaris|abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 98, "data_px": 264847405, "nodata_px": 1094460644},
  "cenchrus_ciliaris|high-abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 97, "data_px": 264378091, "nodata_px": 1094929958},
  "cenchrus_ciliaris|integrated-binary-first": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 342124562, 0: 358486945, 1: 27785188, 2: 5951447, 3: 53007004}},
  "cenchrus_ciliaris|integrated-binary-fifth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 342322727, 0: 407783717, 1: 5649165, 2: 4905953, 3: 26693584}},
  "cenchrus_ciliaris|integrated-binary-tenth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 342350597, 0: 424367304, 1: 3697548, 2: 2694763, 3: 14244934}},
  "elaeagnus_angustifolia|occurrence": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 800171529, "nodata_px": 559136520},
  "elaeagnus_angustifolia|abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 96, "data_px": 786942631, "nodata_px": 572365418},
  "elaeagnus_angustifolia|high-abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 787285901, "nodata_px": 572022148},
  "elaeagnus_angustifolia|occurrence-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 768849052, "nodata_px": 590458997},
  "elaeagnus_angustifolia|abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 96, "data_px": 753484104, "nodata_px": 605823945},
  "elaeagnus_angustifolia|high-abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 753827374, "nodata_px": 605480675},
  "elaeagnus_angustifolia|integrated-binary-first": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 28623611, 0: 191150286, 1: 141929360, 2: 48756183, 3: 376895706}},
  "elaeagnus_angustifolia|integrated-binary-fifth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 30624791, 0: 387639025, 1: 65382996, 2: 37748932, 3: 265959402}},
  "elaeagnus_angustifolia|integrated-binary-tenth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 30887891, 0: 505164272, 1: 25383600, 2: 60291440, 3: 165627943}},
  "salsola_tragus|occurrence": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 786401989, "nodata_px": 572906060},
  "salsola_tragus|abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 786674897, "nodata_px": 572633152},
  "salsola_tragus|high-abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 787296248, "nodata_px": 572011801},
  "salsola_tragus|occurrence-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 738506020, "nodata_px": 620802029},
  "salsola_tragus|abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 712357485, "nodata_px": 646950564},
  "salsola_tragus|high-abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 724173566, "nodata_px": 635134483},
  "salsola_tragus|integrated-binary-first": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 47928959, 0: 261892067, 1: 186182389, 2: 10142461, 3: 281209270}},
  "salsola_tragus|integrated-binary-fifth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 48071746, 0: 475417747, 1: 64089227, 2: 14042797, 3: 185733629}},
  "salsola_tragus|integrated-binary-tenth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 48237521, 0: 556087727, 1: 38588589, 2: 29372044, 3: 115069265}},
  "taeniatherum_caput_medusae|occurrence": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 96, "data_px": 787045561, "nodata_px": 572262488},
  "taeniatherum_caput_medusae|abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 96, "data_px": 787233892, "nodata_px": 572074157},
  "taeniatherum_caput_medusae|high-abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 96, "data_px": 787158209, "nodata_px": 572149840},
  "taeniatherum_caput_medusae|occurrence-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 96, "data_px": 510728964, "nodata_px": 848579085},
  "taeniatherum_caput_medusae|abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 96, "data_px": 544912771, "nodata_px": 814395278},
  "taeniatherum_caput_medusae|high-abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 96, "data_px": 544837088, "nodata_px": 814470961},
  "taeniatherum_caput_medusae|integrated-binary-first": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 273231187, 0: 253335365, 1: 111889078, 2: 26082421, 3: 122817095}},
  "taeniatherum_caput_medusae|integrated-binary-fifth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 275370039, 0: 414748207, 1: 32490899, 2: 4715140, 3: 60030861}},
  "taeniatherum_caput_medusae|integrated-binary-tenth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 276106026, 0: 458422871, 1: 16155144, 2: 4252486, 3: 32418619}},
  "tamarix_chinensis_ramosissima|occurrence": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 95, "data_px": 786942631, "nodata_px": 572365418},
  "tamarix_chinensis_ramosissima|abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 94, "data_px": 786987061, "nodata_px": 572320988},
  "tamarix_chinensis_ramosissima|high-abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 95, "data_px": 786987061, "nodata_px": 572320988},
  "tamarix_chinensis_ramosissima|occurrence-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 95, "data_px": 730245926, "nodata_px": 629062123},
  "tamarix_chinensis_ramosissima|abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 94, "data_px": 738866863, "nodata_px": 620441186},
  "tamarix_chinensis_ramosissima|high-abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 95, "data_px": 738857399, "nodata_px": 620450650},
  "tamarix_chinensis_ramosissima|integrated-binary-first": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 56513928, 0: 284935006, 1: 128560337, 2: 15354208, 3: 301991667}},
  "tamarix_chinensis_ramosissima|integrated-binary-fifth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 56885483, 0: 463812346, 1: 41950795, 2: 19341806, 3: 205364716}},
  "tamarix_chinensis_ramosissima|integrated-binary-tenth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 56954439, 0: 527659640, 1: 23843267, 2: 24841334, 3: 154056466}},
  "ventenata_dubia|occurrence": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 98, "data_px": 787223478, "nodata_px": 572084571},
  "ventenata_dubia|abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 787296232, "nodata_px": 572011817},
  "ventenata_dubia|high-abundance": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 784671214, "nodata_px": 574636835},
  "ventenata_dubia|occurrence-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 98, "data_px": 616281430, "nodata_px": 743026619},
  "ventenata_dubia|abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 619000795, "nodata_px": 740307254},
  "ventenata_dubia|high-abundance-masked": {"dtype": "uint8", "nodata": 255, "min": 0, "max": 100, "data_px": 616375777, "nodata_px": 742932272},
  "ventenata_dubia|integrated-binary-first": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 164454089, 0: 311417696, 1: 28771755, 2: 60495190, 3: 222216416}},
  "ventenata_dubia|integrated-binary-fifth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 170230431, 0: 517134089, 1: 12756265, 2: 33168539, 3: 54065822}},
  "ventenata_dubia|integrated-binary-tenth": {"dtype": "int8", "nodata": -128, "min": -1, "max": 3, "data_px": 787355146, "nodata_px": 571952903, "class_counts": {-1: 170676706, 0: 552374781, 1: 8571330, 2: 23908563, 3: 31823766}},
}

# Data pixels retained by the MESS-masked variant as a % of the plain product (measured).
MASKED_RETENTION = {
  "aegilops_cylindrica|occurrence": 92.4,
  "aegilops_cylindrica|abundance": 100.0,
  "aegilops_cylindrica|high-abundance": 96.4,
  "agropyron_cristatum|occurrence": 87.1,
  "agropyron_cristatum|abundance": 87.7,
  "agropyron_cristatum|high-abundance": 87.4,
  "bromus_arvensis|occurrence": 94.3,
  "bromus_arvensis|abundance": 97.3,
  "bromus_arvensis|high-abundance": 97.3,
  "bromus_japonicus|occurrence": 97.2,
  "bromus_japonicus|abundance": 98.2,
  "bromus_japonicus|high-abundance": 98.2,
  "bromus_rubens|occurrence": 51.5,
  "bromus_rubens|abundance": 79.6,
  "bromus_rubens|high-abundance": 79.6,
  "bromus_tectorum|occurrence": 95.1,
  "bromus_tectorum|abundance": 95.1,
  "bromus_tectorum|high-abundance": 95.1,
  "cenchrus_ciliaris|occurrence": 56.5,
  "cenchrus_ciliaris|abundance": 33.6,
  "cenchrus_ciliaris|high-abundance": 33.6,
  "elaeagnus_angustifolia|occurrence": 96.1,
  "elaeagnus_angustifolia|abundance": 95.7,
  "elaeagnus_angustifolia|high-abundance": 95.8,
  "salsola_tragus|occurrence": 93.9,
  "salsola_tragus|abundance": 90.6,
  "salsola_tragus|high-abundance": 92.0,
  "taeniatherum_caput_medusae|occurrence": 64.9,
  "taeniatherum_caput_medusae|abundance": 69.2,
  "taeniatherum_caput_medusae|high-abundance": 69.2,
  "tamarix_chinensis_ramosissima|occurrence": 92.8,
  "tamarix_chinensis_ramosissima|abundance": 93.9,
  "tamarix_chinensis_ramosissima|high-abundance": 93.9,
  "ventenata_dubia|occurrence": 78.3,
  "ventenata_dubia|abundance": 78.6,
  "ventenata_dubia|high-abundance": 78.6,
}

# ── The integrated-binary class set. The FGDC gives the domain (-1 .. 3) but NO enumerated
# labels, so the labels come from the release's own documentation, not from a guess:
#   INHABIT_VersionHistory.txt (v4 changes): "addition of categorical map combining
#   unsuitable, occurrence suitable, abundance suitable, and high abundance suitable"
#   Jarnevich et al. 2024 (Methods, Spatial outputs): "Finally, we combined the binary maps to
#   display information across all three model groups (occurrence, abundance, high abundance)
#   for each of the three thresholds, WHILE HIGHLIGHTING ANY AREAS OF ENVIRONMENTAL
#   EXTRAPOLATION."
# That last clause is -1: the MESS (multivariate environmental similarity surface, Elith et al.
# 2010) flag for novel environmental conditions -- at least one predictor outside the range of
# the model training data. Independently confirmed by the value census: the -1 pixel count
# matches the area the `-masked` occurrence product suppresses, to 0.06% for cheatgrass and
# 0.10% for red brome and buffelgrass (the three species where -1 is largest).
#
# -1 IS A CLASS, NOT FILL. NoData is -128. A sign test would delete up to 48% of a raster
# (red brome). Palette: ColorBrewer YlOrRd for the nested suitability ranks 1-3, near-white for
# unsuitable, and a desaturated purple for extrapolation so it never reads as "more suitable".
CLASSES = [
    (-1, "Novel environmental conditions",
     "MESS extrapolation flag: at least one predictor at this pixel is outside the range of "
     "values used to train the model, so no suitability rank is asserted here. NOT NoData "
     "(NoData is -128) and NOT a suitability level -- exclude it from suitability accounting "
     "rather than treating it as unsuitable.", "7B68A6"),
    (0, "Unsuitable",
     "Below the fifth-percentile threshold for all three model groups.", "F2F2F2"),
    (1, "Occurrence suitable",
     "At or above the fifth-percentile occurrence threshold, but below the abundance "
     "threshold.", "FED976"),
    (2, "Abundance suitable",
     "At or above the fifth-percentile abundance (>=5% cover) threshold, but below the high "
     "abundance threshold.", "FD8D3C"),
    (3, "High abundance suitable",
     "At or above the fifth-percentile high abundance (>=25% cover) threshold.", "BD0026"),
]
CLASS_CODES = [-1, 0, 1, 2, 3]

# ⚠️ THE RANKS ARE EXCLUSIVE IN THE RASTER AND NESTED IN THE PAPER'S TABLES. Jarnevich et al.:
# "Values were nested such that summaries of occurrence models included locations defined as
# suitable by any of the three model groups." A pixel suitable for high abundance is coded 3
# ONLY -- it does not also appear as 1. So occurrence-suitable area is COUNT(1)+COUNT(2)+
# COUNT(3), i.e. `suitability_class >= 1`, never COUNT(1) alone. Reading class 1 as "all
# occurrence-suitable ground" undercounts it by every cell that is also abundance-suitable.
NESTING = ("Ranks are EXCLUSIVE in the raster but NESTED in the source's own tabulations: "
           "occurrence-suitable ground is `suitability_class >= 1` (classes 1+2+3), "
           "abundance-suitable is `>= 2`, high-abundance-suitable is `= 3`. Counting class 1 "
           "alone undercounts occurrence-suitable ground by every cell that also clears a "
           "higher threshold.")

# ── Canonical column descriptions. These MUST be byte-identical everywhere the column name
# appears: the mcp-data-server #303 fold keeps the first-seen text per column name across a
# collection's assets and silently drops the rest, and verify-stac.py HARD-fails a divergence.
# So nothing species-specific or product-specific belongs here -- that goes in the per-asset
# `description`, which is always rendered.
COL_SUITABILITY = {
    "name": "suitability", "type": "double",
    "description": (
        "Area-weighted MEAN relative habitat suitability, 0-100, of the source pixels covering "
        "the cell (reducer=mean). The model group -- occurrence, abundance (>=5% cover) or high "
        "abundance (>=25% cover) -- is named in this asset's own `description`; one column name "
        "is used across all three so that the shared definition is not duplicated. "
        "**Relative index, not an amount: aggregate with AVG/MIN/MAX, never SUM.** Values are "
        "each model's prediction rescaled to 0-100 and ensembled by continuous Boyce index, so "
        "they are comparable BETWEEN model groups and species only as ranks within a map, not "
        "as absolute probabilities. Source NoData (255) is excluded before averaging. "
        "**Modelled potential habitat, not observed occurrence.** " + SRC),
}
COL_CLASS = {
    # `double`, not int64, and that is measured rather than assumed: the cng-datasets raster
    # `mode` reducer emits its value column as DOUBLE, so the codes read back as -1.0 .. 3.0.
    # Verified 2026-08-27 with a res-5 probe job against a published integrated-binary COG before
    # the real class hexes landed. The catalog precedent is the same (ca-climate-zones-hex declares
    # its mode column float64 with an integer `values` array), and verify-stac.py's
    # values-vs-DISTINCT gate normalizes the trailing ".0" for exactly this reason.
    "name": "suitability_class", "type": "double",
    "description": (
        "Dominant (mode) INHABIT integrated-binary class of the source pixels covering the "
        "cell. **Integer codes stored as double** (an artifact of the `mode` reducer), so compare "
        "with `= 3` or `>= 1` and cast if an exact integer join is needed. Values: " + ", ".join(f"{v}={n}" for v, n, _, _ in CLASSES) + ". " + NESTING +
        " **-1 is a class, not fill** -- it flags novel environmental conditions (MESS "
        "extrapolation, Elith et al. 2010); source NoData is -128 and is excluded. "
        "**Categorical: never SUM or AVG this column** -- count cells per class. The `mode` "
        "reducer keeps only each cell's dominant class and discards the mix, so a per-class "
        "area total from this column undercounts to plurality cells; see this asset's "
        "`description`. " + SRC),
    "values": CLASS_CODES,
}


def hex_cols(value_col):
    return [value_col,
            {"name": "h10", "type": "uint64",
             "description": "H3 cell ID at resolution 10 (native resolution; one row per cell)."},
            {"name": "h9", "type": "uint64",
             "description": "H3 cell ID at resolution 9 (parent rollup)."},
            {"name": "h8", "type": "uint64",
             "description": "H3 cell ID at resolution 8 (parent rollup; the catalog's universal "
                            "join key -- roadless areas, wildfire hazard and land cover all "
                            "carry h8)."},
            # uint64, matching h10/h9/h8 -- measured with pyarrow against a landed phase-1
            # partition on 2026-08-28, not inherited from the res-5 dtype probe (which reported
            # BIGINT for h0 and was wrong for the real run). verify-stac.py does NOT gate declared
            # column types against the data, so this one has to be right by construction.
            {"name": "h0", "type": "uint64",
             "description": "H3 cell ID at resolution 0; hive partition key."}]


def ghm_note(slug):
    """The road-bias sentence that travels with every asset for this species."""
    a_sh, a_rk, a_n, o_sh, o_rk, o_n, bg = GHM[slug]
    verdict = ("a distance-to-road gradient on this species is DEFENSIBLE"
               if o_sh < 5 else
               "treat a distance-to-road gradient on this species with CAUTION"
               if o_sh < 10 else
               "a distance-to-road gradient on this species is SUBSTANTIALLY CIRCULAR and "
               "should not be reported as evidence that roads drive invasion")
    note = (f"Road-bias audit: gHM (Global Human Modification, itself built substantially from "
            f"roads) carries {o_sh:.1f}% of predictor importance (rank {o_rk}/{o_n}) in this "
            f"species' OCCURRENCE models and {a_sh:.1f}% (rank {a_rk}/{a_n}) pooled over all "
            f"model groups, so {verdict}. It does not undermine the suitability surface itself "
            f"-- human modification is a legitimate predictor of invasion. Occurrence "
            f"background samples: {bg}.")
    if bg == "target":
        note += (" This species has NO KDE-background occurrence model; its only occurrence "
                 "model uses the bias-mitigated target-background design.")
    return note


def cog_asset(slug, sci, common, product):
    m = MEASURED[f"{slug}|{product}"]
    key = f"{slug.replace('_', '-')}-{product}-cog"
    pct_data = 100.0 * m["data_px"] / 1359308049

    if is_class(product):
        thr = product.rsplit("-", 1)[1]
        pct, standing = THRESHOLD[thr]
        band = {
            "name": "suitability_class", "data_type": "int8", "nodata": -128,
            "description": (
                f"INHABIT integrated-binary class at the {thr}-percentile ({pct}) threshold for "
                f"{sci} ({common}). {NESTING} Warped nearest-neighbour from the source Albers "
                f"grid, so the class set is exactly the source's: "
                f"{sorted(m['class_counts'].keys())}. Source pixel counts per class: "
                + ", ".join(f"{c}={n:,}" for c, n in sorted(m["class_counts"].items()))
                + f" ({pct_data:.2f}% of the grid is data; the rest is NoData -128 outside "
                  f"CONUS). " + SRC),
            "classification:classes": [
                {"value": v, "name": n, "description": d, "color_hint": c}
                for v, n, d, c in CLASSES],
        }
        title = (f"{common} ({sci}) — integrated suitability class, "
                 f"{thr} percentile ({pct}) (COG)")
        desc = (f"Categorical integrated-binary map for {sci}, combining the thresholded "
                f"occurrence, abundance and high-abundance ensembles at the {pct} percentile "
                f"threshold — {standing}. The three thresholds convey a gradient from inclusive to "
                f"targeted; `fifth` is canonical and `first`/`tenth` are its sensitivity band, so "
                f"report the spread rather than choosing the threshold that suits a conclusion. "
                f"Warped to EPSG:4326 with **nearest-neighbour** resampling (bilinear on class "
                f"codes invents codes with no upstream referent); overviews NEAREST. Colours are "
                f"ColorBrewer YlOrRd for ranks 1–3 with a desaturated purple for the extrapolation "
                f"flag, chosen here — the source ships no palette. {ghm_note(slug)}")
    else:
        group = group_of(product)
        masked = is_masked(product)
        band = {
            "name": "suitability", "data_type": "uint8", "nodata": 255,
            "unit": "relative suitability index (0–100)",
            "description": (
                f"Relative habitat suitability for {group} of {sci} ({common}), 0–100. "
                f"Source-measured range {m['min']}–{m['max']}; {pct_data:.2f}% of the grid is "
                # The NoData clause must say WHY, and it differs by variant. On a `-masked`
                # product much of the 255 is deliberate MESS suppression, not absence of
                # coverage, and retention varies 3x by species -- so a bare "x% is NoData"
                # reads as a coverage statement and understates the restriction. Dropping
                # this when the generator was generalised to all nine products was a
                # regression against the published 48-asset document; restored 2026-08-28.
                f"data ({m['nodata_px']:,} px are NoData 255"
                + (" \u2014 outside CONUS, or suppressed outside the MESS training envelope"
                   if is_masked(product) else " \u2014 outside CONUS")
                + f"). **Relative index, not a "
                f"probability and not an amount.** " + SRC),
        }
        retained = MASKED_RETENTION[f"{slug}|{product[:-len('-masked')] if masked else product}"]
        if masked:
            title = f"{common} ({sci}) — {group} suitability, MESS-restricted (COG)"
            desc = (f"Continuous weighted-ensemble relative suitability for {group} of {sci}, "
                    f"**restricted to the MESS training envelope**: pixels where any predictor "
                    f"falls outside its training range are set to NoData rather than "
                    f"extrapolated. This is the collection's default variant for "
                    f"inventoried-roadless-area work, because roadless country is "
                    f"disproportionately the high-elevation, undersampled terrain where "
                    f"unrestricted extrapolation is least trustworthy. "
                    f"**The restriction is not cosmetic here: it retains {retained}% of the plain "
                    f"product's data pixels for this species × model group** — quantified per "
                    f"species in the collection README, and for the most-affected species the "
                    f"masked/plain choice moves an area total more than the threshold choice "
                    f"does. ")
        else:
            title = f"{common} ({sci}) — {group} suitability, unrestricted (COG)"
            desc = (f"Continuous weighted-ensemble relative suitability for {group} of {sci}, "
                    f"**unrestricted** — suitability is predicted everywhere the model can be "
                    f"evaluated, including where predictors fall outside the range they were "
                    f"trained on. **Prefer the `-masked` companion for inventoried-roadless-area "
                    f"work**, which suppresses exactly that extrapolation; the masked variant "
                    f"retains {retained}% of this product's data pixels for this species × model "
                    f"group, and the difference is concentrated in the undersampled "
                    f"high-elevation terrain roadless areas occupy. Published so the "
                    f"masked/unmasked spread is auditable rather than assumed. ")
        desc += (f"Warped to EPSG:4326 with bilinear resampling (`-srcnodata 255`, so NoData is "
                 f"excluded from interpolation and cannot bleed into data); overviews AVERAGE. "
                 f"{ghm_note(slug)}")

    return key, {
        "href": f"{COLL}/{slug}/{product}.tif",
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "title": title, "description": desc, "roles": ["data", "visual"],
        "raster:bands": [band],
    }


def hex_asset(slug, sci, common, product):
    m = MEASURED[f"{slug}|{product}"]
    key = f"{slug.replace('_', '-')}-{product}-hex"
    value_col = COL_CLASS if is_class(product) else COL_SUITABILITY

    if is_class(product):
        thr = product.rsplit("-", 1)[1]
        pct, standing = THRESHOLD[thr]
        title = (f"{common} ({sci}) — integrated suitability class, "
                 f"{thr} percentile ({pct}) (H3 res 10)")
        desc = (f"H3 resolution-10 hex of the integrated-binary {thr}-percentile ({pct}) class map "
                f"for {sci} ({common}) — {standing} — **reducer `mode`**, so each cell takes the "
                f"dominant class of the source pixels it covers. "
                f"⚠️ **`mode` keeps only the dominant class and discards the mix, so this asset "
                f"cannot answer \"how much area is high-abundance-suitable\" without "
                f"undercounting to plurality cells.** At ~1.55 source pixels per res-10 cell the "
                f"loss is small, but it is not zero and it is one-directional: minority classes "
                f"inside a mixed cell vanish. Per-class fractional coverage is not produced by "
                f"this pipeline; an area-accounting use case needs a `fractions` build. "
                f"{NESTING} "
                f"**-1 is a class (MESS extrapolation), not NoData** — filter it out of "
                f"suitability accounting explicitly; a `>= 0` or `>= 1` predicate does that. "
                f"Source class pixel counts: "
                + ", ".join(f"{c}={n:,}" for c, n in sorted(m["class_counts"].items()))
                + f". {ghm_note(slug)}")
    else:
        group = group_of(product)
        masked = is_masked(product)
        retained = MASKED_RETENTION[f"{slug}|{product[:-len('-masked')] if masked else product}"]
        variant = "MESS-restricted" if masked else "unrestricted"
        title = f"{common} ({sci}) — {group} suitability, {variant} (H3 res 10)"
        desc = (f"H3 resolution-10 hex of {variant} relative suitability for {group} of "
                f"{sci} ({common}), **reducer `mean`** — the area-weighted mean of the source "
                f"pixels covering each cell. Suitability is a normalized 0–100 index, so `mean` "
                f"is the correct reducer and **`SUM(suitability)` is meaningless**: aggregate "
                f"across cells with AVG (or MAX for a hotspot), never SUM. Cells with no valid "
                f"source pixel are absent rather than zero, and the missing cells are *unknown*, "
                f"not *unsuitable*. ")
        if masked:
            desc += (f"This layer is sparse where the MESS restriction applies — for this "
                     f"species × model group the restricted product retains {retained}% of the "
                     f"plain product's data pixels. ")
        else:
            desc += (f"**Prefer the `-masked` companion for inventoried-roadless-area work**: it "
                     f"suppresses extrapolation beyond the training envelope, and retains "
                     f"{retained}% of this product's data pixels for this species × model group. ")
        desc += f"**Modelled potential habitat, not observed occurrence.** {ghm_note(slug)}"

    return key, {
        "href": f"{COLL}/{slug}/{product}/hex/h0=*/data_0.parquet",
        "type": "application/x-parquet",
        "title": title, "description": desc, "roles": ["data"],
        "h3:native_resolution": 10,
        "h3:parent_resolutions": [9, 8, 0],
        "table:columns": hex_cols(value_col),
    }


# ── Assemble ────────────────────────────────────────────────────────────────────────────────
# PHASE selects which products have a built COG:
#   "1"    the four phase-1 products    "2"  the five phase-2 products
#   "all"  all nine (default)
# READY_LAYERS selects which of those have a landed hex:
#   unset  every one           "NONE"  none (COG-only interim)
#   "a|b,c|d"                  exactly those "<species>|<product>" keys
_phase = os.environ.get("PHASE", "all").strip().lower()
PRODUCTS = {"1": PHASE1, "2": PHASE2, "all": ALL_PRODUCTS}[_phase]

_ready_env = os.environ.get("READY_LAYERS", "").strip()
if not _ready_env:
    READY = None
elif _ready_env.upper() == "NONE":
    READY = set()
else:
    READY = set(_ready_env.split(","))

assets = {}
n_hex = 0
for slug, sci, common, _sb in SPECIES:
    for product in PRODUCTS:
        k, a = cog_asset(slug, sci, common, product)
        assets[k] = a
        if READY is None or f"{slug}|{product}" in READY:
            k, a = hex_asset(slug, sci, common, product)
            assets[k] = a
            n_hex += 1

SPECIES_TABLE = "; ".join(
    f"{sci} ({common}, ScienceBase {sb})" for _s, sci, common, sb in SPECIES)

DESCRIPTION = (
    "Habitat-suitability surfaces for 12 fire-cycle-relevant invasive plants from the USGS "
    "Invasive Species Habitat Tool (INHABIT) v4.0, June 2024 — the ten exotic annual grasses "
    "and forbs that build continuous fine fuels, plus the two riparian woody invaders "
    "(tamarisk, Russian olive). Twelve of the release's 259 species; extending to the full "
    "release is separate work, not a silent expansion.\n\n"
    "⚠️ **This is modelled POTENTIAL habitat, not observed occurrence.** A high-suitability "
    "pixel is a statement about where a species could establish or become abundant given the "
    "environment, not a record that it is present. Every result from this collection reads "
    "\"suitable habitat for X\", never \"X is present\". The claim it supports is about "
    "invasion pressure and vulnerability, not realized invasion.\n\n"
    "**Products.** Three continuous weighted-ensemble surfaces per species — suitability for "
    "occurrence, for abundance (≥5% cover) and for high abundance (≥25% cover) — each a "
    "relative 0–100 index (`mean` reducer; aggregate with AVG, never SUM), plus a categorical "
    "`integrated-binary` map that thresholds and combines all three (`mode` reducer), at three "
    "percentile thresholds. Nine products per species, 108 layers.\n\n"
    "**`-masked` is the default for inventoried-roadless-area work.** The `-masked` variants "
    "suppress suitability outside the MESS training envelope (multivariate environmental "
    "similarity surface, Elith et al. 2010 — at least one predictor outside its training "
    "range). Roadless country is disproportionately high-elevation, undersampled terrain, "
    "exactly where unrestricted extrapolation is least trustworthy. The restriction is "
    "substantial and varies about 3× across these species: it retains 95% of cheatgrass "
    "occurrence pixels but only 34% of buffelgrass abundance pixels, so for the most-affected "
    "species the masked-vs-plain choice moves an area total more than the threshold choice "
    "does. Per-species retention is tabulated in the README and on each asset.\n\n"
    "**`fifth` (0.05) is the canonical threshold**, named up front so a later analysis cannot "
    "pick whichever threshold supports its conclusion. `first` (0.01, inclusive) and `tenth` "
    "(0.10, targeted) are the sensitivity band.\n\n"
    "⚠️ **Class `-1` in the integrated-binary maps is a class, not fill.** It is the MESS "
    "extrapolation flag; NoData is `-128`. It reaches 48% of a raster (red brome), so a sign "
    "test that treats negatives as fill silently deletes half the map. " + NESTING + "\n\n"
    "⚠️ **Road-bias audit: it fires, and it splits the species.** gHM (Global Human "
    "Modification — built substantially from roads, and in this catalog already as "
    "`global-human-modification`) is a predictor in all 12 models. Restricted to the occurrence "
    "models, which is what a distance-to-road gradient leans on, its share of predictor "
    "importance runs from 2.0% for cheatgrass (rank 6/23) to 25.0% for jointed goatgrass (rank "
    "1/24). So a road-distance gradient is defensible for cheatgrass, medusahead (3.1%) and red "
    "brome (4.0%), and substantially circular — the model restating its own predictor — for "
    "jointed goatgrass, buffelgrass (22.4%), Russian olive (17.6%), tamarisk (17.1%) and "
    "Russian thistle (12.9%). This does not undermine the suitability surfaces: human "
    "modification is a legitimate predictor of invasion. It undermines only the inference "
    "\"suitability rises near roads, therefore roads drive invasion\" for the high-gHM species. "
    "Per-species figures are on every asset; method and per-model-group breakdown in "
    "`catalog/invasives/BUILD.md`.\n\n"
    "⚠️ **CONUS only — the largest roadless block is not covered.** INHABIT v4 excludes Alaska, "
    "where the Tongass and Chugach are the single largest roadless acreage in the National "
    "Forest System. Every national statement drawn from this collection is a CONUS statement "
    "and must be reported against the rule-affected base acreage rather than as a national "
    "total. INHABIT Global V1 (doi:10.5066/P13AJ46S) could close the gap later but is a "
    "different grid and different models, not pixel-comparable with v4 CONUS.\n\n"
    "**Grid.** Source is Albers Conical Equal Area (NAD83/GRS 1980) at 98.4693338923368 m — the "
    "FGDC `absres`, which the papers round to \"90 m\"; all 108 source rasters share one "
    "44319×30671 grid. Warped to EPSG:4326 at 0.001096100359° (57745×25711), nearest-neighbour "
    "for the class rasters and bilinear for the continuous, with `-srcnodata` set so NoData "
    "cannot bleed into data. H3 native resolution 10 (≈1.55 source pixels per cell) with "
    "parents 9, 8 and 0; `h8` is the catalog's universal join key.\n\n"
    "**v3.0 (doi:10.5066/P9V54H5K) is not comparable and is deliberately not held.** v4 changed "
    "the ensemble from model agreement to continuous relative suitability, so v3 and v4 pixel "
    "values do not mean the same thing.\n\n"
    "Species: " + SPECIES_TABLE + "."
)

coll = {
    "stac_version": "1.0.0",
    "stac_extensions": [
        "https://stac-extensions.github.io/table/v1.2.0/schema.json",
        "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
        "https://stac-extensions.github.io/classification/v2.0.0/schema.json",
        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
    ],
    "type": "Collection",
    "id": "inhabit-v4-2024",
    "title": "INHABIT v4.0 (2024) — invasive-plant habitat suitability, 12 fire-relevant species (CONUS)",
    "description": DESCRIPTION,
    "license": "public-domain",
    "keywords": ["invasive species", "habitat suitability", "species distribution model",
                 "cheatgrass", "annual grass", "fine fuels", "wildfire", "roadless",
                 "tamarisk", "INHABIT", "USGS", "CONUS", "H3"],
    "extent": {
        # CONUS, from the warped EPSG:4326 grid actually published (57745x25711 @
        # 0.001096100359 deg from -128.386308874497, 51.268044444672).
        "spatial": {"bbox": [[-128.386308874497, 23.093342014672,
                              -65.084314604497, 51.268044444672]]},
        # The v4 release date. Occurrence records used in fitting run 1980-2023 (records were
        # filtered to observation date >= 1980), so the interval opens there rather than at the
        # publication date -- the surfaces describe that record window.
        "temporal": {"interval": [["1980-01-01T00:00:00Z", "2024-06-30T00:00:00Z"]]},
    },
    "sci:doi": DOI,
    "sci:citation": CITE,
    "sci:publications": [
        {"doi": "10.3897/neobiota.96.134842",
         "citation": "Jarnevich, C.S., et al. 2024. Predicted occurrence and abundance habitat "
                     "suitability of invasive plants in the contiguous United States: updates "
                     "for the INHABIT web tool. NeoBiota 96:261-278."},
        {"doi": "10.1371/journal.pone.0263056",
         "citation": "Engelstad, P., et al. 2022. INHABIT: A web-based decision support tool "
                     "for invasive plant species habitat visualization and assessment across "
                     "the contiguous United States. PLoS ONE 17(2):e0263056."},
    ],
    "providers": [
        {"name": "U.S. Geological Survey, Fort Collins Science Center",
         "roles": ["producer", "licensor"], "url": f"https://doi.org/{DOI}"},
        {"name": "Boettiger Lab (cng-datasets COG + H3 processing)",
         "roles": ["processor"], "url": BASE},
    ],
    "links": [
        {"rel": "self", "href": f"{COLL}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": ROOT, "type": "application/json"},
        {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
        {"rel": "license", "href": f"https://doi.org/{DOI}", "type": "text/html"},
        {"rel": "cite-as", "href": f"https://doi.org/{DOI}", "type": "text/html"},
        {"rel": "describedby", "href": f"{BASE}/README.md", "type": "text/markdown"},
    ],
    "assets": assets,
}

_n_layers = len(SPECIES) * len(PRODUCTS)
if READY is not None:
    coll["description"] += (
        f"\n\n[Interim publish: {n_hex} of {_n_layers} hex layers are live; the remainder land as "
        f"the res-10 hex fan-out completes. All {_n_layers} COGs are published and "
        f"grid-verified.]")

bucket = {
    "stac_version": "1.0.0",
    "type": "Collection",
    "id": "public-invasives",
    "title": "Invasive species — habitat suitability and distribution",
    "description": (
        "Invasive-species datasets: modelled habitat suitability and distribution surfaces. "
        "Currently holds USGS INHABIT v4.0 (2024) potential-habitat suitability for 12 "
        "fire-cycle-relevant invasive plants across the contiguous United States. All child "
        "collections are modelled POTENTIAL habitat unless stated otherwise — not observed "
        "occurrence."),
    "license": "public-domain",
    "keywords": ["invasive species", "habitat suitability", "species distribution model"],
    "extent": {
        "spatial": {"bbox": [[-128.386308874497, 23.093342014672,
                              -65.084314604497, 51.268044444672]]},
        "temporal": {"interval": [["1980-01-01T00:00:00Z", "2024-06-30T00:00:00Z"]]},
    },
    "links": [
        {"rel": "self", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": ROOT, "type": "application/json"},
        {"rel": "parent", "href": ROOT, "type": "application/json"},
        {"rel": "child", "href": f"{COLL}/stac-collection.json", "type": "application/json",
         "title": "INHABIT v4.0 (2024) — invasive-plant habitat suitability, 12 fire-relevant "
                  "species (CONUS)"},
    ],
}

json.dump(coll, open("/tmp/inhabit-v4-2024-stac.json", "w"), indent=2)
json.dump(bucket, open("/tmp/invasives-bucket-stac.json", "w"), indent=2)
print(f"wrote /tmp/inhabit-v4-2024-stac.json  — {len(assets)} assets "
      f"({len(assets) - n_hex} COG, {n_hex} hex)")
print("wrote /tmp/invasives-bucket-stac.json — bucket collection, 1 child")
