import ibis
from ibis import _
from cng.utils import *
import os
import shutil

con = ibis.duckdb.connect()
set_secrets(con)
con.raw_sql("SET preserve_insertion_order=false") # saves RAM
con.raw_sql("SET http_timeout=1200")
con.raw_sql("SET http_retries=30")

# Create /tmp/hex directory if it doesn't exist
local_dir = "/tmp/hex"
os.makedirs(local_dir, exist_ok=True)

# remove NA and write to local directory first
(con
    .read_parquet("s3://public-wetlands/nwi/bigchunks/**").
    to_parquet(f"{local_dir}/", partition_by = "h0")
)

# Upload from local directory to S3
(con
    .read_parquet(f"{local_dir}/**/*.parquet")
    .to_parquet("s3://public-wetlands/nwi/hex/", partition_by = "h0")
)

# Clean up local directory
shutil.rmtree(local_dir)

