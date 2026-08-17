#!/usr/bin/env python3
"""Walk the NRP STAC tree from the root catalog and emit every collection URL.

Cheap: fetches only JSON docs (catalog.json / stac-collection.json) over HTTPS and
follows `child` links — no data reads. One line per collection:

    <kind>\t<id>\t<self-url>\t<error>

kind is `leaf-data` (has a parquet asset — the data-backed checks apply), `meta`
(only child links), or `leaf-nodata`. Feed the URLs to run-sweep.sh.

Usage:  python3 enumerate-collections.py > collections.tsv
"""
import json, sys, urllib.request
from collections import Counter

ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
seen = {}


def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except Exception as e:  # noqa: BLE001 — record and continue the walk
        return {"__error__": str(e)}


def walk(url):
    if url in seen:
        return
    doc = seen.setdefault(url, fetch(url))
    if "__error__" in doc:
        return
    for link in doc.get("links", []):
        if link.get("rel") == "child" and link.get("href"):
            walk(link["href"])


walk(ROOT)

rows = []
for url, doc in seen.items():
    if "__error__" in doc:
        rows.append(("ERROR", "", url, doc["__error__"]))
        continue
    assets = doc.get("assets", {}) or {}
    has_parquet = any(
        (a.get("type", "") or "").endswith("parquet") or "parquet" in (a.get("href", "") or "")
        for a in assets.values())
    has_children = any(l.get("rel") == "child" for l in doc.get("links", []))
    kind = "leaf-data" if has_parquet else ("meta" if has_children else "leaf-nodata")
    rows.append((kind, doc.get("id", ""), url, ""))

for kind, cid, url, err in sorted(rows):
    print(f"{kind}\t{cid}\t{url}\t{err}")

print(f"# {len(rows)} collections; by kind: {dict(Counter(r[0] for r in rows))}",
      file=sys.stderr)
