"""Mask one hexed raster partition to land and write it (data-workflows #564).

Used by the Armada microsliced path, where each job handles a single
(h0, variable, member). Masking here rather than at join time keeps the staged
intermediate to the land subset instead of all 5,764,801 cells of the h0.

A separate script rather than inline SQL on purpose: the same statement embedded in a shell
command inside a YAML pod spec has to survive three layers of quoting, and the escaping
collapses in ways that only show up at runtime.

Exit 3 means nothing survived the mask, which the caller treats as a skip rather than a failure.
"""
import argparse
import sys

import duckdb

ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True)
ap.add_argument("--mask", required=True)
ap.add_argument("--out", required=True)
args = ap.parse_args()

con = duckdb.connect()
con.execute(
    """
    COPY (
        SELECT r.* FROM read_parquet(?) r
        SEMI JOIN (SELECT DISTINCT h8 FROM read_parquet(?)) m ON r.h8 = m.h8
    ) TO '""" + args.out + """' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
    """,
    [args.src, args.mask],
)

n = con.execute("SELECT COUNT(*) FROM read_parquet(?)", [args.out]).fetchone()[0]
print(f"masked rows: {n}")
sys.exit(3 if n == 0 else 0)
