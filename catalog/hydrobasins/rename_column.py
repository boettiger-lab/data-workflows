"""
Rename 'id' column back to 'HYBAS_ID' in existing hexed HydroBasins data.

This script fixes the column naming in previously processed H3 hexagon datasets.
It reads from the old location (level_XX/hexes/) and writes to new location (LXX/)
with the correct HYBAS_ID column name.
"""
import argparse
import ibis
from ibis import _
from cng.utils import set_secrets
import os
import shutil

def main():
    parser = argparse.ArgumentParser(
        description="Rename 'id' column to 'HYBAS_ID' in hexed HydroBasins data"
    )
    parser.add_argument(
        "--level", 
        type=int, 
        required=True, 
        help="HydroBasins level to process (e.g., 3, 4, 5, 6)"
    )
    parser.add_argument(
        "--input-url",
        default=None,
        help="Input parquet location (defaults to s3://public-hydrobasins/level_XX/hexes/)"
    )
    parser.add_argument(
        "--output-url",
        default=None,
        help="Output parquet location (defaults to s3://public-hydrobasins/LXX/)"
    )
    parser.add_argument(
        "--use-local-cache",
        action="store_true",
        help="Use local /tmp cache to reduce memory pressure"
    )
    args = parser.parse_args()

    # Set defaults based on level if not provided
    if args.input_url is None:
        args.input_url = f"s3://public-hydrobasins/level_{args.level:02d}/hexes/"
    if args.output_url is None:
        args.output_url = f"s3://public-hydrobasins/L{args.level}/"

    print(f"Processing Level {args.level}")
    print(f"Input:  {args.input_url}")
    print(f"Output: {args.output_url}")

    # Setup DuckDB connection
    con = ibis.duckdb.connect()
    set_secrets(con)
    con.raw_sql("SET preserve_insertion_order=false")  # saves RAM
    con.raw_sql("SET http_timeout=1200")
    con.raw_sql("SET http_retries=30")

    # Read the data
    print("\nReading hexed data...")
    table = con.read_parquet(f"{args.input_url}**/*.parquet")
    
    # Check if 'id' column exists and rename it
    if 'id' in table.columns:
        print("Renaming 'id' column to 'HYBAS_ID'...")
        table = table.rename(HYBAS_ID='id')
    elif 'HYBAS_ID' in table.columns:
        print("Column already named 'HYBAS_ID', no rename needed")
    else:
        raise ValueError(f"Neither 'id' nor 'HYBAS_ID' found in columns: {table.columns}")
    
    # Count rows for reporting
    row_count = table.count().execute()
    print(f"Processing {row_count:,} hexagons...")
    
    if args.use_local_cache:
        # Use local cache to reduce memory pressure
        local_dir = "/tmp/hex_rename"
        os.makedirs(local_dir, exist_ok=True)
        
        print("Writing to local cache with h0 partitioning...")
        table.to_parquet(f"{local_dir}/", partition_by="h0")
        
        print("Uploading to S3 with h0 partitioning...")
        (con
            .read_parquet(f"{local_dir}/**/*.parquet")
            .to_parquet(args.output_url, partition_by="h0")
        )
        
        print("Cleaning up local cache...")
        shutil.rmtree(local_dir)
    else:
        # Direct write to S3
        print("Writing to S3 with h0 partitioning...")
        table.to_parquet(args.output_url, partition_by="h0")
    
    print(f"\n✓ Successfully renamed column and wrote {row_count:,} hexagons to {args.output_url}")
    print("✓ Data is partitioned by h0 for efficient spatial queries")


if __name__ == "__main__":
    main()
