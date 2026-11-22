#!/usr/bin/env python3
"""Build a table of IUCN Red List threats with scope, severity and timing (#1017).

`iucn-taxonomy-2025` keeps only `threat_codes`. STAR's split of a species' score among its
threats (Mair et al. 2021, Supplementary Table 2) needs each threat's scope, severity and
timing, so this script reads them from the Red List API v4 for the taxa STAR scores: those
with a range polygon (`in_holdings`), category NT, VU, EN or CR, and at least one threat code.

  fetch : for each target, GET /taxa/sis/{id}, choose the assessment with
          backfill_taxonomy.choose() (the global assessment matching the row's published
          category and year, else the latest global one, else the matching regional one),
          GET /assessment/{id}, and cache only the threats and the assessment's identity,
          one JSON file per taxon in CACHE_DIR. A record already in the #825 cache
          (PRIOR_CACHE_DIR) for the same taxon is reused instead of fetched.
  build : one row per taxon and threat, written to OUT_PARQUET with a .report.json.

  python3 fetch_threats.py fetch|build|all
Env: IUCN_API_KEY (never logged), SRC_PARQUET (local copy of the published taxonomy table),
     OUT_PARQUET, CACHE_DIR, PRIOR_CACHE_DIR, IUCN_REQUEST_DELAY, SYNC_CMD, SYNC_EVERY,
     ONLY_IDS (comma list, for testing). backfill_taxonomy.py must sit beside this file.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backfill_taxonomy as bt  # noqa: E402  get(), choose(), _code(); reads the same env

SRC = os.environ.get("SRC_PARQUET", "/work/src/iucn-taxonomy.parquet")
OUT = os.environ.get("OUT_PARQUET", "/work/out/iucn-threats.parquet")
CACHE = Path(os.environ.get("CACHE_DIR", "/work/api-cache"))
PRIOR = Path(os.environ.get("PRIOR_CACHE_DIR", "/work/prior-cache"))
DELAY = float(os.environ.get("IUCN_REQUEST_DELAY", "0.3"))
SYNC_CMD = os.environ.get("SYNC_CMD", "")
SYNC_EVERY = int(os.environ.get("SYNC_EVERY", "500"))
KEEP = ("code", "timing", "scope", "severity", "score", "ias", "virus", "ancestry",
        "internationalTrade", "description")


def targets():
    import duckdb
    q = ("SELECT sis_taxon_id, latest_year_published, latest_category_code, latest_assessment_id "
         f"FROM read_parquet('{SRC}') WHERE in_holdings "
         "AND latest_category_code IN ('NT', 'VU', 'EN', 'CR') AND len(threat_codes) > 0 "
         "ORDER BY sis_taxon_id")
    return duckdb.connect().execute(q).fetchall()


def slim(sis: int, fetched: str, choice: str | None, a: dict | None, status: str) -> dict:
    rec = {"sis_taxon_id": sis, "fetched": fetched, "choice": choice, "status": status}
    if a:
        rec["assessment_id"] = a.get("assessment_id")
        rec["year_published"] = a.get("year_published")
        rec["category"] = (a.get("red_list_category") or {}).get("code")
        rec["threats"] = [{k: t.get(k) for k in KEEP} for t in a.get("threats") or []]
    return rec


def write(rec: dict) -> None:
    tmp = CACHE / f".{rec['sis_taxon_id']}.json.tmp"
    tmp.write_text(json.dumps(rec))
    tmp.rename(CACHE / f"{rec['sis_taxon_id']}.json")


def fetch() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    rows = targets()
    only = {int(x) for x in os.environ.get("ONLY_IDS", "").split(",") if x}
    if only:
        rows = [r for r in rows if r[0] in only]
    todo = [r for r in rows if not (CACHE / f"{r[0]}.json").exists()]
    reused = 0
    for r in list(todo):  # the #825 cache already holds the chosen assessment for these taxa
        p = PRIOR / f"{r[0]}.json"
        if p.exists():
            old = json.loads(p.read_text())
            if old.get("status") == "ok" and old.get("assessment"):
                write(slim(r[0], old.get("fetched"), old.get("choice"), old["assessment"], "ok"))
                todo.remove(r)
                reused += 1
    print(f"{len(rows)} target taxa, {reused} reused from the #825 cache, "
          f"{len(rows) - len(todo) - reused} already cached, {len(todo)} to fetch", flush=True)
    for i, (sis, year, cat, aid) in enumerate(todo, 1):
        fetched = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        taxa = bt.get(f"/taxa/sis/{sis}")
        time.sleep(DELAY)
        if taxa is None:
            rec = slim(sis, fetched, None, None, "taxon-404")
        else:
            chosen, how = bt.choose(taxa.get("assessments") or [], year, cat, aid)
            if not chosen:
                rec = slim(sis, fetched, how, None, "no-assessment")
            else:
                a = bt.get(f"/assessment/{chosen}")
                time.sleep(DELAY)
                rec = slim(sis, fetched, how, a, "ok" if a else "assessment-404")
        write(rec)
        if i % 100 == 0:
            print(f"  {i}/{len(todo)} fetched", flush=True)
        if SYNC_CMD and i % SYNC_EVERY == 0:
            subprocess.run(SYNC_CMD, shell=True, check=False)
    if SYNC_CMD:
        subprocess.run(SYNC_CMD, shell=True, check=False)


def _text(v):
    if isinstance(v, dict):
        return v.get("en")
    return None if v is None else str(v)


def build() -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    want = {r[0] for r in targets()}
    recs = [json.loads(p.read_text()) for p in sorted(CACHE.glob("*.json"))]
    recs = [r for r in recs if r["sis_taxon_id"] in want]
    report: dict = {"target_taxa": len(want), "cached": len(recs), "by_status_choice": {}}
    rows = []
    no_threats = 0
    for r in recs:
        k = f"{r.get('status')}/{r.get('choice')}"
        report["by_status_choice"][k] = report["by_status_choice"].get(k, 0) + 1
        ts = r.get("threats") or []
        if r.get("status") == "ok" and not ts:
            no_threats += 1
        for t in ts:
            rows.append({
                "sis_taxon_id": r["sis_taxon_id"],
                "assessment_id": r.get("assessment_id"),
                "year_published": None if r.get("year_published") is None else str(r["year_published"]),
                "threat_code": bt._code(t.get("code")) if t.get("code") is not None else None,
                "threat_name": _text(t.get("description")),
                "timing": t.get("timing"),
                "scope": t.get("scope"),
                "severity": t.get("severity"),
                "score": t.get("score"),
                "invasive_species": _text(t.get("ias")),
                "virus": _text(t.get("virus")),
            })
    report["taxa_without_threats"] = no_threats
    report["taxa_with_threats"] = len({x["sis_taxon_id"] for x in rows})
    report["rows"] = len(rows)
    report["not_cached"] = len(want - {r["sis_taxon_id"] for r in recs})
    fetched = sorted(r["fetched"] for r in recs if r.get("fetched"))
    report["fetched_first"], report["fetched_last"] = (fetched[0], fetched[-1]) if fetched else (None, None)
    for col in ("timing", "scope", "severity"):
        vals: dict = {}
        for x in rows:
            vals[str(x[col])] = vals.get(str(x[col]), 0) + 1
        report[f"{col}_values"] = dict(sorted(vals.items(), key=lambda kv: -kv[1]))
    try:
        report["red_list_version"] = bt.get("/information/red_list_version")["red_list_version"]
    except Exception as e:
        print(f"  red_list_version unavailable: {e}", file=sys.stderr)
        report["red_list_version"] = None
    print(json.dumps(report, indent=1), flush=True)

    schema = pa.schema([("sis_taxon_id", pa.int64()), ("assessment_id", pa.int64()),
                        ("year_published", pa.string()), ("threat_code", pa.string()),
                        ("threat_name", pa.string()), ("timing", pa.string()),
                        ("scope", pa.string()), ("severity", pa.string()),
                        ("score", pa.string()), ("invasive_species", pa.string()),
                        ("virus", pa.string())])
    rows.sort(key=lambda x: (x["sis_taxon_id"], x["threat_code"] or ""))
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), OUT, compression="zstd")
    Path(OUT).with_suffix(".report.json").write_text(json.dumps(report, indent=1))
    print(f"wrote {OUT}: {len(rows)} rows for {report['taxa_with_threats']} taxa", flush=True)


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    if step in ("fetch", "all"):
        fetch()
    if step in ("build", "all"):
        build()
