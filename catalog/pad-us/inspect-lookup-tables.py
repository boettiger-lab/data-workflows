"""
Inspect PAD-US lookup tables to document their structure
"""

import duckdb

# S3 endpoint and public access
base_url = "https://s3-west.nrp-nautilus.io/public-padus/padus-4-1/lookup"

tables = [
    "Public_Access",
    "Category", 
    "Designation_Type",
    "GAP_Status",
    "IUCN_Category",
    "Agency_Name",
    "Agency_Type",
    "State_Name"
]

con = duckdb.connect()

print("# PAD-US 4.1 Lookup Tables\n")

for table in tables:
    url = f"{base_url}/{table}.parquet"
    
    print(f"## {table}\n")
    
    # Get row count
    count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{url}')").fetchone()[0]
    print(f"**Rows:** {count}\n")
    
    # Get schema
    schema = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{url}')").fetchall()
    print("**Schema:**")
    for col_name, col_type, _, _, _, _ in schema:
        print(f"- `{col_name}`: {col_type}")
    print()
    
    # Show all rows (since they're small lookup tables)
    print("**All Values:**")
    print("```")
    result = con.execute(f"SELECT * FROM read_parquet('{url}') ORDER BY 1").fetchall()
    for row in result:
        print(row)
    print("```\n")
    print("---\n")
