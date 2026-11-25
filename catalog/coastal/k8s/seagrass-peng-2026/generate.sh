#!/usr/bin/env bash
# Generate one cng-datasets raster-workflow per period (#788).
# DEVIATION from a single generated workflow: one workflow per period, because the generator's
# --years takes one source URL with a {year} placeholder, not a ~300-tile mosaic per period.
# Each mosaics its period's tiles (tiles-<period>.txt, staged by stage-raw.yaml) into one global
# 10 m COG, then hexes it to staging-<period>/hex/; consolidate.yaml joins the two into hex/ with a
# period column.
# Reducer: `total` integrates value x each pixel's spherical area. A pixel's value 1 means the
# pixel is wholly seagrass, i.e. 1 km2 of seagrass per km2, so declaring the units km2/km2 makes
# the column seagrass km2 per cell. nodata 0 = not seagrass: cells with none get no row.
set -euo pipefail
cd "$(dirname "$0")"
# 2023-2024: the 17 h0 positions that ran over 40 min in 2019-2020 (median 15.5 min; up to 85 min,
# and a 70-min unit was preempted at opportunistic) are built separately below, split into res-1
# units so each pod is short. The main 2023-2024 job takes the other 105 positions.
HEAVY="0,5,14,20,34,35,43,45,52,75,78,88,93,96,98,100,105"
REST=$(python3 -c "h={$HEAVY}; print(','.join(str(i) for i in range(122) if i not in h))")
declare -A EXTRA=([2023-2024]="--h0-subset $REST")
for p in 2019-2020 2023-2024; do
  urls=()
  inner="GlobalSeagrass${p/-/_}"   # each zip holds one folder, kept by stage-raw.yaml
  while read -r t; do urls+=(--source-url "s3://public-coastal/raw/seagrass-peng-2026/$p/$inner/$t"); done < "tiles-$p.txt"
  cng-datasets raster-workflow --dataset "seagrass-peng-2026/staging-$p" "${urls[@]}" \
    --bucket public-coastal --namespace geo-workflows \
    --output-cog-name "seagrass-peng-2026/seagrass-$p-cog.tif" --cog-storage 100Gi \
    --h3-resolution 10 --parent-resolutions "8,0" --value-column seagrass_km2 \
    --hex-resampling total --value-units "km2/km2" --nodata 0 \
    --hex-memory 16Gi --hex-cpu 4 --max-parallelism 40 --priority-class opportunistic \
    --output-dir "$p" ${EXTRA[$p]:-}
done
# The heavy positions of 2023-2024, at --chunk-resolution 1 (7 units each; the generator adds a merge
# step that restores one file per h0). Own prefix: staging-2023-2024-heavy/hex/.
p=2023-2024; urls=(); inner="GlobalSeagrass${p/-/_}"
while read -r t; do urls+=(--source-url "s3://public-coastal/raw/seagrass-peng-2026/$p/$inner/$t"); done < "tiles-$p.txt"
cng-datasets raster-workflow --dataset "seagrass-peng-2026/staging-$p-heavy" "${urls[@]}" \
  --bucket public-coastal --namespace geo-workflows \
  --output-cog-name "seagrass-peng-2026/seagrass-$p-cog.tif" --cog-storage 100Gi \
  --h3-resolution 10 --parent-resolutions "8,0" --value-column seagrass_km2 \
  --hex-resampling total --value-units "km2/km2" --nodata 0 \
  --hex-memory 16Gi --hex-cpu 4 --max-parallelism 40 --priority-class opportunistic \
  --h0-subset "$HEAVY" --chunk-resolution 1 \
  --output-dir "$p-heavy"
