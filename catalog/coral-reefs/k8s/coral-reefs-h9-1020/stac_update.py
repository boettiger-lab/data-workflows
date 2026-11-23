#!/usr/bin/env python3
"""Rewrite the coral reef polygons' hex asset for the h9 + cover_frac build (#1020).

    stac_update.py LIVE_COLLECTION OUT_COLLECTION --rows N --km2 A --km2-capped C \
        [--readme LIVE_README OUT_README]

Edits only the `polygons-hex` asset (title, description, columns, h3:*) and the
collection-level column dictionary: adds `h9` before `h8` and `cover_frac`
after `h9`, and rewrites the `h8` entry, which is now a parent. Everything else
in the live file is kept, so the publish job can run this against whatever is
live at the time. Fails loudly if an anchor is missing rather than writing a
half-updated file.

With --readme, also rewrites the bucket README's "### H3 hex" paragraph, which
describes the polygon hex, and fails if that paragraph is not found.
"""
import argparse
import json
import sys

ap = argparse.ArgumentParser()
ap.add_argument("live_collection")
ap.add_argument("out_collection")
ap.add_argument("--rows", type=int, required=True, help="hex row count, read from the published hex")
ap.add_argument("--km2", type=float, required=True, help="sum of cover_frac x h3_cell_area(h9), from the hex")
ap.add_argument("--km2-capped", type=float, required=True,
                help="sum over h9 cells of least(sum(cover_frac), 1) x cell area, from the hex")
ap.add_argument("--readme", nargs=2, metavar=("LIVE_README", "OUT_README"))
a = ap.parse_args()

HREF = "https://s3-west.nrp-nautilus.io/public-coral-reefs/unep-wcmc-coral-reefs/polygons/hex/h0=*/data_0.parquet"
POLY_KM2 = 151_390  # sum of ST_Area_Spheroid over the 17,504 polygons

DESCRIPTION = (
    "H3 cells of the reef polygons at resolution 9 (~0.105 km² cells), Hive-partitioned by h0: one row "
    f"for every (reef polygon, resolution-9 cell) pair where the polygon overlaps the cell, {a.rows / 1e6:.1f}M "
    "rows. Reefs are narrow, so most cells lie only partly inside a reef: `cover_frac` gives the share of the "
    "cell's area inside that polygon, 1 for a cell wholly inside, between 0 and 1 on the reef edge. Weight a "
    "cell by `cover_frac` when measuring area; an unweighted count of cells overstates reef area, since most rows "
    "are partial edge cells. Reef polygons overlap one another, so one cell can carry rows from several reefs whose fractions sum "
    "above 1: for total reef area, sum `cover_frac` per h9 and cap it at 1 before weighting by cell area. "
    f"Summed that way the hex gives {a.km2_capped:,.0f} km²; without the cap {a.km2:,.0f} km², against "
    f"{POLY_KM2:,} km² for the polygons on the WGS 84 ellipsoid (H3 cell areas are on a sphere, about 0.3% "
    "larger at reef latitudes). Fractions treat polygon edges as straight lines in longitude and latitude, as "
    "H3 does. For the area method, see the catalog's H3 guide.\n\n"
    "h8 and h0 are the parents of h9; h0 is the partition key. To join a dataset at h8 or coarser, take the "
    "parent and keep weighting each h9 row by `cover_frac` rather than counting cells. Feature counts come from "
    "COUNT(DISTINCT _cng_fid). Every attribute column describes the whole feature and is repeated on every "
    "cell that feature covers, so de-duplicate on _cng_fid before summarising one; GIS_AREA_K additionally "
    "repeats across features, as described on the GeoParquet asset. This build replaced, in November 2026, a "
    "resolution-8 hex that assigned each cell to a reef by its centre with no coverage fraction, which "
    "overstated reef area by about half (#1020)."
)

H9 = {"name": "h9", "type": "uint64",
      "description": "H3 cell identifier at resolution 9, the hex's native resolution."}
COVER_FRAC = {
    "name": "cover_frac",
    "type": "float",
    "description": ("Share of the h9 cell's area that lies inside this reef polygon, from just above 0 to 1 "
                    "(1 when the cell is wholly inside). Reef polygons overlap, so fractions from different "
                    "reefs on one cell can sum above 1; cap the per-cell sum at 1 for total reef area. "
                    "Polygon edges are taken as straight lines in longitude and latitude, as in H3. Hex only."),
}
H8 = {"name": "h8", "type": "uint64",
      "description": "H3 cell identifier at resolution 8, the parent of h9, for joins with datasets at h8."}

ATTRS = [("LAYER_NAME", "string"), ("OGC_FID", "int64"), ("METADATA_I", "double"), ("ORIG_NAME", "string"),
         ("NAME", "string"), ("FAMILY", "string"), ("GENUS", "string"), ("SPECIES", "string"),
         ("DATA_TYPE", "string"), ("SURVEY_MET", "string"), ("START_DATE", "string"), ("END_DATE", "string"),
         ("DATE_TYPE", "string"), ("VERIF", "string"), ("LOC_DEF", "string"), ("GIS_AREA_K", "double"),
         ("REP_AREA_K", "string"), ("Shape_Leng", "double"), ("Shape_Area", "double"), ("_cng_fid", "int64")]
ASSET_COLUMNS = ATTRS + [("h9", "uint64"), ("cover_frac", "float"), ("h8", "uint64"), ("h0", "int64")]

d = json.load(open(a.live_collection))
if "polygons-hex" not in d.get("assets", {}):
    sys.exit("no polygons-hex asset in the live collection")
hexa = d["assets"]["polygons-hex"]
hexa["href"] = HREF
hexa["title"] = "Global Distribution of Coral Reefs (UNEP-WCMC WCMC-008 v4.1) — H3 hex parquet (resolution 9)"
hexa["description"] = DESCRIPTION
hexa["table:columns"] = [{"name": n, "type": t} for n, t in ASSET_COLUMNS]
hexa["h3:native_resolution"] = 9
hexa["h3:parent_resolutions"] = [8, 0]

cols = d.get("table:columns")
if not cols:
    sys.exit("live collection has no table:columns dictionary")
cols = [c for c in cols if c["name"] not in ("h9", "cover_frac")]
names = [c["name"] for c in cols]
if "h8" not in names:
    sys.exit("no h8 column to place h9 and cover_frac before")
i = names.index("h8")
cols[i] = H8
cols[i:i] = [H9, COVER_FRAC]
d["table:columns"] = cols

json.dump(d, open(a.out_collection, "w"), indent=2, ensure_ascii=False)
open(a.out_collection, "a").write("\n")
print("ok")

if a.readme:
    OLD = ("Native resolution **8**, parent resolution **0** (the hive partition key). One row per\n"
           "(feature, cell) pair, so de-duplicate on `_cng_fid` before summarising a feature attribute.\n")
    NEW = ("Native resolution **9**, parent resolutions **8** and **0** (h0 is the hive partition key). One\n"
           "row per (reef polygon, h9 cell) pair for every cell the polygon overlaps, so de-duplicate on\n"
           "`_cng_fid` before summarising a feature attribute. `cover_frac` is the share of the cell inside\n"
           "that polygon: weight cells by it for area, and because reef polygons overlap, cap its per-cell\n"
           "sum at 1 for total reef area (#1020).\n")
    r = open(a.readme[0]).read()
    if r.count(OLD) != 1:
        sys.exit("README hex paragraph not found exactly once")
    open(a.readme[1], "w").write(r.replace(OLD, NEW))
    print("readme ok")
