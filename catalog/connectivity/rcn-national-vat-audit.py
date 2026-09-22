#!/usr/bin/env python3
"""Gate A for issue #606: the VAT is the complete value set of RCN_National_2024.

`rcn-national-cog.yaml` reclassifies the TNC RCN composite codes to a publishable
`rcn_class` band through a VRT ComplexSource <LUT>. A LUT interpolates linearly between
its entries, so the reclass is exact only if every source pixel is either 0 (the mask
background) or one of the 297 codes the VAT lists. A code the VAT omitted would silently
receive an interpolated class instead of nodata.

`rcn-national-vat-audit.yaml` bincounts the full native 193419x133487 Int32 grid in 16
stripes. This aggregates those stripes and asserts, against the VAT:

  * no mask-valid pixel that is not a VAT code, and no VAT code that is mask-invalid
  * every VAT code present, with its exact `Count`
  * background (value 0 plus the out-of-range ESRI sentinels) accounts for exactly the
    rest of the grid

The raster carries background two ways: blocks entirely outside the mapped footprint
read as 0, while nodata pixels inside partially-covered blocks hold an out-of-range
ESRI Int32 sentinel. Both are mask-invalid and both are outside the VAT, so the LUT's
end guards send them to 255 — but the audit reports the sentinels explicitly rather
than letting an unexplained value ride.

Usage:
    python3 catalog/connectivity/rcn-national-vat-audit.py
"""

import csv
import io
import json
import sys
import urllib.request

BASE = "https://s3-west.nrp-nautilus.io/public-connectivity/raw"
VAT = f"{BASE}/vat/a00000020_vat_RCN_National_2024.csv"
PARTS = [f"{BASE}/vat-audit/part-{i:02d}.json" for i in range(16)]
NX, NY = 193419, 133487
NAMED = {"Not in Network": 0, "Resilient Not in Network": 1}


def fetch(url):
    with urllib.request.urlopen(url) as r:
        return r.read()


def main():
    vat = {}
    labels = {}
    for r in csv.DictReader(io.StringIO(fetch(VAT).decode())):
        v = int(r["Value"])
        cls = int(r["Vals"]) if r["Vals"].strip() else NAMED[r["RCN_DESC_NEW"].strip()]
        vat[v] = (int(float(r["Count"])), cls)
        labels[cls] = r["RCN_DESC_NEW"].strip()

    hist = {}
    oor = {}
    pixels = 0
    valid_from_mask = 0
    valid_not_in_vat = 0
    seen = set()
    for url in PARTS:
        part = json.loads(fetch(url))
        seen.add(part["index"])
        pixels += part["pixels"]
        valid_from_mask += part["valid_from_mask"]
        valid_not_in_vat += part["valid_not_in_vat"]
        for v, n in part["out_of_range_hist"].items():
            oor[int(v)] = oor.get(int(v), 0) + n
        for v, n in part["hist"].items():
            hist[int(v)] = hist.get(int(v), 0) + n

    fail = []
    if seen != set(range(16)):
        fail.append(f"stripes missing: {sorted(set(range(16)) - seen)}")
    if pixels != NX * NY:
        fail.append(f"stripes cover {pixels} pixels, grid is {NX * NY}")
    if valid_not_in_vat:
        fail.append(f"{valid_not_in_vat} mask-valid pixels are not a VAT code")

    unexpected = {v: n for v, n in hist.items() if v != 0 and v not in vat}
    if unexpected:
        fail.append(f"{len(unexpected)} source values absent from the VAT: "
                    f"{dict(list(sorted(unexpected.items()))[:10])}")

    missing = [v for v in vat if v not in hist]
    if missing:
        fail.append(f"{len(missing)} VAT codes absent from the raster: {missing[:10]}")

    mismatched = {v: (hist[v], vat[v][0]) for v in vat
                  if v in hist and hist[v] != vat[v][0]}
    if mismatched:
        fail.append(f"{len(mismatched)} VAT counts disagree with the raster: "
                    f"{dict(list(sorted(mismatched.items()))[:10])}")

    vat_total = sum(c for c, _ in vat.values())
    if valid_from_mask != vat_total:
        fail.append(f"the mask calls {valid_from_mask} pixels valid, the VAT counts "
                    f"{vat_total}")
    oor_total = sum(oor.values())
    background = hist.get(0, 0) + oor_total
    if background != NX * NY - vat_total:
        fail.append(f"background (0 plus sentinels) is {background}, expected "
                    f"{NX * NY - vat_total}")
    # The LUT guards (-2^31, 0, 99999) and (404312, 2^31-1) all emit 255, so every
    # value outside the VAT maps to nodata whatever the sentinel turns out to be.
    inside = [v for v in oor if 0 <= v <= 404311]
    if inside:
        fail.append(f"values reported out of range that are not: {inside[:10]}")

    by_class = {}
    for v, (count, cls) in vat.items():
        by_class[cls] = by_class.get(cls, 0) + count
    print(f"grid            {NX} x {NY} = {NX * NY:,} pixels")
    print(f"mapped          {vat_total:,} ({100 * vat_total / (NX * NY):.2f}%)")
    print(f"mask-valid      {valid_from_mask:,}")
    print(f"background      {background:,} = {hist.get(0, 0):,} zeros "
          f"+ {oor_total:,} sentinel")
    for v, n in sorted(oor.items()):
        print(f"  sentinel {v:>12}  {n:>15,}  -> rcn_class 255 (nodata)")
    print(f"source codes    {len(vat)} -> {len(by_class)} classes\n")
    print(f"{'rcn_class':>9}  {'pixels':>15}  {'share':>7}  label")
    for cls in sorted(by_class):
        print(f"{cls:>9}  {by_class[cls]:>15,}  "
              f"{100 * by_class[cls] / vat_total:>6.3f}%  {labels[cls]}")

    print()
    if fail:
        print("GATE A FAILED")
        for f in fail:
            print(f"  - {f}")
        return 1
    print("GATE A PASSED: the VAT is the complete value set; every count matches.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
