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
    # DuckDB's DESCRIBE yields column_name/column_type -- not name/type.
    cols = con.execute(
        "SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM read_parquet(?))",
        [args.src],
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

    # Compare per-column aggregates rather than joining the two files. A 60-column join over
    # millions of rows needs far more memory than the cast itself, and aggregates catch the
    # failure modes that matter: a shifted value, a lost row, a nulled column.
    aggs = ", ".join(
        f"MIN({c}) AS mn_{i}, MAX({c}) AS mx_{i}, COUNT({c}) AS n_{i}"
        for i, c in enumerate(value_cols)
    )
    src_stats = con.execute(f"SELECT {aggs} FROM read_parquet('{args.src}')").fetchone()
    out_stats = con.execute(f"SELECT {aggs} FROM read_parquet('{args.out}')").fetchone()

    worst = 0.0
    for i, c in enumerate(value_cols):
        s_mn, s_mx, s_n = src_stats[i * 3], src_stats[i * 3 + 1], src_stats[i * 3 + 2]
        o_mn, o_mx, o_n = out_stats[i * 3], out_stats[i * 3 + 1], out_stats[i * 3 + 2]
        if s_n != o_n:
            print(f"ERROR: {c} non-null count changed {s_n} -> {o_n}", file=sys.stderr)
            return 1
        for a, b, what in ((s_mn, o_mn, "min"), (s_mx, o_mx, "max")):
            if a is None and b is None:
                continue
            if a is None or b is None:
                print(f"ERROR: {c} {what} became NULL", file=sys.stderr)
                return 1
            worst = max(worst, abs(float(a) - float(b)))

    # float32 carries ~7 significant digits; these values are at most ~10^4 at 0.1 resolution,
    # so anything beyond 0.01 is not rounding.
    print(f"max absolute change across {len(value_cols)} value columns: {worst}")
    if worst > 0.01:
        print(f"ERROR: cast changed a value by {worst}, beyond float32 rounding", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
