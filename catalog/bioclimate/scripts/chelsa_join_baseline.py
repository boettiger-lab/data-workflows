"""Join the per-variable baseline hex partitions for one h0 (data-workflows #448).

The present-day baseline is an observational climatology, not an ensemble: one raster per
variable, no GCM members. So the output is one plain column per variable rather than the futures'
five members plus median/min/max, and a delta against a future collection reads directly:

    SELECT AVG(f.bio1_median - b.bio1) FROM <future> f JOIN <baseline> b USING (h8)

Values arrive already in physical units — cng-datasets hands the raster path to exactextract,
whose GDAL source applies the band scale/offset. No transform here.

Exit 3 means nothing survived the land mask, which the caller treats as a skip.
"""
import argparse
import glob
import json
import sys

import duckdb


def part(root, var, h0):
    hits = glob.glob(f"{root}/{var}/h0={h0}/data_0.parquet")
    if not hits:
        raise SystemExit(f"ERROR: missing partition for {var} h0={h0}")
    return hits[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--h0", required=True)
    ap.add_argument("--vars", required=True)
    ap.add_argument("--hex-root", required=True)
    ap.add_argument("--mask", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--bounds", required=True)
    args = ap.parse_args()

    variables = [v.strip() for v in args.vars.split(",") if v.strip()]
    bounds = json.loads(args.bounds)
    con = duckdb.connect()
    paths = {v: part(args.hex_root, v, args.h0) for v in variables}
    base = variables[0]

    sel = ", ".join(f"CAST({v}t.{v} AS FLOAT) AS {v}" for v in variables)
    joins = " ".join(f"JOIN read_parquet('{paths[v]}') {v}t ON {v}t.h8 = {base}t.h8"
                     for v in variables if v != base)

    con.execute(f"""
        COPY (
            SELECT {base}t.h8, {base}t.h5, {base}t.h4, {base}t.h0, {sel}
            FROM read_parquet('{paths[base]}') {base}t
            {joins}
            SEMI JOIN (SELECT DISTINCT h8 FROM read_parquet('{args.mask}')) msk
              ON {base}t.h8 = msk.h8
        ) TO '{args.out}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
    """)

    before = con.execute(f"SELECT COUNT(*) FROM read_parquet('{paths[base]}')").fetchone()[0]
    after = con.execute(f"SELECT COUNT(*) FROM read_parquet('{args.out}')").fetchone()[0]
    print(f"MASK h0={args.h0} rows_before={before} rows_after={after}")
    if after == 0:
        print("EMPTY after land mask")
        return 3

    failures = 0
    for v in variables:
        lo, hi, nulls = con.execute(
            f"SELECT MIN({v}), MAX({v}), COUNT(*) FILTER (WHERE {v} IS NULL) "
            f"FROM read_parquet('{args.out}')").fetchone()
        print(f"MEASURED {v}: min={lo} max={hi} nulls={nulls}")
        blo, bhi = bounds[v]
        # A wrong scale/offset or a leaked nodata sentinel survives every structural check,
        # because a linear transform preserves ordering and cardinality. Only a physical
        # bound catches it.
        if lo is not None and lo < blo:
            print(f"ERROR: {v} min {lo} below bound {blo}", file=sys.stderr); failures += 1
        if hi is not None and hi > bhi:
            print(f"ERROR: {v} max {hi} above bound {bhi}", file=sys.stderr); failures += 1
    return 5 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
