#!/usr/bin/env python3
"""Coral polygons: default style with its reason, and provenance without the raw/ path (#1020).

    set_style_provenance.py COLLECTION.json BUCKET_README.md style-asset.json

Sets `style-polygons` (one colour, with the reason why no attribute is worth colouring by),
and rewrites the provenance sentence in the collection description and the bucket README so
it records the archive's size and sha256 without pointing into raw/ (AGENTS.md Step 1b).
Idempotent.
"""
import json
import re
import sys

coll, readme, spec = sys.argv[1:4]
doc = json.load(open(coll))
before = json.loads(json.dumps(doc))
doc["assets"].update(json.load(open(spec)))

SHA = "09c7fe54c85b365c3968b8945034ebc649389c2832b0ab4b91dd2e50ee3a7124"
OLD = (f"The source archive is kept at `s3://public-coral-reefs/raw/WCMC008_CoralReefs2018_v4_1.zip` "
       f"(220,904,276 bytes, sha256 `{SHA}`).")
NEW = f"The source archive `WCMC008_CoralReefs2018_v4_1.zip` was 220,904,276 bytes, sha256 `{SHA}`."
assert OLD in doc["description"] or NEW in doc["description"], "provenance sentence not found"
doc["description"] = doc["description"].replace(OLD, NEW)
assert "public-coral-reefs/raw/" not in json.dumps(doc), "collection still points into raw/"
changed = {k for k in set(before) | set(doc) if before.get(k) != doc.get(k)}
assert changed <= {"description", "assets"}, changed
json.dump(doc, open(coll, "w"), indent=2, ensure_ascii=False)
print("collection:", sorted(changed))

md = open(readme).read()
OLD_MD = ("The source archive is retained at\n`s3://public-coral-reefs/raw/WCMC008_CoralReefs2018_v4_1.zip`\n"
          f"(220,904,276 bytes, sha256 `{SHA}`).")
NEW_MD = ("The source archive `WCMC008_CoralReefs2018_v4_1.zip` was 220,904,276 bytes,\n"
          f"sha256 `{SHA}`.")
assert OLD_MD in md or NEW_MD in md, "README provenance not found"
md = md.replace(OLD_MD, NEW_MD)
assert "public-coral-reefs/raw/" not in md
open(readme, "w").write(md)
print("README: provenance rewritten")
