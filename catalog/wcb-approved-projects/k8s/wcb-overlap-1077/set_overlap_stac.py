"""#1077: describe the overlap hex (every project, with cover_frac) on the LIVE
wcb-approved-projects collection. Run after the plan/hex/repartition jobs in this directory.

    python3 set_overlap_stac.py stac-collection.json
"""
import json
import sys

path = sys.argv[1]
c = json.load(open(path))
a = c["assets"]["wcb-approved-projects-hex"]

names = [x["name"] for x in a["table:columns"]]
assert "cover_frac" not in names
a["table:columns"].insert(names.index("h10"), {"name": "cover_frac", "type": "double"})
top = c["table:columns"]
tnames = [x["name"] for x in top]
assert "cover_frac" not in tnames
top.insert(tnames.index("h10") if "h10" in tnames else len(top), {
    "name": "cover_frac", "type": "double",
    "description": "Share of the h10 cell's area that lies inside the project's polygon, from "
                   "just above 0 to 1 (1 when the cell is wholly inside). Hex asset only."})

d = a["description"]
OLD_PRESENCE = d[d.index("Presence only, with no coverage fraction"):d.index("Per-feature attribute columns")]
NEW_PRESENCE = (
    "Every project has rows: one for each resolution-10 cell its polygon overlaps, including "
    "cells it covers only in part, so a project smaller than a cell still has one. Each row "
    "carries `cover_frac`, the share of that cell's area inside the project's polygon (1 for a "
    "cell wholly inside it): weight each cell's area by `cover_frac`, for a project's own "
    "area or for the area of projects inside another layer. Projects overlap one "
    "another (an easement and a later grant on the same land), so for the area they cover "
    "together take `MAX(cover_frac)` per cell, a lower bound, rather than adding. `h9` and `h8` "
    "locate a cell for joins; they are not units of area.\n\n")
d = d.replace(OLD_PRESENCE, NEW_PRESENCE, 1)
TAIL = (" 332 of 3,915 source features are smaller than one native H3 cell and polyfill to zero "
        "cells, so they are absent from the hex; query the flat GeoParquet for complete feature "
        "coverage.")
assert TAIL in d
a["description"] = d.replace(TAIL, "", 1)

OLD = ("The H3 hex asset covers ~3,581 of 3,915 projects; the ~334 absent projects have "
       "placeholder polygons too small to intersect any H3 resolution-10 cell (~1,478 m²).")
assert OLD in c["description"]
c["description"] = c["description"].replace(
    OLD, "Every project is in the H3 hex asset, with the share of each cell it covers "
         "(`cover_frac`).", 1)

json.dump(c, open(path, "w"), indent=2, ensure_ascii=False)
print("ok")
