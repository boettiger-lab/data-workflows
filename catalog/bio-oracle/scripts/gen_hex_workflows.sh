#!/usr/bin/env bash
# Generate the 18 Bio-ORACLE hex workflows (data-workflows #53).
#
# Native h6 with parents 5,0: the source is 0.05 deg (~31 km2 pixel) and the raster
# protocol anchors a ~5 km pixel at h6 (36.1 km2 cell, ratio 0.86, guardrail <= ~10).
# This dataset therefore carries no h8 column, by design.
#
# Three post-generation fixes are applied to every hex job:
#   1. cng-datasets flattens `--dataset a/b` to `a-b/hex/` for the parquet output;
#      rewrite it to `a/b/hex/` so the hex sits beside its COG.
#   2. Replace `backoffLimit: 0` with backoffLimitPerIndex + maxFailedIndexes, so a
#      partially-completed indexed run surfaces as Failed instead of silently
#      publishing a subset of h0 partitions (#409).
#   3. Exclude the known bad-egress hosts from nodeAffinity.
set -euo pipefail
cd "$(dirname "$0")/../../.."
source .venv/bin/activate

BUCKET=public-bio-oracle
OUTROOT=catalog/bio-oracle/k8s

# name|prefix|value_column
LAYERS='
thetao-mean|depthmean|thetao_mean
so-mean|depthmean|so_mean
sws-mean|depthmean|sws_mean
swd-mean-sin|depthmean|swd_sin
swd-mean-cos|depthmean|swd_cos
no3-mean|depthmean|no3_mean
po4-mean|depthmean|po4_mean
si-mean|depthmean|si_mean
o2-mean|depthmean|o2_mean
dfe-mean|depthmean|dfe_mean
phyc-mean|depthmean|phyc_mean
ph-mean|depthmean|ph_mean
bathymetry-mean|terrain|bathymetry_mean
slope|terrain|slope
aspect-sin|terrain|aspect_sin
aspect-cos|terrain|aspect_cos
tpi|terrain|topographic_position_index
tri|terrain|terrain_ruggedness_index
'

echo "$LAYERS" | grep -v '^$' | while IFS='|' read -r NAME PREFIX VALCOL; do
  OUT="$OUTROOT/$PREFIX/$NAME"
  cng-datasets raster-workflow \
    --dataset "$PREFIX/$NAME" \
    --source-url "s3://$BUCKET/$PREFIX/$NAME/$NAME-cog.tif" \
    --bucket "$BUCKET" --namespace geo-workflows \
    --h3-resolution 6 --parent-resolutions "5,0" \
    --value-column "$VALCOL" --hex-resampling mean \
    --hex-memory 32Gi --max-parallelism 61 \
    --output-dir "$OUT" >/dev/null

  HEX="$OUT/$PREFIX-$NAME-hex.yaml"

  # 1. un-flatten the parquet output path
  sed -i "s|s3://$BUCKET/$PREFIX-$NAME/hex/|s3://$BUCKET/$PREFIX/$NAME/hex/|g" "$HEX"

  # 2. partial indexed runs must fail, not publish a subset
  python3 - "$HEX" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
assert 'backoffLimit: 0' in s, f'{p}: expected backoffLimit: 0 to replace'
s = s.replace('  backoffLimit: 0\n',
              '  backoffLimitPerIndex: 2\n  maxFailedIndexes: 0\n')
# 3. keep pods off the known bad-egress hosts
old = """              - key: feature.node.kubernetes.io/pci-10de.present
                operator: NotIn"""
new = """              - key: kubernetes.io/hostname
                operator: NotIn
                values:
                - hpc-nrp-g1.nmsu.edu
                - service-02.nrp.mghpcc.org
              - key: feature.node.kubernetes.io/pci-10de.present
                operator: NotIn"""
assert old in s, f'{p}: expected nodeAffinity block'
s = s.replace(old, new)
open(p, 'w').write(s)
PY

  echo "generated $HEX ($VALCOL -> $PREFIX/$NAME/hex/)"
done
