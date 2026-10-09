#!/usr/bin/env python3
"""Assemble facts.json for the six #627 layers from machine output, never by eye.

    kubectl -n geo-workflows logs job/wrc-2-make-cogs-rest --tail=-1 > cogs.log
    python3 make_facts.py --cog-log cogs.log --hex-facts hex.json --merge facts.json

`--cog-log` supplies the EXACT COG statistics and the geotransform (the `COGSTATS {...}` lines
that make-cogs-bp-cfl-exposure.yaml prints). `--hex-facts` supplies the measured hex row counts
and cell-space bboxes, as a JSON object keyed by dataset, transcribed from duckdb-geo MCP results.

⚠️ The COG figures here are `raster_stats.py`'s full-resolution blockwise pass, NOT
`ComputeStatistics(True)`. #592 published the approximate ones and had to retract a max that was
28% (CONUS) and 53% (Alaska) low. gen_stac.py feeds `cog_min`/`cog_max`/`cog_mean` straight into
`raster:bands` statistics, so the distinction is the difference between a correct collection and a
wrong one.

⚠️ `bbox` is the HEX footprint, measured from cell centroids, not the COG's geotransform corners.
A COG's corners include its nodata margin; on #586 that was 2.4 degrees out.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

RAW = {
    "wrc-2-bp-conus": "BP_CONUS.tif",
    "wrc-2-bp-ak": "BP_AK.tif",
    "wrc-2-cfl-conus": "CFL_CONUS.tif",
    "wrc-2-cfl-ak": "CFL_AK.tif",
    "wrc-2-exposure-conus": "Exposure_CONUS.tif",
    "wrc-2-exposure-ak": "Exposure_AK.tif",
}

# The file index's published range per theme, for a sanity bound on the measured max.
# ⚠️ NOT the FGDC Logical_Consistency_Report, whose figures are 1st-edition leftovers
# (it says CFL 0-408.2 where the file index says 0-861.7). See BUILD.md.
PUBLISHED_MAX = {"bp": 0.14, "cfl": 861.7, "exposure": 1.0}


def parse_cog_log(path: str) -> dict:
    """{dataset: stats} from the job's own `=== [i] SRC -> DS-cog.tif` + `COGSTATS {...}` lines."""
    out, current = {}, None
    with open(path, errors="replace") as fh:
        for line in fh:
            m = re.search(r"===\s*\[\d+\]\s+\S+\s*->\s*(\S+)-cog\.tif", line)
            if m:
                current = m.group(1)
                continue
            if line.startswith("COGSTATS "):
                if current is None:
                    sys.exit("FATAL: COGSTATS line before any dataset header")
                st = ast.literal_eval(line[len("COGSTATS "):].strip())
                if current in out and out[current] != st:
                    sys.exit(f"FATAL: two differing COGSTATS for {current}; a retry left both")
                out[current] = st
                current = None
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cog-log", required=True)
    ap.add_argument("--hex-facts", required=True,
                    help="JSON {dataset: {rows, bbox}} measured via the duckdb-geo MCP")
    ap.add_argument("--merge", default=os.path.join(HERE, "facts.json"),
                    help="existing facts.json to merge into (the two RPS entries are preserved)")
    a = ap.parse_args()

    cog = parse_cog_log(a.cog_log)
    with open(a.hex_facts) as fh:
        hexf = json.load(fh)

    facts = {}
    if os.path.exists(a.merge):
        with open(a.merge) as fh:
            facts = json.load(fh)

    missing = [d for d in RAW if d not in cog]
    if missing:
        sys.exit(f"FATAL: no COGSTATS for {missing}")

    for ds, raw_name in RAW.items():
        st, hx = cog[ds], hexf.get(ds)
        if hx is None:
            sys.exit(f"FATAL: no measured hex facts for {ds}")
        theme = ds.removeprefix("wrc-2-").rsplit("-", 1)[0]
        if st["min"] < 0:
            sys.exit(f"FATAL: {ds} min {st['min']} < 0 -- sentinel leak, not data")
        if st["max"] > PUBLISHED_MAX[theme] * 1.001:
            sys.exit(f"FATAL: {ds} max {st['max']} exceeds the published "
                     f"{PUBLISHED_MAX[theme]} for {theme}")
        facts[ds] = {
            "raw_name": raw_name,
            "created": hx["created"],
            "cog_min": st["min"],
            "cog_max": st["max"],
            "cog_mean": st["mean"],
            "cog_std": st["std"],
            "cog_valid_px": st["count"],
            "bbox": hx["bbox"],
            "rows": hx["rows"],
        }
        print(f"  {ds:<24} max {st['max']:<22} mean {st['mean']:<22} rows {hx['rows']:,}")

    with open(a.merge, "w") as fh:
        json.dump(facts, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {a.merge} with {len(facts)} datasets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
