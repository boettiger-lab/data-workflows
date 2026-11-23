#!/usr/bin/env python3
"""Rewrite the IHO collection's high-seas hex asset for the h8 + cover_frac build (#1016).

    stac_update.py LIVE_COLLECTION OUT_COLLECTION --rows N --km2 A

Edits only the `high-seas-hex` asset (title, description, columns, h3:*) and
the collection-level column dictionary: adds `cover_frac` after `h8` and drops
the h4/h3/h2/h1 entries, which no asset carries once the resolution-4 hex is
replaced. Everything else in the live file is kept, so the publish job can run
this against whatever is live at the time. Fails loudly if an anchor is
missing rather than writing a half-updated file.
"""
import argparse
import json
import sys

ap = argparse.ArgumentParser()
ap.add_argument("live_collection")
ap.add_argument("out_collection")
ap.add_argument("--rows", type=int, required=True, help="hex row count, read from the published hex")
ap.add_argument("--km2", type=float, required=True, help="sum of cover_frac x h3_cell_area, from the hex")
a = ap.parse_args()

HREF = "https://s3-west.nrp-nautilus.io/public-high-seas/iho/high-seas/hex/h0=*/data_00.parquet"

DESCRIPTION = (
    "H3 cells of the World High Seas v2 polygon at resolution 8 (~0.74 km² cells), the resolution of "
    f"the EEZ hex, Hive-partitioned by h0: one row for every resolution-8 cell the high seas overlap, "
    f"{a.rows / 1e6:.1f}M rows, each cell once. Cells on EEZ and coastal boundaries that lie only partly "
    "in the high seas are included, and `cover_frac` gives the share of each cell's area inside the "
    "high seas: 1 for a cell wholly inside, between 0 and 1 on the boundary. Weight a cell by "
    "`cover_frac` when measuring area; an unweighted count of cells overstates the high seas by its "
    "boundary cells. As a mask, `cover_frac = 1` selects cells wholly in "
    "the high seas, and any row selects every cell that touches them. Fractions treat polygon edges as "
    "straight lines in longitude and latitude, as H3 does. The fraction-weighted area of all cells is "
    f"{a.km2 / 1e6:.1f}M km², against {222_496_418 / 1e6:.1f}M km² for the polygon on the WGS 84 "
    "ellipsoid (`area_km2`): H3 cell areas are on a sphere, so per-region areas from the hex run up to "
    "about 0.4% above the ellipsoidal area near the equator and up to about 0.9% below it near the "
    "poles. h0 is the parent of h8 and the partition key; join coarser datasets with "
    "h3_cell_to_parent(h8, r). name, mrgid, source and area_km2 are the single source feature's, "
    "repeated on every row, and area_km2 is the whole polygon's area, not a cell's. This build replaced, "
    "in November 2026, a resolution-4 hex (~1,770 km² cells) that counted every boundary cell as wholly "
    "high seas, which overstated high-seas totals along EEZ boundaries (#1016)."
)

COVER_FRAC = {
    "name": "cover_frac",
    "type": "float",
    "description": ("Share of the h8 cell's area that lies inside the high seas, from just above 0 to 1 "
                    "(1 when the cell is wholly inside). Polygon edges are taken as straight lines in "
                    "longitude and latitude, as in H3. High-seas hex only."),
}

ASSET_COLUMNS = [
    ("_cng_fid", "int64"), ("OGC_FID", "int64"), ("name", "string"), ("mrgid", "int64"),
    ("source", "string"), ("area_km2", "int64"), ("h8", "uint64"), ("cover_frac", "float"), ("h0", "int64"),
]
DROP = {"h4", "h3", "h2", "h1"}

d = json.load(open(a.live_collection))
if "high-seas-hex" not in d.get("assets", {}):
    sys.exit("no high-seas-hex asset in the live collection")
hexa = d["assets"]["high-seas-hex"]
hexa["href"] = HREF
hexa["title"] = "World High Seas v2 H3 Hex Parquet (resolution 8)"
hexa["description"] = DESCRIPTION
hexa["table:columns"] = [{"name": n, "type": t} for n, t in ASSET_COLUMNS]
hexa["h3:native_resolution"] = 8
hexa["h3:parent_resolutions"] = [0]

# Columns still carried by another asset are kept even if listed in DROP.
others = {c["name"] for k, v in d["assets"].items() if k != "high-seas-hex"
          for c in v.get("table:columns", [])}
cols = d.get("table:columns")
if not cols:
    sys.exit("live collection has no table:columns dictionary")
cols = [c for c in cols if c["name"] not in DROP or c["name"] in others]
names = [c["name"] for c in cols]
if "cover_frac" in names:
    cols[names.index("cover_frac")] = COVER_FRAC
else:
    if "h8" not in names:
        sys.exit("no h8 column to place cover_frac after")
    cols.insert(names.index("h8") + 1, COVER_FRAC)
d["table:columns"] = cols

json.dump(d, open(a.out_collection, "w"), indent=2, ensure_ascii=False)
open(a.out_collection, "a").write("\n")
print("ok")
