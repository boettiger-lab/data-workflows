#!/usr/bin/env bash
# Generate one cng-datasets raster-workflow per COG built by cogs.yaml (#792).
# DEVIATION from a single generated workflow: one workflow per epoch, because the generator has no
# epoch dimension (datasets#172). Each writes <collection>/staging-<epoch>/hex/; consolidate.yaml
# then joins them into <collection>/hex/ with epoch, km2 and fraction.
# `sum` with nodata 0,255 = coverage-weighted count of ecosystem pixels per h8 cell; since
# datasets#232 cells with no such pixel get no row.
set -euo pipefail
cd "$(dirname "$0")"
gen() {  # gen <collection> <epoch> <cog key> <value column> <hex memory>
  cng-datasets raster-workflow --dataset "$1/staging-$2" \
    --source-url "s3://public-coastal/$1/$3" --bucket public-coastal --namespace geo-workflows \
    --h3-resolution 8 --parent-resolutions 0 --value-column "$4" \
    --hex-resampling sum --nodata "0,255" --hex-memory "$5" --hex-cpu 4 --max-parallelism 40 \
    --priority-class opportunistic \
    --output-dir "hex/$1-$2"
}
# Opportunistic: each h0 unit runs minutes to under an hour, and many sit idle (ocean-only h0 or
# localizing the COG), which default priority puts outside the NRP usage policy (#804).
# Hex memory: densest h0 cells peaked at ~4 GiB at 16Gi (NRP flags pods far below their request).
for e in 1999-2001 2002-2004 2005-2007 2008-2010 2011-2013 2014-2016 2017-2019; do
  gen tidal-flats-v1-2 "$e" "tidal-flats-$e-cog.tif" flat_px 8Gi
done
for e in 1984-1986 1987-1989 1990-1992 1993-1995 1996-1998; do
  gen tidal-flats-v1-1 "$e" "tidal-flats-$e-cog.tif" flat_px 8Gi
done
gen tidal-flats-v1-1 datamask datamask-cog.tif mapped_px 8Gi
# 10 m source: ~9x the pixels per cell of the 30 m layers.
gen tidal-marsh-2020 2020 tidal-marsh-2020-cog.tif marsh_px 16Gi
# h0 position 17 (base cell 93) straddles the antimeridian and ran ~66 min per 100k-cell chunk
# (7 of 34 in 7.75 h); split into res-2 units the same h0 runs <= 4 min per unit (datasets#295,
# fixed upstream in datasets PR #298 after 0.11.4: seam cells are now read unwrapped). Separate prefix (job names would collide with the main
# run); its h0 partition is copied into staging-2020/hex/ once the main job is deleted.
cng-datasets raster-workflow --dataset tidal-marsh-2020/staging-2020-h0-17 \
  --source-url s3://public-coastal/tidal-marsh-2020/tidal-marsh-2020-cog.tif --bucket public-coastal \
  --namespace geo-workflows --h3-resolution 8 --parent-resolutions 0 --value-column marsh_px \
  --hex-resampling sum --nodata "0,255" --hex-memory 8Gi --hex-cpu 4 --max-parallelism 25 \
  --priority-class opportunistic --h0-subset 17 --chunk-resolution 2 \
  --output-dir hex/tidal-marsh-2020-2020-h0-17
# h0 position 73 (base cell 77) also straddles the antimeridian and was preempted repeatedly at
# the h0 level; same treatment (datasets#295).
cng-datasets raster-workflow --dataset tidal-marsh-2020/staging-2020-h0-73 \
  --source-url s3://public-coastal/tidal-marsh-2020/tidal-marsh-2020-cog.tif --bucket public-coastal \
  --namespace geo-workflows --h3-resolution 8 --parent-resolutions 0 --value-column marsh_px \
  --hex-resampling sum --nodata "0,255" --hex-memory 8Gi --hex-cpu 4 --max-parallelism 25 \
  --priority-class opportunistic --h0-subset 73 --chunk-resolution 2 \
  --output-dir hex/tidal-marsh-2020-2020-h0-73
# #811: the marsh COG is georeferenced -170..190, and before datasets#298 the hex step pruned every
# cell west of -170. Rebuild the h0 cells overlapping -180..-170 (60S-60N) with :latest (3d8baf1);
# the antimeridian fix also makes --chunk-resolution unnecessary. consolidate-marsh.yaml then
# rewrites just those partitions of tidal-marsh-2020/hex/.
cng-datasets raster-workflow --dataset tidal-marsh-2020/staging-2020 \
  --source-url s3://public-coastal/tidal-marsh-2020/tidal-marsh-2020-cog.tif --bucket public-coastal \
  --namespace geo-workflows --h3-resolution 8 --parent-resolutions 0 --value-column marsh_px \
  --hex-resampling sum --nodata "0,255" --hex-memory 16Gi --hex-cpu 4 --max-parallelism 14 \
  --priority-class opportunistic --h0-cells "6,11,17,25,35,45,56,63,77,90,93,106,109,117" \
  --output-dir hex/tidal-marsh-2020-2020-am
