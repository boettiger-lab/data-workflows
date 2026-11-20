#!/usr/bin/env python3
"""Run the Portolan validator (rashid) on changed collections. ADVISORY: always exits 0 (#1003).

rashid 0.4.0 reads a directory tree with a root `catalog.json`, relative hrefs and
children named `collection.json`. Our collections have none of the three (#761), so
each collection is staged into a temp dir with those shims applied locally (nothing is
uploaded), checked with `rashid check --no-data`, and the findings the shims create are
dropped. The data pass is not run: rashid reads data only over https.

    rashid-advisory.py --yaml catalog/x/k8s/y/*.yaml      # collections a recipe touches
    rashid-advisory.py https://s3-west.nrp-nautilus.io/<bucket>/<ds>/stac-collection.json

Writes a per-rule summary to stdout and, in CI, to $GITHUB_STEP_SUMMARY.
"""
import argparse
import collections
import importlib.util
import json
import os
import posixpath
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

NRP = "https://s3-west.nrp-nautilus.io"
# Shim artifacts (#761): LNK-006 is the file-name rule the rename hides anyway; every
# finding on the shim root catalog.json is dropped too. --no-live skips LIV-* (404s on
# the renamed files).
SHIM_RULES = {"PTL-LNK-006"}

_spec = importlib.util.spec_from_file_location(
    "verify_stac", Path(__file__).with_name("verify-stac.py"))
vs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vs)


def fetch(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.read()
    except Exception:
        return None


def stage(url: str, root: Path) -> Path:
    """Mirror one collection into root/<bucket-path>/collection.json with the #761 shims."""
    if not url.startswith(NRP + "/"):
        raise ValueError(f"not an NRP collection URL: {url}")
    bucket, _, key = url[len(NRP) + 1:].partition("/")
    base = f"{NRP}/{bucket}/"
    coll_dir = posixpath.dirname(key)                    # '' for a bucket-root collection
    doc = json.loads(fetch(url) or b"null")
    if doc is None:
        raise FileNotFoundError("collection not readable (not published yet?)")
    dest = root / coll_dir
    dest.mkdir(parents=True, exist_ok=True)
    to_root = posixpath.relpath("catalog.json", coll_dir or ".")

    def rel(href: str) -> str:
        if not href.startswith(base):
            return href
        return posixpath.relpath(href[len(base):], coll_dir or ".")

    for link in doc.get("links", []):
        r, href = link.get("rel"), link.get("href", "")
        if r == "self":
            link["href"] = "./collection.json"
        elif r in ("root", "parent"):
            link["href"] = to_root
        else:
            if r == "describedby" and href.startswith(base):   # stage the README it names
                body = fetch(href)
                if body is not None:
                    p = root / href[len(base):]
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(body)
            link["href"] = rel(href)
    for a in doc.get("assets", {}).values():
        if "href" in a:
            a["href"] = rel(a["href"])
    (dest / "collection.json").write_text(json.dumps(doc, indent=1))
    (root / "catalog.json").write_text(json.dumps({
        "type": "Catalog", "stac_version": doc.get("stac_version", "1.1.0"),
        "id": "rashid-shim-root", "description": "Local shim root (#1003); not published.",
        "links": [{"rel": "root", "href": "./catalog.json", "type": "application/json"},
                  {"rel": "self", "href": "./catalog.json", "type": "application/json"},
                  {"rel": "child", "href": f"./{posixpath.join(coll_dir, 'collection.json')}",
                   "type": "application/json"}]}, indent=1))
    return dest / "collection.json"


def check(url: str) -> tuple[list[dict], str | None]:
    """rashid findings for one collection, shim artifacts removed."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            stage(url, root)
        except Exception as e:
            return [], f"could not stage: {e}"
        p = subprocess.run(["rashid", "check", str(root), "--no-data", "--no-live",
                            "--json", "--all"], capture_output=True, text=True)
        try:
            report = json.loads(p.stdout)
        except json.JSONDecodeError:
            return [], f"rashid exit {p.returncode}: {(p.stderr or p.stdout)[-500:]}"
    return [f for f in report.get("findings", [])
            if f.get("rule_id") not in SHIM_RULES and f.get("path") != "catalog.json"], None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="*", help="Collection URLs.")
    ap.add_argument("--yaml", nargs="*", default=[], help="Changed workflow YAMLs.")
    ap.add_argument("--bucket", help="Bucket (with --dataset), as in verify-stac.py.")
    ap.add_argument("--dataset", default="")
    args = ap.parse_args()

    urls = list(args.sources)
    if args.bucket:
        urls.append(vs.resolve_collection_url(args.bucket, args.dataset))
    for y in args.yaml:
        for b, d in sorted(vs.targets_from_yaml(Path(y).read_text())):
            urls.append(vs.resolve_collection_url(b, d))
    urls = list(dict.fromkeys(urls))
    if not urls:
        print("rashid: no collections to check.")
        return 0

    ver = subprocess.run(["rashid", "--version"], capture_output=True, text=True).stdout
    lines = ["## Portolan validator (rashid), advisory",
             f"`{ver.splitlines()[0] if ver else 'rashid'}`, `--no-data`, with the #761 local "
             "shims. Findings do not fail this job (#1003).", ""]
    for url in urls:
        found, err = check(url)
        lines.append(f"### {url}")
        if err:
            lines += [f"Not checked: {err}", ""]
            continue
        by = collections.Counter((f.get("severity", "?"), f.get("rule_id", "?")) for f in found)
        msg = {}
        for f in found:
            msg.setdefault(f.get("rule_id", "?"), f.get("message", ""))
        if not by:
            lines += ["No findings.", ""]
            continue
        lines += ["| severity | rule | n | example |", "|---|---|---|---|"]
        for (sev, rule), n in sorted(by.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            lines.append(f"| {sev} | {rule} | {n} | {msg[rule][:160].replace('|', '/')} |")
        lines.append("")
    out = "\n".join(lines)
    print(out)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(out + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # advisory: never fail the job
        print(f"rashid advisory step errored: {e}", file=sys.stderr)
        sys.exit(0)
