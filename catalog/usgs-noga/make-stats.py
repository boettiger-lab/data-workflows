#!/usr/bin/env python3
"""Measure the published NOGA assets with the duckdb-geo MCP and write stats.json for
make-stac.py (issue #700).

  python3 catalog/usgs-noga/make-stats.py --report /tmp/build-report.json --out /tmp/stats.json
"""

import argparse
import importlib.util
import json
import pathlib
import re
from collections import Counter

REPO = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("vs", REPO / "scripts" / "verify-stac.py")
_vs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vs)

S3 = "s3://public-usgs/noga-assessment-units"
FLAT = f"read_parquet('{S3}.parquet')"
HEX = f"read_parquet('{S3}/hex/h0=*/data_0.parquet')"
VALUE_COLUMNS = ["PROVNAME", "ASSESSMETHOD", "ACCUMTYPE", "RESERVOIRTYPE", "STATUS"]
# Provinces whose rows all have a null PROVNAME; the name is taken from the release title.
PROVNAME_FROM_TITLE = {
    "5010": "San Joaquin Basin",
    "5013": "Ventura Basin",
    "5047": "Western Gulf",
    "5060": "Cherokee Platform",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True, help="build-report.json from noga-preprocess.py")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    report = json.load(open(args.report))

    mcp = _vs.MCPClient()
    mcp.initialize()

    def one(sql):
        return mcp.query(sql)[0]

    def rows(sql):
        # Aggregate to one JSON cell: the MCP returns at most a 50-row preview.
        return json.loads(one(f"SELECT to_json(list(r)) AS j FROM ({sql}) r")["j"])

    def modified(glob):
        return one(
            "SELECT strftime(MIN(last_modified) AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%M:%SZ') AS t "
            f"FROM read_blob('{glob}')"
        )["t"]

    names = [r["column_name"] for r in mcp.query(f"SELECT column_name FROM (DESCRIBE SELECT * FROM {FLAT})")]
    volume = " OR ".join(f"{c} IS NOT NULL" for c in names if re.search(r"_(MMB|BCF)$", c))
    flat = one(
        "SELECT COUNT(*) AS n, COUNT(DISTINCT ASSESSCODE) AS codes, "
        f"COUNT(*) FILTER (WHERE {volume}) AS with_volumes, "
        "COUNT(DISTINCT PROVCODE) AS provinces, "
        "COUNT(*) FILTER (WHERE REGNAME IS NULL) AS null_region, "
        "COUNT(*) FILTER (WHERE PROVNAME IS NULL) AS null_provname, "
        "COUNT(*) FILTER (WHERE TPSNAME IS NULL) AS null_tpsname, "
        "MIN(release_pubdate) AS pmin, MAX(release_pubdate) AS pmax, "
        "MIN(ST_XMin(geom)) AS xmin, MIN(ST_YMin(geom)) AS ymin, "
        f"MAX(ST_XMax(geom)) AS xmax, MAX(ST_YMax(geom)) AS ymax FROM {FLAT}"
    )
    hexs = one(f"SELECT COUNT(*) AS n, COUNT(DISTINCT h8) AS h8 FROM {HEX}")

    values = {
        c: [r["v"] for r in rows(f"SELECT DISTINCT {c} AS v FROM {FLAT} WHERE {c} IS NOT NULL ORDER BY 1")]
        for c in VALUE_COLUMNS
    }
    values["REGNAME"] = [r["v"] for r in rows(
        f"SELECT REGNAME AS v, COUNT(*) AS k FROM {FLAT} WHERE REGNAME IS NOT NULL "
        "GROUP BY 1 ORDER BY k DESC, v")]

    def spellings(code, name):
        """{code: {name: count}} over the rows that carry a name."""
        out = {}
        for r in rows(f"SELECT {code} AS c, {name} AS n, COUNT(*) AS k FROM {FLAT} "
                      f"WHERE {name} IS NOT NULL GROUP BY ALL"):
            out.setdefault(r["c"], Counter())[r["n"]] = r["k"]
        return out

    def canonical(sp):
        return {c: min(n, key=lambda s: (-n[s], s)) for c, n in sp.items()}

    def variants(sp):
        return {c: sorted(n) for c, n in sorted(sp.items()) if len(n) > 1}

    prov, tps = spellings("PROVCODE", "PROVNAME"), spellings("TPSCODE", "TPSNAME")
    provcode_names = {**PROVNAME_FROM_TITLE, **canonical(prov)}
    codes = [r["c"] for r in rows(f"SELECT DISTINCT PROVCODE AS c FROM {FLAT}")]
    missing = sorted(set(codes) - set(provcode_names))
    if missing:
        raise SystemExit(f"no province name for {missing}; add it to PROVNAME_FROM_TITLE")
    created_hex = modified(f"{S3}/hex/h0=*/data_0.parquet")
    stats = {
        "rows": int(flat["n"]),
        "distinct_assesscode": int(flat["codes"]),
        "rows_with_volumes": int(flat["with_volumes"]),
        "distinct_provinces": int(flat["provinces"]),
        "null_region": int(flat["null_region"]),
        "null_provname": int(flat["null_provname"]),
        "null_tpsname": int(flat["null_tpsname"]),
        "superseded": report["au_polygons_merged"] - report["au_polygons_published"],
        "pubdate_min": flat["pmin"],
        "pubdate_max": flat["pmax"],
        "bbox": [float(flat[k]) for k in ("xmin", "ymin", "xmax", "ymax")],
        "hex_rows": int(hexs["n"]),
        "distinct_h8": int(hexs["h8"]),
        "values": values,
        "provcode_names": {c: provcode_names[c] for c in codes},
        "provname_variants": variants(prov),
        "tpscode_names": canonical(tps),
        "tpsname_variants": variants(tps),
        "created": created_hex,
        "created_parquet": modified(f"{S3}.parquet"),
        "created_pmtiles": modified(f"{S3}.pmtiles"),
        "created_hex": created_hex,
    }
    with open(args.out, "w") as fh:
        json.dump(stats, fh, indent=2)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
