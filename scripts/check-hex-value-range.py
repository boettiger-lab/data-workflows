#!/usr/bin/env python3
"""Assert a published hex layer's values fall in its documented physical range.

Why this exists
---------------
During the LANDFIRE 2024 canopy build (data-workflows#515) a hex layer was published
with 42.66% of its cells carrying the source fill code 32767, and a mean of
165.2 kg/m^3 for a variable whose valid maximum is 0.45. The nodata list had omitted
one of the two fill codes.

Every signal we normally rely on passed it:

  * the k8s job succeeded, all indexes;
  * the partition was written, at a plausible size;
  * memory and runtime looked healthy;
  * the schema was correct -- int-typed, no nulls;
  * verify-stac.py was clean, because the values are in-type and non-null.

It was caught only by asking whether the numbers were physically possible. Worse than
the flagged cells were ~1M where `mean` had *blended* fill with real measurements: those
are not filterable after the fact, and they look like ordinary small values.

So: for any layer whose variable has a known physical domain, assert it. The check is one
query and catches a class of error that completion and schema signals structurally cannot.

Usage
-----
    check-hex-value-range.py --bucket public-landfire --dataset landfire-2024-cbd \\
        --column cbd --min 1 --max 45 --scale 0.01 --unit 'kg/m^3' \\
        --forbid 32767 --forbid 0

Exit 0 if every assertion holds, 1 otherwise.
"""
import argparse, importlib.util, pathlib, sys

# Reuse verify-stac.py's MCP client rather than re-implementing the transport. The
# endpoint speaks JSON-RPC over SSE with a session handshake -- an earlier draft of this
# script POSTed plain JSON to a guessed URL, which would have failed at the first call.
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("verify_stac", SCRIPT_DIR / "verify-stac.py")
_vs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vs)


def run_sql(sql):
    c = _vs.MCPClient()
    c.initialize()
    rows = c.query(sql)
    return rows[0] if rows else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--column", required=True)
    ap.add_argument("--min", type=float, required=True, help="minimum valid RAW value")
    ap.add_argument("--max", type=float, required=True, help="maximum valid RAW value")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="raw -> physical multiplier, for reporting (e.g. 0.01 for kg/m^3 x100)")
    ap.add_argument("--unit", default="")
    ap.add_argument("--forbid", type=float, action="append", default=[],
                    help="a value that must not appear at all (fill/sentinel codes). Repeatable.")
    ap.add_argument("--tolerance", type=float, default=1e-6,
                    help="float slack on the bounds; `mean` over identical pixels can land at "
                         "max+1e-14, which is noise rather than an out-of-range value")
    a = ap.parse_args()

    path = f"s3://{a.bucket}/{a.dataset}/hex/h0=*/data_0.parquet"
    col = a.column
    forbid_sql = ", ".join(
        f"count(*) FILTER (WHERE {col} = {v}) AS forbid_{str(v).replace('-','neg').replace('.','_')}"
        for v in a.forbid) or "0 AS no_forbidden_declared"

    sql = f"""
      SELECT count(*) AS cells,
             min({col}) AS lo, max({col}) AS hi, avg({col}) AS mean,
             count(*) FILTER (WHERE {col} IS NULL) AS nulls,
             count(*) FILTER (WHERE {col} < {a.min - a.tolerance}
                                 OR {col} > {a.max + a.tolerance}) AS out_of_range,
             {forbid_sql}
      FROM read_parquet('{path}')
    """
    row = run_sql(sql)
    print(f"=== {a.dataset}.{col} ===")
    print(f"  {row}")

    fails = []
    r = row if isinstance(row, dict) else {}

    def get(k, default=0):
        """The MCP returns every column as a STRING, so '0' is truthy. Coerce before
        testing -- an earlier version of this script reported FAIL on a clean layer
        with every count at zero for exactly this reason."""
        v = r.get(k, default)
        if v is None:
            return default
        try:
            f = float(v)
        except (TypeError, ValueError):
            return v
        return int(f) if f == int(f) else f

    if get("out_of_range"):
        fails.append(f"{get('out_of_range')} cells outside [{a.min}, {a.max}]")
    if get("nulls"):
        fails.append(f"{get('nulls')} NULL cells")
    for v in a.forbid:
        k = f"forbid_{str(v).replace('-','neg').replace('.','_')}"
        if get(k):
            fails.append(f"{get(k)} cells carry forbidden value {v} (fill/sentinel leaked)")

    if fails:
        print("\nFAIL:")
        for f in fails:
            print(f"  - {f}")
        print(f"\nA fill code in the data usually means --nodata omitted one. Note that cells "
              f"where the reducer BLENDED fill with real values will NOT appear in these counts "
              f"and are unrecoverable -- rebuild rather than filter.")
        return 1

    lo, hi, mean = get("lo"), get("hi"), get("mean")
    if a.scale != 1.0:
        print(f"  physical: {lo} -> {float(lo)*a.scale:g}, {hi} -> {float(hi)*a.scale:g}, "
              f"mean {float(mean)*a.scale:g} {a.unit}".rstrip())
    print("OK: all values within the declared physical domain; no fill or sentinel leaked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
