#!/usr/bin/env bash
# Generate the cluster job YAMLs for the CBN plant-richness family (issue #229).
#
# Two Kling et al. (2018) CBN rasters, each processed 3 ways from ONE WGS84
# reprojection of the EPSG:3310 source:
#   1. full continuous COG  + hex-max  (reducer=max  — peak richness per cell)
#   2. (same COG)           + hex-mean (reducer=mean — area-weighted mean per cell)
#   3. 80th-percentile hotspot COG (pixels >= P80) + p80-hex (reducer=max)
#
# Per dataset the build order is: cog -> hex-max -> hex-mean -> p80-cog -> p80-hex.
# Hex jobs read the WGS84 COG (so hex MAX validates exactly against the COG).
# exact-extract (tool default) does area-weighted per-cell aggregation, one row per cell.
set -euo pipefail
cd "$(dirname "$0")/k8s"

BUCKET=public-ca30x30
IMAGE=ghcr.io/boettiger-lab/datasets:latest

# dataset-segment | source-raster-filename | value-column
# Source rasters carry a valid CA-Albers WKT but no EPSG authority code ("unnamed"
# PROJCS), which makes the tool's AutoIdentifyEPSG() crash ("Unsupported SRS").
# We re-tag them to EPSG:3310 (lossless metadata edit; the WKT IsSame(3310)) and
# stage the normalized *_epsg3310.tif into raw/ — that is the build input below.
DATASETS=(
  "plant-richness|species_D_epsg3310.tif|richness"
  "rarity-weighted-endemic-plant-richness|endemicspecies_E_epsg3310.tif|rwe"
)

# ---- shared pod fragments -------------------------------------------------
ENV_BLOCK=$(cat <<'EOF'
        env:
        - name: AWS_ACCESS_KEY_ID
          valueFrom: {secretKeyRef: {name: aws, key: AWS_ACCESS_KEY_ID}}
        - name: AWS_SECRET_ACCESS_KEY
          valueFrom: {secretKeyRef: {name: aws, key: AWS_SECRET_ACCESS_KEY}}
        - {name: AWS_S3_ENDPOINT, value: rook-ceph-rgw-nautiluss3.rook}
        - {name: AWS_PUBLIC_ENDPOINT, value: s3-west.nrp-nautilus.io}
        - {name: AWS_HTTPS, value: 'false'}
        - {name: AWS_VIRTUAL_HOSTING, value: 'FALSE'}
        - {name: GDAL_DATA, value: /usr/share/gdal}
        - {name: PYTHONPATH, value: /usr/lib/python3/dist-packages}
EOF
)

VOL_AFFINITY=$(cat <<'EOF'
        volumeMounts:
        - {name: rclone-config, mountPath: /root/.config/rclone, readOnly: true}
      volumes:
      - name: rclone-config
        secret: {secretName: rclone-config}
      priorityClassName: opportunistic
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - {key: feature.node.kubernetes.io/pci-10de.present, operator: NotIn, values: ['true']}
EOF
)

# ---- single-pod job (COG build / P80 build) -------------------------------
# args: $1 job-name  $2 mem  $3 ephemeral  $4 command-string  -> stdout
single_job() {
  local name=$1 mem=$2 eph=$3 cmd=$4
  cat <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: ${name}
  labels: {k8s-app: ${name}}
spec:
  backoffLimit: 1
  ttlSecondsAfterFinished: 10800
  template:
    metadata:
      labels: {k8s-app: ${name}}
    spec:
      restartPolicy: Never
      containers:
      - name: task
        image: ${IMAGE}
        imagePullPolicy: Always
${ENV_BLOCK}
        command:
        - bash
        - -c
        - |
$(printf '%s\n' "$cmd" | sed 's/^/            /')
        resources:
          requests: {cpu: '4', memory: ${mem}, ephemeral-storage: ${eph}}
          limits:   {cpu: '4', memory: ${mem}, ephemeral-storage: ${eph}}
${VOL_AFFINITY}
EOF
}

# ---- indexed hex job (122 h0 regions) -------------------------------------
# args: $1 job-name  $2 command-string -> stdout
hex_job() {
  local name=$1 cmd=$2
  cat <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: ${name}
  labels: {k8s-app: ${name}}
spec:
  completions: 122
  parallelism: 61
  completionMode: Indexed
  backoffLimitPerIndex: 2
  maxFailedIndexes: 0
  podFailurePolicy:
    rules:
    - action: Ignore
      onPodConditions:
      - {type: DisruptionTarget}
  ttlSecondsAfterFinished: 10800
  template:
    metadata:
      labels: {k8s-app: ${name}}
    spec:
      restartPolicy: Never
      containers:
      - name: hex-task
        image: ${IMAGE}
        imagePullPolicy: Always
${ENV_BLOCK}
        command:
        - bash
        - -c
        - |
$(printf '%s\n' "$cmd" | sed 's/^/            /')
        resources:
          requests: {cpu: '4', memory: 32Gi, ephemeral-storage: 20Gi}
          limits:   {cpu: '4', memory: 32Gi, ephemeral-storage: 20Gi}
${VOL_AFFINITY}
EOF
}

for entry in "${DATASETS[@]}"; do
  IFS='|' read -r DS SRC VAL <<<"$entry"
  DIR="$DS"; mkdir -p "$DIR"
  PFX="s3://${BUCKET}/${DS}"
  RAW="${PFX}/raw/${SRC}"
  COG="${PFX}/${DS}-cog.tif"
  P80COG="${PFX}/${DS}-p80-cog.tif"

  # 1. full continuous WGS84 COG (reproject) + fill normalization.
  #    The 3310->4326 warp emits a SECOND near-nodata value (~-3.3999997e38)
  #    alongside the declared -3.4e38, which a single --nodata cannot exclude
  #    (leaks ~850k fill pixels into hex/percentile). Collapse every fill pixel
  #    (< -1e30 or non-finite) to one exact float32 sentinel and re-flag nodata,
  #    so downstream hex (--nodata -3.4e38) and the P80 pass exclude all fill.
  single_job "${DS}-cog" 32Gi 20Gi \
"set -e
cng-datasets raster --input \"${RAW}\" --output-cog \"${COG}\" \\
  --target-crs EPSG:4326 --value-column ${VAL} --nodata -3.4e38 --resampling near --compression deflate
python3 - <<'PY'
import subprocess, numpy as np
from osgeo import gdal
gdal.UseExceptions()
ND = np.float32(-3.4e38)
subprocess.run(['rclone','copyto','nrp:${BUCKET}/${DS}/${DS}-cog.tif','/tmp/full.tif'], check=True)
ds = gdal.Open('/tmp/full.tif'); b = ds.GetRasterBand(1); arr = b.ReadAsArray()
fill = ~np.isfinite(arr) | (arr < -1e30)
arr = np.where(fill, ND, arr).astype('float32')
drv = gdal.GetDriverByName('GTiff')
t = drv.Create('/tmp/clean.tif', ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Float32)
t.SetGeoTransform(ds.GetGeoTransform()); t.SetProjection(ds.GetProjection())
ob = t.GetRasterBand(1); ob.WriteArray(arr); ob.SetNoDataValue(float(ND)); t.FlushCache(); t = None
gdal.Translate('/tmp/clean-cog.tif', '/tmp/clean.tif', format='COG',
               creationOptions=['COMPRESS=DEFLATE','BLOCKSIZE=512'])
v = arr[~fill]
print('CLEANED valid=%d fill=%d min=%.5f max=%.5f' % (int((~fill).sum()), int(fill.sum()), float(v.min()), float(v.max())))
PY
rclone copyto /tmp/clean-cog.tif nrp:${BUCKET}/${DS}/${DS}-cog.tif
echo 'clean COG uploaded'" \
    > "${DIR}/${DS}-cog.yaml"

  # 2. hex-max (peak richness per cell)
  hex_job "${DS}-hex-max" \
"set -e
cng-datasets raster --input \"${COG}\" --output-parquet ${PFX}/hex-max/ \\
  --h0-index \${JOB_COMPLETION_INDEX} --resolution 8 --parent-resolutions 0 \\
  --value-column ${VAL} --hex-resampling max --nodata -3.4e38" \
    > "${DIR}/${DS}-hex-max.yaml"

  # 3. hex-mean (area-weighted mean richness per cell)
  hex_job "${DS}-hex-mean" \
"set -e
cng-datasets raster --input \"${COG}\" --output-parquet ${PFX}/hex-mean/ \\
  --h0-index \${JOB_COMPLETION_INDEX} --resolution 8 --parent-resolutions 0 \\
  --value-column ${VAL} --hex-resampling mean --nodata -3.4e38" \
    > "${DIR}/${DS}-hex-mean.yaml"

  # 4. P80 hotspot COG: compute P80 over valid pixels of the full COG, keep >= P80
  single_job "${DS}-p80-cog" 32Gi 20Gi \
"set -e
python3 - <<'PY'
import subprocess, numpy as np
from osgeo import gdal
gdal.UseExceptions()
subprocess.run(['rclone','copyto','nrp:${BUCKET}/${DS}/${DS}-cog.tif','/tmp/full-cog.tif'], check=True)
ds = gdal.Open('/tmp/full-cog.tif'); b = ds.GetRasterBand(1)
nd = b.GetNoDataValue(); arr = b.ReadAsArray()
# robust fill mask (threshold, not exact-equality) — see cog clean step
valid_mask = np.isfinite(arr) & (arr > -1e30)
p80 = float(np.percentile(arr[valid_mask], 80))
print('COMPUTED_P80=%r' % p80)
keep = valid_mask & (arr >= p80)
out = np.where(keep, arr, nd).astype('float32')
drv = gdal.GetDriverByName('GTiff')
tmp = drv.Create('/tmp/p80.tif', ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Float32)
tmp.SetGeoTransform(ds.GetGeoTransform()); tmp.SetProjection(ds.GetProjection())
ob = tmp.GetRasterBand(1); ob.WriteArray(out); ob.SetNoDataValue(nd); tmp.FlushCache(); tmp = None
gdal.Translate('/tmp/p80-cog.tif', '/tmp/p80.tif', format='COG',
               creationOptions=['COMPRESS=DEFLATE','BLOCKSIZE=512'])
open('/tmp/p80-value.txt','w').write('%s\n' % p80)
print('RETAINED_PIXELS=%d  MIN_RETAINED=%.6f  MAX_RETAINED=%.6f' % (int(keep.sum()), float(arr[keep].min()), float(arr[keep].max())))
PY
rclone copyto /tmp/p80-cog.tif   nrp:${BUCKET}/${DS}/${DS}-p80-cog.tif
rclone copyto /tmp/p80-value.txt nrp:${BUCKET}/${DS}/p80-value.txt
echo 'P80 build done'" \
    > "${DIR}/${DS}-p80-cog.yaml"

  # 5. p80-hex (peak richness per cell, hotspot footprint only)
  hex_job "${DS}-p80-hex" \
"set -e
cng-datasets raster --input \"${P80COG}\" --output-parquet ${PFX}/p80-hex/ \\
  --h0-index \${JOB_COMPLETION_INDEX} --resolution 8 --parent-resolutions 0 \\
  --value-column ${VAL} --hex-resampling max --nodata -3.4e38" \
    > "${DIR}/${DS}-p80-hex.yaml"

  echo "generated ${DIR}/ ($(ls "${DIR}"/*.yaml | wc -l) job yamls)"
done
