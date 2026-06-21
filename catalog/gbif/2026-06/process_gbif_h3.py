"""
GBIF 2026-06 — Stage 1: H3 index + h0 partition (port of catalog/gbif/process_gbif_h3.py).

Reads the 2026-06-01 GBIF occurrence snapshot from AWS Open Data (anonymous),
adds H3 index columns h0..h10 from decimallat/long, filters invalid coords, and
writes h0-partitioned chunks to s3://public-gbif/2026-06/chunks/h0=<int>/.

Changes vs the 2025-06 script (see data-workflows#247):
- date 2025-06-01 -> 2026-06-01; output prefix 2026-06; files_per_chunk 25 -> 42
  (source grew 4,599 -> 8,375 files; 42*200 >= 8,375 keeps 200 completions).
- SINGLE-PASS write: one COPY ... PARTITION_BY (h0) per chunk (reads each source
  file once) instead of the original per-distinct-h0 re-read loop. Chunk files may
  duplicate across pod retries; Stage 2 dedups by gbifid so that is harmless.
- h0 partition dirs are the natural uint64 (decimal), matching the IUCN hex layout.
- Keeps h0..h10 (the live 2025-06 hex carries all 11 resolutions; do not regress).
"""
import duckdb, os, sys
import boto3
from botocore import UNSIGNED
from botocore.config import Config

SRC_BUCKET = "gbif-open-data-us-east-1"
SRC_PREFIX = "occurrence/2026-06-01/occurrence.parquet/"
OUTPUT = "s3://public-gbif/2026-06/chunks"
FILES_PER_CHUNK = 42

job_index = int(os.environ.get("JOB_COMPLETION_INDEX", "0"))

# --- list source files (anonymous public AWS bucket) ---
s3 = boto3.client("s3", region_name="us-east-1", config=Config(signature_version=UNSIGNED))
files = []
for page in s3.get_paginator("list_objects_v2").paginate(Bucket=SRC_BUCKET, Prefix=SRC_PREFIX):
    for o in page.get("Contents", []):
        if not o["Key"].endswith("/"):
            files.append(f"s3://{SRC_BUCKET}/{o['Key']}")
files.sort()
start = job_index * FILES_PER_CHUNK
end = min(start + FILES_PER_CHUNK, len(files))
if start >= len(files):
    print(f"job {job_index}: beyond file range ({len(files)} files) — nothing to do")
    sys.exit(0)
chunk = files[start:end]
print(f"job {job_index}: source files [{start}:{end}] = {len(chunk)} of {len(files)}")

# --- DuckDB ---
con = duckdb.connect("/tmp/duck.db")
con.execute("INSTALL httpfs; LOAD httpfs")
con.execute("INSTALL h3 FROM community; LOAD h3")
con.execute("SET threads=8")
con.execute("SET http_retries=10; SET http_retry_wait_ms=3000")
con.execute("SET preserve_insertion_order=false")

key = os.environ.get("AWS_ACCESS_KEY_ID", "")
secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
endpoint = os.environ.get("AWS_S3_ENDPOINT", "rook-ceph-rgw-nautiluss3.rook")
use_ssl = str(os.environ.get("AWS_HTTPS", "false").lower() == "true").lower()
con.execute(f"""
    CREATE SECRET public_gbif (TYPE S3, KEY_ID '{key}', SECRET '{secret}', REGION 'us-east-1',
        ENDPOINT '{endpoint}', USE_SSL {use_ssl}, URL_STYLE 'path', SCOPE 's3://public-gbif')
""")
con.execute("""
    CREATE SECRET gbif_public (TYPE S3, KEY_ID '', SECRET '', REGION 'us-east-1',
        SCOPE 's3://gbif-open-data-us-east-1')
""")

con.execute(f"""
    COPY (
        SELECT *,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 0)  AS h0,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 1)  AS h1,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 2)  AS h2,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 3)  AS h3,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 4)  AS h4,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 5)  AS h5,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 6)  AS h6,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 7)  AS h7,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 8)  AS h8,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 9)  AS h9,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 10) AS h10
        FROM read_parquet({chunk})
        WHERE decimallatitude IS NOT NULL AND decimallongitude IS NOT NULL
          AND decimallatitude  BETWEEN -90  AND 90
          AND decimallongitude BETWEEN -180 AND 180
    ) TO '{OUTPUT}'
    (FORMAT parquet, PARTITION_BY (h0), COMPRESSION zstd,
     FILENAME_PATTERN 'job{job_index:04d}_{{i}}', OVERWRITE_OR_IGNORE true)
""")
print(f"job {job_index}: done")
