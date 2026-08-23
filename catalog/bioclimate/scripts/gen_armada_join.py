"""Generate the Armada join phase for microsliced CHELSA hexing (data-workflows #564).

Phase 1 (gen_armada_hex.py) writes one staged parquet per (h0, variable, member). This phase is
one job per h0: it pulls that h0's 35 staged pieces, joins them on h8 into the wide row, computes
median/min/max per variable, checks each against a physical plausibility bound, and writes the
published partition.

This phase exists only because the work was microsliced. The all-in-one k8s pod joined in /tmp
for free; splitting the work means the intermediates go to S3 and something has to bring them
back together. That is the honest cost of microslicing, alongside the ~100-150 GB of staged
intermediates per (ssp, period) combination.
"""
import argparse
import sys

import yaml

VARS = ["bio1", "bio4", "bio5", "bio6", "bio12", "bio15", "bio17"]
MEMBERS = ["gfdl_esm4", "ipsl_cm6a_lr", "mpi_esm1_2_hr", "mri_esm2_0", "ukesm1_0_ll"]

SCRIPT = r"""set -euo pipefail
H0IDX=__H0IDX__ ; SSP=__SSP__ ; PERIOD=__PERIOD__
STAGING=__STAGING__ ; VARS=__VARS__ ; MEMBERS=__MEMBERS__
rm -rf /tmp/hex /tmp/mask && mkdir -p /tmp/hex /tmp/mask

rclone copyto nrp:public-grids/hex/h0-valid.parquet /tmp/h0grid.parquet \
  --retries 5 --low-level-retries 20 --retries-sleep 10s
H0=$(python3 /opt/scripts/chelsa_h0_for_index.py --grid /tmp/h0grid.parquet --index ${H0IDX})
echo "h0-index ${H0IDX} -> ${H0}"

# rclone copyto exits 0 when the source is absent, so test for the file itself.
rclone copyto "nrp:public-ecoregion/ecoregion/hex/h0=${H0}/data_0.parquet" /tmp/mask/eco.parquet \
  --retries 5 --low-level-retries 20 --retries-sleep 10s 2>/dev/null || true
if [ ! -s /tmp/mask/eco.parquet ]; then
  echo "no land in h0=${H0} — nothing to join"; exit 0
fi

# Pull this h0's staged pieces into the layout chelsa_join_vars.py expects.
missing=0
for V in ${VARS//,/ }; do
  for M in ${MEMBERS//,/ }; do
    D="/tmp/hex/${V}_${M}/h0=${H0}"
    mkdir -p "$D"
    rclone copyto "nrp:public-bioclimate/${STAGING}/${SSP}-${PERIOD}/${V}_${M}/h0=${H0}/data_0.parquet" \
      "${D}/data_0.parquet" --retries 5 --low-level-retries 20 --retries-sleep 10s 2>/dev/null || true
    if [ ! -s "${D}/data_0.parquet" ]; then
      echo "MISSING staged piece: ${V}_${M} h0=${H0}" >&2
      missing=$((missing+1))
    fi
  done
done
# Fail loudly rather than joining a subset: a partial join would write a partition that looks
# complete by row count but silently lacks variables.
if [ "$missing" -ne 0 ]; then
  echo "ERROR: ${missing} staged pieces missing for h0=${H0}; refusing to join a subset" >&2
  exit 1
fi

set +e
python3 /opt/scripts/chelsa_join_vars.py \
  --h0 "${H0}" --vars "${VARS}" --members "${MEMBERS}" \
  --bounds "${BOUNDS}" \
  --hex-root /tmp/hex --mask /tmp/mask/eco.parquet --out /tmp/final.parquet
rc=$?
set -e
if [ "$rc" -eq 3 ]; then echo "empty after land mask — skipping h0=${H0}"; exit 0; fi
if [ "$rc" -ne 0 ]; then echo "join failed rc=${rc}"; exit "$rc"; fi

rclone copyto /tmp/final.parquet \
  "nrp:public-bioclimate/__OUTPREFIX__/${SSP}-${PERIOD}/hex/h0=${H0}/data_0.parquet" \
  --retries 5 --low-level-retries 20 --retries-sleep 10s
echo "h0=${H0} joined and published"
"""

BOUNDS = ('{"bio1":[-100,60],"bio4":[0,5000],"bio5":[-70,65],"bio6":[-100,45],'
          '"bio12":[0,12000],"bio15":[0,400],"bio17":[0,6000]}')


def make_pod(h0idx, ssp, period, staging, outprefix, variables, members, memory, cpu):
    script = (SCRIPT
              .replace("__H0IDX__", str(h0idx)).replace("__SSP__", ssp)
              .replace("__PERIOD__", period).replace("__STAGING__", staging)
              .replace("__OUTPREFIX__", outprefix)
              .replace("__VARS__", ",".join(variables))
              .replace("__MEMBERS__", ",".join(members)))
    return {
        "restartPolicy": "Never",
        "terminationGracePeriodSeconds": 30,
        "containers": [{
            "name": "join",
            "image": "ghcr.io/boettiger-lab/datasets:latest",
            "imagePullPolicy": "Always",
            "env": [
                {"name": "AWS_ACCESS_KEY_ID", "valueFrom": {"secretKeyRef": {"name": "aws", "key": "AWS_ACCESS_KEY_ID"}}},
                {"name": "AWS_SECRET_ACCESS_KEY", "valueFrom": {"secretKeyRef": {"name": "aws", "key": "AWS_SECRET_ACCESS_KEY"}}},
                {"name": "AWS_S3_ENDPOINT", "value": "rook-ceph-rgw-nautiluss3.rook"},
                {"name": "AWS_PUBLIC_ENDPOINT", "value": "s3-west.nrp-nautilus.io"},
                {"name": "AWS_HTTPS", "value": "false"},
                {"name": "AWS_VIRTUAL_HOSTING", "value": "FALSE"},
                {"name": "PYTHONPATH", "value": "/usr/lib/python3/dist-packages"},
                {"name": "BOUNDS", "value": BOUNDS},
            ],
            "command": ["bash", "-c", script],
            "volumeMounts": [
                {"name": "rclone-config", "mountPath": "/root/.config/rclone", "readOnly": True},
                {"name": "scripts", "mountPath": "/opt/scripts", "readOnly": True},
            ],
            "resources": {
                "requests": {"cpu": str(cpu), "memory": memory, "ephemeral-storage": "40Gi"},
                "limits": {"cpu": str(cpu), "memory": memory, "ephemeral-storage": "40Gi"},
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
    # Defaults to the published path. Point a partial or trial run somewhere else: a join over a
    # subset of variables writes a partition that looks valid but silently lacks columns, and it
    # would overwrite a complete one.
    ap.add_argument("--output-prefix", default="chelsa-2-1")
    ap.add_argument("--h0-indexes", default="0-121")
    ap.add_argument("--vars", default=",".join(VARS))
    ap.add_argument("--members", default=",".join(MEMBERS))
    # NRP caps controller-less pods at 16 cores / 32 GB, and every Armada pod is
    # controller-less. 48Gi was rejected at admission:
    #   admission webhook "pod.nrp-nautilus.io" denied the request:
    #   PODs without controllers are limited to 16 cores and 32 GB of RAM
    ap.add_argument("--memory", default="32Gi")
    ap.add_argument("--cpu", type=int, default=8)
    ap.add_argument("--priority-class", default="armada-preemptible")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if "-" in args.h0_indexes and "," not in args.h0_indexes:
        lo, hi = args.h0_indexes.split("-")
        idxs = list(range(int(lo), int(hi) + 1))
    else:
        idxs = [int(i) for i in args.h0_indexes.split(",")]
    variables = [v.strip() for v in args.vars.split(",") if v.strip()]
    members = [m.strip() for m in args.members.split(",") if m.strip()]

    jobs = [{
        "namespace": args.namespace,
        "priorityClassName": args.priority_class,
        "podSpec": make_pod(i, args.ssp, args.period, args.staging, args.output_prefix,
                            variables, members, args.memory, args.cpu),
    } for i in idxs]

    with open(args.out, "w") as f:
        yaml.safe_dump({"queue": args.queue, "jobSetId": args.job_set_id, "jobs": jobs},
                       f, sort_keys=False)
    print(f"{len(jobs)} join jobs -> {args.out} "
          f"({len(variables)} vars x {len(members)} members per h0)")


if __name__ == "__main__":
    sys.exit(main())
