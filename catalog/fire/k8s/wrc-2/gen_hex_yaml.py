#!/usr/bin/env python3
"""Emit the six res-10 hex Jobs for #627 (BP, CFL, Exposure x CONUS/Alaska).

    python3 gen_hex_yaml.py            # writes wrc-2-<theme>-<domain>-hex.yaml

Six near-identical manifests differing only in theme copy and the h0 fan-out, so they are
generated rather than hand-maintained -- the same reason catalog/fire/k8s/wrc-2-pa has a
generator. #592's two RPS manifests were written by hand and drifted: the Alaska one still
carries a "3 populated h0 partitions" prediction that its own build disproved.

The h0 lists come from h0-selection.json, which h0_select.py derives from each COG's OWN
valid-pixel tile footprint. Read h0_select.py's header before changing any of them.
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

THEMES = {
    "bp": dict(
        title="Burn Probability",
        column="bp",
        note="""# Reducer `mean`: BP is the modelled annual PROBABILITY that a location burns. A probability is
# an intensity, not an amount integrated over the pixel, so `sum` would add probabilities and
# produce a number greater than 1 that means nothing -- the error class that made the carbon layer
# ~7x low (#171/#202). The cell mean is the probability for the cell, which is the quantity
# consumers compare across land classes.
#
# Source range is 0 to 0.14 nationally. A cell value of 0.01 is a roughly 1 percent chance of
# burning in a given year under the modelled conditions.""",
        oversampled=True,
    ),
    "cfl": dict(
        title="Conditional Flame Length",
        column="cfl",
        note="""# Reducer `mean`: CFL is a LENGTH in feet -- the mean flame length for a fire burning in the
# direction of maximum spread, conditional on a fire occurring. A length is an intensity, not an
# amount integrated over the pixel; summing flame lengths across a cell is meaningless (#171/#202).
#
# ⚠️ CFL is CONDITIONAL. It is not reduced by a location being unlikely to burn, so it must not be
# read as expected intensity on its own -- pair it with `wrc-2-bp-*` for that. Source range is 0 to
# 861.7 feet nationally, and that maximum is far above any plausible free-burning flame length
# because the source models extreme fire behaviour in heavy fuels; it is the published range.""",
        oversampled=True,
    ),
    "exposure": dict(
        title="Exposure Type",
        column="exposure",
        note="""# Reducer `mean`, and this is the choice worth stating clearly because the obvious reading of the
# name is wrong. EXPOSURE TYPE IS CONTINUOUS, NOT CATEGORICAL: Float32 with no colour table and no
# category names, measured 0.0 to 1.0 on the source (Exposure_AK mean 0.759). 1 is direct exposure
# from adjacent burnable wildland vegetation, values between 0 and 1 are indirect exposure from
# embers and home-to-home ignition with higher meaning closer to directly exposed, and 0 is
# non-exposed. `mode` on a float continuum is meaningless -- it would return whichever value
# happens to repeat -- and it is what the word "Type" invites. The web application bins this for
# display; binning belongs to the application, not to the published data.
#
# Source range is 0 to 1 nationally, so a sentinel leak shows up immediately as a value outside it.""",
        oversampled=False,
    ),
}

DOMAINS = {
    "conus": dict(
        long="continental United States",
        short="CONUS",
        clip="",
        deadline=64800,
    ),
    "ak": dict(
        long="Alaska",
        short="Alaska",
        clip="""#
# The Alaska COG is clipped to -180..-129 lon (see make-cogs-bp-cfl-exposure.yaml): the source
# EPSG:3338 grid spans the antimeridian and a naive warp yields a ~360-deg-wide, almost entirely
# nodata raster. The dropped far-western Aleutians hold no National Forest System land.
#
# h0 576707042908045311 (index 105) is the DATELINE cell, and on #592's RPS build it was Alaska's
# densest partition at 107.8 M cells. Its polygon is stored in planar lat/lon spanning about -178
# to +177, so a plain envelope test gets it wrong in both directions; h0_select.py unwraps exactly
# as cog.py:_cell_footprint does. Its presence in the output is the standard check that the
# antimeridian was handled rather than seam-inflated.""",
        deadline=64800,
    ),
}

TMPL = """# WRC v2 {title}, {domain_long} -- res-10 `mean` hex. #627.
#
# Source publication RDS-2020-0016-2, *Wildfire Risk to Communities* 2nd Edition -- the same DOI as
# the published `wrc-2-rps-*` pair (#592), a DIFFERENT one from `catalog/fire/k8s/wrc-2-pa/`
# (RDS-2020-0060-2, populated areas).
#
{note}
#
# Resolution 10 with parents 9, 8, 0: the source is 30 m and `h10` (0.0150 km^2) is the catalog's
# finest, so 30 m is mildly UNDER-sampled, accepted per the raster-hexing anchor table. Native 10
# -> 9, 8, 0 matches `roadless-areas-2001` (public-usfs), `silvis-wui-2020` (public-wui) and the
# sibling `wrc-2-rps-{domain}` cell for cell, which is the point of the ingest.
#
# Reads the WGS84 COG built by make-cogs-bp-cfl-exposure.yaml, never the staged Albers raw:
# `cng-datasets` hands exactextract H3 polygons in DEGREES, so against a metre-based Albers grid
# every cell reads nodata and the job writes ZERO rows while exiting 0 (#586).{clip}
#
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# THE h0 FAN-OUT IS {n} INDEXES, NOT 122, AND THE LIST IS A PROOF RATHER THAN A GUESS
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# At res 10 an h0 index that holds no data is NOT free: `cng-datasets` prunes only h0 cells whose
# footprint misses the raster's BOUNDING BOX, and every surviving cell enumerates all 282,475,249
# res-10 children before discovering they are nodata -- about five hours at 192Gi. This COG is
# large, so each such pod also rclone-localizes it first to produce nothing.
#
# The list below is every h0 whose footprint intersects THIS LAYER'S OWN valid-pixel tile
# footprint, measured over the full-resolution pass make-cogs-bp-cfl-exposure.yaml already
# performs: a 512x512 tile is recorded if ANY pixel in it is valid, so the union of tiles contains
# every valid pixel and an h0 that misses it provably holds none. See h0_select.py.
#
# ⛔ DO NOT substitute a neighbouring layer's populated h0 set, however identical the clip box.
# #592 measured why: RPS Alaska populates FIVE h0, but `whp-2023-classified-ak` over the same clip
# box populates THREE, and trimming to the borrowed set would have dropped 4.25 M cells across two
# partitions. check-hex-coverage.sh cannot catch that -- it verifies that expected partitions are
# PRESENT, never that unexpected ones are ABSENT.
#
#   h0 index -> cell
{h0map}
#
# ⚠️ `priorityClassName` is deliberately OMITTED. Default priority 0 is admitted in geo-workflows
# and is two billion points above `opportunistic` (-2000000000); a res-10 h0 runs for hours and an
# opportunistic pod that long is near-certain to be preempted (skill `pod-preemption`).
# ⛔ Do NOT node-pin: a 192Gi/8cpu pod fills a node, so pinning serializes the job (#307 turned a
# CONUS res-10 hex from hours into 30-50 h).
apiVersion: batch/v1
kind: Job
metadata:
  name: {job}
  namespace: geo-workflows
  labels: {{k8s-app: {job}}}
spec:
  completions: {n}
  # One wave: every index here is real work, so concurrency sets wall clock almost entirely.
  parallelism: {n}
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
  ttlSecondsAfterFinished: 604800
  template:
    metadata: {{labels: {{k8s-app: {job}}}}}
    spec:
      restartPolicy: Never
      # 18 h. #592 measured its densest CONUS slice at 314 minutes and its Alaska dateline slice
      # in the same band; its CONUS run had to be rescued once for straddling a 6 h deadline, so
      # the headroom is free.
      activeDeadlineSeconds: {deadline}
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
        # MANDATORY: cng-datasets rclone-localizes the COG before hexing. Generated YAML omits
        # this secret and the job then fails on localize.
        - {{name: rclone-config, mountPath: /root/.config/rclone, readOnly: true}}
        command:
        - bash
        - -c
        - |-
          set -e
          # Slot -> h0 index. Measured from this layer's own COG; see the header.
          H0S=({h0s})
          H0=${{H0S[${{JOB_COMPLETION_INDEX}}]}}
          echo "=== WRC v2 {title} {domain_short} res-10 mean, h0-index ${{H0}} (slot ${{JOB_COMPLETION_INDEX}}) ==="
          cng-datasets raster \\
            --input "s3://public-fire/{ds}-cog.tif" \\
            --output-parquet "s3://public-fire/{ds}/hex/" \\
            --h0-index ${{H0}} \\
            --resolution 10 --parent-resolutions 9,8,0 \\
            --value-column {column} --hex-resampling mean --nodata -9999
        resources:
          # ⛔ 192Gi, and NOT scaled down for a small domain. MEMORY AT RES 10 DOES NOT SCALE WITH
          # CELL COUNT. Measured live on #592's CONUS run, four pods sampled together:
          #     h0-index 14 =  69.4 M cells -> 132,065 Mi
          #     h0-index 71 =  47.8 M cells -> 133,356 Mi
          #     h0-index 20 = 226.7 M cells -> 133,593 Mi
          #     h0-index 50 = 107.0 M cells -> 134,460 Mi
          # A 4.7x range in cells gives a 1.8% range in memory, because the cost is the CONSTANT
          # 282,475,249-cell res-10 enumeration every surviving h0 performs, not the output. So
          # 128Gi (131,072 Mi) sits BELOW the observed steady state and would OOM every slice,
          # not merely the dense one. Ephemeral 50Gi covers the localized COG plus output.
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


def main() -> None:
    with open(os.path.join(HERE, "h0-selection.json")) as fh:
        sel = json.load(fh)

    for theme_key, theme in THEMES.items():
        for domain_key, domain in DOMAINS.items():
            ds = f"wrc-2-{theme_key}-{domain_key}"
            picked = sel["datasets"][ds]
            h0s = picked["h0_indexes"]
            cells = picked["h0_cells"]
            assert len(h0s) == len(cells), ds
            h0map = "\n".join(
                f"#   {i:>5}  ->  {c}" for i, c in zip(h0s, cells)
            )
            body = TMPL.format(
                title=theme["title"], note=theme["note"], column=theme["column"],
                domain=domain_key, domain_long=domain["long"], domain_short=domain["short"],
                clip=domain["clip"], deadline=domain["deadline"],
                job=f"{ds}-hex", ds=ds, n=len(h0s),
                h0s=" ".join(str(x) for x in h0s), h0map=h0map,
            )
            path = os.path.join(HERE, f"{ds}-hex.yaml")
            with open(path, "w") as fh:
                fh.write(body)
            print(f"wrote {os.path.basename(path)}  {len(h0s)} completions  h0 {h0s}")


if __name__ == "__main__":
    main()
