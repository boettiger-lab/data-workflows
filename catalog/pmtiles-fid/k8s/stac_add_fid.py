#!/usr/bin/env python3
"""#735: add the lean `_cng_fid` column (name + type) to PMTiles assets' table:columns.

    stac_add_fid.py <stac-collection-url> <asset-key>... --out FILE
"""
import argparse, json, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("url"); ap.add_argument("assets", nargs="+"); ap.add_argument("--out", required=True)
a = ap.parse_args()
d = json.load(urllib.request.urlopen(a.url))
for k in a.assets:
    cols = d["assets"][k].setdefault("table:columns", [])
    if not any(c.get("name") == "_cng_fid" for c in cols):
        cols.insert(0, {"name": "_cng_fid", "type": "int64"})
        print("added", k)
json.dump(d, open(a.out, "w"), indent=2, ensure_ascii=False)
