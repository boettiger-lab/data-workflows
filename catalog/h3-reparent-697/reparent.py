"""
Re-derive the coarser H3 columns of a point-occurrence hex from its native cell (#697).

GBIF 2026-09 and OBIS 2026-09-09 computed every resolution independently from the coordinate
(h3_latlng_to_cell(lat, lng, k)). H3 does not nest exactly, so for 7-9% of rows h0 (the hive
partition key) is not the parent of the native cell, and joins on `hX AND h0` drop those rows.
cng-datasets derives parents with h3_cell_to_parent; this rebuild makes these two collections do
the same, and moves each affected row to the partition of its new h0.

Two stages, one pod per partition each, all output under STAGE (never the published path):

  MODE=split   source partition S -> STAGE/stay/h0=S/data_0.parquet   (rows whose new h0 is S,
                                                                        in their original order)
                                  -> STAGE/moved/h0=T/from_S_*.parquet (rows whose new h0 is T != S)
  MODE=merge   target partition T -> STAGE/hex/h0=T/data_0.parquet
               = stay rows (original order) followed by incoming rows sorted by the native cell.

Keeping the stay rows' order avoids re-sorting the 91% of rows that do not move: the source files
were sorted by h1..h5, which the new parent columns match almost everywhere.

Env: BUCKET, SRC_PREFIX (e.g. 2026-09/hex), STAGE_PREFIX, NATIVE (e.g. h10), MODE,
     JOB_COMPLETION_INDEX, AWS_*; optional DUCKDB_MEMORY_LIMIT, DUCKDB_TEMP.
"""
import os
import re
import sys

import boto3
import duckdb
from botocore.config import Config

BUCKET = os.environ["BUCKET"]
SRC = os.environ["SRC_PREFIX"].strip("/")
STAGE = os.environ["STAGE_PREFIX"].strip("/")
NATIVE = os.environ["NATIVE"]
NATIVE_RES = int(NATIVE[1:])
MODE = os.environ["MODE"]
idx = int(os.environ.get("JOB_COMPLETION_INDEX", "0"))
# REMAP="80,106" re-runs those partition indexes: this pod's completion index picks one of them.
if os.environ.get("REMAP", "").strip():
    _remap = [int(x) for x in os.environ["REMAP"].split(",")]
    if idx >= len(_remap):
        sys.exit(0)
    idx = _remap[idx]
    print(f"REMAP -> partition index {idx}")

key = os.environ["AWS_ACCESS_KEY_ID"]
secret = os.environ["AWS_SECRET_ACCESS_KEY"]
endpoint = os.environ.get("AWS_S3_ENDPOINT", "rook-ceph-rgw-nautiluss3.rook")
use_ssl = os.environ.get("AWS_HTTPS", "false").lower() == "true"
s3 = boto3.client("s3", aws_access_key_id=key, aws_secret_access_key=secret,
                  endpoint_url=f"{'https' if use_ssl else 'http'}://{endpoint}",
                  config=Config(signature_version="s3v4"))


def keys(prefix):
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix + "/"):
        for o in page.get("Contents", []):
            yield o["Key"]


def partitions(*prefixes):
    found = set()
    for p in prefixes:
        for k in keys(p):
            m = re.search(r"/h0=(\d+)/", k)
            if m and k.endswith(".parquet"):
                found.add(int(m.group(1)))
    return sorted(found)


con = duckdb.connect("/tmp/duck.db")
con.execute("INSTALL httpfs; LOAD httpfs; INSTALL h3 FROM community; LOAD h3")
con.execute("SET http_retries=10; SET http_retry_wait_ms=3000")
if os.environ.get("DUCKDB_MEMORY_LIMIT"):
    con.execute(f"SET memory_limit='{os.environ['DUCKDB_MEMORY_LIMIT']}'")
if os.environ.get("DUCKDB_TEMP"):
    os.makedirs(os.environ["DUCKDB_TEMP"], exist_ok=True)
    con.execute(f"SET temp_directory='{os.environ['DUCKDB_TEMP']}'")
con.execute(f"""CREATE SECRET s (TYPE S3, KEY_ID '{key}', SECRET '{secret}', REGION 'us-east-1',
    ENDPOINT '{endpoint}', USE_SSL {str(use_ssl).lower()}, URL_STYLE 'path')""")
PQ = "FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 1000000"


def rp(paths):
    return f"read_parquet({paths!r}, hive_partitioning=false)"


if MODE == "split":
    parts = partitions(SRC)
    if idx >= len(parts):
        print(f"index {idx} >= {len(parts)} partitions; nothing to do")
        sys.exit(0)
    S = parts[idx]
    src = f"s3://{BUCKET}/{SRC}/h0={S}/data_0.parquet"
    cols = con.execute(f"DESCRIBE SELECT * FROM {rp([src])}").fetchall()
    hcols = {name: typ for name, typ, *_ in cols if re.fullmatch(r"h\d+", name)}
    assert NATIVE in hcols and "h0" in hcols, f"missing {NATIVE} or h0 in {sorted(hcols)}"
    repl = ", ".join(
        f"CAST(h3_cell_to_parent(CAST({NATIVE} AS UBIGINT), {int(c[1:])}) AS {t}) AS {c}"
        for c, t in hcols.items() if int(c[1:]) < NATIVE_RES)
    con.execute(f"CREATE VIEW v AS SELECT * REPLACE ({repl}) FROM {rp([src])}")

    # Idempotent retry: clear this source's earlier output first.
    stale = [k for k in keys(f"{STAGE}/moved") if f"/from_{S}_" in k]
    for k in stale:
        s3.delete_object(Bucket=BUCKET, Key=k)

    con.execute(f"COPY (SELECT * FROM v WHERE h0 = {S}) "
                f"TO 's3://{BUCKET}/{STAGE}/stay/h0={S}/data_0.parquet' ({PQ})")
    con.execute(f"COPY (SELECT * FROM v WHERE h0 <> {S}) TO 's3://{BUCKET}/{STAGE}/moved' "
                f"({PQ}, PARTITION_BY (h0), WRITE_PARTITION_COLUMNS true, "
                f"FILENAME_PATTERN 'from_{S}_{{i}}', OVERWRITE_OR_IGNORE true)")

    n_src = con.execute(f"SELECT COUNT(*) FROM {rp([src])}").fetchone()[0]
    n_stay = con.execute(
        f"SELECT COUNT(*) FROM {rp([f's3://{BUCKET}/{STAGE}/stay/h0={S}/data_0.parquet'])}").fetchone()[0]
    moved = [f"s3://{BUCKET}/{k}" for k in keys(f"{STAGE}/moved") if f"/from_{S}_" in k]
    n_moved = con.execute(f"SELECT COUNT(*) FROM {rp(moved)}").fetchone()[0] if moved else 0
    print(f"split h0={S}: src={n_src} stay={n_stay} moved={n_moved} into {len(moved)} partitions")
    assert n_src == n_stay + n_moved, "ROW COUNT MISMATCH"

elif MODE == "merge":
    import pyarrow.fs as pafs
    import pyarrow.parquet as pq

    parts = partitions(f"{STAGE}/stay", f"{STAGE}/moved")
    if idx >= len(parts):
        print(f"index {idx} >= {len(parts)} partitions; nothing to do")
        sys.exit(0)
    T = parts[idx]
    stay_key = f"{STAGE}/stay/h0={T}/data_0.parquet"
    has_stay = any(k == stay_key for k in keys(f"{STAGE}/stay/h0={T}"))
    moved = [f"s3://{BUCKET}/{k}" for k in keys(f"{STAGE}/moved/h0={T}") if k.endswith(".parquet")]
    out_key = f"{STAGE}/hex/h0={T}/data_0.parquet"

    fs = pafs.S3FileSystem(access_key=key, secret_key=secret, endpoint_override=endpoint,
                           scheme="https" if use_ssl else "http", region="us-east-1")
    first = f"s3://{BUCKET}/{stay_key}" if has_stay else moved[0]
    order = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {rp([first])}").fetchall()]

    local_moved = "/tmp/moved.parquet"
    if moved:
        cols = ", ".join('"' + c.replace('"', '""') + '"' for c in order)  # OBIS has `order`, `class`
        con.execute(f"COPY (SELECT {cols} FROM {rp(moved)} ORDER BY {NATIVE}) "
                    f"TO '{local_moved}' ({PQ})")

    sources = []
    if has_stay:
        sources.append(pq.ParquetFile(fs.open_input_file(f"{BUCKET}/{stay_key}")))
    if moved:
        sources.append(pq.ParquetFile(local_moved))
    # Nullable throughout: a stay file can mark a column required (no nulls in that partition)
    # while incoming rows from other partitions carry nulls in it.
    import pyarrow as pa
    schema = pa.schema([f.with_nullable(True) for f in sources[0].schema_arrow])
    n_out = 0
    with fs.open_output_stream(f"{BUCKET}/{out_key}") as sink, \
            pq.ParquetWriter(sink, schema, compression="zstd") as w:
        for f in sources:
            for i in range(f.num_row_groups):
                t = f.read_row_group(i)
                if t.schema != schema:
                    t = t.select(schema.names).cast(schema)
                w.write_table(t, row_group_size=1_000_000)
                n_out += t.num_rows

    out = f"s3://{BUCKET}/{out_key}"
    n_in = sum(f.metadata.num_rows for f in sources)
    hk = [c for c in order if re.fullmatch(r"h\d+", c) and int(c[1:]) < NATIVE_RES]
    bad = con.execute(
        f"SELECT COUNT(*) FILTER (WHERE h0 <> {T}), COUNT(*) FILTER (WHERE "
        + " OR ".join(f"CAST({c} AS UBIGINT) <> h3_cell_to_parent(CAST({NATIVE} AS UBIGINT), {int(c[1:])})"
                      for c in hk)
        + f"), COUNT(*) FROM {rp([out])}").fetchone()
    print(f"merge h0={T}: stay={'yes' if has_stay else 'no'} moved_files={len(moved)} "
          f"in={n_in} written={n_out} read_back={bad[2]} wrong_h0={bad[0]} wrong_parent={bad[1]}")
    assert n_in == n_out == bad[2], "ROW COUNT MISMATCH"
    assert bad[0] == 0 and bad[1] == 0, "PARENT CHAIN NOT EXACT"
    if os.environ.get("DUCKDB_TEMP"):
        import shutil
        shutil.rmtree(os.environ["DUCKDB_TEMP"], ignore_errors=True)
else:
    sys.exit(f"unknown MODE {MODE}")
print("done")
