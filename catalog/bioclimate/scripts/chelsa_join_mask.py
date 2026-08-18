"""Join the per-quantile hex partitions for one h0 and apply the land mask (data-workflows #564).

Each ensemble quantile is hexed separately by `cng-datasets raster` into
`<hex-root>/p<q>/h0=<cell>/data_0.parquet`. They share a grid, a resolution and an h0, so they
share an h8 key — this joins them into one wide row per cell and then restricts to land.

The land mask is the WWF Terrestrial Ecoregions h8 hex (chosen over Overture countries, which is
a sovereignty boundary that includes territorial and archipelagic waters and omits Antarctica).

Exit 3 means "nothing survived the mask" — the caller treats that as a skip, not a failure.
"""
import argparse
import glob
import sys

import duckdb

QUANTILES = (10, 50, 90)


def part(hex_root: str, q: int, h0: str) -> str:
    hits = glob.glob(f"{hex_root}/p{q}/h0={h0}/data_0.parquet")
    if not hits:
        raise SystemExit(f"ERROR: missing hex partition for p{q} h0={h0}")
    return hits[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--h0", required=True)
    ap.add_argument("--var", required=True)
    ap.add_argument("--hex-root", required=True)
    ap.add_argument("--mask", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    con = duckdb.connect()
    paths = {q: part(args.hex_root, q, args.h0) for q in QUANTILES}

    counts = {q: con.execute(f"SELECT COUNT(*) FROM read_parquet('{p}')").fetchone()[0]
              for q, p in paths.items()}
    print(f"rows per quantile: {counts}")
    if len(set(counts.values())) != 1:
        # Not fatal -- an inner join keeps only cells present in all three -- but it should not
        # happen for rasters that share a grid and mask, so make it visible.
        print("WARNING: quantile partitions differ in row count; join will keep the intersection")

    base = args.var
    sel = ", ".join(f"p{q}.{base}_p{q}" for q in QUANTILES)
    joins = " ".join(
        f"JOIN read_parquet('{paths[q]}') p{q} ON p{q}.h8 = p50.h8"
        for q in QUANTILES if q != 50
    )

    con.execute(f"""
        COPY (
            SELECT p50.h8, p50.h5, p50.h4, p50.h0, {sel}
            FROM read_parquet('{paths[50]}') p50
            {joins}
            SEMI JOIN (SELECT DISTINCT h8 FROM read_parquet('{args.mask}')) m
              ON p50.h8 = m.h8
        ) TO '{args.out}'
        (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
    """)

    after = con.execute(f"SELECT COUNT(*) FROM read_parquet('{args.out}')").fetchone()[0]
    before = counts[50]
    print(f"MASK h0={args.h0} rows_before={before} rows_after={after} "
          f"kept={100.0 * after / before if before else 0:.2f}%")
    if after == 0:
        print("EMPTY after land mask")
        return 3

    rng = con.execute(f"""
        SELECT MIN({base}_p50), MAX({base}_p50), COUNT(*) FILTER (WHERE {base}_p50 IS NULL)
        FROM read_parquet('{args.out}')
    """).fetchone()
    print(f"MEASURED {base}_p50 min={rng[0]} max={rng[1]} nulls={rng[2]}")
    # Ordering invariant: p10 <= p50 <= p90 must hold for every cell.
    bad = con.execute(f"""
        SELECT COUNT(*) FROM read_parquet('{args.out}')
        WHERE {base}_p10 > {base}_p50 OR {base}_p50 > {base}_p90
    """).fetchone()[0]
    print(f"CHECK quantile-ordering violations: {bad}")
    if bad:
        print("ERROR: ensemble quantiles are not monotonic", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
