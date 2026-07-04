#!/usr/bin/env python3
"""Phase 2 of the MinIO backup mirror (issue #354): rewrite the mirrored STAC so
the MinIO copy is a FULLY SELF-CONTAINED, independently-navigable catalog — the
MinIO analog of source.coop's rewrite-stac-hrefs.py (#158/#351).

MinIO (minio.carlboettiger.info) is the complete off-NRP backup of every public-*
bucket AND a public-read, served HTTPS endpoint. It must be usable as a recovery
catalog when NRP S3 is down — so NO href may point back to NRP.

For every STAC `*.json` mirrored under `minio:public-<bucket>/`:

  Rewrite any href `https://s3-west.nrp-nautilus.io/public-<X>/<path>` to
  `https://minio.carlboettiger.info/public-<X>/<path>` IFF `public-<X>` is a
  MinIO-scoped bucket (read from minio-sync-cron-config.yaml's buckets.txt — the
  same single source of truth the sync jobs use). Covers EVERY href — self,
  **root, parent**, child, describedby, and all assets.

Two things distinguish this from the source.coop rewriter, both by design:

  1. **Self-contained (root/parent included).** source.coop deliberately leaves
     root/parent pointing at the canonical NRP root; MinIO must NOT. This falls
     out of the scope list, not special-casing: `public-data` (the root catalog's
     bucket) IS in the MinIO scope, so root/parent hrefs — which target
     `public-data/stac/catalog.json` — get swapped to MinIO automatically. (On
     source.coop the identical logic leaves them at NRP because `public-data` is
     not in that scope.) No separate root-catalog generator is needed: MinIO
     preserves bucket names 1:1 and already mirrors `public-data`, so the root
     catalog is already present and is rewritten like any other file.

  2. **No license subset, no child-dropping.** MinIO mirrors everything verbatim
     (including HOLD sub-paths and no-redistribution datasets), so there is no
     filter to a license-clear subset and nothing to drop.

Bucket enumeration is PER BUCKET (`rclone lsf -R minio:public-<bucket>/`): the
scoped `geo-workflow` key DENIES s3:ListAllMyBuckets, so a bare `minio:` list
would 403. Only in-scope buckets are visited.

Idempotent: a 2nd run is a no-op (a minio href won't re-match the NRP host).
Writes to MinIO ONLY; refuses any dest that is not `minio:public-<bucket>/...`.
NRP is never modified. Run with --dry-run first.

Usage:
  ./rewrite-stac-hrefs.py --dry-run                    # report changes, write nothing
  ./rewrite-stac-hrefs.py                               # rewrite in place on MinIO
  ./rewrite-stac-hrefs.py --buckets data padus          # limit to some buckets
  SCOPE_FILE=/config/buckets.txt ./rewrite-stac-hrefs.py
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MINIO_REMOTE = "minio"                       # rclone remote (dest: minio:public-<bucket>)
NRP_HOST = "https://s3-west.nrp-nautilus.io"
MINIO_HOST = "https://minio.carlboettiger.info"
# NRP bucket-name is preserved 1:1 on MinIO, so this is a pure host swap that
# keeps the `/public-<X>/<path>` tail intact.
NRP_PREFIX_RE = re.compile(re.escape(NRP_HOST) + r"/public-([a-z0-9-]+)/")


def scoped_buckets() -> set[str]:
    """The MinIO-scoped bucket short-names (e.g. 'padus', 'data'), read from the
    generated sync scope so this never drifts from gen-minio-sync.sh / the cron.

    Two sources, both first-field-of-each-non-comment-line:
    - $SCOPE_FILE (the CronJob's mounted /config/buckets.txt) — plain buckets.txt.
    - else the committed minio-sync-cron-config.yaml ConfigMap (the `buckets.txt:`
      block scalar) at its repo-relative path."""
    scope_file = os.environ.get("SCOPE_FILE")
    if scope_file:
        lines = Path(scope_file).read_text().splitlines()
    else:
        cfg = Path(__file__).resolve().parents[1] / "k8s" / "minio-sync-cron-config.yaml"
        lines, in_data = [], False
        for line in cfg.read_text().splitlines():
            if line.strip().startswith("buckets.txt:"):
                in_data = True
                continue
            if in_data:
                lines.append(line)
    buckets = set()
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        buckets.add(s.split()[0])
    if not buckets:
        sys.exit("FATAL: no buckets parsed from scope")
    return buckets


def rewrite_string(s: str, buckets: set[str]) -> str:
    """Swap an NRP href to its MinIO equivalent iff the target bucket is mirrored
    to MinIO. Non-mirrored targets are left as NRP hrefs (no MinIO copy to point
    at) — the correct fallback, and it can't create a dead MinIO link."""
    m = NRP_PREFIX_RE.match(s)
    if m and m.group(1) in buckets:
        return MINIO_HOST + "/public-" + m.group(1) + "/" + s[m.end():]
    return s


def transform(obj, buckets: set[str], stats: dict):
    """Recursively rewrite every href string. No links are dropped."""
    if isinstance(obj, dict):
        return {k: transform(v, buckets, stats) for k, v in obj.items()}
    if isinstance(obj, list):
        return [transform(v, buckets, stats) for v in obj]
    if isinstance(obj, str):
        new = rewrite_string(obj, buckets)
        if new != obj:
            stats["rewritten_hrefs"] += 1
        return new
    return obj


def list_stac_files(bucket: str) -> list[str]:
    """STAC json under one MinIO bucket. Per-bucket (the scoped key denies
    ListAllMyBuckets, so a bare `minio:` list would 403). Returns paths relative
    to the remote root, i.e. `public-<bucket>/...`, excluding `.json/` colliding-
    prefix artifacts (a pre-existing NRP S3 hygiene issue; see #158)."""
    dest = f"{MINIO_REMOTE}:public-{bucket}/"
    r = subprocess.run(
        ["rclone", "lsf", "-R", "--include", "*.json", dest],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"  SKIP bucket public-{bucket} (list failed): {r.stderr.strip()}",
              file=sys.stderr)
        return []
    files = []
    for f in r.stdout.splitlines():
        if ".json/" in f:  # colliding-prefix artifact
            continue
        low = f.lower()
        if any(t in low for t in ("stac", "collection", "catalog")):
            files.append(f"public-{bucket}/{f}")
    return sorted(files)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report changes, write nothing")
    ap.add_argument("--buckets", nargs="*", help="limit to these buckets (default: all in scope)")
    args = ap.parse_args()

    buckets = scoped_buckets()
    print(f"MinIO scope ({len(buckets)} buckets): {' '.join(sorted(buckets))}\n")

    visit = sorted(set(args.buckets) & buckets) if args.buckets else sorted(buckets)
    if args.buckets:
        skipped = set(args.buckets) - buckets
        if skipped:
            print(f"ignoring out-of-scope buckets: {' '.join(sorted(skipped))}")

    tot = {"changed": 0, "rewritten_hrefs": 0, "files": 0}
    for bucket in visit:
        files = list_stac_files(bucket)
        tot["files"] += len(files)
        for f in files:
            raw = subprocess.run(["rclone", "cat", f"{MINIO_REMOTE}:{f}"],
                                 capture_output=True, text=True)
            if raw.returncode != 0 or not raw.stdout.strip():
                print(f"  SKIP (unfetchable): {f}")
                continue
            try:
                doc = json.loads(raw.stdout)
            except json.JSONDecodeError:
                print(f"  SKIP (not JSON): {f}")
                continue
            stats = {"rewritten_hrefs": 0}
            new_doc = transform(doc, buckets, stats)
            if stats["rewritten_hrefs"] == 0:
                continue
            tot["changed"] += 1
            tot["rewritten_hrefs"] += stats["rewritten_hrefs"]
            print(f"  {'WOULD WRITE' if args.dry_run else 'WRITE'}: {f}  "
                  f"({stats['rewritten_hrefs']} hrefs)")
            if args.dry_run:
                continue
            # Safety guard: write back ONLY under minio:public-<bucket>/.
            if f.startswith("/") or ".." in f.split("/") or not f.startswith("public-"):
                sys.exit(f"REFUSING: '{f}' is not a path under minio:public-<bucket>")
            dest = f"{MINIO_REMOTE}:{f}"
            body = json.dumps(new_doc, indent=2, ensure_ascii=False) + "\n"
            # --s3-no-check-bucket: the scoped key can't s3:CreateBucket (buckets
            # already exist); without it rcat probes the bucket and 403s.
            p = subprocess.run(
                ["rclone", "rcat", "--s3-no-check-bucket", dest],
                input=body, text=True, capture_output=True,
            )
            if p.returncode != 0:
                sys.exit(f"FATAL writing {dest}: {p.stderr}")

    print(f"\n{'(dry-run) ' if args.dry_run else ''}"
          f"{tot['files']} STAC files scanned; {tot['changed']} changed; "
          f"{tot['rewritten_hrefs']} hrefs rewritten.")


if __name__ == "__main__":
    main()
