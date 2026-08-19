"""Resolve a cng-datasets h0 *index* (0-121) to its h0 *cell id* (data-workflows #564).

`cng-datasets raster --h0-index N` looks N up in the h0 grid parquet by its `i` column. Doing
the same lookup up front lets a job decide whether an h0 holds any land *before* paying to hex
it: only 108 of the 122 h0 cells intersect the WWF ecoregions land mask, so the remaining 14
would otherwise hex every ensemble member and then discard the result.
"""
import argparse
import sys

import duckdb

ap = argparse.ArgumentParser()
ap.add_argument("--grid", required=True, help="local path to the h0 grid parquet")
ap.add_argument("--index", type=int, required=True)
args = ap.parse_args()

row = duckdb.connect().execute(
    "SELECT h0 FROM read_parquet(?) WHERE i = ?", [args.grid, args.index]
).fetchone()

if row is None:
    print(f"ERROR: no h0 cell for index {args.index}", file=sys.stderr)
    sys.exit(1)

print(row[0])
