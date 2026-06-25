#!/usr/bin/env python3
"""Audit a vector parquet asset for per-feature row duplication and classify how
each attribute may be aggregated.

WHY THIS EXISTS
---------------
A vector GeoParquet often stores one logical feature as several rows that share a
feature id. There are TWO very different reasons this happens, and they demand
OPPOSITE aggregation rules — confusing them silently corrupts answers:

  * REPEATED  — the same measure/site spread over several rows (e.g. a ballot
                measure spanning multiple counties; a Ramsar site split into
                polygon parcels). The per-feature value is *copied* onto every
                row. A raw SUM double-counts; you must dedup by the key first,
                and COUNT(DISTINCT key) is the feature count.
  * VARIES    — genuinely distinct per-row records that happen to share a key
                (e.g. the same conservation site funded by several sponsors, each
                a different amount). Here SUM is CORRECT and dedup would UNDERCOUNT
                by dropping real contributions.

The decisive, data-backed test is: *does the value vary within the key?* This
tool answers it. It does NOT guess the key (guessing is exactly what produces
false positives — a 34%-blank source id, or a class label like `name` that
covers thousands of distinct parcels). You supply the key you mean.

Lesson source: data-workflows #309 (landvote was REPEATED → dedup; TPL
conservation-almanac funding is VARIES → keep & SUM).

USAGE
-----
    scripts/audit-feature-dup.py <parquet-url|s3-url> --key COL [--cols a,b,...]
    scripts/audit-feature-dup.py <stac-collection-url> --asset <asset-key> --key COL

Runs entirely on the duckdb-geo MCP (cluster metal, internal S3) — never local
duckdb — so it honours the data-workflows big-data boundary. All set arithmetic
is pushed into SQL (the MCP truncates large markdown tables), so results are
tiny and truncation-proof.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

# Reuse the battle-tested MCP client + helpers from verify-stac.py (sibling file
# with a hyphen, so load it by path rather than import).
_VS = Path(__file__).with_name("verify-stac.py")
_spec = importlib.util.spec_from_file_location("verify_stac", _VS)
_vs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vs)
MCPClient, MCPError, to_s3 = _vs.MCPClient, _vs.MCPError, _vs._to_s3

# Columns that are never the thing you aggregate (synthetic ids, geometry, hive keys).
SKIP_COL = re.compile(
    r"^(_cng_fid|ogc_fid|fid|bbox|geometry|geom|shape|h\d+)$", re.I)
NUMERIC = re.compile(r"int|double|float|decimal|real|hugeint|numeric", re.I)

# cng-datasets assigns `_cng_fid` (and the older `_fid`) as a synthetic id that is
# monotonically increasing — ONE PER INPUT ROW, never derived from a source id.
# It is the canonical key for the feature→H3-cell expansion (one polygon → many
# cells), so COUNT(DISTINCT _cng_fid) collapses hexing. It is NOT a logical-entity
# key: if the *source file* already holds several rows per logical entity (a Ramsar
# site split into parcels; a ballot measure spanning counties), `_cng_fid` is still
# unique per row and CANNOT reveal that upstream duplication. Only an upstream
# domain id (ramsarid, landvote_id, WDPA SITE_ID) can. Auditing on a per-row id
# therefore always looks "clean" — a false all-clear.
PER_ROW_ID = re.compile(r"^(_cng_fid|_fid|ogc_fid|fid)$", re.I)


def q(name: str) -> str:
    """Double-quote a SQL identifier, escaping embedded quotes (e.g. 'Area (ha)')."""
    return '"' + name.replace('"', '""') + '"'


def resolve_parquet(source: str, asset: str | None) -> str:
    """Return an s3:// path for the parquet to audit, from a parquet URL or a STAC
    collection URL (+ --asset)."""
    if source.endswith("stac-collection.json") or "/stac" in source:
        doc = json.load(urllib.request.urlopen(source, timeout=60)) if source.startswith("http") \
            else json.loads(Path(source).read_text())
        assets = doc.get("assets", {})
        if asset:
            if asset not in assets:
                sys.exit(f"asset '{asset}' not in collection (have: {', '.join(assets)})")
            href = assets[asset].get("href", "")
        else:
            parq = [k for k, a in assets.items()
                    if "parquet" in (a.get("type", "") + k) and "hex" not in k]
            if len(parq) != 1:
                sys.exit(f"specify --asset (parquet assets: {', '.join(parq) or 'none'})")
            href = assets[parq[0]].get("href", "")
        s3 = to_s3(href)
        if not s3:
            sys.exit(f"could not map asset href to s3://: {href}")
        return s3
    s3 = to_s3(source)
    return s3 or source


def describe(mcp: MCPClient, s3: str) -> list[tuple[str, str]]:
    rows = mcp.query(f"DESCRIBE SELECT * FROM read_parquet('{s3}')")
    return [(r.get("column_name", ""), r.get("column_type", "")) for r in rows]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source", help="parquet URL/s3 path, or a STAC collection URL (+ --asset)")
    p.add_argument("--key", required=True, help="feature-identifier column you mean to dedup on")
    p.add_argument("--asset", help="asset key, when source is a STAC collection")
    p.add_argument("--cols", help="comma-separated columns to classify (default: all aggregatable)")
    p.add_argument("--endpoint", default=os.environ.get("MCP_ENDPOINT", _vs.DEFAULT_MCP))
    args = p.parse_args()

    s3 = resolve_parquet(args.source, args.asset)
    mcp = MCPClient(endpoint=args.endpoint)
    try:
        mcp.initialize()
    except Exception as e:
        sys.exit(f"MCP not reachable ({e}). Ask the user to reconnect duckdb-geo; "
                 f"do NOT fall back to local duckdb (big-data boundary).")

    schema = describe(mcp, s3)
    names = {n for n, _ in schema}
    if args.key not in names:
        sys.exit(f"key '{args.key}' not a column. Columns: {', '.join(sorted(names))}")
    typ = {n: t for n, t in schema}

    if args.cols:
        cols = [c.strip() for c in args.cols.split(",") if c.strip()]
        missing = [c for c in cols if c not in names]
        if missing:
            sys.exit(f"--cols not in schema: {', '.join(missing)}")
    else:
        cols = [n for n, _ in schema if n != args.key and not SKIP_COL.match(n)]

    key = q(args.key)
    print(f"# Feature-dup audit\n  parquet: {s3}\n  key:     {args.key}\n")

    if PER_ROW_ID.match(args.key):
        print(f"  ⚠ '{args.key}' is a cng-datasets per-row synthetic id (one per INPUT\n"
              f"    ROW, not per logical entity). It is the right key for the feature→H3-cell\n"
              f"    (hex) axis, but it is unique per row, so this audit can only ever report\n"
              f"    CLEAN — it CANNOT reveal upstream duplication (one entity in many source\n"
              f"    rows). Re-run with --key <upstream domain id> (e.g. ramsarid, landvote_id,\n"
              f"    SITE_ID) to check that axis.\n")

    # 1) Is there duplication at all?
    base = mcp.query(
        f"SELECT COUNT(*) AS rows, COUNT(DISTINCT {key}) AS distinct_key, "
        f"COUNT(*) FILTER (WHERE {key} IS NULL OR CAST({key} AS VARCHAR) = '') AS blank_key "
        f"FROM read_parquet('{s3}')")[0]
    rows, distinct_key, blank_key = (int(base["rows"]), int(base["distinct_key"]),
                                     int(base["blank_key"]))
    extra = rows - distinct_key
    print(f"  rows={rows:,}  distinct {args.key}={distinct_key:,}  "
          f"blank {args.key}={blank_key:,}  extra rows={extra:,}")
    if blank_key:
        print(f"  ⚠ {blank_key:,} rows have a blank/NULL key — a blank key collapses to one\n"
              f"    group and FAKES duplication. Confirm '{args.key}' is really the feature id.")
    if extra <= 0:
        print(f"\n✅ CLEAN relative to {args.key}: one row per {args.key}. COUNT(*) is the "
              f"feature count and SUM over any column is safe —")
        if PER_ROW_ID.match(args.key):
            print(f"  but remember {args.key} is unique per row by construction, so this only\n"
                  f"  rules out duplication *relative to that key*. To rule out UPSTREAM logical\n"
                  f"  duplication, re-run with the upstream domain id as --key.")
        else:
            print(f"  for this key. (A per-row synthetic id like _cng_fid would also look clean;\n"
                  f"  upstream duplication only shows up under the upstream domain id.)")
        return 0
    print(f"\n  {args.key} repeats across rows ({rows/max(distinct_key,1):.2f}x). "
          f"Classifying each column by whether its value VARIES within {args.key}:\n")

    # 2) For each candidate column, how many multi-row key-groups have >1 distinct value?
    #    All computed in SQL over the grouped set; one compact result row.
    aggs = ", ".join(
        f"SUM(CASE WHEN nd_{i} > 1 THEN 1 ELSE 0 END) AS vary_{i}" for i in range(len(cols)))
    nds = ", ".join(f"COUNT(DISTINCT {q(c)}) AS nd_{i}" for i, c in enumerate(cols))
    grouped = (f"SELECT {key} AS k, COUNT(*) AS n, {nds} FROM read_parquet('{s3}') "
               f"GROUP BY {key} HAVING COUNT(*) > 1")
    res = mcp.query(f"SELECT COUNT(*) AS dup_groups, {aggs} FROM ({grouped})")[0]
    dup_groups = int(res["dup_groups"])
    print(f"  {dup_groups:,} features occupy more than one row.\n")

    repeated, varies = [], []
    for i, c in enumerate(cols):
        (varies if int(res.get(f"vary_{i}", 0)) > 0 else repeated).append(c)

    def show(title, items):
        if items:
            print(title)
            for c in items:
                print(f"    - {c}  ({typ.get(c, '?')})")
            print()

    show("REPEATED within key  →  per-feature value; raw SUM double-counts.\n"
         "    Dedup first: SELECT DISTINCT " + args.key + ", <col> …  (or GROUP BY " + args.key + ").", repeated)
    show("VARIES within key    →  genuinely per-row; SUM is CORRECT, do NOT dedup\n"
         "    (dropping rows would undercount — the sponsor/transaction-split pattern).", varies)

    # 3) Quantify inflation for REPEATED numeric columns: raw SUM vs deduped SUM.
    num = [c for c in repeated if NUMERIC.search(typ.get(c, ""))]
    if num:
        print("Inflation if you SUM the raw rows instead of deduping (REPEATED numerics):")
        for c in num:
            try:
                r = mcp.query(
                    f"SELECT (SELECT SUM({q(c)}) FROM read_parquet('{s3}')) AS raw, "
                    f"(SELECT SUM(v) FROM (SELECT DISTINCT {key}, {q(c)} AS v "
                    f"  FROM read_parquet('{s3}'))) AS dedup")[0]
                raw, ded = r.get("raw"), r.get("dedup")
                rawf, dedf = float(raw), float(ded)
                factor = f"{rawf/dedf:.2f}x" if dedf else "n/a"
                print(f"    - {c}: raw SUM={raw}  deduped SUM={ded}  (inflated {factor})")
            except (MCPError, ValueError, TypeError, ZeroDivisionError):
                print(f"    - {c}: could not compute (non-numeric or null sum)")
        print()

    print("COUNT note: use COUNT(DISTINCT " + args.key + f") = {distinct_key:,} for the "
          f"feature count, not COUNT(*) = {rows:,}.")
    print("\nNext: record the correct rule in the asset's STAC table:columns description\n"
          "(name the key, REPEATED→dedup-before-SUM, VARIES→safe-to-SUM). See AGENTS.md\n"
          "“Per-feature row duplication”.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
