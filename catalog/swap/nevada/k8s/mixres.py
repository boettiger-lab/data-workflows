#!/usr/bin/env python3
"""Mixed-resolution H3 hex helper (data-workflows #381/#383).

Species-range layers get NATIVE h10 for smaller ranges and NATIVE h8 for very
large ranges (which would explode at res 10). One hex run can't do per-feature
resolution, so we:
  1. split   — write <flat>-small.parquet = features whose res-8 cell count <= THRESH
  2. (res-10 hex the small set with cng-datasets, separately)
  3. merge   — final hex = res-8 hex (large features only) UNION BY NAME res-10 hex
               (small features), written hive-partitioned by h0. h8 is complete
               for every feature (universal join key); h10/h9 are NULL for the
               large (res-8-native) features.

Usage:
  mixres.py split <flat.parquet> <res8_hex_glob> <out_small.parquet> <thresh>
  mixres.py merge <res8_hex_glob> <res10_hex_glob> <small.parquet> <out_hex_dir>
"""
import os, sys, duckdb

def con():
    c = duckdb.connect()
    c.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
    c.execute(f"""
      SET s3_endpoint='{os.environ["AWS_S3_ENDPOINT"]}';
      SET s3_access_key_id='{os.environ["AWS_ACCESS_KEY_ID"]}';
      SET s3_secret_access_key='{os.environ["AWS_SECRET_ACCESS_KEY"]}';
      SET s3_use_ssl=false; SET s3_url_style='path';
    """)
    return c

cmd = sys.argv[1]
c = con()
if cmd == "split":
    flat, hexglob, out, thresh = sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
    c.execute(f"""
      COPY (
        SELECT f.* FROM read_parquet('{flat}') f
        WHERE f._cng_fid IN (
          SELECT _cng_fid FROM read_parquet('{hexglob}')
          GROUP BY _cng_fid HAVING COUNT(DISTINCT h8) <= {thresh}
        )
      ) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 2000)
    """)
    n = c.execute(f"SELECT COUNT(*) FROM read_parquet('{out}')").fetchone()[0]
    print(f"split: wrote {n} small features -> {out}")
elif cmd == "merge":
    hex8, hex10, small, outdir = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
    # large = features NOT in the small set
    c.execute(f"""
      COPY (
        SELECT * FROM read_parquet('{hex10}')
        UNION ALL BY NAME
        SELECT * FROM read_parquet('{hex8}')
        WHERE _cng_fid NOT IN (SELECT _cng_fid FROM read_parquet('{small}'))
      ) TO '{outdir}'
      (FORMAT PARQUET, PARTITION_BY (h0), FILENAME_PATTERN 'data_{{i}}',
       COMPRESSION ZSTD, OVERWRITE_OR_IGNORE)
    """)
    tot = c.execute(f"SELECT COUNT(*) nrow, COUNT(DISTINCT _cng_fid) fids, COUNT(DISTINCT h8) h8, SUM(CASE WHEN h10 IS NULL THEN 1 ELSE 0 END) h10null FROM read_parquet('{outdir}/h0=*/data_0.parquet')").fetchdf()
    print("merge:\n", tot.to_string())
else:
    sys.exit(f"unknown cmd {cmd}")
