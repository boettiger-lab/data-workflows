"""
GBIF 2026-06 — Stage 2: consolidate each h0 partition (port of
catalog/gbif/consolidate_h0_partitions.py).

Per JOB_COMPLETION_INDEX, picks one h0 partition under 2026-06/chunks/, reads all
its Stage-1 files, and writes ONE optimized file 2026-06/hex/h0=<int>/data_0.parquet.

Changes vs the 2025-06 script (data-workflows#247):
- DEDUP by gbifid (QUALIFY row_number()=1) so per-h0 COUNT(*) == COUNT(DISTINCT gbifid)
  (#244; also absorbs any chunk duplication from Stage-1 retries).
- ONE FILE PER h0: write to a single data_0.parquet path (no FILE_SIZE_BYTES, no
  multi-thread per-file split) — fixes the 126-shards-per-h0 over-sharding (#279).
  Densest h0 becomes one multi-GB file; reads still prune via 1M-row row groups.
- Clean output path (no '//', #240); 2025-06 -> 2026-06 prefixes.
- Spatial sort ORDER BY h1..h5 retained for row-group locality.
"""
import duckdb, os, sys
import boto3
from botocore.config import Config

BUCKET = "public-gbif"
IN_PREFIX = "2026-06/chunks"
OUT_PREFIX = "2026-06/hex"

job_index = int(os.environ.get("JOB_COMPLETION_INDEX", "0"))
# REMAP lets a rechunk job reprocess a subset of the sorted-h0 indices (the dense
# partitions that OOM at the standard memory). REMAP="4,12,..." maps this pod's
# completion index onto the original index into the sorted h0 list.
_remap = os.environ.get("REMAP", "").strip()
if _remap:
    _idx = [int(x) for x in _remap.split(",")]
    if job_index >= len(_idx):
        print(f"job {job_index}: beyond REMAP length {len(_idx)} — nothing to do")
        sys.exit(0)
    job_index = _idx[job_index]
    print(f"REMAP active -> original sorted-h0 index {job_index}")

key = os.environ.get("AWS_ACCESS_KEY_ID", "")
secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
endpoint = os.environ.get("AWS_S3_ENDPOINT", "rook-ceph-rgw-nautiluss3.rook")
use_ssl = os.environ.get("AWS_HTTPS", "false").lower() == "true"
endpoint_url = f"{'https' if use_ssl else 'http'}://{endpoint}"

s3 = boto3.client("s3", aws_access_key_id=key, aws_secret_access_key=secret,
                  endpoint_url=endpoint_url, config=Config(signature_version="s3v4"))

# --- discover h0 partitions in chunks/ ---
h0s = set()
for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=IN_PREFIX + "/"):
    for o in page.get("Contents", []):
        for part in o["Key"].split("/"):
            if part.startswith("h0="):
                h0s.add(part)
                break
h0s = sorted(h0s)
print(f"discovered {len(h0s)} h0 partitions in {IN_PREFIX}")
if job_index >= len(h0s):
    print(f"job {job_index}: beyond partition range ({len(h0s)}) — nothing to do")
    sys.exit(0)
h0 = h0s[job_index]

files = []
for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=f"{IN_PREFIX}/{h0}/"):
    for o in page.get("Contents", []):
        if o["Key"].endswith(".parquet"):
            files.append(f"s3://{BUCKET}/{o['Key']}")
if not files:
    print(f"job {job_index}: no files in {h0}")
    sys.exit(0)
out = f"s3://{BUCKET}/{OUT_PREFIX}/{h0}/data_0.parquet"
print(f"job {job_index}: consolidating {h0} ({len(files)} files) -> {out}")

con = duckdb.connect("/tmp/duck.db")
con.execute("INSTALL httpfs; LOAD httpfs")
con.execute("SET http_retries=10; SET http_retry_wait_ms=3000")
con.execute("SET preserve_insertion_order=false")
# Dense-partition tuning (set only by the high-RAM rechunk job; unset = standard run).
# Big RAM is the primary lever (in-memory dedup+sort is far faster than spill);
# fewer threads keeps peak memory efficient; temp_directory is a PVC spill backstop.
if os.environ.get("DUCKDB_MEMORY_LIMIT"):
    con.execute(f"SET memory_limit='{os.environ['DUCKDB_MEMORY_LIMIT']}'")
if os.environ.get("DUCKDB_THREADS"):
    con.execute(f"SET threads={int(os.environ['DUCKDB_THREADS'])}")
if os.environ.get("DUCKDB_TEMP"):
    con.execute(f"SET temp_directory='{os.environ['DUCKDB_TEMP']}'")
con.execute(f"""
    CREATE SECRET public_gbif (TYPE S3, KEY_ID '{key}', SECRET '{secret}', REGION 'us-east-1',
        ENDPOINT '{endpoint}', USE_SSL {str(use_ssl).lower()}, URL_STYLE 'path', SCOPE 's3://public-gbif')
""")
con.execute(f"""
    COPY (
        SELECT *
        FROM read_parquet({files})
        QUALIFY row_number() OVER (PARTITION BY gbifid) = 1
        ORDER BY h1, h2, h3, h4, h5
    ) TO '{out}'
    (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 1000000)
""")
n = con.execute(f"SELECT COUNT(*), COUNT(DISTINCT gbifid) FROM read_parquet('{out}')").fetchone()
print(f"job {job_index}: wrote {h0} rows={n[0]} distinct_gbifid={n[1]}")
assert n[0] == n[1], f"DEDUP FAILED: {n[0]} rows != {n[1]} distinct gbifid"
print(f"job {job_index}: done")
