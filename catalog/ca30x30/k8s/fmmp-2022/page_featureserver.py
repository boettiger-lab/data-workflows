#!/usr/bin/env python3
"""Page the FMMP 2022 ArcGIS FeatureServer into GeoJSON pages (#615).

The ArcGIS Hub export API for this item serves a truncated cached artifact
(45,285 of 127,133 features, 13 of 38 counties), so the service itself is the
only usable source. Paging is ordered by OBJECTID so offsets are stable, and the
assembled total is checked against the service's own returnCountOnly before
anything is written -- a short read must fail the job, not produce a small file.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SERVICE = (
    "https://gis.conservation.ca.gov/server/rest/services/DLRP/"
    "CaliforniaImportantFarmland_2022/FeatureServer/0/query"
)
PAGE_SIZE = 2000  # the service's maxRecordCount
OUT_DIR = "/tmp/pages"
COUNT_FILE = "/tmp/expected_count.txt"
RETRIES = 6
TIMEOUT = 300


def fetch(params):
    """GET the query endpoint with retries; return the parsed JSON body."""
    url = f"{SERVICE}?{urllib.parse.urlencode(params)}"
    last = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
                body = r.read()
            payload = json.loads(body)
            # ArcGIS reports errors with HTTP 200 and an "error" member.
            if isinstance(payload, dict) and "error" in payload:
                raise RuntimeError(f"service error: {payload['error']}")
            return payload
        except (urllib.error.URLError, TimeoutError, ValueError, RuntimeError) as e:
            last = e
            backoff = 2 ** attempt
            print(f"  attempt {attempt + 1}/{RETRIES} failed ({e}); retrying in {backoff}s",
                  flush=True)
            time.sleep(backoff)
    raise RuntimeError(f"giving up on {url}: {last}")


def main():
    expected = fetch({"where": "1=1", "returnCountOnly": "true", "f": "json"})["count"]
    print(f"Service reports {expected} features", flush=True)
    if expected <= 0:
        sys.exit("FATAL: service reports no features")

    os.makedirs(OUT_DIR, exist_ok=True)
    for stale in os.listdir(OUT_DIR):
        os.remove(os.path.join(OUT_DIR, stale))

    total = 0
    oids = set()
    page = 0
    offset = 0
    while offset < expected:
        payload = fetch({
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "orderByFields": "OBJECTID",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
            "f": "geojson",
        })
        feats = payload.get("features") or []
        if not feats:
            sys.exit(f"FATAL: empty page at offset {offset} with {total}/{expected} collected")

        path = os.path.join(OUT_DIR, f"page_{page:04d}.geojson")
        with open(path, "w") as fh:
            json.dump({"type": "FeatureCollection", "features": feats}, fh)

        oids.update(f["properties"]["OBJECTID"] for f in feats)
        total += len(feats)
        page += 1
        offset += len(feats)
        print(f"  page {page}: +{len(feats)} -> {total}/{expected}", flush=True)

    print(f"Collected {total} features in {page} pages; {len(oids)} distinct OBJECTIDs")
    if total != expected:
        sys.exit(f"FATAL: collected {total} features, service reports {expected}")
    if len(oids) != expected:
        sys.exit(f"FATAL: {len(oids)} distinct OBJECTIDs for {expected} features "
                 "-- paging returned duplicates, offsets are not stable")

    with open(COUNT_FILE, "w") as fh:
        fh.write(str(expected))


if __name__ == "__main__":
    main()
