#!/bin/bash
# Convert WDPA GDB to GeoParquet and generate PMTiles

set -e

echo "Converting WDPA GDB to GeoParquet..."

# Convert GDB layer to GeoParquet
# Use -preserve_fid to keep OBJECTID as a regular field instead of just the FID
# This avoids Arrow type mapping issues when reading the parquet back
ogr2ogr \
  -f Parquet \
  /vsis3/public-wdpa/WDPA_Dec2025.parquet \
  /vsis3/public-wdpa/WDPA_Dec2025_Public.gdb \
  WDPA_poly_Dec2025 \
  -unsetFid \
  -progress

echo "GeoParquet created successfully!"

# Generate PMTiles directly from GDB using ogr2ogr pipe to tippecanoe
echo "Generating PMTiles from GDB..."

ogr2ogr -f GeoJSONSeq /vsistdout/ \
  /vsis3/public-wdpa/WDPA_Dec2025_Public.gdb \
  WDPA_poly_Dec2025 \
  | tippecanoe \
  -o /tmp/WDPA_Dec2025.pmtiles \
  -l wdpa \
  --drop-densest-as-needed \
  --extend-zooms-if-still-dropping \
  --force

echo "PMTiles created successfully!"

# Upload PMTiles to S3
echo "Uploading PMTiles to S3..."

aws s3 cp /tmp/WDPA_Dec2025.pmtiles s3://public-wdpa/WDPA_Dec2025.pmtiles \
  --endpoint-url https://s3-west.nrp-nautilus.io

echo "All conversions complete!"
