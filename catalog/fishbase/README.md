# FishBase Data Processing

## Importing FishBase/SeaLifeBase SQL to Parquet via DuckDB

This workflow imports FishBase (fbapp) and SeaLifeBase (slbapp) SQL dumps into a MySQL Docker container, then uses DuckDB's MySQL plugin to directly export all tables to Parquet format, preserving schema types.

### Prerequisites

- Docker installed and running
- Python 3 with DuckDB installed (`pip install duckdb`)

### Steps

#### Import FishBase (fbapp)

1. **Deploy MySQL and import SQL dump**:

   ```bash
   bash mysql_docker_import.sh fbapp 2025-04-01/fbapp.sql
   ```

2. **Export tables to Parquet using DuckDB**:

   ```bash
   python export_to_parquet.py fbapp 25.04
   ```

   This exports all tables to `data/fb/v25.04/parquet/`

#### Import SeaLifeBase (slbapp)

1. **Remove the existing container and start fresh**:

   ```bash
   docker rm -f fishbase-mysql
   bash mysql_docker_import.sh slbapp 2025-04-01/slbapp.sql
   ```

2. **Export tables to Parquet using DuckDB**:

   ```bash
   python export_to_parquet.py slbapp 25.04
   ```

   This exports all tables to `data/slb/v25.04/parquet/`

### What This Does

The import script:
- Starts a MySQL 8.0 container
- Imports the specified SQL dump into the database
- Exposes MySQL on port 3306

The export script:
- Connects to the MySQL container using DuckDB's MySQL plugin
- Discovers all tables in the specified database
- Exports each table to a `.parquet` file with full schema preservation
- Organizes files by database and version: `data/{fb|slb}/v{YY.MM}/parquet/`

### Access the data in DuckDB

```python
import duckdb
con = duckdb.connect()

# Read a parquet file
con.execute("SELECT * FROM read_parquet('data/fb/v25.04/parquet/species.parquet') LIMIT 10")

# Or scan entire directory
con.execute("SELECT * FROM read_parquet('data/fb/v25.04/parquet/*.parquet')")
```

### MySQL Container Management

- Stop container: `docker stop fishbase-mysql`
- Start container: `docker start fishbase-mysql`
- Remove container: `docker rm -f fishbase-mysql`

### Benefits of This Approach

- **Type Safety**: DuckDB preserves MySQL column types (INT, VARCHAR, DATETIME, etc.)
- **Efficiency**: Direct database-to-parquet conversion without intermediate files
- **Simplicity**: Single Python script handles all tables automatically