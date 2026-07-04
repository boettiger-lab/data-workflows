#!/usr/bin/env python3
"""Phase 3 of the source.coop mirror campaign (issue #351): publish the unified
GLEN root STAC catalog at ``cboettig/glen/catalog.json`` — the source.coop analog
of NRP's ``public-data/stac/catalog.json`` — plus the ``glen`` landing-page README.

Runs AFTER the data sync (phase 1) and the STAC href rewrite (phase 2), because
the child collections it links must already be source.coop-consistent.

Design (see issue #351):
  * The STAC catalog is a TREE. This root links only the curated TOP-LEVEL
    collections; everything nested/cross-collection (e.g. ``gfw`` under
    ``high-seas``, the CAL FIRE leaves under ``fire-perimeters``) is reached by
    descending those collections — NOT linked directly here.
  * Child list = NRP root's top-level ``child`` links, FILTERED to the mirror
    scope, with hrefs rewritten to ``data.source.coop/cboettig/…``. The mirror
    scope (source-sync-scope ConfigMap / REPOS) is the license gate; the NRP root
    supplies the real collection entry points at their true (possibly nested)
    paths. A child whose target bucket is NOT in scope stays an NRP href and is
    dropped — so restricted collections (wdpa, iucn, hydrobasins, icca, tpl, …)
    can never leak into the public mirror catalog. Enforced by construction.
  * Navigation is downward-only by design: the mirrored collections' own
    ``root``/``parent`` links keep pointing at the canonical NRP root (#158
    decision). glen is an entry point you descend from.

The scope reader (``mirrored_repos``) and href rewriter (``rewrite_string``) are
REUSED from the sibling phase-2 script ``rewrite-stac-hrefs.py`` — loaded by path
(its filename has a hyphen, so it can't be a normal import). In the CronJob both
scripts are fetched to the same /tmp dir; locally they sit side by side here.

Writes to source.coop ONLY; refuses any dest that is not ``cboettig/glen/…``.
NRP is never modified. Run with --dry-run first.

Usage:
  ./gen-root-catalog.py --dry-run                    # build + print, write nothing
  ./gen-root-catalog.py --readme glen-README.md      # build, publish catalog.json + README
  SCOPE_FILE=/config/repos.txt ./gen-root-catalog.py --readme /tmp/glen-README.md
"""
import argparse
import importlib.util
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

NRP_ROOT_URL = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
GLEN_REMOTE = "source:us-west-2.opendata.source.coop/cboettig/glen"
GLEN_PUBLIC = "https://data.source.coop/cboettig/glen"
# Sanity floor: refuse to publish a catalog with implausibly few children (a
# scope/parse/fetch glitch emptying the tree). ~28 top-level collections are in
# scope today; 15 is a safe circuit-breaker in the spirit of the sync's
# --max-delete guard. Raise if the in-scope set ever shrinks below it.
MIN_CHILDREN = 15


def _load_rewrite_module():
    """Load the sibling phase-2 script by path (hyphenated filename → not
    importable normally). Importing under a non-__main__ name does NOT run its
    main()."""
    path = Path(__file__).resolve().parent / "rewrite-stac-hrefs.py"
    if not path.exists():
        sys.exit(f"FATAL: sibling script not found: {path}")
    spec = importlib.util.spec_from_file_location("rewrite_stac_hrefs", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fetch_nrp_root(url: str, tries: int = 6) -> dict:
    """Fetch + parse the NRP root catalog, retrying transient failures (the Ceph
    S3 endpoint 503s under load / degradation). Fail hard rather than publish a
    truncated catalog. A local file path (or file:// URL) is read directly —
    useful for testing and for publishing from a cached copy when Ceph is down."""
    local = url[len("file://"):] if url.startswith("file://") else url
    if Path(local).exists():
        return json.loads(Path(local).read_text())
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001 — includes HTTPError/URLError/JSON
            last = e
            wait = min(2 ** i, 30)
            print(f"  NRP root fetch attempt {i + 1}/{tries} failed ({e}); "
                  f"retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    sys.exit(f"FATAL: could not fetch NRP root catalog after {tries} tries: {last}")


def build_children(nrp_root: dict, repos: set, rewrite_string) -> list:
    """Keep NRP root's top-level `child` links whose target is in the mirror
    scope, rewriting each href to its source.coop equivalent. A non-scope target
    is left as an NRP href by rewrite_string (unchanged) → we drop it."""
    children = []
    for link in nrp_root.get("links", []):
        if not isinstance(link, dict) or link.get("rel") != "child":
            continue
        href = link.get("href", "")
        new = rewrite_string(href, repos)
        if new == href:  # not rewritten ⇒ target bucket not in scope ⇒ drop
            continue
        child = {"rel": "child", "href": new, "type": "application/json"}
        # id / title are optional on a STAC link; carry them through when present.
        if link.get("id"):
            child["id"] = link["id"]
        if link.get("title"):
            child["title"] = link["title"]
        children.append(child)
    return children


def build_catalog(children: list) -> dict:
    return {
        "stac_version": "1.0.0",
        "type": "Catalog",
        "id": "glen",
        "title": "GLEN — Boettiger Lab Geospatial Datasets (source.coop mirror)",
        "description": (
            "The unified GLEN root STAC catalog: a navigable, self-describing "
            "index of the Boettiger Lab's public, license-clear geospatial "
            "collections mirrored to Source Cooperative (cboettig/*). This is the "
            "off-NRP public mirror of the canonical catalog at "
            "s3-west.nrp-nautilus.io/public-data/stac/catalog.json — point a STAC "
            "client here and descend to reach each collection and its items. "
            "It links only the license-clear subset actually mirrored; "
            "no-redistribution collections are intentionally absent. Individual "
            "collections keep their root/parent links pointing at the canonical "
            "NRP root, so navigation from this catalog is downward by design."
        ),
        "links": [
            {"rel": "self", "href": f"{GLEN_PUBLIC}/catalog.json",
             "type": "application/json"},
            {"rel": "root", "href": f"{GLEN_PUBLIC}/catalog.json",
             "type": "application/json"},
            *children,
        ],
    }


def rclone_rcat(dest: str, body: str) -> None:
    """Write `body` to `dest` on source.coop. Guarded to the glen sub-path; the
    creds have account-wide access to a SHARED bucket, so refuse anything else."""
    if not dest.startswith(GLEN_REMOTE + "/"):
        sys.exit(f"REFUSING: dest '{dest}' is not under {GLEN_REMOTE}/")
    # --s3-no-check-bucket: scoped creds can't s3:CreateBucket; without it rcat
    # probes the (existing, shared) bucket and 403s.
    p = subprocess.run(
        ["rclone", "rcat", "--s3-no-check-bucket", dest],
        input=body, text=True, capture_output=True,
    )
    if p.returncode != 0:
        sys.exit(f"FATAL writing {dest}: {p.stderr}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="build + print the catalog, write nothing")
    ap.add_argument("--readme", help="path to the static glen README.md to publish")
    ap.add_argument("--nrp-root", default=NRP_ROOT_URL,
                    help="NRP root catalog URL (override for testing)")
    ap.add_argument("--min-children", type=int, default=MIN_CHILDREN,
                    help="refuse to publish fewer than this many child links")
    args = ap.parse_args()

    rw = _load_rewrite_module()
    repos = rw.mirrored_repos()
    print(f"mirror scope ({len(repos)} repos): {' '.join(sorted(repos))}\n")

    nrp_root = fetch_nrp_root(args.nrp_root)
    children = build_children(nrp_root, repos, rw.rewrite_string)
    total = sum(1 for l in nrp_root.get("links", []) if l.get("rel") == "child")
    print(f"NRP root has {total} top-level child links; "
          f"{len(children)} are in-scope (license-clear) and kept:\n")
    for c in children:
        print(f"  {c.get('id', '(no id)'):32} {c['href']}")

    if len(children) < args.min_children:
        sys.exit(f"\nFATAL: only {len(children)} in-scope children "
                 f"(< floor {args.min_children}); refusing to publish a "
                 f"suspiciously small catalog. Check scope + NRP root fetch.")

    catalog = build_catalog(children)
    body = json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"

    if args.dry_run:
        print(f"\n(dry-run) would write {GLEN_REMOTE}/catalog.json "
              f"({len(children)} children)")
        if args.readme:
            print(f"(dry-run) would write {GLEN_REMOTE}/README.md "
                  f"from {args.readme}")
        return

    rclone_rcat(f"{GLEN_REMOTE}/catalog.json", body)
    print(f"\nWROTE {GLEN_REMOTE}/catalog.json ({len(children)} children)")

    if args.readme:
        readme = Path(args.readme)
        if not readme.exists():
            sys.exit(f"FATAL: --readme file not found: {readme}")
        rclone_rcat(f"{GLEN_REMOTE}/README.md", readme.read_text())
        print(f"WROTE {GLEN_REMOTE}/README.md (from {readme})")


if __name__ == "__main__":
    main()
