#!/usr/bin/env python3
"""Apply a default-style fix (#1019) to a live collection, in place.

    set_styles.py COLLECTION.json style-assets.json

Adds the style assets in spec["set"] (built with scripts/default-style.py, each the new default
for its PMTiles file), sets the roles in spec["roles"] (demotes the old one-colour default to a
plain style), and points the thumbnail description at spec["thumbnail"]. Touches only `assets`;
idempotent.
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
if th and spec.get("thumbnail"):
    th["description"] = f"Preview drawn from the collection's default style {spec['thumbnail']}."
changed = {k for k in set(before) | set(doc) if before.get(k) != doc.get(k)}
assert changed <= {"assets"}, changed
json.dump(doc, open(path, "w"), indent=2, ensure_ascii=False)
print("assets:", sorted(k for k in doc["assets"] if before["assets"].get(k) != doc["assets"].get(k)))
