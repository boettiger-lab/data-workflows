"""Add the marine mammal richness layers (#1045) to the LIVE iucn-richness-2025 collection, in place.

usage: add_marine_mammal.py <stac-collection.json>   (rewritten in place; idempotent)
"""
import json
import sys

path = sys.argv[1]
d = json.load(open(path))
BASE = "https://s3-west.nrp-nautilus.io/public-iucn"
CREATED = "2026-11-24T18:10:46Z"

RULE = (
    "Marine mammals are the cetaceans, pinnipeds (seals, sea lions and the walrus) and sirenians "
    "(dugong and manatees) whose IUCN Red List systems include Marine, plus the sea otter, the marine "
    "otter and the polar bear: 109 species counted, 35 of them threatened. The hippopotamus, "
    "Arctic fox and river otters are left out, although IUCN lists Marine among their systems. "
    "Counts come from the IUCN Red List range maps (Red List version 2025-2), using the ranges where "
    "the species is extant or probably extant, native or reintroduced, and resident, breeding or "
    "non-breeding; each species is counted once per cell."
)
LAYERS = {
    "marine-mammal-sr": dict(col="marine_mammal_sr", file="Marine_Mammal_SR_2025",
                             label="Marine Mammal Species Richness",
                             what="the number of marine mammal species", render=("bupu", [0.0, 25.0])),
    "marine-mammal-thr-sr": dict(col="marine_mammal_thr_sr", file="Marine_Mammal_THR_SR_2025",
                                 label="Marine Mammal Threatened Species Richness",
                                 what="the number of marine mammal species assessed Vulnerable, Endangered "
                                      "or Critically Endangered", render=("oranges", [0.0, 8.0])),
}

for key, L in LAYERS.items():
    d["assets"][f"{key}-cog"] = {
        "href": f"{BASE}/cog/richness/{L['file']}_4326.tif",
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "title": f"{L['label']} — Cloud-Optimized GeoTIFF (WGS84)",
        "roles": ["data", "visual"],
        "description": (f"{L['what'].capitalize()} per pixel, on the same 0.1° grid as the other "
                        "richness COGs. Each pixel takes the count of the resolution-5 H3 cell that "
                        "contains its centre. 0 is no data (no marine mammal range covers it)."),
        "created": CREATED,
    }
    d["assets"][f"{key}-hex"] = {
        "href": f"{BASE}/hex/{L['col']}/h0=*/data_0.parquet",
        "type": "application/x-parquet",
        "title": f"{L['label']} — H3 Hex Parquet (resolution 5)",
        "roles": ["data"],
        "description": (f"{L['what'].capitalize()} whose range covers each H3 resolution-5 cell, one "
                        "row per cell; cells with no marine mammal are absent. Counted directly from "
                        "the range maps. A count of distinct species cannot be combined across cells "
                        "by SUM or MAX into a regional species count: that needs the range maps "
                        "(iucn-ranges-2025)."),
        "h3:native_resolution": 5,
        "h3:parent_resolutions": [4, 3, 0],
        "table:columns": [{"name": L["col"], "type": "int32"}, {"name": "h5", "type": "uint64"},
                          {"name": "h4", "type": "uint64"}, {"name": "h3", "type": "uint64"},
                          {"name": "h0", "type": "int64"}],
        "created": CREATED,
    }
    d.setdefault("renders", {})[key] = {"title": L["label"], "assets": [f"{key}-cog"],
                                        "colormap_name": L["render"][0], "rescale": [L["render"][1]]}
    cols = d.setdefault("table:columns", [])
    if not any(c["name"] == L["col"] for c in cols):
        cols.append({"name": L["col"], "type": "int32",
                     "description": f"{L['what'].capitalize()} whose IUCN range covers the cell. {RULE}"})

PARA = (
    "\n\nTwo marine mammal layers, Marine Mammal SR and Marine Mammal THR_SR, are also counted by us "
    "from the IUCN range maps. IUCN's published mammal richness rasters do not separate marine "
    "mammals, and the marine layers above count them together with every other marine group. " + RULE +
    " Ranges of wide-ranging whales were mapped at H3 resolution 5, so counts are reliable at that "
    "resolution and coarser."
)
if "Marine Mammal SR" not in d["description"]:
    d["description"] += PARA
for k in ["marine mammals", "cetaceans", "pinnipeds"]:
    if k not in d["keywords"]:
        d["keywords"].append(k)
json.dump(d, open(path, "w"), indent=2, ensure_ascii=False)
print("ok", len(d["assets"]), "assets")
