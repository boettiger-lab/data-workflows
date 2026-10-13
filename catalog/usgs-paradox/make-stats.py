#!/usr/bin/env python3
"""Measure the published Paradox Basin assets with the duckdb-geo MCP and write stats.json
for make-stac.py (issue #722).

  python3 catalog/usgs-paradox/make-stats.py --out /tmp/stats.json
"""

import argparse
import importlib.util
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("vs", REPO / "scripts" / "verify-stac.py")
_vs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vs)

S3 = "s3://public-usgs/paradox-basin-assessment-units"
FLAT = f"read_parquet('{S3}.parquet')"
HEX = f"read_parquet('{S3}/hex/h0=*/data_0.parquet')"
VALUE_COLUMNS = ["REG_NUM", "REG_NAME", "PROVCODE", "PROV_NAME", "ASSESSTYPE", "ASSESSPROB"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    mcp = _vs.MCPClient()
    mcp.initialize()

    def one(sql):
        return mcp.query(sql)[0]

    def modified(glob):
        return one(
            "SELECT strftime(MIN(last_modified) AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%M:%SZ') AS t "
            f"FROM read_blob('{glob}')"
        )["t"]

    flat = one(
        "SELECT COUNT(*) AS n, ROUND(SUM(OILMEAN), 2) AS oil, "
        "ROUND(SUM(ADGASMEAN + NAGASMEAN), 2) AS gas, ROUND(SUM(NGLMEAN + NAGLMEAN), 2) AS ngl, "
        "MIN(ST_XMin(geom)) AS xmin, MIN(ST_YMin(geom)) AS ymin, "
        f"MAX(ST_XMax(geom)) AS xmax, MAX(ST_YMax(geom)) AS ymax FROM {FLAT}"
    )
    hexs = one(f"SELECT COUNT(*) AS n, COUNT(DISTINCT h8) AS h8 FROM {HEX}")
    values = {
        c: [r["v"] for r in mcp.query(
            f"SELECT DISTINCT {c} AS v FROM {FLAT} WHERE {c} IS NOT NULL ORDER BY 1")]
        for c in VALUE_COLUMNS
    }
    tps = [[r["c"], r["n"]] for r in mcp.query(
        f"SELECT DISTINCT TPSCODE AS c, TPSNAME AS n FROM {FLAT} ORDER BY 1")]

    created_parquet = modified(f"{S3}.parquet")
    stats = {
        "rows": int(flat["n"]),
        "totals": {k: float(flat[k]) for k in ("oil", "gas", "ngl")},
        "bbox": [float(flat[k]) for k in ("xmin", "ymin", "xmax", "ymax")],
        "hex_rows": int(hexs["n"]),
        "distinct_h8": int(hexs["h8"]),
        "values": values,
        "tps": tps,
        "created": created_parquet,
        "created_parquet": created_parquet,
        "created_pmtiles": modified(f"{S3}.pmtiles"),
        "created_hex": modified(f"{S3}/hex/h0=*/data_0.parquet"),
    }
    with open(args.out, "w") as fh:
        json.dump(stats, fh, indent=2)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
