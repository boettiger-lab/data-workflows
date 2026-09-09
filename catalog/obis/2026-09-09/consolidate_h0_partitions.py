"""
OBIS 2026-09-09 - Stage 2: consolidate one h0 partition into a single file.

Per JOB_COMPLETION_INDEX, picks one h0 partition under 2026-09-09/chunks/, reads all
its Stage-1 fragments, dedups by the OBIS record UUID `_id`, sorts by h8 for row-group
locality, and writes ONE file 2026-09-09/hex/h0=<int>/data_0.parquet.

Dedup is load-bearing, not defensive: Stage 1 pods can be retried or preempted after a
partial write, so a fragment may be duplicated. Deduping on `_id` (OBIS's globally
unique record id) makes the stage idempotent, so per-h0 COUNT(*) == COUNT(DISTINCT _id).

One file per h0 rather than DuckDB's default multi-file split: over-sharding was the
dominant read cost on the GBIF hex (#279). Reads still prune via 1M-row row groups.
h0 itself is not a column here; it is the hive partition key, recovered from the path.
"""
import os
import sys

import boto3
import duckdb

BASE = "s3://public-obis/2026-09-09"
BUCKET = "public-obis"
CHUNKS_PREFIX = "2026-09-09/chunks/"

job_index = int(os.environ.get("JOB_COMPLETION_INDEX", "0"))

endpoint = os.environ.get("AWS_S3_ENDPOINT", "rook-ceph-rgw-nautiluss3.rook")
use_https = os.environ.get("AWS_HTTPS", "false").lower() == "true"
endpoint_url = f"{'https' if use_https else 'http'}://{endpoint}"

# --- find this pod's h0 partition ---
s3 = boto3.client(
    "s3",
    endpoint_url=endpoint_url,
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    region_name="us-east-1",
)
cells = []
for page in s3.get_paginator("list_objects_v2").paginate(
    Bucket=BUCKET, Prefix=CHUNKS_PREFIX, Delimiter="/"
):
    for p in page.get("CommonPrefixes", []):
        part = p["Prefix"].rstrip("/").split("/")[-1]
        if part.startswith("h0="):
            cells.append(part[3:])
cells.sort()
print(f"job {job_index}: {len(cells)} h0 partitions present", flush=True)
if job_index >= len(cells):
    print(f"job {job_index}: beyond partition count, nothing to do")
    sys.exit(0)
cell = cells[job_index]

con = duckdb.connect("/tmp/duck.db")
con.execute("INSTALL httpfs; LOAD httpfs")
con.execute("SET threads=4")
con.execute(f"SET memory_limit='{os.environ.get('DUCKDB_MEMORY_LIMIT', '40GB')}'")
con.execute("SET http_retries=10; SET http_retry_wait_ms=3000")
con.execute("SET preserve_insertion_order=false")
con.execute(f"""
    CREATE SECRET public_obis (TYPE S3, KEY_ID '{os.environ["AWS_ACCESS_KEY_ID"]}',
        SECRET '{os.environ["AWS_SECRET_ACCESS_KEY"]}', REGION 'us-east-1',
        ENDPOINT '{endpoint}', USE_SSL {str(use_https).lower()}, URL_STYLE 'path',
        SCOPE 's3://{BUCKET}')
""")

src = f"{BASE}/chunks/h0={cell}/*.parquet"
dst = f"{BASE}/hex/h0={cell}/data_0.parquet"
print(f"job {job_index}: h0={cell} -> {dst}", flush=True)

con.execute(f"""
    COPY (
        SELECT * FROM read_parquet('{src}', union_by_name=true)
        QUALIFY row_number() OVER (PARTITION BY _id) = 1
        ORDER BY h8
    ) TO '{dst}' (FORMAT PARQUET, COMPRESSION zstd, ROW_GROUP_SIZE 1000000)
""")

n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{dst}')").fetchone()[0]
print(f"job {job_index}: h0={cell} wrote {n} rows", flush=True)
