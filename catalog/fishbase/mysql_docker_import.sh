#!/bin/bash
# Script to deploy MySQL in Docker, import SQL dump, and export tables to Parquet using DuckDB

# Check for required arguments
if [ $# -lt 2 ]; then
    echo "Usage: $0 <db_name> <sql_file>"
    echo "Example: $0 fbapp 2025-04-01/fbapp.sql"
    echo "Example: $0 slbapp 2025-04-01/slbapp.sql"
    exit 1
fi

# Set variables from command-line arguments
db_name=$1
sql_file=$2
db_user=root
db_pass=fishpass
container_name=fishbase-mysql

# 1. Start MySQL container
echo "Starting MySQL container..."
docker run --name $container_name \
  -e MYSQL_ROOT_PASSWORD=$db_pass \
  -p 3306:3306 \
  -d mysql:8.0

echo "Waiting for MySQL to initialize..."
sleep 10

# 2. Copy SQL file into container
echo "Copying SQL file to container..."
docker cp $sql_file $container_name:/tmp/${db_name}.sql

# 3. Import SQL dump into MySQL
echo "Importing SQL dump (this may take several minutes)..."
docker exec -i $container_name bash -c "mysql -uroot -p$db_pass < /tmp/${db_name}.sql"

echo ""
echo "MySQL import complete!"
echo ""
echo "MySQL connection details:"
echo "  Host: localhost"
echo "  Port: 3306"
echo "  Database: $db_name"
echo "  User: $db_user"
echo "  Password: $db_pass"
echo ""
echo "To export tables to Parquet using DuckDB, run:"
echo "  python export_to_parquet.py $db_name <version>"
echo "  Example: python export_to_parquet.py fbapp 25.04"
echo "  Example: python export_to_parquet.py slbapp 25.04"
echo ""
echo "To stop the container: docker stop $container_name"
echo "To start the container: docker start $container_name"
echo "To remove the container: docker rm -f $container_name"
