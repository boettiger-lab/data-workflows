"""Add the marine richness layers (#807) to the LIVE iucn-richness-2025 collection, in place.

usage: add_marine.py <stac-collection.json>   (rewritten in place; idempotent)
"""
import json
import sys

path = sys.argv[1]
d = json.load(open(path))
BASE = "https://s3-west.nrp-nautilus.io/public-iucn"
CREATED = "2026-11-23T21:44:45Z"

RULE = (
    "Marine species are those whose IUCN Red List systems include Marine, including species that "
    "also live on land or in fresh water (seabirds, shorebirds, sea turtles, mangroves, diadromous "
    "fishes, otters). Counts come from the IUCN Red List range maps (Red List version 2025-2, with "
    "BirdLife bird ranges), using the ranges where the species is extant or probably extant, native "
    "or reintroduced, and resident, breeding or non-breeding; each species is counted once per cell."
)
LAYERS = {
    "marine-sr": dict(col="marine_sr", file="Marine_SR_2025", label="Marine Species Richness",
                      what="the number of marine species", render=("bupu", [0.0, 1700.0])),
    "marine-thr-sr": dict(col="marine_thr_sr", file="Marine_THR_SR_2025",
                          label="Marine Threatened Species Richness",
                          what="the number of marine species assessed Vulnerable, Endangered or "
                               "Critically Endangered", render=("oranges", [0.0, 190.0])),
}

for key, L in LAYERS.items():
    d["assets"][f"{key}-cog"] = {
        "href": f"{BASE}/cog/richness/{L['file']}_4326.tif",
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "title": f"{L['label']} — Cloud-Optimized GeoTIFF (WGS84)",
        "roles": ["data", "visual"],
        "description": (f"{L['what'].capitalize()} per pixel, on the same 0.1° grid as the other "
                        "richness COGs. Each pixel takes the count of the resolution-5 H3 cell that "
                        "contains its centre. 0 is no data (no marine species range covers it)."),
        "created": CREATED,
    }
    d["assets"][f"{key}-hex"] = {
        "href": f"{BASE}/hex/{L['col']}/h0=*/data_0.parquet",
        "type": "application/x-parquet",
        "title": f"{L['label']} — H3 Hex Parquet (resolution 5)",
        "roles": ["data"],
        "description": (f"{L['what'].capitalize()} whose range covers each H3 resolution-5 cell, one "
                        "row per cell; cells with no marine species are absent. Unlike the other "
                        "richness layers, which IUCN publishes as rasters, this layer is counted "
                        "directly from the range maps. A count of distinct species cannot be "
                        "combined across cells by SUM or MAX into a regional species count: that "
                        "needs the range maps (iucn-ranges-2025)."),
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
    "\n\nTwo marine layers, Marine SR and Marine THR_SR, are counted by us from the IUCN range maps "
    "rather than taken from IUCN's published richness rasters, which cover no marine taxa. " + RULE +
    " About 18,000 marine species are counted, about 1,500 of them threatened; the largest groups "
    "are ray-finned fishes, sharks and rays, reef-building corals and marine snails. Because "
    "species that also live on land are included, inland cells can carry small counts from "
    "widespread shorebirds and waterbirds, and coastal cells include open-ocean species whose "
    "ranges reach the coast. Ranges of wide-ranging species were mapped at H3 resolution 5, so "
    "counts are reliable at that resolution and coarser."
)
if "Marine SR" not in d["description"]:
    d["description"] += PARA
for k in ["marine", "Marine fishes", "Corals"]:
    if k not in d["keywords"]:
        d["keywords"].append(k)
json.dump(d, open(path, "w"), indent=2, ensure_ascii=False)
print("ok", len(d["assets"]), "assets")
