#!/usr/bin/env bash
# Generate the hex workflows for #800: one per change (loss, gain), each reading the derived class
# COG built by cogs.yaml (class = type x 100 + year; 9/99 = missing type/year; 0 = no change).
# `fractions` gives each class's coverage-weighted share of each h10 cell, so area is
# frac x cell area; consolidate.yaml turns the staging rows into the published hex with change,
# ecosystem, period and area_km2. Opportunistic: each h0 unit is short (pod-preemption skill).
# Generated before the class rasters existed, the hex jobs read them directly. Regenerated after,
# the tool flags them "not a COG" (no overviews) and adds a preprocess-cog copy, so the gain and
# gain-heavy hex manifests carry a DEVIATION pointing them back at the class raster; the loss
# manifests are the original generation, as run.
set -euo pipefail
cd "$(dirname "$0")"
# Gain: the six h0 positions whose loss units ran past 25 min (median 5.3 min; 107 was preempted at
# ~40 min) are built separately, in res-1 units, under staging-gain-heavy/; the main gain job
# takes the other 116.
HEAVY="4,14,21,44,78,107"
REST=$(python3 -c "h={$HEAVY}; print(','.join(str(i) for i in range(122) if i not in h))")
declare -A EXTRA=([gain]="--h0-subset $REST")
for c in loss gain; do
  cng-datasets raster-workflow --dataset "tidal-wetland-change-v1-0-1/staging-$c" \
    --source-url "s3://public-coastal/tidal-wetland-change-v1-0-1/staging/$c-class-cog.tif" \
    --bucket public-coastal --namespace geo-workflows \
    --h3-resolution 10 --parent-resolutions "8,0" --value-column class \
    --hex-resampling fractions --nodata 0 \
    --hex-memory 16Gi --hex-cpu 4 --max-parallelism 40 --priority-class opportunistic \
    --output-dir "$c" ${EXTRA[$c]:-}
done
cng-datasets raster-workflow --dataset "tidal-wetland-change-v1-0-1/staging-gain-heavy" \
  --source-url "s3://public-coastal/tidal-wetland-change-v1-0-1/staging/gain-class-cog.tif" \
  --bucket public-coastal --namespace geo-workflows \
  --h3-resolution 10 --parent-resolutions "8,0" --value-column class \
  --hex-resampling fractions --nodata 0 \
  --hex-memory 16Gi --hex-cpu 4 --max-parallelism 40 --priority-class opportunistic \
  --h0-subset "$HEAVY" --chunk-resolution 1 \
  --output-dir gain-heavy
