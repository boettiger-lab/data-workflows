#!/bin/bash
# Create PMTiles from Ramsar GeoParquet

set -e

echo "Converting GeoParquet to GeoJSONSeq for tippecanoe..."

# Convert parquet to GeoJSONSeq (which tippecanoe can read)
# Set encoding options to handle UTF-8 properly
ogr2ogr \
  -f GeoJSONSeq \
  /tmp/ramsar_complete.geojsonl \
  /vsis3/public-wetlands/ramsar/ramsar_complete.parquet \
  -lco ENCODING=UTF-8 \
  -progress

echo "GeoJSONSeq created successfully!"

# Generate PMTiles from the GeoJSONSeq
echo "Generating PMTiles from GeoJSONSeq..."

# Use --read-parallel to handle encoding issues more gracefully
tippecanoe \
  -o /tmp/ramsar_complete.pmtiles \
  -l ramsar \
  --drop-densest-as-needed \
  --extend-zooms-if-still-dropping \
  --force \
  --attribute-type="Site name":string \
  /tmp/ramsar_complete.geojsonl

echo "PMTiles created successfully!"

# Upload PMTiles to S3
echo "Uploading PMTiles to S3..."

# Configure mc alias if not already configured
mc alias set s3 https://${AWS_PUBLIC_ENDPOINT} ${AWS_ACCESS_KEY_ID} ${AWS_SECRET_ACCESS_KEY}

mc cp /tmp/ramsar_complete.pmtiles s3/public-wetlands/ramsar/ramsar_wetlands.pmtiles

echo "PMTiles uploaded successfully!"
