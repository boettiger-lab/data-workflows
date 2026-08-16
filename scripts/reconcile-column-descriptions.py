#!/usr/bin/env python3
"""Reconcile divergent per-column descriptions in a STAC collection (data-workflows#532).

`get_stac_details` folds per-column `description` text across all assets in a collection and
**first-seen wins** (mcp-data-server#303), so a column documented two ways loses one version
silently. `verify-stac.py check_column_description_consistency` reports each such
`column-description-divergent`. This tool fixes them mechanically for the AUTO cohort:

    canonical text = the flat GeoParquet asset's text for that column, applied to EVERY asset.

The flat GeoParquet is the documented single authority (AGENTS.md). Any per-feature
duplication note that lived inline on a hex column is not deleted — it is ensured at the hex
asset `description` level, which is the location the renderer always surfaces and which
satisfies `verify-stac.py check_hex_dup_warning` for the whole asset.

Two safety guards, because a flat text is not always grain-neutral:
  * If the flat canonical text contains a FLAT-GRAIN-SPECIFIC claim that would be false on a
    hex asset (e.g. "one row per case on the flat GeoParquet, so SUM is correct here"), the
    column is NOT auto-set — it is reported as needs-judgment and left untouched.
  * A collection with no flat GeoParquet asset, or with a divergent column absent from the
    flat asset, is out of scope for this tool (the #532 JUDGMENT cohort) — reported, skipped.

The tool is a pure transform: it reads a collection JSON (URL / file / --bucket [--dataset])
and writes the reconciled JSON to an output dir. It never writes to S3 (publishing is a
separate cluster step). Run `verify-stac.py` on the output before publishing.

Usage:
    reconcile-column-descriptions.py <url-or-file> [...] [--out DIR] [--verbose]
    reconcile-column-descriptions.py --bucket public-wdpa --dataset wdpa --out /tmp/recon
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

NRP = "https://s3-west.nrp-nautilus.io"
GEOM = {"geom", "geometry", "shape", "the_geom"}

# A hex column carrying a per-feature magnitude gets an inline dedup clause; detect it so we
# can (a) know which columns to name in the relocated asset-level note and (b) know the clause
# is being intentionally stripped, not lost.
DEDUP_CLAUSE = re.compile(
    r"repeated (on|for|across) (every|the)|never (use )?sum|do not sum|don't sum|"
    r"dedup|deduplicat|select distinct|count\(distinct|row_number|per[- ]?feature total",
    re.I)

# Same signal verify-stac.py check_hex_dup_warning accepts at the asset/collection level.
ASSET_NOTE = re.compile(
    r"repeated (on|for|across) (every|the)|never (use )?sum|do not sum|don't sum|"
    r"not safe to sum|per[- ]?feature|count\(distinct|select distinct|dedup|"
    r"deduplicat|multiply by .*cell area|sum is the .*total|area-weighted|reducer",
    re.I)

# A flat text that makes a claim only true at the flat grain — copying it onto a hex asset
# would render a FALSE statement for every consumer (the #512 "stale text outlives its asset"
# trap). Such a column needs manual reconciliation, not a verbatim copy.
FLAT_SPECIFIC = re.compile(
    r"on the flat geoparquet|one row per .{0,40}\bflat\b|sum is correct here|"
    r"flat asset[^s]|so sum is correct|one row per (case|feature|site|record)\b",
    re.I)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def load(src: str) -> dict:
    if src.startswith("http"):
        return fetch(src)
    return json.loads(Path(src).read_text())


def is_hex_href(href: str) -> bool:
    return "h0=" in href or "/hex/" in href


def flat_asset_key(doc: dict) -> str | None:
    """The flat GeoParquet asset: a non-hex parquet asset carrying a geometry column."""
    for k, a in doc.get("assets", {}).items():
        href = a.get("href", "")
        if is_hex_href(href):
            continue
        if a.get("type", "") not in ("application/x-parquet", "application/parquet",
                                     "application/vnd.apache.parquet"):
            # still accept if it clearly has table:columns + a geom column
            pass
        cols = {c.get("name", "").lower() for c in a.get("table:columns", [])}
        if cols & GEOM:
            return k
    return None


def divergent_columns(doc: dict) -> dict:
    """name -> {asset_key: text} for columns whose text differs across assets."""
    m: dict[str, dict[str, str]] = {}
    for k, a in doc.get("assets", {}).items():
        for c in a.get("table:columns", []):
            n, t = c.get("name", ""), c.get("description", "")
            if n and t:
                m.setdefault(n, {})[k] = t
    return {n: d for n, d in m.items() if len({norm(x) for x in d.values()}) > 1}


def reconcile(doc: dict, verbose=False) -> dict:
    """Mutate doc in place. Return a report dict."""
    report = {"id": doc.get("id", "?"), "status": "ok", "changed": [], "skipped": [],
              "hex_notes_added": [], "reason": ""}
    div = divergent_columns(doc)
    if not div:
        report["status"] = "already-clean"
        return report
    fk = flat_asset_key(doc)
    if not fk:
        report["status"] = "judgment"
        report["reason"] = "no flat GeoParquet asset"
        report["skipped"] = sorted(div)
        return report
    flat_cols = {c.get("name", ""): c.get("description", "")
                 for c in doc["assets"][fk].get("table:columns", [])}

    # Per hex asset, the per-feature-total column names whose inline dedup clause we strip.
    stripped_by_asset: dict[str, list[str]] = {}

    for name, per in sorted(div.items()):
        if name not in flat_cols or not flat_cols[name]:
            report["skipped"].append(name)
            report.setdefault("skip_reasons", {})[name] = "not on flat asset"
            continue
        canonical = flat_cols[name]
        if FLAT_SPECIFIC.search(canonical):
            report["skipped"].append(name)
            report.setdefault("skip_reasons", {})[name] = "flat text is grain-specific"
            continue
        # Apply canonical to every asset that carries this column; record hex strips.
        for ak, a in doc.get("assets", {}).items():
            for c in a.get("table:columns", []):
                if c.get("name") != name:
                    continue
                old = c.get("description", "")
                if norm(old) == norm(canonical):
                    continue
                if is_hex_href(a.get("href", "")) and DEDUP_CLAUSE.search(old):
                    stripped_by_asset.setdefault(ak, []).append(name)
                c["description"] = canonical
        report["changed"].append(name)

    # Ensure the per-feature dedup note survives at the hex asset description level — the
    # location the #303 fold always renders and that satisfies check_hex_dup_warning. Added
    # only when we actually stripped an inline clause and the hex asset lacks its own note.
    for ak, names in stripped_by_asset.items():
        asset = doc["assets"][ak]
        if ASSET_NOTE.search(asset.get("description", "") or ""):
            continue  # already carries a note
        cols_list = ", ".join(sorted(set(names)))
        note = (f" Per-feature attribute columns ({cols_list}) are repeated on every hex "
                f"cell the feature covers, so a raw SUM over hex rows double-counts; dedup "
                f"by _cng_fid first, e.g. SELECT DISTINCT _cng_fid, {sorted(set(names))[0]}.")
        asset["description"] = (asset.get("description", "") or "").rstrip()
        asset["description"] = (asset["description"] + note).strip()
        report["hex_notes_added"].append({"asset": ak, "columns": sorted(set(names))})

    # Post-check: recompute divergences.
    remaining = divergent_columns(doc)
    report["remaining"] = sorted(remaining)
    if remaining and not report["skipped"]:
        report["status"] = "partial"
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sources", nargs="*", help="collection STAC URL(s) or file path(s)")
    p.add_argument("--bucket", help="bucket (with --dataset) to derive the collection URL")
    p.add_argument("--dataset", default="")
    p.add_argument("--out", default="/tmp/recon", help="output dir for reconciled JSON")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    srcs = list(args.sources)
    if args.bucket:
        seg = f"/{args.dataset}" if args.dataset else ""
        srcs.append(f"{NRP}/{args.bucket}{seg}/stac-collection.json")
    if not srcs:
        p.error("provide a collection URL/file or --bucket [--dataset]")

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    reports = []
    for src in srcs:
        doc = load(src)
        rep = reconcile(doc, verbose=args.verbose)
        reports.append(rep)
        if rep["status"] in ("ok", "partial") and rep["changed"]:
            cid = doc.get("id", "collection")
            outpath = outdir / f"{cid}.stac-collection.json"
            outpath.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
            rep["out"] = str(outpath)

    for rep in reports:
        print(f"\n=== {rep['id']} [{rep['status']}] ===")
        if rep.get("reason"):
            print(f"  reason: {rep['reason']}")
        if rep["changed"]:
            print(f"  reconciled ({len(rep['changed'])}): {', '.join(rep['changed'])}")
        for hn in rep["hex_notes_added"]:
            print(f"  + hex note on '{hn['asset']}' for: {', '.join(hn['columns'])}")
        if rep["skipped"]:
            print(f"  SKIPPED (needs judgment): {', '.join(rep['skipped'])}")
            for n, why in rep.get("skip_reasons", {}).items():
                print(f"      {n}: {why}")
        if rep.get("remaining"):
            print(f"  REMAINING divergent after run: {', '.join(rep['remaining'])}")
        if rep.get("out"):
            print(f"  -> {rep['out']}")
    # exit non-zero if any collection still has remaining divergences it could not fix
    bad = [r for r in reports if r.get("remaining")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
