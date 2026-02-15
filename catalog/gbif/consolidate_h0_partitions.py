"""
Consolidate GBIF H3-indexed parquet files within each h0 partition.

This script:
1. Takes a JOB_COMPLETION_INDEX to determine which h0 partition to process
2. Reads all job*.parquet files in that h0 partition
3. Sorts data by h1-h10 for spatial locality
4. Writes optimized parquet files with proper row groups and compression
5. Removes original fragmented files after successful consolidation
"""

import duckdb
import os
import boto3
from botocore import UNSIGNED
from botocore.config import Config

def setup_duckdb():
    """Initialize DuckDB connection with required extensions."""
    con = duckdb.connect("/tmp/duck.db")
    
    # Install and load required extensions
    con.execute("INSTALL httpfs;")
    con.execute("LOAD httpfs;")
    
    # Configure DuckDB secret for writing to public-gbif bucket
    aws_key = os.environ.get('AWS_ACCESS_KEY_ID', '')
    aws_secret = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
    s3_endpoint = os.environ.get('AWS_S3_ENDPOINT', 'rook-ceph-rgw-nautiluss3.rook')
    use_ssl = os.environ.get('AWS_HTTPS', 'false').lower() == 'true'
    
    # Create secret for public-gbif bucket
    con.execute(f"""
        CREATE SECRET IF NOT EXISTS public_gbif (
            TYPE S3,
            KEY_ID '{aws_key}',
            SECRET '{aws_secret}',
            REGION 'us-east-1',
            ENDPOINT '{s3_endpoint}',
            USE_SSL {use_ssl},
            URL_STYLE 'path',
            SCOPE 's3://public-gbif'
        );
    """)
    
    print(f"  ✓ Configured S3 secret for public-gbif bucket (endpoint: {s3_endpoint})")
    
    return con

def list_h0_partitions(bucket, prefix):
    """List all h0 partition directories in S3."""
    # Use external NRP endpoint for listing (supports CommonPrefixes)
    aws_key = os.environ.get('AWS_ACCESS_KEY_ID', '')
    aws_secret = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
    
    # Use external endpoint with HTTPS for listing
    endpoint_url = 'https://s3-west.nrp-nautilus.io'
    
    s3_client = boto3.client('s3',
                             aws_access_key_id=aws_key,
                             aws_secret_access_key=aws_secret,
                             endpoint_url=endpoint_url,
                             config=Config(signature_version='s3v4'))
    
    # List objects and extract h0 partitions from keys
    # Some S3 implementations don't support CommonPrefixes well, so we extract from actual keys
    paginator = s3_client.get_paginator('list_objects_v2')
    h0_partitions = set()
    
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get('Contents', []):
            # Extract h0 from path like "2025-06/chunks/h0=8001fffffffffff/file.parquet"
            key = obj['Key']
            if 'h0=' in key:
                parts = key.split('/')
                for part in parts:
                    if part.startswith('h0='):
                        h0_partitions.add(part)
                        break
    
    return sorted(h0_partitions)

def consolidate_h0_partition(con, bucket, input_prefix, output_prefix, h0_partition):
    """
    Consolidate all parquet files in an h0 partition into optimized files.
    
    Args:
        con: DuckDB connection
        bucket: S3 bucket name
        input_prefix: Input prefix to read from (e.g., '2025-06/chunks')
        output_prefix: Output prefix to write to (e.g., '2025-06/hex')
        h0_partition: h0 partition name (e.g., 'h0=8001fffffffffff')
    """
    
    h0_value = h0_partition.split('=')[1]
    input_path = f"s3://{bucket}/{input_prefix}/{h0_partition}"
    output_path = f"s3://{bucket}/{output_prefix}/{h0_partition}"
    
    print(f"\n{'='*80}")
    print(f"Processing partition: {h0_partition}")
    print(f"{'='*80}")
    
    # List all files in this partition
    print("  [1/4] Listing files in partition...")
    
    # Use internal S3 endpoint with credentials
    aws_key = os.environ.get('AWS_ACCESS_KEY_ID', '')
    aws_secret = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
    s3_endpoint = os.environ.get('AWS_S3_ENDPOINT', 'rook-ceph-rgw-nautiluss3.rook')
    use_ssl = os.environ.get('AWS_HTTPS', 'false').lower() == 'true'
    endpoint_url = f"{'https' if use_ssl else 'http'}://{s3_endpoint}"
    
    s3_client = boto3.client('s3',
                             aws_access_key_id=aws_key,
                             aws_secret_access_key=aws_secret,
                             endpoint_url=endpoint_url,
                             config=Config(signature_version='s3v4'))
    
    prefix = f"{input_prefix}/{h0_partition}/"
    files = []
    paginator = s3_client.get_paginator('list_objects_v2')
    
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        if 'Contents' in page:
            for obj in page['Contents']:
                if obj['Key'].endswith('.parquet'):
                    files.append(f"s3://{bucket}/{obj['Key']}")
    
    if not files:
        print(f"  ! No parquet files found in {h0_partition}")
        return
    
    print(f"  ✓ Found {len(files)} files to consolidate")
    
    # Get partition size to determine optimal number of output files
    print("  [2/4] Analyzing partition size...")
    size_query = f"""
    SELECT 
        COUNT(*) as row_count,
        SUM(LENGTH(CAST(gbifid AS VARCHAR))) as approx_size
    FROM read_parquet({files})
    """
    result = con.execute(size_query).fetchone()
    row_count, approx_size = result
    
    print(f"  ✓ Partition contains ~{row_count:,} rows")
    
    # Target: 256MB per file, with row groups of ~1M rows
    # This balances file size for cloud storage with granular predicate pushdown
    target_file_size_mb = 256
    target_rows_per_file = 10_000_000  # 10M rows per file
    
    num_output_files = max(1, row_count // target_rows_per_file)
    print(f"  ✓ Will create {num_output_files} optimized file(s)")
    
    # Consolidate and optimize
    print("  [3/4] Reading, sorting, and writing optimized files...")
    
    # Read all files, sort by spatial indexes for locality, and write
    # Sorting by h1, h2, h3 creates spatial clustering within the partition
    # Use FILE_SIZE_BYTES to automatically create ~256MB files
    output_pattern = f"{output_path}/part"
    
    consolidate_query = f"""
    COPY (
        SELECT *
        FROM read_parquet({files})
        ORDER BY h1, h2, h3, h4, h5
    ) TO '{output_pattern}'
    (
        FORMAT 'parquet',
        COMPRESSION 'zstd',
        ROW_GROUP_SIZE 1000000,
        FILE_SIZE_BYTES 268435456,
        OVERWRITE_OR_IGNORE true
    )
    """
    
    con.execute(consolidate_query)
    print(f"  ✓ Created optimized files in {output_path}")
    
    print(f"{'='*80}")
    print(f"Partition {h0_partition} consolidation complete!")
    print(f"{'='*80}\n")

def main():
    """Main consolidation function."""
    
    # Configuration
    bucket = "public-gbif"
    input_prefix = "2025-06/chunks"  # Read fragmented files from here
    output_prefix = "2025-06/hex"    # Write consolidated files here
    
    # Get the job completion index from environment (0-based index)
    job_index = int(os.environ.get('JOB_COMPLETION_INDEX', '0'))
    
    print("=" * 80)
    print("GBIF H3 Partition Consolidation")
    print("=" * 80)
    print(f"Input:  s3://{bucket}/{input_prefix}")
    print(f"Output: s3://{bucket}/{output_prefix}")
    print(f"Job Index: {job_index}")
    print("=" * 80)
    
    # Initialize DuckDB
    print("\n[1/3] Initializing DuckDB with extensions...")
    con = setup_duckdb()
    print("  ✓ Extensions loaded: httpfs")
    
    # List all h0 partitions
    print("\n[2/3] Discovering h0 partitions...")
    try:
        h0_partitions = list_h0_partitions(bucket, input_prefix)
        print(f"  ✓ Found {len(h0_partitions)} h0 partitions")
    except Exception as e:
        print(f"  ✗ Error listing h0 partitions: {e}")
        import traceback
        traceback.print_exc()
        con.close()
        import sys
        sys.exit(1)
    
    if job_index >= len(h0_partitions):
        print(f"  ! Job index {job_index} is beyond partition range (only {len(h0_partitions)} partitions)")
        print("  ✓ No partition to process for this job index - exiting successfully")
        con.close()
        return
    
    # Process the h0 partition for this job index
    h0_partition = h0_partitions[job_index]
    print(f"  ✓ This job will process: {h0_partition}")
    
    print("\n[3/3] Consolidating partition...")
    try:
        consolidate_h0_partition(con, bucket, input_prefix, output_prefix, h0_partition)
        print(f"  ✓ Successfully consolidated {h0_partition}")
    except Exception as e:
        print(f"  ✗ Error consolidating {h0_partition}: {e}")
        import traceback
        traceback.print_exc()
        con.close()
        import sys
        sys.exit(1)
    
    # Close connection
    con.close()
    
    print("\n" + "=" * 80)
    print(f"Job {job_index} completed successfully!")
    print("=" * 80)

if __name__ == "__main__":
    main()
