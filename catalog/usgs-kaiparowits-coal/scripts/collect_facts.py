#!/usr/bin/env python3
"""Measure the per-coverage facts gen_stac.py needs, from the published objects.

bbox comes from the published GeoParquet via the duckdb-geo MCP (cluster metal, internal
S3), and every `created` timestamp from the object's own Last-Modified header. Nothing is
transcribed from a build log: an asset timestamp is what keeps "which asset came from
which conversion" answerable later.

Usage: collect_facts.py --out /tmp/kaiparowits-facts.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

BUCKET = "public-usgs"
DATASET = "kaiparowits-coal-resources"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"

REPO = pathlib.Path(__file__).resolve().parents[3]


def load_mcp():
    """Reuse verify-stac.py's MCP client rather than keeping a second copy of it."""
    path = REPO / "scripts" / "verify-stac.py"
    spec = importlib.util.spec_from_file_location("verify_stac", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    client = mod.MCPClient()
    client.initialize()
    return client


def last_modified(url: str) -> str:
    """RFC 3339 UTC from the object's Last-Modified header."""
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.headers["Last-Modified"]
    dt = datetime.strptime(raw, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def first_hex_key(cov: str) -> str:
    """One real hex partition file, since the asset href is a glob."""
    url = (f"{BASE}/?list-type=2&prefix={DATASET}/{cov}/hex/&max-keys=100")
    with urllib.request.urlopen(url, timeout=60) as r:
        root = ET.fromstring(r.read())
    ns = {"s3": root.tag.split("}")[0].strip("{")}
    for c in root.findall("s3:Contents", ns):
        key = c.find("s3:Key", ns).text
        if key.endswith(".parquet"):
            return f"{BASE}/{key}"
    raise SystemExit(f"no hex partition found for {cov}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    # Imported here so the coverage list has exactly one definition.
    spec = importlib.util.spec_from_file_location(
        "gen_stac", pathlib.Path(__file__).with_name("gen_stac.py"))
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    coverages = list(gen.COVERAGES)

    mcp = load_mcp()
    union = "\nUNION ALL\n".join(
        f"SELECT '{c}' AS cov, MIN(ST_XMin(geom)) AS xmin, MIN(ST_YMin(geom)) AS ymin, "
        f"MAX(ST_XMax(geom)) AS xmax, MAX(ST_YMax(geom)) AS ymax "
        f"FROM read_parquet('s3://{BUCKET}/{DATASET}/{c}.parquet')"
        for c in coverages)
    rows = mcp.query(union)
    bboxes = {r["cov"]: [round(float(r[k]), 6) for k in ("xmin", "ymin", "xmax", "ymax")]
              for r in rows}

    facts = {}
    for cov in coverages:
        parquet = f"{BASE}/{DATASET}/{cov}.parquet"
        pmtiles = f"{BASE}/{DATASET}/{cov}.pmtiles"
        hexf = first_hex_key(cov)
        created = {
            "parquet": last_modified(parquet),
            "pmtiles": last_modified(pmtiles),
            "hex": last_modified(hexf),
        }
        # The collection is as new as its newest asset.
        created["collection"] = max(created.values())
        facts[cov] = {"bbox": bboxes[cov], "created": created}
        print(f"  {cov:11s} bbox={bboxes[cov]} built={created['collection']}")

    xs = [facts[c]["bbox"] for c in coverages]
    facts["_parent"] = {
        "bbox": [min(b[0] for b in xs), min(b[1] for b in xs),
                 max(b[2] for b in xs), max(b[3] for b in xs)],
        "created": max(facts[c]["created"]["collection"] for c in coverages),
    }
    print(f"  {'_parent':11s} bbox={facts['_parent']['bbox']}")

    with open(args.out, "w") as fh:
        json.dump(facts, fh, indent=2)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
