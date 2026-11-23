#!/usr/bin/env python3
"""Correct the licence metadata of LIVE collections, in place (#949).

    apply.py fixes.json COLLECTION_PATH COLLECTION.json

Each fix (keyed by `collection`, the path inside the bucket host) sets `license`, replaces every
`rel: license` link with `license_links`, applies `description_replace` ([old, new] pairs; an
`old` that is absent is reported, never guessed at) and appends `description_append` once.
Each fix carries the `evidence` its terms came from. Touches nothing else; a second run changes
nothing.
"""
import json
import sys

fixes, coll, path = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
f = next((x for x in fixes if x["collection"] == coll), None)
if f is None:
    sys.exit(f"{coll}: no fix listed")
doc = json.load(open(path))
did = []

if doc.get("license") != f["license"]:
    doc["license"] = f["license"]
    did.append("license")
links = doc.setdefault("links", [])
old = [l for l in links if l.get("rel") == "license"]
if old != f["license_links"]:
    doc["links"] = [l for l in links if l.get("rel") != "license"] + f["license_links"]
    did.append("license link")
desc = doc.get("description", "")
for a, b in f.get("description_replace", []):
    if a in desc:
        desc = desc.replace(a, b)
        did.append("description")
    elif b not in desc:
        print(f"{coll}: description lacks {a!r}; left as is")
add = f.get("description_append")
if add and add not in desc:
    desc = desc.rstrip() + "\n\n" + add
    did.append("terms")
doc["description"] = desc
with open(path, "w") as fh:
    fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
print(f"{coll}: {', '.join(did) or 'unchanged'}")
