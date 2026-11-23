"""Name the national census boundary styles for what they show, and record why they are one colour.

  python3 set_style.py style KEY STYLE.json       # edits the style file in place
  python3 set_style.py collection KEY COLL.json   # edits the collection's style asset in place

Seven census-2024/2025 boundary layers are national, but their default styles were copied from
California app layers ("California Counties", "CA Assembly Districts") and drew every feature in
one colour without saying why, which verify-stac refuses. Only names and metadata change; the
paint is kept.
"""
import json
import sys

NAMES = {
    "state": "US states",
    "county": "US counties",
    "tract": "US census tracts",
    "cd": "US congressional districts (119th Congress)",
    "place": "US places (cities and towns)",
    "sldl": "US state legislative districts (lower chamber)",
    "sldu": "US state legislative districts (upper chamber)",
}
REASON = ("Administrative boundaries, drawn as outlines for reference; the layer has no "
          "attribute worth colouring.")


def describe(key):
    return f"{NAMES[key]} drawn as outlines with a light fill, for reference."


if __name__ == "__main__":
    mode, key, path = sys.argv[1:4]
    d = json.load(open(path))
    if mode == "style":
        d["name"] = NAMES[key]
        m = d.setdefault("metadata", {})
        m["description"] = describe(key)
        m["glen:single_colour_reason"] = REASON
    else:
        a = d["assets"][f"style-{key}"]
        a["title"] = NAMES[key]
        a["description"] = describe(key)
    json.dump(d, open(path, "w"), indent=2, ensure_ascii=False)
