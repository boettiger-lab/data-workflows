#!/usr/bin/env python3
"""
Post-process IUCN hexed datasets to remove 0 values.
Reads from s3://public-iucn/hex/{layer_name}/** 
Writes to s3://public-iucn/richness/hex/{layer_name}/** partitioned by h0
"""

import argparse
import os
import ibis
from ibis import _


def setup_s3_connection():
    """Configure S3 connection using environment variables."""
    con = ibis.duckdb.connect(extensions=["spatial", "h3"])
    
    # Configure S3 access
    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    endpoint = os.environ.get("AWS_PUBLIC_ENDPOINT", "s3-west.nrp-nautilus.io")
    
    con.raw_sql(f"""
        CREATE SECRET IF NOT EXISTS (
            TYPE S3,
            KEY_ID '{access_key}',
            SECRET '{secret_key}',
            REGION 'us-west-2',
            ENDPOINT '{endpoint}',
            URL_STYLE 'path'
        );
    """)
    
    return con


def process_layer(layer_name: str, value_column: str):
    """
    Process a single layer: read, filter out 0s, write with h0 partitioning.
    
    Args:
        layer_name: Name of the layer (e.g., 'reptiles_thr_sr')
        value_column: Name of the value column to filter
    """
    print(f"Processing layer: {layer_name}")
    
    con = setup_s3_connection()
    
    # Read input data
    input_path = f"s3://public-iucn/hex/{layer_name}/**"
    print(f"Reading from: {input_path}")
    df = con.read_parquet(input_path)
    
    # Filter out 0 values
    print(f"Filtering out 0 values from column: {value_column}")
    df_filtered = df.filter(_[value_column] != 0)
    
    # Count records
    total_records = df.count().execute()
    filtered_records = df_filtered.count().execute()
    removed_records = total_records - filtered_records
    
    print(f"Total records: {total_records:,}")
    print(f"Records after filtering: {filtered_records:,}")
    print(f"Records removed (0 values): {removed_records:,}")
    
    # Write output partitioned by h0
    output_path = f"s3://public-iucn/richness/hex/{layer_name}"
    print(f"Writing to: {output_path} (partitioned by h0)")
    
    df_filtered.to_parquet(
        output_path,
        partition_by="h0",
        compression="zstd"
    )
    
    print(f"✓ Successfully processed {layer_name}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Post-process IUCN hexed datasets to remove 0 values"
    )
    parser.add_argument(
        "--layer-name",
        required=True,
        help="Layer name (e.g., 'reptiles_thr_sr')"
    )
    parser.add_argument(
        "--value-column",
        required=True,
        help="Value column name to filter (usually same as layer name)"
    )
    
    args = parser.parse_args()
    
    try:
        process_layer(args.layer_name, args.value_column)
        print("Post-processing completed successfully!")
    except Exception as e:
        print(f"Error processing {args.layer_name}: {e}")
        raise


if __name__ == "__main__":
    main()
