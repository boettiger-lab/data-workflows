#!/usr/bin/env bash
# Peru-first hex (#440): the h0 base cells covering Peru (51, 69, 71, 89), read from the VRT over the
# tiles staged so far (height-peru.vrt / sd-peru.vrt), written to the final hex paths. The global run
# from height.vrt / sd.vrt rewrites these partitions with the full extent.
# --chunk-resolution 2: an h0 window of 10 m pixels is tens of GB; a res-2 unit is ~2 GB.
set -euo pipefail
cd "$(dirname "$0")"
gen() {  # gen <layer> <value column>
  cng-datasets raster-workflow --dataset "canopy-height-2020/$1" \
    --source-url "s3://public-land-cover/canopy-height-2020/$1-peru.vrt" --bucket public-land-cover \
    --namespace geo-workflows --h3-resolution 9 --parent-resolutions "8,0" --value-column "$2" \
    --hex-resampling mean --nodata 255 --hex-memory 16Gi --hex-cpu 4 --max-parallelism 40 \
    --priority-class opportunistic --h0-cells "51,69,71,89" --chunk-resolution 2 \
    --output-dir "peru/$1"
}
gen height canopy_height_m
gen sd canopy_height_sd_m
