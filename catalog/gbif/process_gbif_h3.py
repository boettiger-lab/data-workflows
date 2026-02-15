"""
Process GBIF parquet data from S3, add H3 geospatial indexes (h0-h10), 
and write back to S3 partitioned by h0.

This script:
1. Reads parquet files from s3://gbif-open-data-us-east-1/occurrence/2025-06-01/occurrence.parquet/
2. Adds H3 index columns (h0 through h10) based on decimallongitude and decimallatitude
3. Writes results to s3://public-gbif/2025-06/chunks partitioned by h0
4. Appends to existing partitions to avoid overwriting
"""

import duckdb
import os
from pathlib import Path
import boto3
from botocore import UNSIGNED
from botocore.config import Config

def setup_duckdb():
    """Initialize DuckDB connection with required extensions."""
    con = duckdb.connect("/tmp/duckdb.db")
    
    # Install and load required extensions
    con.execute("INSTALL httpfs;")
    con.execute("LOAD httpfs;")
    con.execute("INSTALL h3 FROM community;")
    con.execute("LOAD h3;")
    con.execute("SET THREADS=40;") # I/O bound

    
    # Configure DuckDB secret for writing to public-gbif bucket
    # This uses the custom S3 endpoint from the k8s environment
    aws_key = os.environ.get('AWS_ACCESS_KEY_ID', '')
    aws_secret = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
    s3_endpoint = os.environ.get('AWS_S3_ENDPOINT', 'rook-ceph-rgw-nautiluss3.rook')
    use_ssl = os.environ.get('AWS_HTTPS', 'false').lower() == 'true'
    
    # Create secret for public-gbif bucket (our output bucket)
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
    
    # Create an anonymous secret for the public GBIF bucket (no credentials needed)
    con.execute("""
        CREATE SECRET IF NOT EXISTS gbif_public (
            TYPE S3,
            KEY_ID '',
            SECRET '',
            REGION 'us-east-1',
            SCOPE 's3://gbif-open-data-us-east-1'
        );
    """)
    
    print(f"  ✓ Configured S3 secret for public-gbif bucket (endpoint: {s3_endpoint})")
    print(f"  ✓ GBIF source bucket will use anonymous/public access (no auth)")
    
    return con

def get_source_files(con, source_path):
    """List all parquet files in the source S3 bucket."""
    query = f"""
    SELECT DISTINCT filename 
    FROM read_parquet('{source_path}/*', filename=true)
    LIMIT 1
    """
    try:
        # First check if we can access the bucket
        con.execute(f"SELECT COUNT(*) FROM read_parquet('{source_path}/*') LIMIT 1")
        return source_path
    except Exception as e:
        print(f"Error accessing source: {e}")
        return None

def process_gbif_chunk(con, source_files, output_base, job_index):
    """
    Process multiple GBIF parquet files and write to output bucket partitioned by h0.
    
    Args:
        con: DuckDB connection
        source_files: List of paths to source parquet files
        output_base: Base path for output (s3://public-gbif/2025-06/chunks)
        job_index: Job completion index for unique filenames
    """
    
    print(f"Processing {len(source_files)} files")
    print(f"  First file: {source_files[0]}")
    if len(source_files) > 1:
        print(f"  Last file: {source_files[-1]}")
    
    # Query to add H3 columns and partition by h0
    # We'll process each h0 partition separately to avoid overwriting
    # DuckDB's read_parquet accepts a list of files as a parameter
    query = """
    WITH data_with_h3 AS (
        SELECT 
            *,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 0) AS h0,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 1) AS h1,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 2) AS h2,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 3) AS h3,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 4) AS h4,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 5) AS h5,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 6) AS h6,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 7) AS h7,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 8) AS h8,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 9) AS h9,
            h3_latlng_to_cell(decimallatitude, decimallongitude, 10) AS h10
        FROM read_parquet(?)
        WHERE decimallatitude IS NOT NULL 
          AND decimallongitude IS NOT NULL
          AND decimallatitude BETWEEN -90 AND 90
          AND decimallongitude BETWEEN -180 AND 180
    )
    SELECT DISTINCT h0 FROM data_with_h3
    """
    # First, get all unique h0 values in this chunk
    h0_values = con.execute(query, [source_files]).fetchall()
    
    print(f"Found {len(h0_values)} unique h0 partitions in this chunk")
    
    # Process each h0 partition separately
    for (h0_val,) in h0_values:
        h0_hex = format(h0_val, 'x')  # Convert to hex string
        output_path = f"{output_base}/h0={h0_hex}"
        
        print(f"  Writing h0={h0_hex} to {output_path}")
        
        # Use deterministic filename: job_index + h0_hex
        # This prevents duplicates across runs and makes output idempotent
        filename = f"job{job_index:04d}_h0{h0_hex}.parquet"
        
        write_query = f"""
        COPY (
            SELECT 
                *,
                h3_latlng_to_cell(decimallatitude, decimallongitude, 0) AS h0,
                h3_latlng_to_cell(decimallatitude, decimallongitude, 1) AS h1,
                h3_latlng_to_cell(decimallatitude, decimallongitude, 2) AS h2,
                h3_latlng_to_cell(decimallatitude, decimallongitude, 3) AS h3,
                h3_latlng_to_cell(decimallatitude, decimallongitude, 4) AS h4,
                h3_latlng_to_cell(decimallatitude, decimallongitude, 5) AS h5,
                h3_latlng_to_cell(decimallatitude, decimallongitude, 6) AS h6,
                h3_latlng_to_cell(decimallatitude, decimallongitude, 7) AS h7,
                h3_latlng_to_cell(decimallatitude, decimallongitude, 8) AS h8,
                h3_latlng_to_cell(decimallatitude, decimallongitude, 9) AS h9,
                h3_latlng_to_cell(decimallatitude, decimallongitude, 10) AS h10
            FROM read_parquet(?)
            WHERE decimallatitude IS NOT NULL 
              AND decimallongitude IS NOT NULL
              AND decimallatitude BETWEEN -90 AND 90
              AND decimallongitude BETWEEN -180 AND 180
              AND h3_latlng_to_cell(decimallatitude, decimallongitude, 0) = ?
        ) TO '{output_path}/{filename}'
        (FORMAT 'parquet', COMPRESSION 'snappy')
        """
        con.execute(write_query, [source_files, h0_val])
        print(f"    ✓ Completed h0={h0_hex}")

def main():
    """Main processing function."""
    
    # Configuration
    source_path = "s3://gbif-open-data-us-east-1/occurrence/2025-06-01/occurrence.parquet"
    output_base = "s3://public-gbif/2025-06/chunks"
    
    # Get the job completion index from environment (0-based index)
    job_index = int(os.environ.get('JOB_COMPLETION_INDEX', '0'))
    
    # Configuration for chunking
    target_completions = 200  # Target number of jobs
    files_per_chunk = 25      # Files per job
    
    print("=" * 80)
    print("GBIF H3 Processing (Chunked)")
    print("=" * 80)
    print(f"Source: {source_path}")
    print(f"Output: {output_base}")
    print(f"Job Index: {job_index}")
    print(f"Files per chunk: {files_per_chunk}")
    print("=" * 80)
    
    # Initialize DuckDB
    print("\n[1/4] Initializing DuckDB with extensions...")
    con = setup_duckdb()
    print("  ✓ Extensions loaded: httpfs, h3")
    
    # Get list of ALL files to process using boto3 (much faster than DuckDB)
    print("\n[2/4] Discovering all source files...")
    
    try:
        # Parse S3 path
        bucket = 'gbif-open-data-us-east-1'
        prefix = 'occurrence/2025-06-01/occurrence.parquet/'
        
        # Create anonymous S3 client for public bucket
        s3_client = boto3.client('s3', 
                                 region_name='us-east-1',
                                 config=Config(signature_version=UNSIGNED))
        
        # List all objects in the bucket with the prefix
        all_files = []
        paginator = s3_client.get_paginator('list_objects_v2')
        
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            if 'Contents' in page:
                for obj in page['Contents']:
                    # Skip directories and only include actual files
                    if not obj['Key'].endswith('/'):
                        # Build full S3 path
                        full_path = f"s3://{bucket}/{obj['Key']}"
                        all_files.append(full_path)
        
        all_files.sort()
        print(f"  ✓ Found {len(all_files)} total files")
        
    except Exception as e:
        print(f"  ! Error listing files: {e}")
        import traceback
        traceback.print_exc()
        import sys
        sys.exit(1)
    
    # Determine which chunk of files this job should process
    print(f"\n[3/4] Determining file chunk for job index {job_index}...")
    start_idx = job_index * files_per_chunk
    end_idx = min(start_idx + files_per_chunk, len(all_files))
    
    if start_idx >= len(all_files):
        print(f"  ! Job index {job_index} is beyond file range (only {len(all_files)} files)")
        print("  ✓ No files to process for this job index - exiting successfully")
        con.close()
        return
    
    files_to_process = all_files[start_idx:end_idx]
    print(f"  ✓ Processing files {start_idx} to {end_idx-1} ({len(files_to_process)} files)")
    print(f"    First file: {files_to_process[0]}")
    print(f"    Last file: {files_to_process[-1]}")
    
    # Process this chunk of files
    print(f"\n[4/4] Processing chunk {job_index}...")
    try:
        process_gbif_chunk(con, files_to_process, output_base, job_index)
        print(f"  ✓ Chunk {job_index} completed successfully")
    except Exception as e:
        error_msg = f"Error processing chunk {job_index}: {e}"
        print(f"  ✗ {error_msg}")
        import traceback
        traceback.print_exc()
        con.close()
        import sys
        sys.exit(1)
    
    # Close connection
    con.close()
    
    print("\n" + "=" * 80)
    print(f"Chunk {job_index} completed successfully!")
    print("=" * 80)

if __name__ == "__main__":
    main()
