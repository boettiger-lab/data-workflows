import ibis
from ibis import _
from cng.utils import *
import os
import shutil
import subprocess

con = ibis.duckdb.connect()
set_secrets(con)
con.raw_sql("SET preserve_insertion_order=false")  # saves RAM
con.raw_sql("SET http_timeout=1200")
con.raw_sql("SET http_retries=30")

# Create /tmp/hex directory if it doesn't exist
local_dir = "/tmp/hex"
os.makedirs(local_dir, exist_ok=True)

print("Reading chunks and writing to local directory with h0 partitioning...")
# Read all chunks and write to local directory with h0 partitioning
(con
    .read_parquet("s3://public-wdpa/chunks/*.parquet")
    .to_parquet(f"{local_dir}/", partition_by="h0")
)

print("Uploading partitioned data to S3...")
# Upload from local directory to S3 with h0 partitioning
(con
    .read_parquet(f"{local_dir}/**/*.parquet")
    .to_parquet("s3://public-wdpa/hex/", partition_by="h0")
)

print("Cleaning up local directory...")
# Clean up local directory
shutil.rmtree(local_dir)

print("✓ Repartitioning complete!")

# Only clean up chunks directory if repartitioning was successful
print("Removing chunks directory from S3...")
try:
    # Try using mc (minio client) first
    result = subprocess.run(
        ["mc", "rm", "--recursive", "--force", "s3/public-wdpa/chunks/"],
        capture_output=True,
        text=True,
        timeout=300
    )
    if result.returncode == 0:
        print("✓ Chunks directory removed successfully")
    else:
        print(f"⚠ mc cleanup failed: {result.stderr}")
        # Try aws cli as fallback
        result = subprocess.run(
            ["aws", "s3", "rm", "s3://public-wdpa/chunks/", "--recursive",
             "--endpoint-url", os.environ.get("AWS_PUBLIC_ENDPOINT", "https://s3-west.nrp-nautilus.io")],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            print("✓ Chunks directory removed successfully (aws cli)")
        else:
            print(f"⚠ aws cleanup failed: {result.stderr}")
            print("Note: Chunks directory may need manual cleanup")
except Exception as e:
    print(f"⚠ Error during cleanup: {e}")
    print("Note: Chunks directory may need manual cleanup")

print("✓ All done!")
