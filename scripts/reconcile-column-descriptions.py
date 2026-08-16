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


# Index / key columns are never per-feature magnitudes — they must not be named in a
# "never SUM, dedup" note even if their hex text happens to mention repetition.
SAFE_COLS = {"_cng_fid", "bbox", "fid", "ogc_fid", "objectid"}
_H3 = re.compile(r"^h\d{1,2}$")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def grain_neutral(text: str) -> str:
    """Drop whole sentences that make a flat-grain-specific claim, leaving a canonical text
    true on every asset. Returns '' if nothing survives (then the column needs judgment)."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = [p for p in parts if p and not FLAT_SPECIFIC.search(p)]
    return norm(" ".join(kept))


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


def _h3_canonical(name: str) -> str:
    """Grain-neutral text for an H3 index column. Grain (native vs rollup) is declared by
    h3:native_resolution / h3:parent_resolutions on the asset, so the column text must not
    encode it (that is exactly what makes h-columns diverge across hex/hex-fractions)."""
    n = int(name[1:])
    if n == 0:
        return "H3 cell ID at resolution 0; the Hive partition key for hive-partitioned reads."
    return f"H3 cell ID at resolution {n}."


def _has_cng_fid(asset: dict) -> bool:
    """A vector feature hex carries _cng_fid; a raster reduction (categorical/continuous hex)
    does not. A '_cng_fid dedup' note only makes sense on the former."""
    return any(c.get("name") == "_cng_fid" for c in asset.get("table:columns", []))


def _apply_canonical(doc: dict, name: str, canonical: str, report: dict,
                     stripped_by_asset: dict) -> None:
    """Set `canonical` as the description of `name` on every asset that carries it, recording
    any hex per-feature-magnitude column whose inline dedup clause is thereby stripped."""
    for ak, a in doc.get("assets", {}).items():
        for c in a.get("table:columns", []):
            if c.get("name") != name:
                continue
            old = c.get("description", "")
            if norm(old) == norm(canonical):
                continue
            # Only a vector feature hex (has _cng_fid) can carry a per-feature dedup note.
            # A raster reduction hex has no _cng_fid — its "do not SUM" is a categorical
            # caution, not a per-feature-duplication clause, so never relocate one there.
            if (is_hex_href(a.get("href", "")) and DEDUP_CLAUSE.search(old)
                    and name.lower() not in SAFE_COLS and not _H3.match(name)
                    and _has_cng_fid(a)):
                stripped_by_asset.setdefault(ak, []).append(name)
            c["description"] = canonical
    report["changed"].append(name)


def _ensure_hex_notes(doc: dict, stripped_by_asset: dict, report: dict) -> None:
    """Relocate stripped per-feature dedup clauses to the hex asset description (the location
    the #303 fold always renders and that satisfies check_hex_dup_warning)."""
    for ak, names in stripped_by_asset.items():
        asset = doc["assets"][ak]
        if ASSET_NOTE.search(asset.get("description", "") or ""):
            continue
        uniq = sorted(set(names))
        note = (f" Per-feature attribute columns ({', '.join(uniq)}) are repeated on every "
                f"hex cell the feature covers, so a raw SUM over hex rows double-counts; dedup "
                f"by _cng_fid first, e.g. SELECT DISTINCT _cng_fid, {uniq[0]}.")
        asset["description"] = ((asset.get("description", "") or "").rstrip() + note).strip()
        report["hex_notes_added"].append({"asset": ak, "columns": uniq})


def _apply_overrides(doc: dict, ov: dict, report: dict, stripped_by_asset: dict) -> None:
    """Apply a hand-authored per-collection override: set canonical text for named columns on
    every asset, and append any asset-specific notes to the named asset descriptions."""
    for name, text in (ov.get("columns") or {}).items():
        _apply_canonical(doc, name, text, report, stripped_by_asset)
        report.setdefault("overridden", []).append(name)
    for ak, note in (ov.get("asset_notes") or {}).items():
        if ak in doc.get("assets", {}):
            cur = doc["assets"][ak].get("description", "") or ""
            if norm(note) not in norm(cur):
                doc["assets"][ak]["description"] = (cur.rstrip() + " " + note).strip()


def _resolve_generic(doc: dict, name: str, per: dict, report: dict,
                     stripped_by_asset: dict) -> bool:
    """Resolve a divergent column with no flat canonical by the safe mechanical rules:
    grain-neutral H3 columns, or a clean superset (one variant contains all the others).
    Returns True if resolved; False means it needs a hand-authored override."""
    if _H3.match(name):
        _apply_canonical(doc, name, _h3_canonical(name), report, stripped_by_asset)
        return True
    longest = max(per.values(), key=lambda t: len(norm(t)))
    if all(norm(v) in norm(longest) for v in per.values()):
        base = min(per.values(), key=lambda t: len(norm(t)))
        _apply_canonical(doc, name, base, report, stripped_by_asset)
        return True
    return False


def reconcile(doc: dict, verbose=False, allow_no_flat=False, overrides=None) -> dict:
    """Mutate doc in place. Return a report dict."""
    report = {"id": doc.get("id", "?"), "status": "ok", "changed": [], "skipped": [],
              "hex_notes_added": [], "reason": ""}
    stripped_by_asset: dict[str, list[str]] = {}

    # 1) Hand-authored overrides first (judgment cohort). They win over any auto rule.
    ov = (overrides or {}).get(doc.get("id", ""), {})
    if ov:
        _apply_overrides(doc, ov, report, stripped_by_asset)

    div = divergent_columns(doc)
    if not div:
        _ensure_hex_notes(doc, stripped_by_asset, report)
        report["status"] = "already-clean" if not report["changed"] else "ok"
        return report

    fk = flat_asset_key(doc)
    if fk:
        # 2a) AUTO cohort: canonical = the flat GeoParquet asset's text.
        flat_cols = {c.get("name", ""): c.get("description", "")
                     for c in doc["assets"][fk].get("table:columns", [])}
        for name in sorted(div):
            if name not in flat_cols or not flat_cols[name]:
                # Column absent from the flat asset (typically a hex-only H3 index). Fall back
                # to the mechanical no-flat rules; only skip if those can't resolve it.
                if allow_no_flat and _resolve_generic(doc, name, div[name], report,
                                                      stripped_by_asset):
                    continue
                report["skipped"].append(name)
                report.setdefault("skip_reasons", {})[name] = "not on flat asset"
                continue
            canonical = flat_cols[name]
            if FLAT_SPECIFIC.search(canonical):
                scrubbed = grain_neutral(canonical)
                if scrubbed and not FLAT_SPECIFIC.search(scrubbed):
                    canonical = scrubbed
                    report.setdefault("scrubbed", []).append(name)
                else:
                    report["skipped"].append(name)
                    report.setdefault("skip_reasons", {})[name] = "flat text wholly grain-specific"
                    continue
            _apply_canonical(doc, name, canonical, report, stripped_by_asset)
    elif allow_no_flat:
        # 2b) JUDGMENT cohort: no flat canonical. Auto-resolve only the safe, mechanical
        # classes — grain-neutral H3 columns and clean supersets (one variant is a superset
        # of the others). Genuine data-column divergences are left for --overrides.
        for name, per in sorted(div.items()):
            if not _resolve_generic(doc, name, per, report, stripped_by_asset):
                report["skipped"].append(name)
                report.setdefault("skip_reasons", {})[name] = "genuine divergence (needs override)"
    else:
        report["status"] = "judgment"
        report["reason"] = "no flat GeoParquet asset"
        report["skipped"] = sorted(div)
        return report

    _ensure_hex_notes(doc, stripped_by_asset, report)
    remaining = divergent_columns(doc)
    report["remaining"] = sorted(remaining)
    if remaining:
        report["status"] = "partial"
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sources", nargs="*", help="collection STAC URL(s) or file path(s)")
    p.add_argument("--bucket", help="bucket (with --dataset) to derive the collection URL")
    p.add_argument("--dataset", default="")
    p.add_argument("--out", default="/tmp/recon", help="output dir for reconciled JSON")
    p.add_argument("--no-flat", action="store_true",
                   help="also reconcile collections with no flat GeoParquet asset (JUDGMENT "
                        "cohort): grain-neutral H3 columns + clean supersets auto; genuine "
                        "data-column divergences need --overrides")
    p.add_argument("--overrides", help="JSON file of hand-authored canonical text: "
                                       "{collection_id: {columns: {col: text}, "
                                       "asset_notes: {asset_key: note}}}")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    srcs = list(args.sources)
    if args.bucket:
        seg = f"/{args.dataset}" if args.dataset else ""
        srcs.append(f"{NRP}/{args.bucket}{seg}/stac-collection.json")
    if not srcs:
        p.error("provide a collection URL/file or --bucket [--dataset]")

    overrides = json.loads(Path(args.overrides).read_text()) if args.overrides else None
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    reports = []
    for src in srcs:
        doc = load(src)
        rep = reconcile(doc, verbose=args.verbose, allow_no_flat=args.no_flat,
                        overrides=overrides)
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
        if rep.get("scrubbed"):
            print(f"  (grain-specific clause scrubbed from: {', '.join(rep['scrubbed'])})")
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
