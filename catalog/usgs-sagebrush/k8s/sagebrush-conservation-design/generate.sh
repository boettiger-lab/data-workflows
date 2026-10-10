#!/usr/bin/env bash
# Regenerate the per-period raster recipes for USGS Sagebrush Conservation Design (#770).
#
# One `cng-datasets raster-workflow` run per upstream period, each into its own <period>/
# directory, then the declared deviations below are applied with sed so the result is
# reproducible from this script alone. Run from the repo root with the .venv active
# (scripts/setup-venv.sh).
#
# Deviations from generated output, each also stamped as a comment into the files it touches:
#   1. preprocess-cog: `--resampling bilinear` -> `--resampling nearest`. The generator
#      hardcodes bilinear for the EPSG:4326 warp, which invents class codes on every class
#      boundary of a categorical raster (boettiger-lab/datasets#272).
#   2. hex + merge: write to sagebrush-conservation-design/hex{,-chunks}/period=<period>/
#      instead of sagebrush-conservation-design-<period>/hex{,-chunks}/, so all six periods
#      land in ONE hive-partitioned hex (period=*/h0=*). The generator has no period
#      dimension (boettiger-lab/datasets#172).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
OUT=catalog/usgs-sagebrush/k8s/sagebrush-conservation-design
B=public-usgs-sagebrush
DS=sagebrush-conservation-design

# period key -> upstream GeoTIFF basename (staged to s3://public-usgs-sagebrush/raw/sei/)
declare -A SRC=(
  [1998-2001]=SEI_1998_2001_30_Current.tif
  [2003-2006]=SEI_2003_2006_30_Current.tif
  [2008-2011]=SEI_2008_2011_30_Current.tif
  [2013-2016]=SEI_2013_2016_30_Current.tif
  [2017-2020]=SEI_2017_2020_30_Current.tif
  [2030-2060-rcp85]=SEI_2017_2020_30_ClimateOnly_RCP85_2030-2060_median.tif
)

for P in "${!SRC[@]}"; do
  D=$OUT/$P
  mkdir -p "$D"
  cng-datasets raster-workflow \
    --dataset "$DS-$P" \
    --source-url "s3://$B/raw/sei/${SRC[$P]}" \
    --bucket "$B" --namespace geo-workflows \
    --band 1 \
    --output-cog-name "$DS/$DS-$P-cog.tif" \
    --h3-resolution 10 --parent-resolutions 9,8,0 \
    --value-column sei_class --hex-resampling mode --nodata 0 \
    --h0-cells 9,19,20,36 --chunk-resolution 2 \
    --max-parallelism 40 --hex-memory 8Gi --hex-storage 20Gi --cog-storage 30Gi --merge-storage 50Gi \
    --output-dir "$D"

  # Deviation 1 (datasets#272)
  sed -i 's/--resampling bilinear/--resampling nearest/' "$D/$DS-$P-preprocess-cog.yaml" "$D/configmap.yaml"
  # Deviation 2 (datasets#172)
  sed -i "s#s3://$B/$DS-$P/hex-chunks/\?#s3://$B/$DS/hex-chunks/period=$P/#g; s#s3://$B/$DS-$P/hex\b#s3://$B/$DS/hex/period=$P#g" \
    "$D/$DS-$P-hex.yaml" "$D/$DS-$P-merge.yaml" "$D/configmap.yaml"

  for f in "$D/$DS-$P-preprocess-cog.yaml" "$D/$DS-$P-hex.yaml" "$D/$DS-$P-merge.yaml" "$D/configmap.yaml"; do
    sed -i '1i # DEVIATION from generated output (#770): applied by ../generate.sh -- preprocess-cog\n# resampling bilinear -> nearest (boettiger-lab/datasets#272); hex/merge paths moved under\n# sagebrush-conservation-design/hex{,-chunks}/period=<period>/ (boettiger-lab/datasets#172).' "$f"
  done
done
