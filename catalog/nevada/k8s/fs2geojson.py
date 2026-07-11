#!/usr/bin/env python3
"""Paginate an ArcGIS FeatureServer layer/table to a local GeoJSON (spatial) or
newline-JSON->file (table). Used to stage SWAP 2025 sources that lack a working
ArcGIS Hub `downloads/data` export (#381). Pages via resultOffset to stay under
maxRecordCount and avoid server timeouts on large geometry.

Usage:
  fs2geojson.py <layer_query_url_base> <out_path> [--page N] [--table]
  <layer_query_url_base> = .../FeatureServer/<idx>   (no /query)
"""
import json, sys, urllib.parse, urllib.request

def fetch(url):
    with urllib.request.urlopen(url, timeout=180) as r:
        return json.load(r)

def main():
    base = sys.argv[1].rstrip("/")
    out = sys.argv[2]
    page = 500
    table = False
    for i, a in enumerate(sys.argv):
        if a == "--page":
            page = int(sys.argv[i + 1])
        if a == "--table":
            table = True
    fmt = "json" if table else "geojson"
    feats = []
    offset = 0
    while True:
        params = {
            "where": "1=1", "outFields": "*", "outSR": "4326",
            "f": fmt, "resultOffset": offset, "resultRecordCount": page,
            "returnGeometry": "false" if table else "true",
        }
        url = f"{base}/query?" + urllib.parse.urlencode(params)
        d = fetch(url)
        if table:
            batch = [f["attributes"] for f in d.get("features", [])]
        else:
            batch = d.get("features", [])
        feats.extend(batch)
        exceeded = d.get("properties", {}).get("exceededTransferLimit") or d.get("exceededTransferLimit")
        print(f"  offset {offset}: +{len(batch)} (total {len(feats)})", file=sys.stderr)
        if len(batch) < page and not exceeded:
            break
        if not batch:
            break
        offset += len(batch)
    if table:
        with open(out, "w") as fh:
            for row in feats:
                fh.write(json.dumps(row) + "\n")
    else:
        fc = {"type": "FeatureCollection", "features": feats}
        with open(out, "w") as fh:
            json.dump(fc, fh)
    print(f"wrote {len(feats)} records -> {out}", file=sys.stderr)

if __name__ == "__main__":
    main()
