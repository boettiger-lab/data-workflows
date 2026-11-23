#!/usr/bin/env bash
# Generate the #427 raster workflows (Lumbierres et al. 2021 IUCN level-1 habitat map, 100 m).
# mode:      preprocess-cog (source is a striped GeoTIFF, not a COG) -> lumbierres-habitat-2021-cog.tif,
#            then hex at native 9, parents 8 and 0, dominant class per cell.
# fractions: same COG, share of each class per cell (like cgls-lc100-2019's hex-fractions).
# Short-unit fan-outs at opportunistic per #804.
# PINNED PATH (#1001): the fractions build is published at lumbierres-habitat-2021/fractions/hex/.
# On cng-datasets >= 0.17.0 (datasets#355) a fractions build writes <dataset>/hex-fractions/, so
# regenerating this unchanged would write lumbierres-habitat-2021/fractions/hex-fractions/, which the
# STAC does not reference. Do not regenerate on >= 0.17.0 without updating the published path and STAC.
set -euo pipefail
cd "$(dirname "$0")"
COMMON=(--bucket public-iucn --namespace geo-workflows --h3-resolution 9 --parent-resolutions "8,0"
        --value-column habitat_class --nodata "-32768" --hex-memory 32Gi --hex-cpu 4
        --max-parallelism 30 --priority-class opportunistic)
cng-datasets raster-workflow --dataset lumbierres-habitat-2021 \
  --source-url s3://public-iucn/raw/lumbierres-habitat-2021/habitat_CGLS.tiff \
  --hex-resampling mode "${COMMON[@]}" --output-dir mode
cng-datasets raster-workflow --dataset lumbierres-habitat-2021/fractions \
  --source-url s3://public-iucn/lumbierres-habitat-2021-cog.tif \
  --hex-resampling fractions "${COMMON[@]}" --output-dir fractions
