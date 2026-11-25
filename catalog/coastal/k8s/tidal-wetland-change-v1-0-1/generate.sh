#!/usr/bin/env bash
# Generate the hex workflows for #800: one per change (loss, gain), each reading the derived class
# COG built by cogs.yaml (class = type x 100 + year; 9/99 = missing type/year; 0 = no change).
# `fractions` gives each class's coverage-weighted share of each h10 cell, so area is
# frac x cell area; consolidate.yaml turns the staging rows into the published hex with change,
# ecosystem, period and area_km2. Opportunistic: each h0 unit is short (pod-preemption skill).
set -euo pipefail
cd "$(dirname "$0")"
for c in loss gain; do
  cng-datasets raster-workflow --dataset "tidal-wetland-change-v1-0-1/staging-$c" \
    --source-url "s3://public-coastal/tidal-wetland-change-v1-0-1/staging/$c-class-cog.tif" \
    --bucket public-coastal --namespace geo-workflows \
    --h3-resolution 10 --parent-resolutions "8,0" --value-column class \
    --hex-resampling fractions --nodata 0 \
    --hex-memory 16Gi --hex-cpu 4 --max-parallelism 40 --priority-class opportunistic \
    --output-dir "$c"
done
