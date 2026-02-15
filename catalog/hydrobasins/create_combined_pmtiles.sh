#!/bin/bash
# Create unified PMTiles from HydroBasins Levels 3-6 with zoom-based detail
# Zoom 0-1: Level 3 (major sub-continental watersheds)
# Zoom 2: Level 4
# Zoom 3-4: Level 5
# Zoom 5+: Level 6 (finest detail)

set -e

echo "=========================================="
echo "Creating Unified HydroBasins PMTiles"
echo "=========================================="

# Convert each level to GeoJSONSeq
echo ""
echo "Step 1/5: Converting Level 3 to GeoJSONSeq..."
ogr2ogr \
  -f GeoJSONSeq \
  /tmp/level_03.geojsonl \
  /vsis3/public-hydrobasins/level_03.parquet \
  -progress

echo ""
echo "Step 2/5: Converting Level 4 to GeoJSONSeq..."
ogr2ogr \
  -f GeoJSONSeq \
  /tmp/level_04.geojsonl \
  /vsis3/public-hydrobasins/level_04.parquet \
  -progress

echo ""
echo "Step 3/5: Converting Level 5 to GeoJSONSeq..."
ogr2ogr \
  -f GeoJSONSeq \
  /tmp/level_05.geojsonl \
  /vsis3/public-hydrobasins/level_05.parquet \
  -progress

echo ""
echo "Step 4/5: Converting Level 6 to GeoJSONSeq..."
ogr2ogr \
  -f GeoJSONSeq \
  /tmp/level_06.geojsonl \
  /vsis3/public-hydrobasins/level_06.parquet \
  -progress

echo ""
echo "✓ All GeoJSONSeq files created successfully!"
echo ""

# Concatenate all GeoJSONSeq files and create unified PMTiles in one pass
# This avoids the memory-intensive tile-join merge operation
echo "Step 5/5: Generating unified PMTiles from all levels..."
echo ""

# Add level metadata and zoom range controls to each feature
echo "  - Adding level metadata and zoom controls..."
# Level 3: Zoom 0-1 only
python3 -c "
import json
import sys
for line in open('/tmp/level_03.geojsonl'):
    feature = json.loads(line)
    feature['tippecanoe'] = {'minzoom': 0, 'maxzoom': 1}
    feature['properties']['level'] = 3
    print(json.dumps(feature, separators=(',', ':')))
" > /tmp/level_03_tagged.geojsonl

# Level 4: Zoom 2 only
python3 -c "
import json
import sys
for line in open('/tmp/level_04.geojsonl'):
    feature = json.loads(line)
    feature['tippecanoe'] = {'minzoom': 2, 'maxzoom': 2}
    feature['properties']['level'] = 4
    print(json.dumps(feature, separators=(',', ':')))
" > /tmp/level_04_tagged.geojsonl

# Level 5: Zoom 3-4
python3 -c "
import json
import sys
for line in open('/tmp/level_05.geojsonl'):
    feature = json.loads(line)
    feature['tippecanoe'] = {'minzoom': 3, 'maxzoom': 4}
    feature['properties']['level'] = 5
    print(json.dumps(feature, separators=(',', ':')))
" > /tmp/level_05_tagged.geojsonl

# Level 6: Zoom 5+
python3 -c "
import json
import sys
for line in open('/tmp/level_06.geojsonl'):
    feature = json.loads(line)
    feature['tippecanoe'] = {'minzoom': 5, 'maxzoom': 12}
    feature['properties']['level'] = 6
    print(json.dumps(feature, separators=(',', ':')))
" > /tmp/level_06_tagged.geojsonl

echo "  - Concatenating all levels..."
cat /tmp/level_03_tagged.geojsonl \
    /tmp/level_04_tagged.geojsonl \
    /tmp/level_05_tagged.geojsonl \
    /tmp/level_06_tagged.geojsonl > /tmp/hydrobasins_all.geojsonl

echo "  - Creating unified PMTiles with zoom-controlled detail..."
tippecanoe \
  -o /tmp/hydrobasins_unified.pmtiles \
  -l hydrobasins \
  --force \
  -Z 0 -z 12 \
  /tmp/hydrobasins_all.geojsonl

echo ""
echo "✓ Unified PMTiles created successfully!"
echo ""

# Upload to S3
echo "Uploading unified PMTiles to S3..."

# Configure mc alias if not already configured
mc alias set s3 https://${AWS_PUBLIC_ENDPOINT} ${AWS_ACCESS_KEY_ID} ${AWS_SECRET_ACCESS_KEY}

mc cp /tmp/hydrobasins_unified.pmtiles s3/public-hydrobasins/hydrobasins_unified.pmtiles

echo ""
echo "✓ PMTiles uploaded successfully to s3://public-hydrobasins/hydrobasins_unified.pmtiles"
echo ""

# Clean up temporary files
echo "Cleaning up temporary files..."
rm -f /tmp/level_03.geojsonl \
      /tmp/level_04.geojsonl \
      /tmp/level_05.geojsonl \
      /tmp/level_06.geojsonl \
      /tmp/level_03_tagged.geojsonl \
      /tmp/level_04_tagged.geojsonl \
      /tmp/level_05_tagged.geojsonl \
      /tmp/level_06_tagged.geojsonl \
      /tmp/hydrobasins_all.geojsonl \
      /tmp/hydrobasins_unified.pmtiles

echo ""
echo "=========================================="
echo "✓ Unified PMTiles generation complete!"
echo "=========================================="
echo ""
echo "All HydroBasins levels 3-6 combined into a single PMTiles file"
echo "with automatic detail optimization by zoom level."
echo "Features include a 'level' property (3-6) for filtering/styling."
echo ""
