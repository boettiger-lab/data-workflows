"""Pull every feature of an ArcGIS MapServer layer as GeoJSON (EPSG:4326).

Used by the HI-GLEN stage-raw jobs (#837 osds, #843 benthic-habitat-2007). The layers cap a
query at maxRecordCount (1000), so this lists every objectid first and then fetches them in
batches by id, which cannot skip or repeat a feature the way offset paging can when the
service reorders. It asserts the fetched count equals the layer's own count.

    python3 stage_arcgis.py <layer-url> <out.geojson>
"""
import json
import sys
import time
import urllib.parse
import urllib.request

BATCH = 250


def call(url, params, tries=6):
    data = urllib.parse.urlencode(params).encode()
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, data=data, timeout=300) as r:
                out = json.load(r)
            if "error" in out:
                raise RuntimeError(out["error"])
            return out
        except Exception as e:  # noqa: BLE001 - retry any transport or service error
            if i == tries - 1:
                raise
            print(f"retry {i + 1} after {e}", file=sys.stderr)
            time.sleep(10 * (i + 1))


def pull(layer, out_path):
    q = layer + "/query"
    count = call(q, {"where": "1=1", "returnCountOnly": "true", "f": "json"})["count"]
    ids = sorted(call(q, {"where": "1=1", "returnIdsOnly": "true", "f": "json"})["objectIds"])
    assert len(ids) == count == len(set(ids)), (len(ids), count)
    feats = []
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        fc = call(q, {"objectIds": ",".join(map(str, chunk)), "outFields": "*",
                      "outSR": "4326", "returnGeometry": "true", "f": "geojson"})
        assert not fc.get("exceededTransferLimit"), "transfer limit hit inside an id batch"
        assert len(fc["features"]) == len(chunk), (i, len(fc["features"]), len(chunk))
        feats.extend(fc["features"])
    assert len(feats) == count
    with open(out_path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)
    print(f"{layer}: {len(feats)} features -> {out_path}")
    return feats


if __name__ == "__main__":
    pull(sys.argv[1], sys.argv[2])
