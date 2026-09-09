"""
OBIS 2026-09-09 - Stage 1: flatten, filter, H3-index at h8, partition by h0.

Reads the OBIS occurrence export from AWS Open Data (anonymous, us-east-1),
projects a slim column set out of the nested `interpreted` STRUCT, applies the
OBIS QC filter, adds h8 + h0, and writes h0-partitioned chunks to
s3://public-obis/2026-09-09/chunks/h0=<int>/.

Scope is recorded in data-workflows#660:
  - native h8, parent h0 (h10 deferred, it is a full rebuild from the staged raw)
  - global, unclipped
  - hex only `dropped IS NOT TRUE AND absence IS NOT TRUE` with valid coordinates.
    Dropped records fail OBIS QC; absence records are observations of *nothing
    there* and would inflate any density or richness count.

Why per-file schema normalisation (the main difference vs process_gbif_h3.py):
GBIF's snapshot is one flat schema, so that script can `SELECT *`. OBIS ships one
file per source dataset and `interpreted` is a wide STRUCT whose field set varies
across the 7,102 files. Relying on the first file's schema (or on union_by_name
unifying STRUCT children) is the most likely cause of a stage-1 failure, so each
file's actual `interpreted` keys are read first and missing fields are emitted as
typed NULLs. That guarantees every pod writes the identical output schema, which
is what stage 2 depends on.
"""
import os
import sys

import boto3
import duckdb
from botocore import UNSIGNED
from botocore.config import Config

SRC_BUCKET = "obis-open-data"
SRC_PREFIX = "occurrence/"
OUTPUT = os.environ.get("OUTPUT_PREFIX", "s3://public-obis/2026-09-09/chunks")
TOTAL_SHARDS = int(os.environ.get("TOTAL_SHARDS", "100"))

job_index = int(os.environ.get("JOB_COMPLETION_INDEX", "0"))

# Canonical output schema: (output_name, source, duckdb_type).
# source "top" = top-level parquet column, "interp" = field of the `interpreted` STRUCT.
COLUMNS = [
    ("_id",                           "top",    "VARCHAR"),
    ("dataset_id",                    "top",    "VARCHAR"),
    ("decimallatitude",               "interp", "DOUBLE"),
    ("decimallongitude",              "interp", "DOUBLE"),
    ("scientificname",                "interp", "VARCHAR"),
    ("aphiaid",                       "interp", "BIGINT"),
    ("species",                       "interp", "VARCHAR"),
    ("genus",                         "interp", "VARCHAR"),
    ("family",                        "interp", "VARCHAR"),
    ("order",                         "interp", "VARCHAR"),
    ("class",                         "interp", "VARCHAR"),
    ("phylum",                        "interp", "VARCHAR"),
    ("kingdom",                       "interp", "VARCHAR"),
    ("date_year",                     "interp", "INTEGER"),
    ("eventdate",                     "interp", "VARCHAR"),
    ("minimumdepthinmeters",          "interp", "DOUBLE"),
    ("maximumdepthinmeters",          "interp", "DOUBLE"),
    ("coordinateuncertaintyinmeters", "interp", "DOUBLE"),
    ("shoredistance",                 "interp", "DOUBLE"),
    ("bathymetry",                    "interp", "DOUBLE"),
    ("sst",                           "interp", "DOUBLE"),
    ("sss",                           "interp", "DOUBLE"),
    ("marine",                        "interp", "BOOLEAN"),
    ("brackish",                      "interp", "BOOLEAN"),
    ("redlist_category",              "interp", "VARCHAR"),
    ("flags",                         "top",    "VARCHAR[]"),
]

# --- shard the source file list (anonymous public AWS bucket) ---
s3 = boto3.client("s3", region_name="us-east-1", config=Config(signature_version=UNSIGNED))
files = []
for page in s3.get_paginator("list_objects_v2").paginate(Bucket=SRC_BUCKET, Prefix=SRC_PREFIX):
    for o in page.get("Contents", []):
        if o["Key"].endswith(".parquet"):
            files.append(f"s3://{SRC_BUCKET}/{o['Key']}")
files.sort()

# Round-robin rather than contiguous slicing: OBIS file sizes span several orders of
# magnitude (one file per source dataset), so contiguous blocks make wildly uneven
# pods and the job waits on a single straggler.
chunk = files[job_index::TOTAL_SHARDS]
print(f"job {job_index}: {len(chunk)} of {len(files)} source files", flush=True)
if not chunk:
    print(f"job {job_index}: nothing to do")
    sys.exit(0)

# --- DuckDB ---
con = duckdb.connect("/tmp/duck.db")
con.execute("INSTALL httpfs; LOAD httpfs")
con.execute("INSTALL h3 FROM community; LOAD h3")
con.execute("INSTALL json; LOAD json")
con.execute("SET threads=8")
con.execute("SET memory_limit='40GB'")
con.execute("SET http_retries=10; SET http_retry_wait_ms=3000")
con.execute("SET preserve_insertion_order=false")

key = os.environ.get("AWS_ACCESS_KEY_ID", "")
secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
endpoint = os.environ.get("AWS_S3_ENDPOINT", "rook-ceph-rgw-nautiluss3.rook")
use_ssl = str(os.environ.get("AWS_HTTPS", "false").lower() == "true").lower()
con.execute(f"""
    CREATE SECRET public_obis (TYPE S3, KEY_ID '{key}', SECRET '{secret}', REGION 'us-east-1',
        ENDPOINT '{endpoint}', USE_SSL {use_ssl}, URL_STYLE 'path', SCOPE 's3://public-obis')
""")
con.execute("""
    CREATE SECRET obis_public (TYPE S3, KEY_ID '', SECRET '', REGION 'us-east-1',
        SCOPE 's3://obis-open-data')
""")

# --- staging table in the canonical schema ---
cols_ddl = ", ".join(f'"{n}" {t}' for n, _, t in COLUMNS)
con.execute(f'CREATE OR REPLACE TABLE staging ("h8" UBIGINT, "h0" UBIGINT, {cols_ddl})')


def interpreted_keys(path):
    """Actual field names of this file's `interpreted` STRUCT, lowercased -> as written."""
    row = con.execute(
        f"SELECT json_keys(to_json(interpreted)) FROM read_parquet('{path}') LIMIT 1"
    ).fetchone()
    if not row or row[0] is None:
        return None
    return {k.lower(): k for k in row[0]}


def projection(keys):
    parts = []
    for name, src, typ in COLUMNS:
        if src == "top":
            expr = f'"{name}"'
        else:
            actual = keys.get(name.lower())
            expr = f'interpreted."{actual}"' if actual else "NULL"
        parts.append(f'TRY_CAST({expr} AS {typ}) AS "{name}"')
    return ", ".join(parts)


ok = skipped = failed = 0
for i, path in enumerate(chunk):
    try:
        keys = interpreted_keys(path)
        if keys is None:
            skipped += 1
            continue
        lat = f'interpreted."{keys["decimallatitude"]}"' if "decimallatitude" in keys else None
        lon = f'interpreted."{keys["decimallongitude"]}"' if "decimallongitude" in keys else None
        if lat is None or lon is None:
            print(f"  no coordinates in schema, skipping {path}", flush=True)
            skipped += 1
            continue
        con.execute(f"""
            INSERT INTO staging
            SELECT h3_latlng_to_cell(decimallatitude, decimallongitude, 8) AS h8,
                   h3_latlng_to_cell(decimallatitude, decimallongitude, 0) AS h0,
                   *
            FROM (
                SELECT {projection(keys)}
                FROM read_parquet('{path}')
                WHERE dropped IS NOT TRUE
                  AND absence IS NOT TRUE
                  AND TRY_CAST({lat} AS DOUBLE) BETWEEN -90 AND 90
                  AND TRY_CAST({lon} AS DOUBLE) BETWEEN -180 AND 180
            )
        """)
        ok += 1
    except Exception as e:  # one bad source dataset must not lose the whole shard
        failed += 1
        print(f"  FAILED {path}: {type(e).__name__}: {e}", flush=True)
    if (i + 1) % 25 == 0:
        print(f"  {i + 1}/{len(chunk)} files (ok={ok} skipped={skipped} failed={failed})", flush=True)

n = con.execute("SELECT COUNT(*) FROM staging").fetchone()[0]
print(f"job {job_index}: {n} rows staged (ok={ok} skipped={skipped} failed={failed})", flush=True)
if failed:
    # Surface partial-shard loss loudly rather than silently publishing a short hex.
    print(f"job {job_index}: WARNING {failed} source files failed", flush=True)
if n == 0:
    sys.exit(0)

con.execute(f"""
    COPY (SELECT * FROM staging ORDER BY h0, h8)
    TO '{OUTPUT}'
    (FORMAT PARQUET, PARTITION_BY (h0), COMPRESSION zstd,
     FILENAME_PATTERN 'part_{job_index}_{{uuid}}',
     OVERWRITE_OR_IGNORE true, ROW_GROUP_SIZE 1000000)
""")
print(f"job {job_index}: wrote {n} rows to {OUTPUT}", flush=True)
