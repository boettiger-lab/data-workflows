#!/usr/bin/env python3
"""Phase 2 of the source.coop mirror campaign (issue #158): rewrite the mirrored
STAC so it is self-referential for everything that exists on source.coop, without
touching NRP (which stays canonical).

For every STAC `*.json` under `cboettig/<repo>/` on source.coop:

  1. Rewrite any href `https://s3-west.nrp-nautilus.io/public-<X>/<path>` to
     `https://data.source.coop/cboettig/<X>/<path>` IFF `<X>` is one of the
     mirrored repos (read from source-sync-cron-config.yaml's repos.txt — the
     same single source of truth the sync jobs use). Covers self / child /
     describedby / all asset hrefs, including cross-bucket references.
  2. Leave `root` / `parent` links that point at the NON-mirrored NRP global root
     catalog (`public-data/stac/catalog.json`) UNCHANGED — source.coop collections
     stay navigable up to the canonical NRP root (decision in #158).
  3. Drop dangling `child` links to the excluded HOLD sub-paths that were never
     mirrored (rivers american-rivers/{campaigns,ira-watersheds,roo-cjest},
     high-seas mpa-candidates).

Idempotent: a 2nd run is a no-op (an already-source.coop href won't re-match).
Topology-agnostic: does not assume a fixed root path per repo.

Writes to source.coop ONLY; refuses any path that is not cboettig/<repo>/...
NRP is never modified. Run with --dry-run first.

Usage:
  ./rewrite-stac-hrefs.py --dry-run             # report changes, write nothing
  ./rewrite-stac-hrefs.py                        # rewrite in place on source.coop
  ./rewrite-stac-hrefs.py --repos rivers high-seas   # limit to some repos
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SRC_REMOTE = "source:us-west-2.opendata.source.coop/cboettig"
PUBLIC_URL = "https://data.source.coop/cboettig"
NRP_HOST = "https://s3-west.nrp-nautilus.io"
# bucket->repo mapping is 1:1 minus the `public-` prefix for every mirrored repo.
NRP_PREFIX_RE = re.compile(re.escape(NRP_HOST) + r"/public-([a-z0-9-]+)/")

# child links to these (post-rewrite) source.coop path fragments are dangling:
# the sub-collections were intentionally excluded from the data mirror (#158).
HOLD_PATH_FRAGMENTS = (
    "/cboettig/rivers/american-rivers/campaigns/",
    "/cboettig/rivers/american-rivers/ira-watersheds/",
    "/cboettig/rivers/american-rivers/roo-cjest/",
    "/cboettig/high-seas/mpa-candidates/",
)


def mirrored_repos() -> set[str]:
    """The 27 mirrored repos, read from the generated sync scope (single source
    of truth) so this never drifts from gen-source-sync.sh / the CronJob.

    Two sources, both first-field-of-each-non-comment-line:
    - $SCOPE_FILE (e.g. the CronJob's mounted /config/repos.txt) — plain repos.txt.
    - else the committed source-sync-cron-config.yaml ConfigMap (the `repos.txt:`
      block scalar) at its repo-relative path."""
    scope_file = os.environ.get("SCOPE_FILE")
    if scope_file:
        lines = Path(scope_file).read_text().splitlines()
    else:
        cfg = Path(__file__).resolve().parents[1] / "k8s" / "source-sync-cron-config.yaml"
        lines, in_data = [], False
        for line in cfg.read_text().splitlines():
            if line.strip().startswith("repos.txt:"):
                in_data = True
                continue
            if in_data:
                lines.append(line)
    repos = set()
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        repos.add(s.split()[0])
    if not repos:
        sys.exit("FATAL: no repos parsed from scope")
    return repos


def rewrite_string(s: str, repos: set[str]) -> str:
    """Rewrite an NRP href to its source.coop equivalent iff the target bucket is
    mirrored. Non-mirrored targets (e.g. public-data root catalog) are untouched."""
    m = NRP_PREFIX_RE.match(s)
    if m and m.group(1) in repos:
        return PUBLIC_URL + "/" + m.group(1) + "/" + s[m.end():]
    return s


def transform(obj, repos: set[str], stats: dict):
    """Recursively rewrite hrefs; drop dangling HOLD child links from `links`."""
    if isinstance(obj, dict):
        # Drop dangling HOLD children before recursing into the links list.
        if isinstance(obj.get("links"), list):
            kept = []
            for link in obj["links"]:
                href = link.get("href", "") if isinstance(link, dict) else ""
                new_href = rewrite_string(href, repos) if href else href
                if link.get("rel") == "child" and any(
                    frag in new_href for frag in HOLD_PATH_FRAGMENTS
                ):
                    stats["dropped_children"] += 1
                    continue
                kept.append(link)
            obj["links"] = kept
        return {k: transform(v, repos, stats) for k, v in obj.items()}
    if isinstance(obj, list):
        return [transform(v, repos, stats) for v in obj]
    if isinstance(obj, str):
        new = rewrite_string(obj, repos)
        if new != obj:
            stats["rewritten_hrefs"] += 1
        return new
    return obj


def list_stac_files() -> list[str]:
    """STAC json files under cboettig/, excluding the colliding `.json/` prefix
    artifacts (a pre-existing NRP S3 hygiene issue, out of scope — see #158)."""
    out = subprocess.run(
        ["rclone", "lsf", "-R", "--include", "*.json", SRC_REMOTE + "/"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    files = []
    for f in out:
        low = f.lower()
        if ".json/" in f:  # skip colliding-prefix artifacts
            continue
        if any(t in low for t in ("stac", "collection", "catalog")):
            files.append(f)
    return sorted(files)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report changes, write nothing")
    ap.add_argument("--repos", nargs="*", help="limit to these repos (default: all)")
    args = ap.parse_args()

    repos = mirrored_repos()
    print(f"mirrored repos ({len(repos)}): {' '.join(sorted(repos))}\n")

    files = list_stac_files()
    if args.repos:
        sel = set(args.repos)
        files = [f for f in files if f.split("/")[0] in sel]
    print(f"{len(files)} STAC json files to scan"
          f"{' (dry-run)' if args.dry_run else ''}\n")

    tot = {"changed": 0, "rewritten_hrefs": 0, "dropped_children": 0}
    for f in files:
        # Read via rclone (not the public CDN) so this works identically locally
        # and in-pod, with no curl dependency and no CDN-cache staleness.
        raw = subprocess.run(["rclone", "cat", f"{SRC_REMOTE}/{f}"],
                             capture_output=True, text=True)
        if raw.returncode != 0 or not raw.stdout.strip():
            print(f"  SKIP (unfetchable): {f}")
            continue
        try:
            doc = json.loads(raw.stdout)
        except json.JSONDecodeError:
            print(f"  SKIP (not JSON): {f}")
            continue
        stats = {"rewritten_hrefs": 0, "dropped_children": 0}
        new_doc = transform(doc, repos, stats)
        if stats["rewritten_hrefs"] == 0 and stats["dropped_children"] == 0:
            continue
        tot["changed"] += 1
        tot["rewritten_hrefs"] += stats["rewritten_hrefs"]
        tot["dropped_children"] += stats["dropped_children"]
        note = f"{stats['rewritten_hrefs']} hrefs"
        if stats["dropped_children"]:
            note += f", {stats['dropped_children']} dangling child(ren) dropped"
        print(f"  {'WOULD WRITE' if args.dry_run else 'WRITE'}: {f}  ({note})")
        if args.dry_run:
            continue
        # Safety guard: write back ONLY under cboettig/<repo>/ on source.coop.
        # `f` comes from rclone lsf of the cboettig/ prefix, but guard anyway:
        # reject absolute paths or any `..` that could escape the prefix.
        if f.startswith("/") or ".." in f.split("/") or f.split("/")[0] not in repos:
            sys.exit(f"REFUSING: '{f}' is not a path under a cboettig/<repo>")
        dest = f"{SRC_REMOTE}/{f}"
        body = json.dumps(new_doc, indent=2, ensure_ascii=False) + "\n"
        # --s3-no-check-bucket: our scoped creds can't s3:CreateBucket (the shared
        # bucket already exists); without this rcat probes the bucket and 403s.
        p = subprocess.run(
            ["rclone", "rcat", "--s3-no-check-bucket", dest], input=body, text=True,
            capture_output=True,
        )
        if p.returncode != 0:
            sys.exit(f"FATAL writing {dest}: {p.stderr}")

    print(f"\n{'(dry-run) ' if args.dry_run else ''}"
          f"{tot['changed']} files changed; {tot['rewritten_hrefs']} hrefs rewritten; "
          f"{tot['dropped_children']} dangling child links dropped.")


if __name__ == "__main__":
    main()
