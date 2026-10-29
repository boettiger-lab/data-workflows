#!/usr/bin/env bash
# Global hex (#440): native 9, parents 8 and 0, mean, from the VRT over ETH's tiles (height.vrt,
# sd.vrt). --chunk-resolution 2: a whole-h0 window of 10 m pixels is tens of GB; a res-2 unit is ~2 GB.
# k8s, not the auto-chosen Armada: 5,882 units at 100 pods at a time stays inside the pod guideline,
# and k8s keeps per-index retries, which Armada drops.
set -euo pipefail
cd "$(dirname "$0")"
gen() {  # gen <layer> <value column>
  cng-datasets raster-workflow --dataset "canopy-height-2020/$1" \
    --source-url "s3://public-land-cover/canopy-height-2020/$1.vrt" --bucket public-land-cover \
    --namespace geo-workflows --h3-resolution 9 --parent-resolutions "8,0" --value-column "$2" \
    --hex-resampling mean --nodata 255 --hex-memory 16Gi --hex-cpu 4 --max-parallelism 100 --hex-retries 4 --max-failed-indexes 30 \
    --priority-class opportunistic --chunk-resolution 2 --backend k8s \
    --output-dir "global/$1"
}
gen height canopy_height_m
gen sd canopy_height_sd_m
