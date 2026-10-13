#!/usr/bin/env python3
"""Assemble `facts.json` for gen_stac.py from measured job output.

Every number that describes the ingested data reaches the published STAC through this script, so
the transcription is mechanical rather than by eye. That matters: on the sibling wrc-2 build,
hand-carried statistics taken from GDAL's overview-backed `approx_ok` path reached the published
`raster:bands` with the maximum 28% low before anyone noticed.

Inputs:
  --cog-facts <file>   the `FACTS {...}` lines from `kubectl logs job/wrc-2-pa-cog-facts`
                       (exact blockwise statistics, measured against the PUBLISHED COG)
  --hex-facts <file>   JSON, `{<dataset>: {"rows": n, "bbox": [...], ...}}`, measured against the
                       published hex parquet with the duckdb-geo MCP

⚠️ The collection bbox comes from the HEX, not from the COG. A COG's geotransform gives the
reprojected *grid* extent, and an Albers -> WGS84 warp bulges that box well past the data: the
CONUS grid reaches 22.43N / 128.39W, hundreds of km into the Gulf of Mexico and the Pacific, where
this layer has no pixels at all. The sibling collections in this bucket (`wrc-2-rps-*`,
`whp-2023-*`) all publish a data extent, and HURisk's is narrower still since it is defined only
where housing-unit density is greater than zero. The grid extent is kept as `cog_grid_bbox` for the
record, and is not what `extent.spatial` is built from.

Static per-dataset facts -- the staged raw's filename and the SOURCE nodata sentinel, which is
what the provenance paragraph quotes -- live in STATIC below. They are properties of the upstream
publication, not of a build, and each was measured in `wrc-2-pa-stage-raw`.

    python3 make_facts.py --cog-facts /tmp/cog-facts.log --hex-facts /tmp/hex-facts.json > facts.json
"""
from __future__ import annotations

import argparse
import json
import sys

# `created` is the published COG's S3 Last-Modified, read from the object itself.
STATIC = {
    "wrc-2-pa-hurisk-conus": {
        "raw_name": "HURisk_CONUS.tif",
        # Int32 band. NOT -9999: this publication uses eight different sentinels.
        "src_nodata_text": "-2147483648",
        "created": "2026-09-16T22:19:14Z",
    },
    "wrc-2-pa-hurisk-ak": {
        "raw_name": "HURisk_AK.tif",
        "src_nodata_text": "-2147483648",
        "created": "2026-09-16T22:05:11Z",
    },
    "wrc-2-pa-huexposure-conus": {
        "raw_name": "HUExposure_CONUS.tif",
        # Float32 band; -FLT_MAX, which survives widening to float64 exactly.
        "src_nodata_text": "-3.4028235e+38",
        "created": "2026-09-17T17:44:03Z",
    },
    "wrc-2-pa-huexposure-ak": {
        "raw_name": "HUExposure_AK.tif",
        "src_nodata_text": "-3.4028235e+38",
        "created": "2026-09-16T22:28:37Z",
    },
}

# Source pixel sums, measured in make-cogs.yaml before the warp. For a `sum` theme this is the
# left-hand side of #611's conservation invariant and is carried into facts.json so the check can
# be re-run from committed evidence.
SRC_SUM = {
    "wrc-2-pa-huexposure-conus": 50484.404891164275,
    "wrc-2-pa-huexposure-ak": 325.4611482655238,
}

REQUIRED = ("bbox", "cog_min", "cog_max", "cog_mean", "created", "raw_name", "rows",
            "src_nodata_text")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cog-facts", required=True)
    ap.add_argument("--hex-facts", required=True)
    args = ap.parse_args()

    facts: dict = {}
    for line in open(args.cog_facts):
        if line.startswith("FACTS "):
            for ds, f in json.loads(line[len("FACTS "):]).items():
                # The grid extent is recorded but is NOT the published bbox -- see the header.
                f["cog_grid_bbox"] = f.pop("bbox")
                facts.setdefault(ds, {}).update(f)

    for ds, f in json.load(open(args.hex_facts)).items():
        facts.setdefault(ds, {}).update(f)

    for ds, st in STATIC.items():
        facts.setdefault(ds, {}).update(st)
    for ds, s in SRC_SUM.items():
        if ds in facts:
            facts[ds]["src_sum"] = s

    bad = False
    for ds in sorted(facts):
        missing = [k for k in REQUIRED if k not in facts[ds]]
        if missing:
            print(f"FATAL: {ds} is missing {missing}", file=sys.stderr)
            bad = True
        # The invariant, checked here so a facts.json that fails it cannot be published.
        if "src_sum" in facts[ds] and "cog_sum" in facts[ds]:
            rel = abs(facts[ds]["cog_sum"] - facts[ds]["src_sum"]) / facts[ds]["src_sum"]
            print(f"  {ds}: COG sum vs source sum  rel {rel:.3e}", file=sys.stderr)
            if rel > 1e-5:
                print(f"FATAL: {ds} did not conserve its total across the warp", file=sys.stderr)
                bad = True
    if bad:
        return 1

    json.dump(facts, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
