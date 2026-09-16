import os

HDR_COMMON = """#
# ⚠️ THE 122-COMPLETION FAN-OUT IS REPLACED BY AN EXPLICIT h0 INDEX LIST, AND IT IS NOT A GUESS.
# `cng-datasets` selects an h0 cell with `WHERE i = <h0-index>` against
# `s3://public-grids/hex/h0-valid.parquet` (`cng_datasets/raster/cog.py`), so the index -> cell
# mapping is a lookup in a published table, not internal state that has to be inferred from pod
# logs. H0S below is every index whose h0 geometry intersects this domain's COG footprint, read
# from that same table. It is a SUPERSET of the cells that will actually hold data -- a cell that
# turns out not to overlap the raster is skipped by the tool in seconds -- so it cannot drop a
# populated cell, which was the stated reason wrc-2 left all 122 in place. It removes {saved} of
# the {orig} pods that would otherwise localize the COG and produce nothing.
#
# ⚠️ `priorityClassName` is deliberately OMITTED. Default priority 0 is admitted in geo-workflows
# and is two billion points above `opportunistic` (-2000000000); a res-10 h0 runs for hours and an
# opportunistic pod that long is near-certain to be preempted (skill `pod-preemption`).
# ⛔ Do NOT node-pin: a 192Gi/8cpu pod fills a node, so pinning serializes the job (#307 turned a
# CONUS res-10 hex from hours into 30-50 h).
"""

TMPL = """# WRC v2 populated areas: {title}, {domain_long} -- res-10 `{reducer}` hex.
#
# Source publication RDS-2020-0060-2 (*Spatial datasets of wildfire risk for populated areas*).
# ⚠️ A DIFFERENT DOI from `catalog/fire/k8s/wrc-2/` (RDS-2020-0016-2, the landscape-wide risk
# components). The `-pa-` in this dataset id marks the split.
#
{reducer_note}#
# Resolution 10 with parents 9, 8, 0: the source is 30 m and `h10` (0.0150 km^2) is the catalog's
# finest, and native 10 -> 9, 8, 0 matches `roadless-areas-2001` (public-usfs), `silvis-wui-2020`
# (public-wui) and the sibling `wrc-2-rps-{domain}` cell for cell, which is the point of the ingest.
#
# Reads the WGS84 COG built by make-cogs.yaml, never the staged Albers raw: `cng-datasets` hands
# exactextract H3 polygons in DEGREES, so against a metre-based Albers grid every cell reads nodata
# and the job writes ZERO rows while exiting 0 (#586).
#
# NoData is -9999 in the COG for every theme in this publication. That is NOT the source's sentinel
# -- the sources use EIGHT different ones, including a POSITIVE 255 for BuildingCount -- it is the
# uniform value make-cogs.yaml collapses them all to. Every theme is non-negative, so -9999 cannot
# collide with a real value.
{clip_note}{hdr_common}apiVersion: batch/v1
kind: Job
metadata:
  name: {job}
  namespace: geo-workflows
  labels: {{k8s-app: {job}}}
spec:
  completions: {n}
  parallelism: 4
  completionMode: Indexed
  backoffLimitPerIndex: 3
  # 0: a partial indexed run must surface as Failed rather than be published as complete (#409).
  maxFailedIndexes: 0
  podFailurePolicy:
    rules:
    # A preemption/eviction is not a data error; don't spend the index's retry budget on it.
    - action: Ignore
      onPodConditions:
      - type: DisruptionTarget
  ttlSecondsAfterFinished: 86400
  template:
    metadata: {{labels: {{k8s-app: {job}}}}}
    spec:
      restartPolicy: Never
      # 18 h. A dense res-10 h0 ran ~5 h on the sibling wrc-2 build and its CONUS dense slice had
      # to be re-run once for straddling a 6 h deadline; the headroom is free.
      activeDeadlineSeconds: 64800
      # rclone's nrp: remote resolves the INTERNAL endpoint, which only cluster DNS can resolve.
      dnsPolicy: ClusterFirst
      containers:
      - name: hex-task
        image: ghcr.io/boettiger-lab/datasets:latest
        imagePullPolicy: Always
        env:
        - {{name: AWS_ACCESS_KEY_ID,     valueFrom: {{secretKeyRef: {{name: aws, key: AWS_ACCESS_KEY_ID}}}}}}
        - {{name: AWS_SECRET_ACCESS_KEY, valueFrom: {{secretKeyRef: {{name: aws, key: AWS_SECRET_ACCESS_KEY}}}}}}
        - {{name: AWS_S3_ENDPOINT,     value: rook-ceph-rgw-nautiluss3.rook}}
        - {{name: AWS_PUBLIC_ENDPOINT, value: s3-west.nrp-nautilus.io}}
        - {{name: AWS_HTTPS,           value: 'false'}}
        - {{name: AWS_VIRTUAL_HOSTING, value: 'FALSE'}}
        - {{name: GDAL_DATA,           value: /usr/share/gdal}}
        - {{name: PYTHONPATH,          value: /usr/lib/python3/dist-packages}}
        - {{name: CNG_HEX_WORKERS,     value: '8'}}
        volumeMounts:
        # MANDATORY: cng-datasets rclone-localizes the COG before hexing. Generated YAML omits this
        # secret and the job then fails on localize.
        - {{name: rclone-config, mountPath: /root/.config/rclone, readOnly: true}}
        command:
        - bash
        - -c
        - |-
          set -e
          # Indexes into s3://public-grids/hex/h0-valid.parquet -- the same table cng-datasets
          # selects with `WHERE i = <h0-index>`. See the header.
          H0S=({h0s})
          H0=${{H0S[${{JOB_COMPLETION_INDEX}}]}}
          echo "=== {title} {domain_short} res-10 {reducer}, completion ${{JOB_COMPLETION_INDEX}} -> h0-index ${{H0}} ==="
          cng-datasets raster \\
            --input "s3://public-fire/{ds}-cog.tif" \\
            --output-parquet "s3://public-fire/{ds}/hex/" \\
            --h0-index ${{H0}} \\
            --resolution 10 --parent-resolutions 9,8,0 \\
            --value-column {col} --hex-resampling {reducer} --nodata -9999
        resources:
          # ⛔ 192Gi is NOT oversized. Memory at res 10 is set by the ENUMERATION, not the output:
          # every surviving h0 enumerates the same 282,475,249 res-10 children. Measured on the
          # sibling wrc-2 CONUS run, four pods spanning 47.8 M to 226.7 M output cells all sat at
          # 132-134 GiB -- a 4.7x range in cells giving 1.8% in memory. So 128Gi (131,072 Mi) sits
          # BELOW the steady state and would OOM every slice, not merely the dense one.
          requests: {{cpu: '8', memory: 192Gi, ephemeral-storage: 50Gi}}
          limits:   {{cpu: '8', memory: 192Gi, ephemeral-storage: 50Gi}}
      volumes:
      - {{name: rclone-config, secret: {{secretName: rclone-config}}}}
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - {{key: feature.node.kubernetes.io/pci-10de.present, operator: NotIn, values: ['true']}}
              # Known-bad egress/S3 hosts: pods schedule but hang on localize.
              - {{key: kubernetes.io/hostname, operator: NotIn, values: [hpc-nrp-g1.nmsu.edu, service-02.nrp.mghpcc.org,
                         nautilus-it-cpu05.fullerton.edu, nautilus-it-cpu13.fullerton.edu,
                         nautilus-it-cpu15.fullerton.edu, nautilus-it-cpu16.fullerton.edu]}}
"""

CONUS_H0 = [9, 12, 14, 20, 42, 50, 71, 78, 89, 100, 104, 120]
AK_H0 = [12, 28, 50, 59, 98, 104, 105]

CLIP = """#
# The Alaska COG is clipped to -180..-129 lon (see make-cogs.yaml): the source EPSG:3338 grid spans
# the antimeridian and a naive warp yields a ~360-deg-wide, almost entirely nodata raster. The
# dropped far-western Aleutians hold no National Forest System land. h0 576707042908045311 (index
# 105) is the dateline cell and must come out populated -- that is the standard check that the
# antimeridian was handled rather than seam-inflated.
"""

MEAN_NOTE = """# Reducer `mean`: HURisk is a unitless INDEX combining all four elements of wildfire risk
# (likelihood, intensity, susceptibility, exposure), defined on pixels where housing-unit density
# is greater than zero. An index is an intensity, not an amount integrated over the pixel, so a
# `sum` would be a meaningless sum of intensities -- the error class that made the carbon layer
# ~7x low (#171/#202). There is no meaningful "total HURisk"; consumers compare means across land
# classes.
#
# ⚠️ Its three near-siblings in this same publication do NOT take `mean`. `HUExposure` is an
# expected COUNT per pixel and takes `sum`; so do BuildingCount, PopCount and HUCount. Do not
# generalise one reducer across this publication -- `BuildingCount`, `BuildingDensity` and
# `BuildingCover` differ only in a suffix and take `sum`, `mean`, `mean`.
"""

SUM_NOTE = """# Reducer `sum`: HUExposure is the expected number of housing units WITHIN A 30 m PIXEL exposed
# to wildfire in a year -- an amount already integrated over the pixel, not an intensity. `mean`
# would answer "the average per-pixel expectation in this cell", which is not the quantity anyone
# wants from it; `sum` gives the expected housing units exposed inside the cell, and totals
# correctly under any further aggregation.
#
# `cng-datasets`' exact-extract `sum` is coverage-weighted and mass-conserving by construction
# (boettiger-lab/datasets#84), and make-cogs.yaml warps this layer with `-r sum` for the same
# reason, so the whole chain conserves mass: hex SUM(huexposure) must equal the COG pixel sum
# within rounding. That invariant is #611's acceptance criterion for the amount layers and is the
# thing to check first if this layer ever looks wrong.
#
# ⚠️ Its near-sibling `HURisk` in this same publication takes `mean`, not `sum` -- it is a unitless
# index. Do not generalise one reducer across this publication.
"""

for ds, title, col, reducer, note in [
    ("wrc-2-pa-hurisk", "Housing Unit Risk", "hurisk", "mean", MEAN_NOTE),
    ("wrc-2-pa-huexposure", "Housing Unit Exposure", "huexposure", "sum", SUM_NOTE),
]:
    for domain, h0s, long, short, clip in [
        ("conus", CONUS_H0, "continental United States", "CONUS", ""),
        ("ak", AK_H0, "Alaska", "Alaska", CLIP),
    ]:
        n = len(h0s)
        hdr = HDR_COMMON.format(saved=122 - n, orig=122)
        body = TMPL.format(
            title=title, domain_long=long, domain_short=short, domain=domain,
            reducer=reducer, reducer_note=note, clip_note=clip, hdr_common=hdr,
            job=f"{ds}-{domain}-hex", n=n, h0s=" ".join(str(x) for x in h0s),
            ds=f"{ds}-{domain}", col=col)
        open(f"{ds}-{domain}-hex.yaml", "w").write(body)
        print("wrote", f"{ds}-{domain}-hex.yaml", n, "completions")
