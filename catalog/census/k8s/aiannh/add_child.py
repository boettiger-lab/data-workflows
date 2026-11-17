#!/usr/bin/env python3
"""Add a child link to a live parent catalog, in place, if it is not there (#944).

    add_child.py PARENT.json CHILD_HREF TITLE
"""
import json
import sys

path, href, title = sys.argv[1:4]
doc = json.load(open(path))
if not any(l.get("rel") == "child" and l.get("href") == href for l in doc["links"]):
    doc["links"].append({"rel": "child", "href": href, "type": "application/json", "title": title})
    print(f"added child {href}")
else:
    print(f"child already listed: {href}")
with open(path, "w") as fh:
    fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
