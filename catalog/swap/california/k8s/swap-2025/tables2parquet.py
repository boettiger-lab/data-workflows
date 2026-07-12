#!/usr/bin/env python3
"""Convert a newline-delimited-JSON table (ArcGIS attribute rows) to Parquet,
adding a universal per-row _cng_fid. Image ships DuckDB as a python module
(no `duckdb` CLI), so this runs in the tables-convert job (#381)."""
import sys
import duckdb

src, out = sys.argv[1], sys.argv[2]
con = duckdb.connect()
con.execute(f"""
  COPY (
    SELECT row_number() OVER () AS _cng_fid, *
    FROM read_json('{src}', format='newline_delimited', auto_detect=true)
  ) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)
""")
n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{out}')").fetchone()[0]
print(f"  {out}: {n} rows")
