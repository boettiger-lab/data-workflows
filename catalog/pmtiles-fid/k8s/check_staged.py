#!/usr/bin/env python3
"""#735: compare each staged PMTiles footer with the live one (range reads only).

Pass: same layer ids and zoom range, staged fields = live fields + _cng_fid
(minus the dropped _ogr_geometry__bbox.* artifact).
"""
import gzip, json, struct, sys, urllib.request
from assets import ASSETS

BASE = "https://s3-west.nrp-nautilus.io"
ITEMS = [(a["bucket"], a["key"]) for a in ASSETS] + [("public-hazard", "flood-hazard.pmtiles")]

def footer(u):
    def get(o, l):
        r = urllib.request.Request(u, headers={"Range": f"bytes={o}-{o+l-1}"})
        return urllib.request.urlopen(r, timeout=60).read()
    h = get(0, 127)
    mo, ml = struct.unpack_from("<QQ", h, 24)
    m = get(mo, ml)
    md = json.loads(gzip.decompress(m) if h[97] == 2 else m)
    vl = md["vector_layers"]
    return [l["id"] for l in vl], (h[100], h[101]), {f for l in vl for f in l.get("fields", {})}

bad = 0
for b, k in ITEMS:
    if len(sys.argv) > 1 and k not in sys.argv[1:]:
        continue
    try:
        sl, sz, sf = footer(f"{BASE}/{b}/staging/735-fid/{k}")
    except Exception as e:
        print(f"PENDING {b}/{k}: {e}"); bad += 1; continue
    # after the swap the live file is the new one; compare against the backup then
    try:
        ll, lz, lf = footer(f"{BASE}/{b}/staging/735-nofid-backup/{k}")
    except Exception:
        ll, lz, lf = footer(f"{BASE}/{b}/{k}")
    lf = {f for f in lf if not f.startswith("_ogr_geometry__bbox")}
    ok = sl == ll and sz == lz and sf == lf | {"_cng_fid"}
    bad += not ok
    print(("OK  " if ok else "DIFF"), f"{b}/{k}", sl, sz,
          "" if ok else f"live={ll}{lz} +{sorted(sf - lf)} -{sorted(lf - sf)}")
sys.exit(1 if bad else 0)
