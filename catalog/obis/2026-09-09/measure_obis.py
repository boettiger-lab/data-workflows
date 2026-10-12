"""Writes /tmp/obis_measurements.json, the input to build_stac.py and build_readme.py.

Hex figures are measured through the duckdb-geo MCP (verify-stac.py's client); raw figures
are read from the staged MANIFEST.txt header.

    python3 measure_obis.py [--created 2026-09-09T18:13:26Z]
"""
import argparse, datetime, importlib.util, json, pathlib, urllib.request

REPO = pathlib.Path(__file__).resolve().parents[3]
HEX = "s3://public-obis/2026-09-09/hex/h0=*/data_0.parquet"
MANIFEST = "https://s3-west.nrp-nautilus.io/public-obis/raw/MANIFEST.txt"

_spec = importlib.util.spec_from_file_location("vs", REPO / "scripts" / "verify-stac.py")
_vs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vs)

ap = argparse.ArgumentParser()
ap.add_argument("--created", default=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
args = ap.parse_args()

r = _vs.MCPClient().query(f"""
    SELECT COUNT(*) AS total, COUNT(DISTINCT dataset_id) AS datasets,
           MIN(date_year) AS y0, MAX(date_year) AS y1
    FROM read_parquet('{HEX}')
""")[0]

header = {}
with urllib.request.urlopen(MANIFEST) as f:
    for line in f:
        line = line.decode().strip()
        if not line:
            break
        k, v = line.split(":", 1)
        header[k] = v.strip()

M = {
    "total": int(r["total"]),
    "datasets": int(r["datasets"]),
    "temporal_start": f"{int(r['y0']):04d}-01-01T00:00:00Z",
    "temporal_end": f"{int(r['y1'])}-12-31T23:59:59Z",
    "raw_files": int(header["file_count"]),
    "raw_bytes": int(header["total_bytes"]),
    "created": args.created,
}
json.dump(M, open("/tmp/obis_measurements.json", "w"), indent=2)
print(json.dumps(M, indent=2))
