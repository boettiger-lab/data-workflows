"""Repartition the remaining PAD-US combined h0 partitions with bounded scratch (#617).

Same output as `cng-datasets repartition` (cng_datasets/vector/repartition.py):
attributes joined from the source parquet, one h0=<cell>/data_0.parquet per h0,
rows ordered by (_cng_fid, h10), provenance key-value metadata. The difference:
the tool sorts a whole h0 partition at once, and h0=577727389698621439
(700M rows) spills past 200Gi of scratch. Here each partition is sorted in
_cng_fid ranges of about RANGE_ROWS rows, each range is written to a small
compressed file, and the ranges are streamed in order into data_0.parquet.

Usage: python3 repartition_ranges.py <h0> [<h0> ...]
"""
import os
import shutil
import subprocess
import sys

import duckdb
from cng_datasets.hex_checks import assert_h3_columns_unsigned
from cng_datasets.provenance import kv_metadata_sql
from cng_datasets.storage.s3 import configure_s3_credentials

CHUNKS = os.environ.get("CHUNKS", "s3://public-padus/padus-4-1/combined/chunks")
SOURCE = os.environ.get("SOURCE", "s3://public-padus/padus-4-1/combined.parquet")
OUTPUT = os.environ.get("OUTPUT", "s3://public-padus/padus-4-1/combined/hex")
RCLONE_OUT = os.environ.get("RCLONE_OUT", "nrp:public-padus/padus-4-1/combined/hex")
ID, FINEST = "_cng_fid", "h10"
RANGE_ROWS = int(os.environ.get("RANGE_ROWS", 50_000_000))
WORK = os.environ.get("WORK", "/tmp/rp")

con = duckdb.connect()
configure_s3_credentials(con)
con.execute(f"SET memory_limit='{os.environ.get('DUCKDB_MEMORY_LIMIT', '40GiB')}'")
con.execute(f"SET temp_directory='{WORK}_duckdb_tmp'")
con.execute("SET http_timeout=1200")
con.execute("SET http_retries=30")
con.execute("SET arrow_large_buffer_size=true")

desc = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{SOURCE}')").fetchall()
attr = [c for c, t, *_ in desc if not t.upper().startswith("GEOMETRY")]
quoted = ", ".join(f'"{c}"' for c in attr)
con.execute(f"CREATE VIEW _source_attrs AS SELECT {quoted} FROM read_parquet('{SOURCE}')")
con.execute(f"CREATE VIEW _chunks AS SELECT * FROM read_parquet('{CHUNKS}/*.parquet')")
join = (f'SELECT s.*, c.* EXCLUDE ("{ID}") FROM _chunks c '
        f'INNER JOIN _source_attrs s ON c."{ID}" = s."{ID}"')

for h0 in sys.argv[1:]:
    h0 = int(h0)
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(f"{WORK}/parts")
    os.makedirs(f"{WORK}/h0={h0}")
    # Rows per feature in this partition, in id order, cut into ranges.
    counts = con.execute(
        f'SELECT "{ID}", count(*) FROM _chunks WHERE h0 = {h0} GROUP BY 1 ORDER BY 1'
    ).fetchall()
    expected = sum(n for _, n in counts)
    ranges, lo, acc = [], counts[0][0], 0
    for fid, n in counts:
        if acc and acc + n > RANGE_ROWS:
            ranges.append((lo, prev))
            lo, acc = fid, 0
        acc += n
        prev = fid
    ranges.append((lo, prev))
    print(f"h0={h0}: {expected:,} rows, {len(counts):,} features, {len(ranges)} ranges", flush=True)

    con.execute("SET preserve_insertion_order=false")
    parts = []
    for i, (a, b) in enumerate(ranges):
        part = f"{WORK}/parts/part_{i:05d}.parquet"
        con.execute(
            f'COPY (SELECT * FROM ({join} WHERE c.h0 = {h0} AND c."{ID}" BETWEEN {a} AND {b}) '
            f'ORDER BY "{ID}", "{FINEST}") TO \'{part}\' (FORMAT PARQUET, COMPRESSION ZSTD)'
        )
        parts.append(part)
        print(f"  range {i + 1}/{len(ranges)} ids {a}-{b} written", flush=True)

    # Stream the sorted ranges, in order, into one file.
    out = f"{WORK}/h0={h0}/data_0.parquet"
    con.execute("SET preserve_insertion_order=true")
    plist = ", ".join(f"'{p}'" for p in parts)
    con.execute(f"COPY (SELECT * FROM read_parquet([{plist}])) TO '{out}' "
                f"(FORMAT PARQUET, COMPRESSION ZSTD{kv_metadata_sql()})")

    # Checks before upload: row count, and the file is ordered by id
    # (each row group's min id >= the previous row group's max id).
    n = con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()[0]
    assert n == expected, f"h0={h0}: wrote {n:,} rows, expected {expected:,}"
    bad = con.execute(f"""
        WITH rg AS (
          SELECT row_group_id, min(stats_min_value::BIGINT) mn, max(stats_max_value::BIGINT) mx
          FROM parquet_metadata('{out}') WHERE path_in_schema = '{ID}' GROUP BY 1),
        w AS (SELECT mn, lag(mx) OVER (ORDER BY row_group_id) prev_mx FROM rg)
        SELECT count(*) FROM w WHERE mn < prev_mx""").fetchone()[0]
    assert bad == 0, f"h0={h0}: {bad} row groups out of id order"

    subprocess.run(["rclone", "copy", f"{WORK}/h0={h0}", f"{RCLONE_OUT}/h0={h0}/",
                    "--transfers", "32", "--s3-upload-concurrency", "16",
                    "--s3-chunk-size", "64M"], check=True)
    shutil.rmtree(WORK)
    print(f"  h0={h0} done ({n:,} rows)", flush=True)

hex_glob = f"{OUTPUT}/h0=*/data_0.parquet"
print(f"Asserting H3 columns are UBIGINT via {hex_glob}...", flush=True)
assert_h3_columns_unsigned(lambda sql: con.execute(sql).fetchall(), hex_glob)
print("All done. Chunks are left in place; remove them after verification.", flush=True)
