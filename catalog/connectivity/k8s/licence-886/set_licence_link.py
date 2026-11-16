#!/usr/bin/env python3
"""Point rcn-national's licence link at the copy of TNC's terms published beside it (#886).

    set_licence_link.py COLLECTION.json

TNC's terms ("TNC Geospatial Data Terms of Use: sublicensing", revised 2023-01-12) live on a Box
share with downloads disabled, so the `.docx` cannot be copied. Carl supplied an image of the full
four-page document, published unchanged as tnc-terms-of-use.png. That copy becomes the first
`license` link; the Box share stays as a second one for readers who can open it. Changes the
`license` links only, and is idempotent.
"""
import json
import sys

COPY = "https://s3-west.nrp-nautilus.io/public-connectivity/rcn-national/tnc-terms-of-use.png"
TITLE = "TNC Geospatial Data Terms of Use: sublicensing (non-commercial, revised 2023-01-12)"

path = sys.argv[1]
doc = json.load(open(path))
links = [l for l in doc["links"] if l.get("rel") != "license"]
box = [l for l in doc["links"] if l.get("rel") == "license" and "box.com" in l.get("href", "")]
if not box:
    sys.exit(f"{path}: no Box licence link found, refusing to change the licence links")
new = [{"rel": "license", "href": COPY, "type": "image/png",
        "title": TITLE + ", copy published with the data"},
       {**box[0], "title": TITLE + ", TNC's Box share"}]
doc["links"] = links + new
with open(path, "w") as fh:
    fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
print(f"{path}: licence links -> {COPY} + Box share")
