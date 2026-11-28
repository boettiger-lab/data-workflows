"""Download the Ramsar Secretariat's site boundaries and centroids (RSIS GeoServer WFS) onto the bundle PVC,
once, so the bundle and the recomputed golds use the same bytes. Layers ramsar_sdi:features_published
(polygons) and ramsar_sdi:features_centroid_published (points).
The server ends a response at about 10 MB with no error, so the layers are fetched in pages sorted by
ramsarid, v_idris: 100 features, halved down to 1 whenever a page does not parse as JSON (a few sites have
very detailed boundaries). The merged collection must hold numberMatched features.
usage: python3 rsis_download.py <out_dir>

Copied from glen-benchmark no-harness/gold/audit/scripts/rsis_download.py (same paging and
checks), with the output directory as an argument, for the Ramsar rebuild (#1074).
"""
import os, json, time, hashlib, datetime, urllib.request
B = ("https://rsis.ramsar.org/geoserver/wfs?service=WFS&version=2.0.0&request=GetFeature"
     "&outputFormat=application/json&sortBy=ramsarid,v_idris&typeNames=")
PAGE = 100
import sys
d = sys.argv[1]; os.makedirs(d, exist_ok=True)


def fetch(url):
    """One page, or None if the server cut it off."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.loads(r.read())
        except ValueError:
            return None                               # truncated: caller shrinks the page
        except OSError as e:
            print(f"  retry {attempt + 1}: {str(e)[:100]}", flush=True)
            time.sleep(15 * (attempt + 1))
    raise SystemExit(f"failed: {url}")


for layer, name in (("ramsar_sdi:features_published", "features_published.geojson"),
                    ("ramsar_sdi:features_centroid_published", "features_centroid_published.geojson")):
    dest = os.path.join(d, name)
    total = fetch(B + layer + "&count=1")["numberMatched"]
    feats, start = [], 0
    while start < total:
        n = PAGE
        while True:
            page = fetch(f"{B}{layer}&count={n}&startIndex={start}")
            if page is not None:
                break
            if n == 1:
                raise SystemExit(f"{name}: feature at index {start} alone exceeds the server's response limit")
            n = max(1, n // 2)
        feats += page["features"]
        start += n
        print(f"{name}: {len(feats)} of {total} (page {n})", flush=True)
    ids = {f.get("id") for f in feats}
    if len(feats) != total or len(ids) != total:
        raise SystemExit(f"{name}: {len(feats)} features, {len(ids)} distinct ids, server says {total}")
    data = json.dumps({"type": "FeatureCollection", "numberMatched": total, "features": feats}).encode()
    open(dest + ".part", "wb").write(data)
    os.replace(dest + ".part", dest)
    print(f"{name}: {total} features, {len(data):,} bytes, sha256 {hashlib.sha256(data).hexdigest()}, "
          f"{datetime.date.today()}", flush=True)
