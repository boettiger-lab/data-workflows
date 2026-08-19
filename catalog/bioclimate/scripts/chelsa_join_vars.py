"""Join all variables x ensemble members for one h0 into one wide, land-masked row per cell.

Layout produced by the hex step:  <hex-root>/<var>_<member>/h0=<cell>/data_0.parquet

For each variable the five member columns are carried through unchanged and joined on `h8`,
then `median` / `min` / `max` are materialised alongside them. The members are the
upstream-faithful representation -- CHELSA ships per-GCM files and no ensemble product -- and
median plus full range is the conventional summary for an ensemble this small (percentiles need
more members to mean anything). Keeping every member means any other summary is a query rather
than a rebuild.

Values arrive **already in physical units**: cng-datasets hands the raster path to exactextract,
whose GDAL source applies the band scale/offset. No transform is applied here. See BUILD.md.

The land mask is the WWF Terrestrial Ecoregions h8 hex. Exit 3 means nothing survived it, which
the caller treats as a skip rather than a failure.
"""
import argparse
import glob
import json
import sys

import duckdb


def part(hex_root: str, var: str, member: str, h0: str) -> str:
    hits = glob.glob(f"{hex_root}/{var}_{member}/h0={h0}/data_0.parquet")
    if not hits:
        raise SystemExit(f"ERROR: missing hex partition for {var}_{member} h0={h0}")
    return hits[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--h0", required=True)
    ap.add_argument("--vars", required=True, help="comma-separated variables, e.g. bio1,bio12")
    ap.add_argument("--members", required=True, help="comma-separated member column suffixes")
    ap.add_argument("--bounds", required=True,
                    help='JSON {"bio1": [-100, 60], ...} physical plausibility bounds per variable')
    ap.add_argument("--hex-root", required=True)
    ap.add_argument("--mask", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    variables = [v.strip() for v in args.vars.split(",") if v.strip()]
    members = [m.strip() for m in args.members.split(",") if m.strip()]
    bounds = json.loads(args.bounds)
    if len(members) < 2:
        print("ERROR: need at least 2 ensemble members", file=sys.stderr)
        return 1

    con = duckdb.connect()
    base_var, base_member = variables[0], members[0]
    base_path = part(args.hex_root, base_var, base_member, args.h0)
    base_alias = f"{base_var}_{base_member}"

    select_parts, join_parts = [], []
    for var in variables:
        cols = [f"{var}_{m}t.{var}_{m}" for m in members]
        arr = "[" + ", ".join(cols) + "]"
        for m in members:
            select_parts.append(f"{var}_{m}t.{var}_{m} AS {var}_{m}")
        select_parts += [
            f"list_sort({arr})[{(len(members) + 1) // 2}] AS {var}_median",
            f"list_min({arr}) AS {var}_min",
            f"list_max({arr}) AS {var}_max",
        ]
        for m in members:
            alias = f"{var}_{m}t"
            if alias == f"{base_alias}t":
                continue
            join_parts.append(
                f"JOIN read_parquet('{part(args.hex_root, var, m, args.h0)}') {alias} "
                f"ON {alias}.h8 = {base_alias}t.h8"
            )

    con.execute(f"""
        COPY (
            SELECT {base_alias}t.h8, {base_alias}t.h5, {base_alias}t.h4, {base_alias}t.h0,
                   {", ".join(select_parts)}
            FROM read_parquet('{base_path}') {base_alias}t
            {" ".join(join_parts)}
            SEMI JOIN (SELECT DISTINCT h8 FROM read_parquet('{args.mask}')) msk
              ON {base_alias}t.h8 = msk.h8
        ) TO '{args.out}'
        (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
    """)

    before = con.execute(f"SELECT COUNT(*) FROM read_parquet('{base_path}')").fetchone()[0]
    after = con.execute(f"SELECT COUNT(*) FROM read_parquet('{args.out}')").fetchone()[0]
    print(f"MASK h0={args.h0} rows_before={before} rows_after={after} "
          f"kept={100.0 * after / before if before else 0:.2f}%")
    if after == 0:
        print("EMPTY after land mask")
        return 3

    failures = 0
    for var in variables:
        lo, hi, nulls, bad = con.execute(f"""
            SELECT MIN({var}_min), MAX({var}_max),
                   COUNT(*) FILTER (WHERE {var}_median IS NULL),
                   COUNT(*) FILTER (WHERE {var}_median < {var}_min OR {var}_median > {var}_max)
            FROM read_parquet('{args.out}')
        """).fetchone()
        print(f"MEASURED {var}: min={lo} max={hi} median_nulls={nulls} ordering_violations={bad}")
        if bad:
            print(f"ERROR: {var} median outside member range in {bad} rows", file=sys.stderr)
            failures += 1
        blo, bhi = bounds[var]
        # A wrong scale/offset or a leaked nodata sentinel is invisible to every structural
        # check -- ordering and cardinality survive a linear transform -- so bound the physical
        # value against what the quantity can actually be.
        if lo is not None and lo < blo:
            print(f"ERROR: {var} min {lo} below plausibility bound {blo}", file=sys.stderr)
            failures += 1
        if hi is not None and hi > bhi:
            print(f"ERROR: {var} max {hi} above plausibility bound {bhi}", file=sys.stderr)
            failures += 1

    return 5 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
