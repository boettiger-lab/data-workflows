"""Add a `renders` entry for each COG that has none (Portolan PTL-VIZ-002, #761).

Rescales are the 2nd-98th percentile of each COG measured with TiTiler /cog/statistics on
2026-11-24, rounded out; colours follow the sibling renders in the same collection. MIROC uses
CNRM's render so the two climate models compare directly.

Usage: add_renders.py <collection.json> <collection path>   (edits the file in place)
"""
import json
import sys

RENDERS = {
    "public-iucn": {
        "fw-fish-sr": ("Freshwater Fish Richness", "blues", [1.0, 220.0]),
        "amphibians-thr-sr": ("Threatened Amphibian Richness", "reds", [0.0, 8.0]),
        "mammals-thr-sr": ("Threatened Mammal Richness", "reds", [0.0, 10.0]),
        "reptiles-thr-sr": ("Threatened Reptile Richness", "reds", [0.0, 6.0]),
        "fw-fish-thr-sr": ("Threatened Freshwater Fish Richness", "reds", [0.0, 8.0]),
    },
    "public-hazard/mid-century-habitat-climate-exposure": {
        "miroc": ("Mid-Century Habitat Climate Exposure (MIROC, hot-dry)", "reds", [0.15, 1.0]),
    },
}
RENDER_EXT = "https://stac-extensions.github.io/render/v2.0.0/schema.json"


def add(c, key):
    renders = c.setdefault("renders", {})
    for name, (title, cmap, rescale) in RENDERS[key].items():
        asset = f"{name}-cog"
        if asset not in c["assets"]:
            sys.exit(f"{key}: no asset {asset}")
        if name in renders:
            continue
        renders[name] = {"title": title, "assets": [asset], "colormap_name": cmap, "rescale": [rescale]}
    if RENDER_EXT not in c.setdefault("stac_extensions", []):
        c["stac_extensions"].append(RENDER_EXT)


def main(path, key):
    c = json.load(open(path))
    add(c, key)
    with open(path, "w") as f:
        json.dump(c, f, indent=2, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    main(*sys.argv[1:3])
