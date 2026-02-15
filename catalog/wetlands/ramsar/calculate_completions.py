#!/usr/bin/env python
"""
Calculate the number of k8s job completions needed for processing a parquet file.
Run this before deploying hex-job.yaml to determine the correct completions value.
"""
import argparse
import ibis
from cng.utils import set_secrets

def main():
    parser = argparse.ArgumentParser(description="Calculate required k8s job completions")
    parser.add_argument("--input-url", required=True, help="Input parquet file URL")
    parser.add_argument("--chunk-size", type=int, default=50, help="Chunk size (default 50)")
    args = parser.parse_args()

    con = ibis.duckdb.connect(extensions=["spatial", "h3"])
    con.raw_sql("INSTALL h3 FROM community; LOAD h3;")
    con.raw_sql("SET http_retries=20")
    con.raw_sql("SET http_retry_wait_ms=5000")
    
    set_secrets(con)

    print(f"Checking: {args.input_url}")
    table = con.read_parquet(args.input_url)
    total_rows = table.count().execute()
    num_chunks = (total_rows + args.chunk_size - 1) // args.chunk_size
    
    print(f"\nTotal rows: {total_rows:,}")
    print(f"Chunk size: {args.chunk_size:,}")
    print(f"Required chunks: {num_chunks} (indices 0 to {num_chunks - 1})")
    print(f"\n{'='*60}")
    print(f"Set 'completions: {num_chunks}' in your k8s job YAML")
    print(f"{'='*60}")
    print(f"\nCalculation: ceil({total_rows:,} / {args.chunk_size}) = {num_chunks}")

if __name__ == "__main__":
    main()
