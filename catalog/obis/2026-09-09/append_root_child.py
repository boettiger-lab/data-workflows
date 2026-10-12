"""Adds the obis-derived child link to the root catalog if it is missing.

    python3 append_root_child.py root.json root-new.json
"""
import json, shutil, sys

src, dst = sys.argv[1:3]
CHILD = {
    "rel": "child",
    "id": "obis-derived",
    "href": "https://s3-west.nrp-nautilus.io/public-obis/stac-collection.json",
    "type": "application/json",
    "title": "OBIS Marine Occurrence Records (global, H3 resolution 8)",
}

root = json.load(open(src))
if any(l.get("href") == CHILD["href"] for l in root["links"]):
    shutil.copyfile(src, dst)
    print("obis-derived already present, unchanged")
else:
    root["links"].append(CHILD)
    json.dump(root, open(dst, "w"), indent=2)
    print("appended obis-derived")
