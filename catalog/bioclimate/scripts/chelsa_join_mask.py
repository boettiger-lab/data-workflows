"""Join the per-GCM hex partitions for one h0, apply units + land mask (data-workflows #564).

Each ensemble member is hexed separately by `cng-datasets raster` into
`<hex-root>/<member>/h0=<cell>/data_0.parquet`. They share a grid, resolution and h0, so they
share an h8 key -- this joins them into one wide row per cell.

Three things happen here that cannot happen earlier:

1. **Units.** `cng-datasets` does not apply the GeoTIFF scale/offset, so hex values are raw
   integers. Because `exact_extract`'s area-weighted mean and CHELSA's scale/offset are both
   linear, `mean(scale*x + offset) == scale*mean(x) + offset` -- applying the transform here is
   exactly equivalent to applying it to the raster, and saves building a float COG per member.

2. **Ensemble statistics.** All five member values are kept as columns; the upstream product
   ships per-GCM files and no ensemble product, so the members are the faithful representation.
   `median`/`min`/`max` are materialised alongside them because a five-member ensemble is
   summarised by its median and full range (percentiles need a larger ensemble), and because
   these are the expressions a consumer is most likely to get wrong across five columns.

3. **Land mask.** WWF Terrestrial Ecoregions h8 hex -- chosen over Overture countries, which is
   a sovereignty boundary that includes territorial and archipelagic waters and omits Antarctica.

Exit 3 means "nothing survived the mask" -- the caller treats that as a skip, not a failure.
"""
import argparse
import glob
import sys

import duckdb


def part(hex_root: str, member_col: str, h0: str) -> str:
    hits = glob.glob(f"{hex_root}/{member_col}/h0={h0}/data_0.parquet")
    if not hits:
        raise SystemExit(f"ERROR: missing hex partition for member {member_col} h0={h0}")
    return hits[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--h0", required=True)
    ap.add_argument("--var", required=True, help="variable prefix, e.g. bio1")
    ap.add_argument("--members", required=True,
                    help="comma-separated member column suffixes, e.g. gfdl_esm4,ipsl_cm6a_lr,...")
    ap.add_argument("--scale", type=float, required=True)
    ap.add_argument("--offset", type=float, required=True)
    ap.add_argument("--hex-root", required=True)
    ap.add_argument("--mask", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sane-min", type=float, default=None,
                    help="fail if any physical value falls below this")
    ap.add_argument("--sane-max", type=float, default=None,
                    help="fail if any physical value rises above this")
    args = ap.parse_args()

    members = [m.strip() for m in args.members.split(",") if m.strip()]
    if len(members) < 2:
        print("ERROR: need at least 2 ensemble members", file=sys.stderr)
        return 1

    var = args.var
    con = duckdb.connect()
    paths = {m: part(args.hex_root, f"{var}_{m}", args.h0) for m in members}

    counts = {m: con.execute(f"SELECT COUNT(*) FROM read_parquet('{p}')").fetchone()[0]
              for m, p in paths.items()}
    print(f"rows per member: {counts}")
    if len(set(counts.values())) != 1:
        print("WARNING: member partitions differ in row count; join keeps the intersection")

    base = members[0]
    # Physical units: raw * scale + offset, applied per member.
    phys = [f"({base}t.{var}_{base} * {args.scale} + {args.offset})" if m == base
            else f"({m}t.{var}_{m} * {args.scale} + {args.offset})"
            for m in members]
    sel_members = ", ".join(f"{e} AS {var}_{m}" for e, m in zip(phys, members))
    arr = "[" + ", ".join(phys) + "]"

    joins = " ".join(
        f"JOIN read_parquet('{paths[m]}') {m}t ON {m}t.h8 = {base}t.h8"
        for m in members if m != base
    )

    con.execute(f"""
        COPY (
            SELECT {base}t.h8, {base}t.h5, {base}t.h4, {base}t.h0,
                   {sel_members},
                   list_sort({arr})[{(len(members) + 1) // 2}] AS {var}_median,
                   list_min({arr})  AS {var}_min,
                   list_max({arr})  AS {var}_max
            FROM read_parquet('{paths[base]}') {base}t
            {joins}
            SEMI JOIN (SELECT DISTINCT h8 FROM read_parquet('{args.mask}')) msk
              ON {base}t.h8 = msk.h8
        ) TO '{args.out}'
        (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
    """)

    after = con.execute(f"SELECT COUNT(*) FROM read_parquet('{args.out}')").fetchone()[0]
    before = counts[base]
    print(f"MASK h0={args.h0} rows_before={before} rows_after={after} "
          f"kept={100.0 * after / before if before else 0:.2f}%")
    if after == 0:
        print("EMPTY after land mask")
        return 3

    lo, hi, nulls = con.execute(f"""
        SELECT MIN({var}_min), MAX({var}_max),
               COUNT(*) FILTER (WHERE {var}_median IS NULL)
        FROM read_parquet('{args.out}')
    """).fetchone()
    print(f"MEASURED {var} physical range: min={lo} max={hi} median_nulls={nulls}")

    # median must lie within [min, max] for every cell -- catches a broken ensemble reduce.
    bad = con.execute(f"""
        SELECT COUNT(*) FROM read_parquet('{args.out}')
        WHERE {var}_median < {var}_min OR {var}_median > {var}_max
    """).fetchone()[0]
    print(f"CHECK median-outside-range violations: {bad}")
    if bad:
        print("ERROR: ensemble median falls outside the member range", file=sys.stderr)
        return 4

    # Plausibility bound -- catches a wrong scale/offset, which is otherwise invisible.
    if args.sane_min is not None and lo is not None and lo < args.sane_min:
        print(f"ERROR: min {lo} below sane bound {args.sane_min}", file=sys.stderr)
        return 5
    if args.sane_max is not None and hi is not None and hi > args.sane_max:
        print(f"ERROR: max {hi} above sane bound {args.sane_max}", file=sys.stderr)
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(main())
