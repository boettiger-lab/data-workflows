#!/bin/bash
# Convert WDPA GDB to GeoParquet

set -e

echo "Converting WDPA GDB to GeoParquet..."

# Convert GDB layer to GeoParquet
ogr2ogr \
  -f Parquet \
  /vsis3/public-wdpa/WDPA_Dec2025.parquet \
  /vsis3/public-wdpa/WDPA_Dec2025_Public.gdb \
  WDPA_poly_Dec2025 \
  -progress

echo "GeoParquet created successfully!"
