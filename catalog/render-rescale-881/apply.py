#!/usr/bin/env python3
"""Set the corrected rescale (and colormap) on the renders listed in fixes.json, in place (#881).

    apply.py fixes.json COLLECTION_PATH COLLECTION.json

The fallback renders stretched viridis over metadata statistics that did not match the data:
for 68 of 166 the range sat far outside the COG's 2nd–98th percentile (TiTiler
/cog/statistics, 2026-11-14), so most pixels drew at one end of the ramp. Each listed render
gets its percentile range rounded to two significant figures; directions (degrees) get 0–360
on the cyclic `twilight`, and the eastward/northward currents a symmetric `rdbu_r`. Only
`rescale` and `colormap_name` change, and a render whose live `rescale` no longer equals
`was` is left alone, so a later hand edit is never overwritten.
"""
import json
import sys

fixes, coll, path = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
doc = json.load(open(path))
for f in (f for f in fixes if f["collection"] == coll):
    r = (doc.get("renders") or {}).get(f["render"])
    if r is None:
        print(f"{coll} {f['render']}: missing, skipped"); continue
    if r.get("rescale") == f["rescale"] and r.get("colormap_name") == f.get("colormap_name", r.get("colormap_name")):
        print(f"{coll} {f['render']}: already set"); continue
    if [[round(x, 3) for x in pair] for pair in r.get("rescale") or []] != [[round(x, 3) for x in pair] for pair in f["was"]]:
        print(f"{coll} {f['render']}: live rescale {r.get('rescale')} is not {f['was']}, skipped"); continue
    r["rescale"] = f["rescale"]
    if "colormap_name" in f:
        r["colormap_name"] = f["colormap_name"]
    print(f"{coll} {f['render']}: {f['was']} -> {f['rescale']} {f.get('colormap_name', '')}")
with open(path, "w") as fh:
    fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
