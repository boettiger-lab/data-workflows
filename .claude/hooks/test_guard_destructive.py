#!/usr/bin/env python3
"""Tests for guard-destructive.py (the PreToolUse safety hook).

Run:  python3 .claude/hooks/test_guard_destructive.py   (exit 0 = all pass)

Cases live here as data so the command that runs this file does not itself
contain the blocked patterns (which would trip the live hook). HOOK is resolved
relative to this file so it works in any checkout/worktree.
"""
import json
import os
import subprocess
import sys

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guard-destructive.py")

BLOCK = [
    # backup / mirror destruction (recovery copies)
    "rclone purge minio:public-padus",
    "rclone sync nrp:public-padus minio:public-padus",
    "rclone delete source:us-west-2.opendata.source.coop/cboettig/cpad",
    "rclone purge nrp:public-padus",                       # whole nrp bucket root
    # S3 bucket-level destruction (any endpoint)
    "aws s3 rb s3://public-padus --force",
    "aws s3api delete-bucket --bucket public-padus",
    "aws s3 rm s3://public-padus/ --recursive",
    "mc rb local/public-padus",
    "mc rm --recursive --force minio/public-padus",
    "rc rb minio/public-padus",                            # rc = rustfs mc drop-in
    "rc rm --recursive minio/public-padus",
    "mc mirror --remove nrp/public-padus minio/public-padus",
    "rc mirror --overwrite a/b c/d",
    # catastrophic kubernetes
    "kubectl delete namespace biodiversity",
    "kubectl -n biodiversity delete ns foo",
    "kubectl delete pvc rustfs-data -n boettiger-lab",
    "kubectl delete pod rustfs -n boettiger-lab",
    "kubectl delete jobs --all -n biodiversity",
    # force-deletion / finalizer-stripping (skill k8s-never-force-delete)
    "kubectl delete pod chelsa-hex-fix43-0 --force --grace-period=0 -n geo-workflows",
    "kubectl -n geo-workflows delete pod stuck-pod --force",
    "kubectl delete pod x -n geo-workflows --grace-period=0",
    "kubectl delete pod x -n geo-workflows --grace-period 0",
    "kubectl patch pvc rechunk-scratch -n geo-workflows -p '{\"metadata\":{\"finalizers\":[]}}'",
    "kubectl edit ns/geo-workflows   # strip finalizers",
    "kubectl replace --raw /api/v1/namespaces/stuck/finalize -f /tmp/ns.json",
    # filesystem
    "rm -rf /",
    "rm -rf $HOME",
    "sudo rm -fr ~",
]

ALLOW = [
    "kubectl -n biodiversity delete job sync-public-land-cover",
    "kubectl delete -f catalog/census/k8s/tract/census-2024-tract-hex.yaml",
    "kubectl apply -f workflow.yaml",
    # graceful deletion with a NONZERO grace period is normal
    "kubectl delete pod x -n geo-workflows --grace-period=30",
    "kubectl delete job stac-fix-579-mpa-terms -n geo-workflows --grace-period=600",
    # reading finalizers is diagnosis, which is what the skill asks for
    "kubectl get ns geo-workflows -o jsonpath='{.metadata.finalizers}'",
    "kubectl describe pvc rechunk-scratch -n geo-workflows",
    # --force on other tools/verbs is out of scope here (covered elsewhere or benign)
    "kubectl apply --force -f catalog/audit/k8s/stac-fix-579-mpa-terms.yaml",
    "git push --force-with-lease origin fix/579-mpa-candidates-terms",
    "rclone purge nrp:public-rap/rap-pfg-cover/staging",   # staging subpath ok
    "rclone copy nrp:public-padus/x.parquet /tmp/",
    "rclone ls minio:public-padus",
    "aws s3 rm s3://public-padus/old/single-key.parquet",  # single key, not --recursive
    "rm -rf /tmp/megamove/f6",
    "git push origin main",
    "duckdb -c 'SELECT 1'",
    "mc ls minio/public-padus",
    "rc ls minio/public-padus",
    "mc mirror nrp/public-padus minio/public-padus",       # additive mirror ok
    "rclone rc core/stats",                                # rclone remote-control, not rc client
    "rclone rc vfs/refresh",
]


def verdict(command):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    rc = subprocess.run([sys.executable, HOOK], input=payload,
                        capture_output=True, text=True).returncode
    return "BLOCK" if rc == 2 else "ALLOW"


def main():
    fails = 0
    for expect, cases in (("BLOCK", BLOCK), ("ALLOW", ALLOW)):
        print(f"=== expect {expect} ===")
        for c in cases:
            got = verdict(c)
            ok = got == expect
            fails += not ok
            print(f"  {'ok  ' if ok else 'FAIL'} [{got}] {c}")
    print(f"\n{'ALL PASS' if fails == 0 else str(fails) + ' FAILURES'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
