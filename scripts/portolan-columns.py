#!/usr/bin/env python3
"""Rewrite live STAC collections into the Portolan column shape and add `rel: pmtiles` links.

Portolan (PORTO-FMT-046/048, glen#441) wants ONE column dictionary on the
collection: every column of every data asset, each with name, type, description and coded
`values`. An asset keeps its own `table:columns` only where its schema differs from the
dictionary, with names and types only. An asset without a list is described by the
dictionary. PORTO-FMT-011 also wants each PMTiles file reachable through a collection-level
`rel: pmtiles` link; the PMTiles asset stays, because the deployed GLEN apps read it.

How the dictionary is built, per collection:
  * Columns are taken from the data assets in this order: flat parquet, hex parquet, PMTiles.
    The first time a column name appears fixes its position and its type, so parquet types
    win over the coarsened PMTiles ones (String/Number).
  * `description`, `values` and any other field come from the first asset that has them.
  * An asset whose (name, type) set equals the dictionary's loses its list; any other asset
    keeps `[{name, type}]` for exactly the columns it has. So an asset that types a column
    differently (`double` vs `number`, or a PMTiles `String`) keeps its own type: nothing
    is lost, and type spellings are not a conflict.

It reads live STAC and publishes nothing. For each collection it writes
<out>/<bucket>/<path>/stac-collection.json, plus <out>/report.md listing what changed and
every conflict that needs a human: a column described two different ways, or an asset whose
coded `values` differ from the dictionary's (usually two different tables in one collection).
A collection with a conflict is reported and NOT written, so it cannot be uploaded by
accident. With --merge-values, differing `values` lists are merged into one instead (#762);
use it only after checking that no code means two things, and say which codes belong to
which table in the description (--notes adds a sentence where the text does not). Gate the output with scripts/verify-stac.py before uploading.

Usage:
  scripts/portolan-columns.py --out /tmp/pc URL [URL ...]
  scripts/portolan-columns.py --out /tmp/pc --urls urls.txt
  scripts/portolan-columns.py --out /tmp/pc --crawl https://s3-west.nrp-nautilus.io/public-census/catalog.json
  scripts/portolan-columns.py ... --links-only        # only add the rel: pmtiles links
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PUBLIC = "https://s3-west.nrp-nautilus.io/"
PMTILES_TYPE = "application/vnd.pmtiles"


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def crawl(url: str, seen: set[str] | None = None) -> list[str]:
    """Every collection under a catalog or collection, following child links."""
    seen = set() if seen is None else seen
    if url in seen:
        return []
    seen.add(url)
    try:
        doc = fetch(url)
    except Exception as e:  # a dead child link should not end the crawl
        print(f"skip {url}: {e}", file=sys.stderr)
        return []
    found = [url] if doc.get("type") == "Collection" else []
    for link in doc.get("links", []):
        if link.get("rel") == "child":
            found += crawl(urllib.parse.urljoin(url, link["href"]), seen)
    return found


def is_parquet(a: dict) -> bool:
    return "parquet" in a.get("type", "")


def is_pmtiles(a: dict) -> bool:
    return "pmtiles" in a.get("type", "")


def is_hex(key: str, a: dict) -> bool:
    href = a.get("href", "")
    return "/hex/" in href or "/h0=*/" in href or key.endswith("-hex")


def data_assets(doc: dict) -> list[tuple[str, dict]]:
    """Assets carrying columns, ordered flat parquet, hex parquet, PMTiles."""
    rank = lambda kv: (0 if is_parquet(kv[1]) and not is_hex(*kv)
                       else 1 if is_parquet(kv[1]) else 2)
    return sorted(((k, a) for k, a in doc.get("assets", {}).items()
                   if (is_parquet(a) or is_pmtiles(a)) and a.get("table:columns")), key=rank)


def build_dictionary(doc: dict, merge_values: bool = False) -> tuple[list[dict], list[str], list[str]]:
    entries: dict[str, dict] = {}
    conflicts: list[str] = []
    merged: list[str] = []
    for key, asset in data_assets(doc):
        for col in asset["table:columns"]:
            name = col.get("name")
            if not name:
                continue
            if name not in entries:
                entries[name] = {"name": name}
                if col.get("type"):
                    entries[name]["type"] = col["type"]
            entry = entries[name]
            for field, value in col.items():
                if field in ("name", "type") or value in (None, "", []):
                    continue
                if field not in entry:
                    entry[field] = copy.deepcopy(value)
                elif field == "description" and entry[field] != value:
                    conflicts.append(f"column `{name}` is described differently on `{key}`")
            if "type" not in entry and col.get("type"):
                entry["type"] = col["type"]
            if col.get("values") and entry.get("values") and col["values"] != entry["values"]:
                if merge_values:  # one list of every code; a person has confirmed no code has two meanings (#762)
                    extra = [v for v in col["values"] if v not in entry["values"]]
                    if extra:
                        entry["values"] = entry["values"] + extra
                        merged.append(f"column `{name}`: added {extra} from `{key}`")
                else:
                    conflicts.append(f"column `{name}` has different coded values on `{key}`")
    ordered = []
    for e in entries.values():  # name, type, description first; the rest as found
        ordered.append({k: e[k] for k in ("name", "type", "description") if k in e}
                       | {k: v for k, v in e.items() if k not in ("name", "type", "description")})
    return ordered, sorted(set(conflicts)), merged


def migrate_columns(doc: dict, merge_values: bool = False,
                    notes_for: dict | None = None) -> tuple[dict, list[str], list[str]]:
    out = copy.deepcopy(doc)
    dictionary, conflicts, notes = build_dictionary(out, merge_values)
    for col in dictionary:  # what a person wrote for a merged column (--notes)
        extra = (notes_for or {}).get(col["name"])
        if isinstance(extra, dict):  # {"add_values": [...], "note": "..."}: codes no table declared
            add = [v for v in extra.get("add_values", []) if v not in col.get("values", [])]
            if add:
                col["values"] = col.get("values", []) + add
                notes.append(f"column `{col['name']}`: added {add} from the notes")
            extra = extra.get("note")
        if extra:
            base = col.get("description", "").rstrip()
            if base and not base.endswith((".", "!", "?")):
                base += "."
            col["description"] = (base + " " + extra).strip()
            notes.append(f"column `{col['name']}`: description extended")
    if not dictionary:
        return out, notes, conflicts
    dict_types = {c["name"]: c.get("type") for c in dictionary}
    for key, asset in data_assets(out):
        own = {c.get("name"): c.get("type") for c in asset["table:columns"] if c.get("name")}
        if own == dict_types:
            del asset["table:columns"]
            notes.append(f"`{key}`: list dropped (matches the dictionary)")
        else:
            asset["table:columns"] = [{k: v for k, v in (("name", c.get("name")),
                                                         ("type", c.get("type"))) if v}
                                      for c in asset["table:columns"] if c.get("name")]
            notes.append(f"`{key}`: keeps {len(own)} names and types")
    out["table:columns"] = dictionary
    return out, notes, conflicts


def add_pmtiles_links(doc: dict) -> list[str]:
    base = next((l.get("href") for l in doc.get("links", []) if l.get("rel") == "self"), "")
    have = {urllib.parse.urljoin(base, l.get("href", ""))
            for l in doc.get("links", []) if l.get("rel") == "pmtiles"}
    notes = []
    for key, asset in doc.get("assets", {}).items():
        if not is_pmtiles(asset) or urllib.parse.urljoin(base, asset.get("href", "")) in have:
            continue
        link = {"rel": "pmtiles", "href": asset["href"], "type": PMTILES_TYPE}
        if asset.get("title"):
            link["title"] = asset["title"]
        if asset.get("vector:layers"):
            link["pmtiles:layers"] = list(asset["vector:layers"])
        doc.setdefault("links", []).append(link)
        notes.append(f"`{key}`: rel pmtiles link added")
    return notes


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("urls", nargs="*")
    p.add_argument("--urls", dest="url_file", help="file with one collection URL per line")
    p.add_argument("--crawl", help="catalog or collection URL to walk for collections")
    p.add_argument("--out", required=True)
    p.add_argument("--links-only", action="store_true", help="add rel pmtiles links only")
    p.add_argument("--merge-values", action="store_true",
                   help="merge differing `values` lists into one, in order, instead of refusing. "
                        "Use only after a person has checked that no code means two things (#762).")
    p.add_argument("--notes", help="JSON {collection path: {column: sentence}} appended to the "
                                   "dictionary description of a merged column; a column may instead "
                                   "map to {\"add_values\": [...], \"note\": \"...\"} to declare "
                                   "codes a table carries without a values list")
    args = p.parse_args()

    urls = list(args.urls)
    if args.url_file:
        urls += [l.strip() for l in Path(args.url_file).read_text().splitlines() if l.strip()]
    if args.crawl:
        urls += crawl(args.crawl)
    out_dir = Path(args.out)
    notes_all = json.loads(Path(args.notes).read_text()) if args.notes else {}
    report = ["# Portolan column migration", ""]
    written = blocked = unchanged = 0
    before = after = 0
    for url in dict.fromkeys(urls):
        if not url.startswith(PUBLIC):
            print(f"skip {url}: not on {PUBLIC}", file=sys.stderr)
            continue
        try:
            doc = fetch(url)
        except Exception as e:
            report += [f"## {url}", f"- could not fetch: {e}", ""]
            blocked += 1
            continue
        if args.links_only:
            new, notes, conflicts = copy.deepcopy(doc), [], []
        elif doc.get("table:columns"):
            new, notes, conflicts = copy.deepcopy(doc), ["already has a column dictionary"], []
        else:
            new, notes, conflicts = migrate_columns(
                doc, args.merge_values, notes_all.get(url[len(PUBLIC):], {}))
        notes += add_pmtiles_links(new)
        rel = url[len(PUBLIC):]
        if conflicts:
            report += [f"## {rel}", "- **not written**, needs a decision:"]
            report += [f"  - {c}" for c in conflicts] + [""]
            blocked += 1
            continue
        if new == doc:
            unchanged += 1
            continue
        old_bytes = len(json.dumps(doc, indent=2))
        new_bytes = len(json.dumps(new, indent=2))
        before, after = before + old_bytes, after + new_bytes
        report += [f"## {rel}", f"- {old_bytes:,} → {new_bytes:,} bytes"]
        report += [f"- {n}" for n in notes] + [""]
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n")
        written += 1
    summary = (f"{written} written, {blocked} not written (conflict or fetch error), "
               f"{unchanged} unchanged; written collections {before:,} → {after:,} bytes")
    report[1:1] = [summary, ""]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text("\n".join(report) + "\n")
    print(summary)
    print(f"report: {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
