"""Generate the Armada job sets for the CHELSA v2.1 present-day baseline (data-workflows #448).

The baseline is an observational climatology, not an ensemble: one raster per variable, no GCM
members. So the schema is plain `bio1`, `bio4`, ... rather than the futures' `bio1_<member>` plus
median/min/max, and a delta against a future collection reads naturally:

    SELECT AVG(f.bio1_median - b.bio1) AS warming_c
    FROM   <future>/hex/... f JOIN <baseline>/hex/... b USING (h8)

Same shape as the futures build otherwise: one hex job per (h0, variable), masked to land before
staging, then one join per h0. Sizing is the measured 8 Gi / 4 cores, and Armada has no retry, so
the caller must still run armada_gapfill.py before joining.
"""
import argparse
import sys

import yaml

VARS = ["bio1", "bio4", "bio5", "bio6", "bio12", "bio15", "bio17"]
BASE = "https://s3-west.nrp-nautilus.io/public-bioclimate"

HEX = r"""set -euo pipefail
H0IDX=__H0IDX__ ; V=__VAR__ ; PERIOD=__PERIOD__ ; STAGING=__STAGING__
RAW="public-bioclimate/raw/chelsa-2-1/${PERIOD}"
F="CHELSA_${V}_${PERIOD}_V.2.1.tif"
rm -rf /tmp/hex /tmp/mask /tmp/cache && mkdir -p /tmp/hex /tmp/mask /tmp/cache

rclone copyto nrp:public-grids/hex/h0-valid.parquet /tmp/h0grid.parquet \
  --retries 5 --low-level-retries 20 --retries-sleep 10s
H0=$(python3 /opt/scripts/chelsa_h0_for_index.py --grid /tmp/h0grid.parquet --index ${H0IDX})
echo "h0-index ${H0IDX} -> ${H0} | ${V} baseline ${PERIOD}"

# rclone copyto exits 0 when the source is absent, so test for the file itself
rclone copyto "nrp:public-ecoregion/ecoregion/hex/h0=${H0}/data_0.parquet" /tmp/mask/eco.parquet \
  --retries 5 --low-level-retries 20 --retries-sleep 10s 2>/dev/null || true
if [ ! -s /tmp/mask/eco.parquet ]; then echo "no land in h0=${H0} — nothing to do"; exit 0; fi

META=$(python3 /opt/scripts/chelsa_read_meta.py --input "/vsicurl/https://${AWS_PUBLIC_ENDPOINT}/${RAW}/${F}")
echo "${V} metadata: ${META}"
eval "$META"
NODATA_ARG=""; if [ -n "${NODATA:-}" ]; then NODATA_ARG="--nodata ${NODATA}"; fi

cng-datasets raster \
  --input "s3://${RAW}/${F}" \
  --output-parquet /tmp/hex/out \
  --h0-index ${H0IDX} \
  --resolution 8 --parent-resolutions 5,4,0 \
  --value-column "${V}" \
  --hex-resampling mean ${NODATA_ARG} \
  --local-cache-dir /tmp/cache

SRC=$(ls /tmp/hex/out/h0=*/data_0.parquet | head -1)
set +e
python3 /opt/scripts/chelsa_mask_one.py --src "${SRC}" --mask /tmp/mask/eco.parquet --out /tmp/masked.parquet
rc=$?; set -e
if [ "$rc" -eq 3 ]; then echo "empty after mask"; exit 0; fi
if [ "$rc" -ne 0 ]; then echo "mask failed rc=${rc}"; exit "$rc"; fi

rclone copyto /tmp/masked.parquet \
  "nrp:public-bioclimate/${STAGING}/${PERIOD}/${V}/h0=${H0}/data_0.parquet" \
  --retries 5 --low-level-retries 20 --retries-sleep 10s
echo "staged ${V} h0=${H0}"
"""

JOIN = r"""set -euo pipefail
H0IDX=__H0IDX__ ; PERIOD=__PERIOD__ ; STAGING=__STAGING__ ; VARS=__VARS__ ; OUTPREFIX=__OUTPREFIX__
rm -rf /tmp/hex /tmp/mask && mkdir -p /tmp/hex /tmp/mask

rclone copyto nrp:public-grids/hex/h0-valid.parquet /tmp/h0grid.parquet \
  --retries 5 --low-level-retries 20 --retries-sleep 10s
H0=$(python3 /opt/scripts/chelsa_h0_for_index.py --grid /tmp/h0grid.parquet --index ${H0IDX})
rclone copyto "nrp:public-ecoregion/ecoregion/hex/h0=${H0}/data_0.parquet" /tmp/mask/eco.parquet \
  --retries 5 --low-level-retries 20 --retries-sleep 10s 2>/dev/null || true
if [ ! -s /tmp/mask/eco.parquet ]; then echo "no land in h0=${H0}"; exit 0; fi

missing=0
for V in ${VARS//,/ }; do
  D="/tmp/hex/${V}/h0=${H0}"; mkdir -p "$D"
  rclone copyto "nrp:public-bioclimate/${STAGING}/${PERIOD}/${V}/h0=${H0}/data_0.parquet" \
    "${D}/data_0.parquet" --retries 5 --low-level-retries 20 --retries-sleep 10s 2>/dev/null || true
  [ -s "${D}/data_0.parquet" ] || { echo "MISSING ${V} h0=${H0}" >&2; missing=$((missing+1)); }
done
# refuse a partial join: it would write a partition that looks complete but lacks variables
if [ "$missing" -ne 0 ]; then echo "ERROR: ${missing} pieces missing for h0=${H0}" >&2; exit 1; fi

set +e
python3 /opt/scripts/chelsa_join_baseline.py --h0 "${H0}" --vars "${VARS}" \
  --hex-root /tmp/hex --mask /tmp/mask/eco.parquet --out /tmp/final.parquet --bounds "${BOUNDS}"
rc=$?; set -e
if [ "$rc" -eq 3 ]; then echo "empty after mask"; exit 0; fi
if [ "$rc" -ne 0 ]; then echo "join failed rc=${rc}"; exit "$rc"; fi

rclone copyto /tmp/final.parquet \
  "nrp:public-bioclimate/${OUTPREFIX}/${PERIOD}/hex/h0=${H0}/data_0.parquet" \
  --retries 5 --low-level-retries 20 --retries-sleep 10s
echo "h0=${H0} joined"
"""

BOUNDS = ('{"bio1":[-100,60],"bio4":[0,5000],"bio5":[-70,65],"bio6":[-100,45],'
          '"bio12":[0,12000],"bio15":[0,400],"bio17":[0,6000]}')


def pod(script, memory, cpu, ephemeral, extra_env=None):
    env = [
        {"name": "AWS_ACCESS_KEY_ID", "valueFrom": {"secretKeyRef": {"name": "aws", "key": "AWS_ACCESS_KEY_ID"}}},
        {"name": "AWS_SECRET_ACCESS_KEY", "valueFrom": {"secretKeyRef": {"name": "aws", "key": "AWS_SECRET_ACCESS_KEY"}}},
        {"name": "AWS_S3_ENDPOINT", "value": "rook-ceph-rgw-nautiluss3.rook"},
        {"name": "AWS_PUBLIC_ENDPOINT", "value": "s3-west.nrp-nautilus.io"},
        {"name": "AWS_HTTPS", "value": "false"},
        {"name": "AWS_VIRTUAL_HOSTING", "value": "FALSE"},
        {"name": "GDAL_DATA", "value": "/usr/share/gdal"},
        {"name": "PYTHONPATH", "value": "/usr/lib/python3/dist-packages"},
        {"name": "CNG_HEX_WORKERS", "value": str(cpu)},
    ] + (extra_env or [])
    return {
        "restartPolicy": "Never", "terminationGracePeriodSeconds": 30,
        "containers": [{
            "name": "task", "image": "ghcr.io/boettiger-lab/datasets:latest",
            "imagePullPolicy": "Always", "env": env, "command": ["bash", "-c", script],
            "volumeMounts": [
                {"name": "rclone-config", "mountPath": "/root/.config/rclone", "readOnly": True},
                {"name": "scripts", "mountPath": "/opt/scripts", "readOnly": True}],
            "resources": {
                "requests": {"cpu": str(cpu), "memory": memory, "ephemeral-storage": ephemeral},
                "limits": {"cpu": str(cpu), "memory": memory, "ephemeral-storage": ephemeral}},
        }],
        "volumes": [
            {"name": "rclone-config", "secret": {"secretName": "rclone-config"}},
            {"name": "scripts", "configMap": {"name": "chelsa-scripts"}}],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["hex", "join"], required=True)
    ap.add_argument("--period", default="1981-2010")
    ap.add_argument("--queue", default="geo-workflows")
    ap.add_argument("--namespace", default="geo-workflows")
    ap.add_argument("--job-set-id", required=True)
    ap.add_argument("--staging", default="staging-baseline")
    ap.add_argument("--output-prefix", default="chelsa-2-1/baseline")
    ap.add_argument("--h0-indexes", default="0-121")
    ap.add_argument("--vars", default=",".join(VARS))
    ap.add_argument("--memory", default="8Gi")
    ap.add_argument("--cpu", type=int, default=4)
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
        if args.phase == "hex":
            for v in variables:
                s = (HEX.replace("__H0IDX__", str(h0idx)).replace("__VAR__", v)
                        .replace("__PERIOD__", args.period).replace("__STAGING__", args.staging))
                jobs.append({"namespace": args.namespace, "priorityClassName": args.priority_class,
                             "podSpec": pod(s, args.memory, args.cpu, "8Gi")})
        else:
            s = (JOIN.replace("__H0IDX__", str(h0idx)).replace("__PERIOD__", args.period)
                     .replace("__STAGING__", args.staging).replace("__VARS__", ",".join(variables))
                     .replace("__OUTPREFIX__", args.output_prefix))
            # 12Gi ephemeral, not 40. A join holds seven small parquet pieces and one output;
            # 40Gi was copied from the futures join and is far more than it needs. It also blocks
            # placement: one job cycled Leased -> Pending -> LeaseReturned repeatedly because no
            # node had that much free ephemeral, while 121 identical jobs placed fine.
            jobs.append({"namespace": args.namespace, "priorityClassName": args.priority_class,
                         "podSpec": pod(s, "8Gi", 4, "12Gi", [{"name": "BOUNDS", "value": BOUNDS}])})

    with open(args.out, "w") as f:
        yaml.safe_dump({"queue": args.queue, "jobSetId": args.job_set_id, "jobs": jobs}, f, sort_keys=False)
    print(f"{len(jobs)} {args.phase} jobs -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
