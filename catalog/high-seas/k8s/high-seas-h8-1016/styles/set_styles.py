#!/usr/bin/env python3
"""Apply the #1016 default-style fixes to the live iho collection, in place.

    set_styles.py COLLECTION.json style-assets.json

Sets the `style-eez-pol-type` asset (EEZ coloured by POL_TYPE, the new default for the EEZ
PMTiles) and the `style-high-seas` asset (one colour, with the reason), demotes `style-eez` to
a plain style, and points the thumbnail description at the new default. Built with
scripts/default-style.py; idempotent.
"""
import json
import sys

path, spec_path = sys.argv[1:3]
doc = json.load(open(path))
spec = json.load(open(spec_path))
before = json.loads(json.dumps(doc))
for k, a in spec["set"].items():
    doc["assets"][k] = a
for k, roles in spec["roles"].items():
    doc["assets"][k]["roles"] = roles
th = doc["assets"].get("thumbnail")
if th:
    th["description"] = "Preview drawn from the collection's default style style-eez-pol-type."
changed = {k for k in set(before) | set(doc) if before.get(k) != doc.get(k)}
assert changed <= {"assets"}, changed
json.dump(doc, open(path, "w"), indent=2, ensure_ascii=False)
print("assets:", sorted(k for k in doc["assets"] if before["assets"].get(k) != doc["assets"].get(k)))
