"""Rewrite a published CHELSA hex partition with float32 value columns (data-workflows #564).

The first (ssp, period) combination was written with DOUBLE value columns before the type was
settled. The source is UInt16 quantised to 0.1 units, so float32 carries far more precision than
the data has, at half the size — and leaving one combination as DOUBLE while the rest are FLOAT
would hand consumers a mixed-type union when they compare scenarios.

Rewriting is far cheaper than re-hexing: it re-reads one partition and casts, rather than
repeating 35 exact_extract passes.

Verifies row count and value equality (within float32 precision) before replacing anything.
"""
import argparse
import sys

import duckdb

H3_COLS = ("h8", "h5", "h4", "h0")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="local source parquet")
    ap.add_argument("--out", required=True, help="local output parquet")
    args = ap.parse_args()

    con = duckdb.connect()
    cols = con.execute(
        "SELECT name, type FROM (DESCRIBE SELECT * FROM read_parquet(?))", [args.src]
    ).fetchall()

    select_parts, value_cols = [], []
    for name, typ in cols:
        if name in H3_COLS:
            select_parts.append(name)
        elif typ.upper() in ("DOUBLE", "FLOAT"):
            select_parts.append(f"CAST({name} AS FLOAT) AS {name}")
            value_cols.append(name)
        else:
            select_parts.append(name)

    if not value_cols:
        print("ERROR: no float/double value columns found", file=sys.stderr)
        return 1

    con.execute(f"""
        COPY (SELECT {", ".join(select_parts)} FROM read_parquet('{args.src}'))
        TO '{args.out}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
    """)

    n_src = con.execute(f"SELECT COUNT(*) FROM read_parquet('{args.src}')").fetchone()[0]
    n_out = con.execute(f"SELECT COUNT(*) FROM read_parquet('{args.out}')").fetchone()[0]
    print(f"rows src={n_src} out={n_out} value_columns={len(value_cols)}")
    if n_src != n_out:
        print(f"ERROR: row count changed {n_src} -> {n_out}", file=sys.stderr)
        return 1

    # float32 has ~7 significant digits; values here are +/-10^4 at 0.1 resolution, so any
    # difference beyond 0.01 means something other than rounding happened.
    checks = ", ".join(
        f"MAX(ABS(CAST(s.{c} AS DOUBLE) - CAST(o.{c} AS DOUBLE)))" for c in value_cols
    )
    worst = con.execute(f"""
        SELECT GREATEST({checks})
        FROM read_parquet('{args.src}') s JOIN read_parquet('{args.out}') o USING (h8)
    """).fetchone()[0]
    print(f"max absolute change across all value columns: {worst}")
    if worst is not None and worst > 0.01:
        print(f"ERROR: cast changed a value by {worst}, beyond float32 rounding", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
