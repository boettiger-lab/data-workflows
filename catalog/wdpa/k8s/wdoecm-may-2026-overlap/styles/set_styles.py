#!/usr/bin/env python3
"""WD-OECM: default style by governance type, and no README link into raw/ (#879).

    set_styles.py COLLECTION.json README.md style-assets.json

Sets `style-wdoecm-gov-type` (GOV_TYPE, 11 classes) as the default for the PMTiles, demotes the
one-colour `style-wdoecm` to a plain style, and drops the README asset-table row that linked the raw GDB (AGENTS.md Step 1b). Idempotent.
"""
import json
import sys

coll, readme, spec_path = sys.argv[1:4]
doc = json.load(open(coll))
spec = json.load(open(spec_path))
before = json.loads(json.dumps(doc))
doc["assets"].update(spec["set"])
for k, roles in spec["roles"].items():
    doc["assets"][k]["roles"] = roles
# The thumbnail is not redrawn here (vector-thumbnail runs out of memory on this GeoParquet); its
# description keeps naming style-wdoecm, the style it was drawn from, which stays as a plain style.
changed = {k for k in set(before) | set(doc) if before.get(k) != doc.get(k)}
assert changed <= {"assets"}, changed
json.dump(doc, open(coll, "w"), indent=2, ensure_ascii=False)
print("collection:", sorted(changed))

lines = open(readme).read().splitlines(keepends=True)
kept = [l for l in lines if not (l.startswith("| Raw GDB |") and "/raw/" in l)]
assert "/raw/" not in "".join(kept), "README still links into raw/"
open(readme, "w").write("".join(kept))
print(f"README: removed {len(lines) - len(kept)} raw row(s)")
