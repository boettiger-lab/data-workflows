#!/usr/bin/env python3
"""Split the generated k8s hex Job (480 completions) into <=200-completion Jobs.

Why: Armada submission was failing server-side (every `armadactl submit` DeadlineExceeded;
no job accepted cluster-wide since 2026-09-28), so the hex runs on the k8s backend. The
generator emits one 480-completion Job; this derives offset Jobs from it so each stays
within the 200-completion guideline, and gives the lower-48 chunks (0-9: the 1,124
dissolved multipolygons, up to 4.1 M estimated cells in one chunk) more RAM.

Run from this directory:  python3 split-k8s-hex.py
Apply the outputs sequentially (one hex Job at a time).
"""
import copy
import yaml

SRC = "surface-management-agency-hex.yaml"
BAD_NODES = ["hpc-nrp-g1.nmsu.edu", "service-02.nrp.mghpcc.org"]
# (suffix, first chunk id, completions, memory, duckdb limit, deadline seconds)
PARTS = [
    ("lower48", 0, 10, "48Gi", "42000MiB", 6 * 3600),
    ("a", 10, 200, "8Gi", "6963MiB", 2 * 3600),
    ("b", 210, 200, "8Gi", "6963MiB", 2 * 3600),
    ("c", 410, 70, "8Gi", "6963MiB", 2 * 3600),
]

base = yaml.safe_load(open(SRC))
for suffix, offset, n, mem, duck, deadline in PARTS:
    job = copy.deepcopy(base)
    name = f"surface-management-agency-hex-{suffix}"
    job["metadata"]["name"] = name
    job["metadata"]["labels"]["k8s-app"] = name
    job["spec"]["completions"] = n
    job["spec"]["parallelism"] = min(50, n)
    job["spec"]["backoffLimitPerIndex"] = 2
    job["spec"]["maxFailedIndexes"] = max(1, n // 20)
    job["spec"]["ttlSecondsAfterFinished"] = 7 * 86400
    tpl = job["spec"]["template"]
    tpl["metadata"]["labels"]["k8s-app"] = name
    tpl["spec"]["activeDeadlineSeconds"] = deadline
    c = tpl["spec"]["containers"][0]
    for e in c["env"]:
        if e["name"] == "DUCKDB_MEMORY_LIMIT":
            e["value"] = duck
    cmd = c["command"][2]
    assert "--chunk-id ${JOB_COMPLETION_INDEX}" in cmd
    c["command"][2] = cmd.replace(
        "--chunk-id ${JOB_COMPLETION_INDEX}",
        f"--chunk-id $(( JOB_COMPLETION_INDEX + {offset} ))")
    for k in ("requests", "limits"):
        c["resources"][k]["memory"] = mem
        c["resources"][k]["cpu"] = "4"
        c["resources"][k]["ephemeral-storage"] = "20Gi" if suffix == "lower48" else "10Gi"
    terms = tpl["spec"]["affinity"]["nodeAffinity"][
        "requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"]
    for t in terms:
        t["matchExpressions"].append(
            {"key": "kubernetes.io/hostname", "operator": "NotIn", "values": BAD_NODES})
    header = (
        "# DEVIATION from generated output (#561): derived from surface-management-agency-hex.yaml\n"
        "# by split-k8s-hex.py. Armada submission is failing server-side, so the hex runs on k8s,\n"
        f"# split into <=200-completion Jobs; this one covers plan chunks {offset}..{offset + n - 1}.\n"
        "# Adds activeDeadlineSeconds, known-bad-node exclusion, per-part memory\n"
        "# (lower-48 chunks 0-9 get 48Gi), maxFailedIndexes ~5%.\n"
    )
    with open(f"{name}.yaml", "w") as f:
        f.write(header)
        yaml.safe_dump(job, f, sort_keys=False)
    print(f"{name}.yaml: chunks {offset}..{offset + n - 1}, {mem}")
