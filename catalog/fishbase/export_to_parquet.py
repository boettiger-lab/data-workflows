#!/usr/bin/env python3
"""
Export tables from MySQL to Parquet using DuckDB MySQL plugin
"""

import duckdb
import sys
import os
from pathlib import Path

# Check for required arguments
if len(sys.argv) < 3:
    print("Usage: python export_to_parquet.py <db_name> <version>")
    print("Example: python export_to_parquet.py fbapp 25.04")
    print("Example: python export_to_parquet.py slbapp 25.04")
    sys.exit(1)

db_name = sys.argv[1]
version = sys.argv[2]

# Determine output directory based on database name
db_prefix = 'fb' if db_name == 'fbapp' else 'slb'
output_dir = Path(f"data/{db_prefix}/v{version}/parquet")
output_dir.mkdir(parents=True, exist_ok=True)

print(f"Database: {db_name}")
print(f"Version: v{version}")
print(f"Output directory: {output_dir}")
print()

# MySQL connection parameters
MYSQL_HOST = "localhost"
MYSQL_PORT = 3306
MYSQL_DB = db_name
MYSQL_USER = "root"
MYSQL_PASSWORD = "fishpass"

# Connect to DuckDB
con = duckdb.connect('fishbase.duckdb')

# Install and load MySQL extension
print("Installing MySQL extension...")
con.execute("INSTALL mysql")
con.execute("LOAD mysql")

# Attach MySQL database
print("Connecting to MySQL database...")
con.execute(f"""
    ATTACH 'host={MYSQL_HOST} port={MYSQL_PORT} database={MYSQL_DB} user={MYSQL_USER} password={MYSQL_PASSWORD}' 
    AS mysql_db (TYPE MYSQL)
""")

# Get list of all tables
print("Fetching table list...")
tables = con.execute(f"""
    SELECT table_name 
    FROM mysql_db.information_schema.tables 
    WHERE table_schema = '{db_name}' AND table_type = 'BASE TABLE'
""").fetchall()

print(f"Found {len(tables)} tables to export\n")

# Export each table to Parquet
for (table_name,) in tables:
    output_file = output_dir / f"{table_name}.parquet"
    print(f"Exporting {table_name}...", end=" ")
    try:
        # Export to Parquet
        con.execute(f"""
            COPY (SELECT * FROM mysql_db.{db_name}.{table_name}) 
            TO '{output_file}' (FORMAT PARQUET)
        """)
        
        # Get row count
        row_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{output_file}')").fetchone()[0]
        print(f"✓ ({row_count:,} rows)")
    except Exception as e:
        print(f"✗ Error: {e}")

print(f"\nExport complete!")
print(f"All tables have been exported to: {output_dir}")

# Close connection
con.close()
