#!/usr/bin/env python3
"""Match a PAD-US 4.1 collection's hex metadata to the cng-datasets 0.12 rebuild (#617).

    hex_text.py <collection.json>          # edits the file in place

The rebuild hexes every feature at H3 resolution 10 with parents 9, 8 and 0, and gives a
feature smaller than one cell the single cell containing a point on its surface, so no
feature is missing from the hex. This rewrites the statements that described the older
build (native h8 for combined, 20 features at resolution 8, sub-cell features absent),
declares the h10/h9 columns and the h3:* resolutions on the hex asset. Running it twice
is a no-op.
"""
import json
import re
import sys

H_COLS = [
    {"name": "h10", "type": "uint64", "description": "H3 cell ID at resolution 10."},
    {"name": "h9", "type": "uint64", "description": "H3 cell ID at resolution 9."},
    {"name": "h8", "type": "uint64", "description": "H3 cell ID at resolution 8."},
    {"name": "h0", "type": "int64",
     "description": "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."},
]
EVERY_FEATURE = ("Every source feature has at least one hex row: a feature smaller than one H3 cell "
                 "gets the single cell that contains a point on its surface.")
REPLACE = [
    ("Most features are at resolution 10 (~15m² cells), with 20 extremely complex geometries "
     "at resolution 8 (~0.74 km² cells).",
     "Features are indexed at H3 resolution 10 (~15m² cells), with parent cells at resolutions "
     "9, 8 and 0."),
    ("use SELECT DISTINCT h8, h0 before joining", "use SELECT DISTINCT h10, h0 before joining"),
    ("at resolution 10 (15m²) and resolution 8 (0.74 km²) for 20 complex features.",
     "at resolution 10 (~15m²)."),
]
ABSENT = re.compile(r"[\d,]+ of [\d,]+ source features are smaller than one native H3 cell and "
                    r"polyfill to zero cells, so they are absent from the hex; query the flat "
                    r"GeoParquet for complete feature coverage\.")


def text(s):
    for old, new in REPLACE:
        s = s.replace(old, new)
    return ABSENT.sub(EVERY_FEATURE, s)


def is_h(c):
    return c["name"][:1] == "h" and c["name"][1:].isdigit()


def with_h(cols, describe):
    rest = [c for c in cols if not is_h(c)]
    h = [dict(c) if describe else {"name": c["name"], "type": c["type"]} for c in H_COLS]
    return rest + h


def main(path):
    doc = json.load(open(path))
    doc["description"] = text(doc["description"])
    if any(is_h(c) for c in doc.get("table:columns", [])):
        doc["table:columns"] = with_h(doc["table:columns"], True)
    for key, asset in doc.get("assets", {}).items():
        if "description" in asset:
            asset["description"] = text(asset["description"])
        if key.endswith("-hex"):
            asset["table:columns"] = with_h(asset.get("table:columns", []), False)
            asset["h3:native_resolution"] = 10
            asset["h3:parent_resolutions"] = [9, 8, 0]
    json.dump(doc, open(path, "w"), indent=2, ensure_ascii=False)
    print(f"{doc['id']}: hex metadata updated")


if __name__ == "__main__":
    main(sys.argv[1])
