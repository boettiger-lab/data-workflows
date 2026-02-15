#!/bin/bash
# Create PMTiles from HydroBasins Level 4

set -e

echo "Converting HydroBasins Level 4 to GeoJSONSeq for tippecanoe..."

# Convert parquet to GeoJSONSeq (which tippecanoe can read)
# Use GeoJSONSeq for streaming large files
ogr2ogr \
  -f GeoJSONSeq \
  /tmp/hydrobasins_level_04.geojsonl \
  /vsis3/public-hydrobasins/level_04.parquet \
  -progress

echo "GeoJSONSeq created successfully!"

# Generate PMTiles from the GeoJSONSeq
echo "Generating PMTiles from GeoJSONSeq..."

tippecanoe \
  -o /tmp/hydrobasins_level_04.pmtiles \
  -l hydrobasins_level_04 \
  --drop-densest-as-needed \
  --extend-zooms-if-still-dropping \
  --force \
  /tmp/hydrobasins_level_04.geojsonl

echo "PMTiles created successfully!"

# Upload PMTiles to S3
echo "Uploading PMTiles to S3..."

# Configure mc alias if not already configured
mc alias set s3 https://${AWS_PUBLIC_ENDPOINT} ${AWS_ACCESS_KEY_ID} ${AWS_SECRET_ACCESS_KEY}

mc cp /tmp/hydrobasins_level_04.pmtiles s3/public-hydrobasins/level_04/hydrobasins_level_04.pmtiles

echo "PMTiles uploaded successfully!"

# Clean up temporary files
rm -f /tmp/hydrobasins_level_04.geojsonl /tmp/hydrobasins_level_04.pmtiles

echo "✓ PMTiles generation complete!"
