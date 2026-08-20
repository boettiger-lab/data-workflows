"""Generate an Armada job set for microsliced CHELSA hexing (data-workflows #564).

One Armada job per (h0, variable, GCM member) — 122 x 7 x 5 = 4,270 units for a full
(ssp, period) combination, each roughly five minutes, against 122 jobs of ~3.5 hours on the
k8s path. Armada is not bound by the k8s indexed-Job completion cap (~200, an etcd pressure
limit), which is what makes this shape possible.

Why microslice, beyond preemption:
  * the unit of loss on preemption drops from hours to minutes
  * each job requests what one raster needs, not the peak of a 35-step chain
  * small pods pack into free scraps instead of waiting for large contiguous slots, so realised
    parallelism is far closer to requested
  * a straggler retries invisibly instead of holding up a batch and leaving stale output

Each job masks to land before staging, so the intermediate is the land subset rather than all
5,764,801 cells of the h0.
"""
import argparse
import json
import sys

import yaml

VARS = ["bio1", "bio4", "bio5", "bio6", "bio12", "bio15", "bio17"]
GCMS = [
    ("GFDL-ESM4", "gfdl_esm4"),
    ("IPSL-CM6A-LR", "ipsl_cm6a_lr"),
    ("MPI-ESM1-2-HR", "mpi_esm1_2_hr"),
    ("MRI-ESM2-0", "mri_esm2_0"),
    ("UKESM1-0-LL", "ukesm1_0_ll"),
]

SCRIPT = r"""set -euo pipefail
H0IDX=__H0IDX__ ; V=__VAR__ ; G=__GCM__ ; C=__COL__
SSP=__SSP__ ; PERIOD=__PERIOD__
RAW="public-bioclimate/raw/chelsa-2-1/${PERIOD}"
GL=$(echo "$G" | tr 'A-Z' 'a-z')
rm -rf /tmp/hex /tmp/mask /tmp/cache && mkdir -p /tmp/hex /tmp/mask /tmp/cache

rclone copyto nrp:public-grids/hex/h0-valid.parquet /tmp/h0grid.parquet \
  --retries 5 --low-level-retries 20 --retries-sleep 10s
H0=$(python3 /opt/scripts/chelsa_h0_for_index.py --grid /tmp/h0grid.parquet --index ${H0IDX})
echo "h0-index ${H0IDX} -> ${H0} | ${V} / ${G}"

# rclone copyto exits 0 when the source is absent, so test for the file itself.
rclone copyto "nrp:public-ecoregion/ecoregion/hex/h0=${H0}/data_0.parquet" /tmp/mask/eco.parquet \
  --retries 5 --low-level-retries 20 --retries-sleep 10s 2>/dev/null || true
if [ ! -s /tmp/mask/eco.parquet ]; then
  echo "no land in h0=${H0} — nothing to do"; exit 0
fi

META=$(python3 /opt/scripts/chelsa_read_meta.py \
  --input "/vsicurl/https://${AWS_PUBLIC_ENDPOINT}/${RAW}/${G}/${SSP}/CHELSA_${V}_${PERIOD}_${GL}_${SSP}_V.2.1.tif")
echo "${V} metadata: ${META}"
eval "$META"
NODATA_ARG=""; if [ -n "${NODATA:-}" ]; then NODATA_ARG="--nodata ${NODATA}"; fi

cng-datasets raster \
  --input "s3://${RAW}/${G}/${SSP}/CHELSA_${V}_${PERIOD}_${GL}_${SSP}_V.2.1.tif" \
  --output-parquet "/tmp/hex/out" \
  --h0-index ${H0IDX} \
  --resolution 8 --parent-resolutions 5,4,0 \
  --value-column "${V}_${C}" \
  --hex-resampling mean ${NODATA_ARG} \
  --local-cache-dir /tmp/cache

SRC=$(ls /tmp/hex/out/h0=*/data_0.parquet | head -1)
# Mask to land before staging: the intermediate becomes the land subset rather than all
# 5,764,801 cells of the h0, which is most of the staging volume for a mostly-ocean cell.
# A script, not inline SQL -- the statement would otherwise have to survive shell, YAML and
# Python quoting, and that escaping collapses at runtime rather than at generation time.
set +e
python3 /opt/scripts/chelsa_mask_one.py \
  --src "${SRC}" --mask /tmp/mask/eco.parquet --out /tmp/masked.parquet
rc=$?
set -e
if [ "$rc" -eq 3 ]; then echo "empty after mask"; exit 0; fi
if [ "$rc" -ne 0 ]; then echo "mask failed rc=${rc}"; exit "$rc"; fi

rclone copyto /tmp/masked.parquet \
  "nrp:public-bioclimate/__STAGING__/${SSP}-${PERIOD}/${V}_${C}/h0=${H0}/data_0.parquet" \
  --retries 5 --low-level-retries 20 --retries-sleep 10s
echo "staged ${V}_${C} h0=${H0}"
"""


def make_pod(h0idx, var, gcm, col, ssp, period, staging, memory, cpu):
    script = (SCRIPT
              .replace("__H0IDX__", str(h0idx)).replace("__VAR__", var)
              .replace("__GCM__", gcm).replace("__COL__", col)
              .replace("__SSP__", ssp).replace("__PERIOD__", period)
              .replace("__STAGING__", staging))
    return {
        "restartPolicy": "Never",
        "terminationGracePeriodSeconds": 30,
        "containers": [{
            "name": "hex",
            "image": "ghcr.io/boettiger-lab/datasets:latest",
            "imagePullPolicy": "Always",
            "env": [
                {"name": "AWS_ACCESS_KEY_ID", "valueFrom": {"secretKeyRef": {"name": "aws", "key": "AWS_ACCESS_KEY_ID"}}},
                {"name": "AWS_SECRET_ACCESS_KEY", "valueFrom": {"secretKeyRef": {"name": "aws", "key": "AWS_SECRET_ACCESS_KEY"}}},
                {"name": "AWS_S3_ENDPOINT", "value": "rook-ceph-rgw-nautiluss3.rook"},
                {"name": "AWS_PUBLIC_ENDPOINT", "value": "s3-west.nrp-nautilus.io"},
                {"name": "AWS_HTTPS", "value": "false"},
                {"name": "AWS_VIRTUAL_HOSTING", "value": "FALSE"},
                {"name": "GDAL_DATA", "value": "/usr/share/gdal"},
                {"name": "PYTHONPATH", "value": "/usr/lib/python3/dist-packages"},
                {"name": "CNG_HEX_WORKERS", "value": str(cpu)},
            ],
            "command": ["bash", "-c", script],
            "volumeMounts": [
                {"name": "rclone-config", "mountPath": "/root/.config/rclone", "readOnly": True},
                {"name": "scripts", "mountPath": "/opt/scripts", "readOnly": True},
            ],
            "resources": {
                "requests": {"cpu": str(cpu), "memory": memory, "ephemeral-storage": "8Gi"},
                "limits": {"cpu": str(cpu), "memory": memory, "ephemeral-storage": "8Gi"},
            },
        }],
        "volumes": [
            {"name": "rclone-config", "secret": {"secretName": "rclone-config"}},
            {"name": "scripts", "configMap": {"name": "chelsa-scripts"}},
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ssp", required=True)
    ap.add_argument("--period", required=True)
    ap.add_argument("--queue", default="geo-workflows")
    ap.add_argument("--namespace", default="geo-workflows")
    ap.add_argument("--job-set-id", required=True)
    ap.add_argument("--staging", default="staging")
    ap.add_argument("--h0-indexes", default="0-121",
                    help="'0-121', or a comma list, to scope a proof run")
    ap.add_argument("--vars", default=",".join(VARS))
    # MEASURED, not inherited. `kubectl top pod` across 25 running slices showed peak 5.4 Gi
    # and mean 3.9 Gi, so 8Gi carries ~48% headroom. The first version asked for 32Gi -- half of
    # the k8s job's 64Gi, which was itself sized for a 35-raster chain rather than one raster --
    # and the scheduler reported "4,231 jobs do not fit on any node" while only ~28 ran. RAM is
    # what limits how many pods the cluster can hold, so an over-request directly throttles
    # concurrency: a node with 10Gi free and cores to spare can take an 8Gi pod but not a 32Gi one.
    #
    # NRP also caps controller-less pods (which every Armada pod is) at 16 cores / 32 GB.
    # Exceeding that is rejected at admission, not at submit -- armadactl --dry-run passes.
    ap.add_argument("--memory", default="8Gi")
    # MEASURED: mean 3.3 cores used against an 8-core request (peak 8.6, but only 19 of 100
    # pods exceeded 7 and 64 used under 4). exact_extract does use its workers, but the localize,
    # metadata read, mask and upload around it are single-threaded, so the lifetime average is far
    # below the hot-loop peak. cpu binds placement on this cluster, so the over-ask throttled our
    # own queue harder than the memory one did.
    ap.add_argument("--cpu", type=int, default=4)
    # armada-default is non-preemptible (priority 100). Preemptible is a fine default once
    # units are minutes rather than hours; see the armada-pipeline skill.
    ap.add_argument("--priority-class", default="armada-preemptible")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if "-" in args.h0_indexes and "," not in args.h0_indexes:
        lo, hi = args.h0_indexes.split("-")
        idxs = list(range(int(lo), int(hi) + 1))
    else:
        idxs = [int(i) for i in args.h0_indexes.split(",")]
    variables = [v.strip() for v in args.vars.split(",") if v.strip()]

    jobs = []
    for h0idx in idxs:
        for var in variables:
            for gcm, col in GCMS:
                jobs.append({
                    "namespace": args.namespace,
                    "priorityClassName": args.priority_class,
                    "podSpec": make_pod(h0idx, var, gcm, col, args.ssp, args.period,
                                        args.staging, args.memory, args.cpu),
                })

    spec = {"queue": args.queue, "jobSetId": args.job_set_id, "jobs": jobs}
    with open(args.out, "w") as f:
        yaml.safe_dump(spec, f, sort_keys=False)
    print(f"{len(jobs)} jobs -> {args.out} "
          f"({len(idxs)} h0 x {len(variables)} vars x {len(GCMS)} members)")


if __name__ == "__main__":
    sys.exit(main())
