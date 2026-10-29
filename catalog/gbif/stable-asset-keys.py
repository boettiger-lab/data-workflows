#!/usr/bin/env python3
"""Give the gbif-derived collection's release assets stable keys (#780).

The collection id `gbif-derived` is the stable entry point for GBIF; the data stays under
dated prefixes (`public-gbif/2026-09/...`). Keys like `gbif-hex-2026-09` put the release back
into the lookup, so a consumer reading the STAC still had to change code at every refresh.
This drops the trailing release from each key; the release stays in the href, the asset
title, and the collection `version`.

Idempotent, and run it again after each refresh, once the hrefs point at the new prefix.

  python3 stable-asset-keys.py            # live collection -> /tmp/gbif-stac-collection.json
  python3 stable-asset-keys.py --in FILE
"""
import argparse
import json
import re
import urllib.request

URL = "https://s3-west.nrp-nautilus.io/public-gbif/stac-collection.json"
OUT = "/tmp/gbif-stac-collection.json"
DATED_KEY = re.compile(r"^(gbif-.+)-(\d{4}-\d{2})$")
DATED_HREF = re.compile(r"/public-gbif/(\d{4}-\d{2})/")

ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="src")
ap.add_argument("--out", default=OUT)
args = ap.parse_args()

if args.src:
    with open(args.src) as f:
        coll = json.load(f)
else:
    with urllib.request.urlopen(URL) as r:
        coll = json.load(r)

assets = {}
for key, asset in coll["assets"].items():
    m = DATED_KEY.match(key)
    if m:
        h = DATED_HREF.search(asset["href"])
        # Never let a key's release disagree with where the asset actually points.
        assert h and h.group(1) == m.group(2), f"{key}: href {asset['href']} is not release {m.group(2)}"
        key = m.group(1)
    assert key not in assets, f"two assets map to {key}"
    assets[key] = asset
coll["assets"] = assets

releases = {h.group(1) for a in assets.values() if (h := DATED_HREF.search(a["href"]))}
assert len(releases) == 1, f"assets point at more than one release: {sorted(releases)}"
assert coll["version"].startswith(releases.pop()), "collection version disagrees with the asset prefixes"

with open(args.out, "w") as f:
    json.dump(coll, f, indent=2, ensure_ascii=False)
    f.write("\n")
print(args.out, sorted(assets))
