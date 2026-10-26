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
    --output-dir "hex/$1-$2"
}
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
