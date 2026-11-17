#!/usr/bin/env python3
"""Set citation fields on LIVE collections, in place (#822).

    apply.py fixes.json COLLECTION_PATH COLLECTION.json

Each fix (keyed by `collection`, the path inside the bucket host) may set `sci:citation`,
`sci:doi` and `sci:publications`, and carries the `source` its text came from. Optional repairs:
`replace_doi` (a wrong dataset DOI: its cite-as links move to the new `sci:doi`),
`provider_rename` and `link_href_fix`. Adds the scientific extension when missing.

Touches nothing else. An existing `sci:citation` that differs is left alone and reported, so a
citation someone wrote by hand is never overwritten; a second run changes nothing.
"""
import json
import sys

SCI = "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"
fixes, coll, path = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
f = next((x for x in fixes if x["collection"] == coll), None)
if f is None:
    sys.exit(f"{coll}: no fix listed")
doc = json.load(open(path))
did = []

have = doc.get("sci:citation")
if have and have != f["sci:citation"]:
    print(f"{coll}: keeps its existing sci:citation (differs from the fix): {have[:100]}")
elif not have:
    doc["sci:citation"] = f["sci:citation"]
    did.append("citation")
if f.get("sci:doi") and doc.get("sci:doi") != f["sci:doi"]:
    old = f.get("replace_doi")
    if doc.get("sci:doi") not in (None, old):
        print(f"{coll}: keeps its existing sci:doi {doc['sci:doi']}")
    else:
        doc["sci:doi"] = f["sci:doi"]
        did.append("doi")
        for l in doc.get("links", []):
            if l.get("rel") == "cite-as" and old and old.lower() in l.get("href", "").lower():
                l["href"] = "https://doi.org/" + f["sci:doi"]
pubs = doc.get("sci:publications") or []
known = {(p.get("doi") or "").lower() for p in pubs}
for p in f.get("sci:publications", []):
    if (p.get("doi") or "").lower() not in known:
        pubs.append(p)
        did.append("publication")
if pubs:
    doc["sci:publications"] = pubs
for p in doc.get("providers", []):
    new = (f.get("provider_rename") or {}).get(p.get("name"))
    if new:
        p["name"] = new
        did.append("provider")
for l in doc.get("links", []):
    new = (f.get("link_href_fix") or {}).get(l.get("href"))
    if new:
        l["href"] = new
        did.append("link")
if did and SCI not in doc.setdefault("stac_extensions", []):
    doc["stac_extensions"].append(SCI)
with open(path, "w") as fh:
    fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
print(f"{coll}: {', '.join(did) or 'unchanged'}")
