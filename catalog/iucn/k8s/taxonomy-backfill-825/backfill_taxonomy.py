#!/usr/bin/env python3
"""Fill the empty assessment fields of the IUCN taxonomy table from the Red List v4 API (#825).

The May 2026 build enriched each taxon from the IUCN tabular export, which held no bird
assessments and missed 6,657 other taxa: those rows have `assessment_date IS NULL` and every
assessment column empty. This script fills exactly those rows, in the table's existing
column formats, without adding or removing columns or rows.

  fetch  : for every row with assessment_date IS NULL, GET /taxa/sis/{id}, choose the
           assessment (below), GET /assessment/{id}. Responses are cached one JSON file per
           taxon under CACHE_DIR (narrative text, references and credits stripped), so a
           restart never refetches. The job syncs CACHE_DIR to S3.
  build  : map each cached assessment to the table's columns and write OUT_PARQUET: the
           published table with those rows' empty columns filled (COALESCE: a value already
           present is never replaced). Row order, column order and types are unchanged.

Which assessment (choose()): the global (scope code 1) assessment whose year_published and
category match the row's latest_year_published / latest_category_code, so the filled fields
describe the same assessment as the status already published; else the latest global one;
for taxa with no global assessment, the regional one matching the row (REGIONAL=skip leaves
those rows empty). The mapping reproduces 50 already-filled rows column for column, except
year_last_seen (not in the v4 API, left NULL) and the two Yes/No flags (BOOL_FLAGS, below).

  python3 backfill_taxonomy.py fetch|build|all
Env: IUCN_API_KEY (never logged), SRC_PARQUET (local copy of the published table),
     OUT_PARQUET, CACHE_DIR, IUCN_REQUEST_DELAY, SYNC_CMD (shell command run every SYNC_EVERY
     fetched taxa, e.g. an rclone copy of CACHE_DIR), ONLY_IDS (comma list, for testing),
     REGIONAL (fill|skip), BOOL_FLAGS (null|api).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

API_BASE = os.environ.get("IUCN_API_BASE", "https://api.iucnredlist.org/api/v4")
API_KEY = os.environ.get("IUCN_API_KEY", "")
DELAY = float(os.environ.get("IUCN_REQUEST_DELAY", "0.5"))
MAX_RETRIES = int(os.environ.get("IUCN_MAX_RETRIES", "8"))
SRC = os.environ.get("SRC_PARQUET", "/work/src/iucn-taxonomy.parquet")  # local copy
OUT = os.environ.get("OUT_PARQUET", "/work/iucn-taxonomy.parquet")
CACHE = Path(os.environ.get("CACHE_DIR", "/work/api-cache"))
SYNC_CMD = os.environ.get("SYNC_CMD", "")
SYNC_EVERY = int(os.environ.get("SYNC_EVERY", "500"))
BOOL_FLAGS = os.environ.get("BOOL_FLAGS", "null")  # null | api; see map_record
REGIONAL = os.environ.get("REGIONAL", "fill")      # fill | skip; see choose()

# Columns this script may fill. Everything else in the table is passed through untouched.
FILL = [
    "common_names_en", "synonyms", "redlist_criteria", "criteria_version", "population_trend",
    "systems", "realm", "assessment_date", "possibly_extinct", "possibly_extinct_in_wild",
    "year_last_seen", "eoo_km2", "aoo_km2", "elevation_lower_m", "elevation_upper_m",
    "depth_lower_m", "depth_upper_m", "population_size", "generation_length",
    "locations_number", "severe_fragmentation", "area_restricted", "threat_codes",
    "habitat_codes", "country_codes", "use_trade_codes", "conservation_action_codes",
    "research_needed_codes", "plant_growth_forms", "common_name_en",
]
LIST_COLS = {"common_names_en", "synonyms", "threat_codes", "habitat_codes", "country_codes",
             "use_trade_codes", "conservation_action_codes", "research_needed_codes",
             "plant_growth_forms"}
BOOL_COLS = {"possibly_extinct", "possibly_extinct_in_wild", "severe_fragmentation",
             "area_restricted"}
STRIP = ("documentation", "references", "credits", "citation", "errata", "stresses")


# ---------------------------------------------------------------- API
def get(path: str):
    import requests
    if not API_KEY:
        raise RuntimeError("IUCN_API_KEY is empty")
    wait = 2.0
    err = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(f"{API_BASE}{path}", timeout=60,
                             headers={"Authorization": API_KEY, "Accept": "application/json"})
            if r.status_code == 404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                ra = r.headers.get("Retry-After")
                s = float(ra) if ra and ra.isdigit() else wait
                print(f"  {r.status_code} on {path}; sleeping {s:.0f}s", file=sys.stderr, flush=True)
                time.sleep(s)
                wait = min(wait * 2, 300)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:  # network errors
            err = e
            print(f"  attempt {attempt + 1} on {path}: {e}", file=sys.stderr, flush=True)
            time.sleep(wait)
            wait = min(wait * 2, 300)
    raise RuntimeError(f"giving up on {path}: {err}")


def is_global(a: dict) -> bool:
    return any(str(s.get("code")) == "1" for s in a.get("scopes") or [])


def choose(assessments: list[dict], year: str | None, cat: str | None, aid: int | None):
    """Return (assessment_id, how). how: id | match | latest | none.

    Only global assessments (scope code 1) count. A row's latest_assessment_id can point at a
    regional assessment (Gulo gulo: 2025 European assessment), and the existing filled rows
    were built from the global one, so the id is used only when it is global.
    """
    glob = [a for a in assessments if is_global(a)]
    if aid and any(a.get("assessment_id") == aid for a in glob):
        return aid, "id"
    m = [a for a in glob if str(a.get("year_published")) == str(year)
         and (cat is None or a.get("red_list_category_code") == cat)]
    if m:
        m.sort(key=lambda a: (bool(a.get("latest")), a.get("assessment_date") or ""), reverse=True)
        return m[0]["assessment_id"], "match"
    lat = [a for a in glob if a.get("latest")]
    if lat:
        return lat[0]["assessment_id"], "latest"
    # No global assessment at all: the taxon is assessed only regionally (e.g. the European
    # Red Lists of bees, bryophytes and plants), and the row's published category is that
    # regional one. Take the regional assessment that matches it, so the filled fields describe
    # the assessment the row already reports. build() drops these when REGIONAL=skip.
    m = [a for a in assessments if str(a.get("year_published")) == str(year)
         and (cat is None or a.get("red_list_category_code") == cat)]
    if m:
        m.sort(key=lambda a: (bool(a.get("latest")), a.get("assessment_date") or ""), reverse=True)
        return m[0]["assessment_id"], "regional-match"
    return None, "none"


def targets():
    import duckdb
    q = (f"SELECT sis_taxon_id, latest_year_published, latest_category_code, latest_assessment_id "
         f"FROM read_parquet('{SRC}') WHERE assessment_date IS NULL ORDER BY sis_taxon_id")
    return duckdb.connect().execute(q).fetchall()


def fetch() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    rows = targets()
    only = {int(x) for x in os.environ.get("ONLY_IDS", "").split(",") if x}
    if only:
        rows = [r for r in rows if r[0] in only]
    todo = [r for r in rows if not (CACHE / f"{r[0]}.json").exists()]
    print(f"{len(rows)} target taxa, {len(rows) - len(todo)} cached, {len(todo)} to fetch", flush=True)
    for i, (sis, year, cat, aid) in enumerate(todo, 1):
        taxa = get(f"/taxa/sis/{sis}")
        time.sleep(DELAY)
        rec: dict = {"sis_taxon_id": sis, "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if taxa is None:
            rec["status"] = "taxon-404"
        else:
            rec["taxon"] = taxa.get("taxon")
            rec["assessments"] = taxa.get("assessments")
            chosen, how = choose(taxa.get("assessments") or [], year, cat, aid)
            rec["choice"] = how
            if chosen:
                a = get(f"/assessment/{chosen}")
                time.sleep(DELAY)
                if a is None:
                    rec["status"] = "assessment-404"
                else:
                    for k in STRIP:
                        a.pop(k, None)
                    a.pop("taxon", None)  # same as rec["taxon"]
                    (a.get("supplementary_info") or {}).pop("conservation_actions_in_place", None)
                    for k in ("conservation_actions", "researches", "habitats", "threats",
                              "use_and_trade", "locations"):
                        for x in a.get(k) or []:
                            x.pop("note", None)
                            x.pop("text", None)
                    rec["assessment"] = a
                    rec["status"] = "ok"
            else:
                rec["status"] = "no-global-assessment"
        tmp = CACHE / f".{sis}.json.tmp"
        tmp.write_text(json.dumps(rec))
        tmp.rename(CACHE / f"{sis}.json")
        if i % 100 == 0:
            print(f"  {i}/{len(todo)} fetched", flush=True)
        if SYNC_CMD and i % SYNC_EVERY == 0:
            subprocess.run(SYNC_CMD, shell=True, check=False)
    if SYNC_CMD:
        subprocess.run(SYNC_CMD, shell=True, check=False)


# ---------------------------------------------------------------- mapping
def _code(c) -> str:
    return str(c).replace("_", ".")


def _codes(items) -> list[str] | None:
    out: list[str] = []
    for x in items or []:
        c = x.get("code")
        if c is not None and _code(c) not in out:
            out.append(_code(c))
    return out or None


def _num(v) -> str | None:
    """Numbers as the export wrote them: integers without a decimal point."""
    if v is None or v == "":
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _yesno(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return True if s in ("yes", "true") else False if s in ("no", "false") else None


def _en(x) -> str | None:
    return ((x or {}).get("description") or {}).get("en")


SYS_ORDER = ["Terrestrial", "Freshwater (=Inland waters)", "Marine"]


def map_record(rec: dict) -> dict:
    """One cache record -> {column: value} in the table's formats (None = leave empty)."""
    out: dict = {c: None for c in FILL}
    tx = rec.get("taxon") or {}
    eng = [c for c in tx.get("common_names") or [] if c.get("language") == "eng"]
    names = []
    for c in eng:
        if c.get("name") and c["name"] not in names:
            names.append(c["name"])
    out["common_names_en"] = names or None
    main = [c["name"] for c in eng if c.get("main") and c.get("name")]
    out["common_name_en"] = main[0] if main else (names[0] if names else None)
    syn = []
    for s in tx.get("synonyms") or []:
        if s.get("name") and s["name"] not in syn:
            syn.append(s["name"])
    out["synonyms"] = syn or None

    a = rec.get("assessment")
    if not a:
        return out
    si = a.get("supplementary_info") or {}
    out["redlist_criteria"] = a.get("criteria") or None
    out["criteria_version"] = (a.get("red_list_category") or {}).get("version") or None
    out["population_trend"] = _en(a.get("population_trend"))
    sysn = [_en(s) for s in a.get("systems") or [] if _en(s)]
    sysn = [s for s in SYS_ORDER if s in sysn] + [s for s in sysn if s not in SYS_ORDER]
    out["systems"] = "|".join(dict.fromkeys(sysn)) or None
    realms = [_en(r) for r in a.get("biogeographical_realms") or [] if _en(r)]
    out["realm"] = "|".join(dict.fromkeys(realms)) or None
    d = a.get("assessment_date")
    out["assessment_date"] = f"{d[:10]} 00:00:00 UTC" if d else None
    out["possibly_extinct"] = a.get("possibly_extinct")
    out["possibly_extinct_in_wild"] = a.get("possibly_extinct_in_the_wild")
    # year_last_seen: not exposed by the v4 API; stays NULL for API-filled rows.
    out["eoo_km2"] = _num(si.get("estimated_extent_of_occurence"))
    out["aoo_km2"] = _num(si.get("estimated_area_of_occupancy"))
    out["elevation_lower_m"] = _num(si.get("lower_elevation_limit"))
    out["elevation_upper_m"] = _num(si.get("upper_elevation_limit"))
    out["depth_lower_m"] = _num(si.get("lower_depth_limit"))
    out["depth_upper_m"] = _num(si.get("upper_depth_limit"))
    out["population_size"] = _num(si.get("population_size"))
    out["generation_length"] = _num(si.get("generational_length"))
    out["locations_number"] = _num(si.get("number_of_locations"))
    # The published table never holds TRUE in these two columns: its build turned every
    # non-null export value, 'Yes' included, into FALSE (#825). Filling them faithfully would
    # make the API-filled rows the only TRUE rows in the table, so by default they stay NULL.
    # BOOL_FLAGS=api writes the API's answer (Yes -> TRUE, No -> FALSE, Unknown -> NULL).
    if BOOL_FLAGS == "api":
        out["severe_fragmentation"] = _yesno(si.get("population_severely_fragmented"))
        out["area_restricted"] = _yesno(si.get("area_restricted_is_restricted"))
    out["threat_codes"] = _codes(a.get("threats"))
    out["habitat_codes"] = _codes(a.get("habitats"))
    cc: list[str] = []
    for loc in a.get("locations") or []:
        c = loc.get("code")
        if (loc.get("presence") in ("Extant", "Probably Extant") and c and "-" not in c
                and c not in cc):
            cc.append(c)
    out["country_codes"] = cc or None
    out["use_trade_codes"] = _codes(a.get("use_and_trade"))
    out["conservation_action_codes"] = _codes(a.get("conservation_actions"))
    out["research_needed_codes"] = _codes(a.get("researches"))
    gf = [_en(g) for g in a.get("growth_forms") or [] if _en(g)]
    out["plant_growth_forms"] = list(dict.fromkeys(gf)) or None
    return out


# ---------------------------------------------------------------- build
def build() -> None:
    import duckdb
    import pyarrow as pa
    import pyarrow.parquet as pq

    recs = [json.loads(p.read_text()) for p in sorted(CACHE.glob("*.json"))]
    want = {r[0] for r in targets()}
    recs = [r for r in recs if r["sis_taxon_id"] in want]
    report: dict = {"target_rows": len(want), "cached": len(recs), "by_status_choice": {},
                    "regional": REGIONAL, "bool_flags": BOOL_FLAGS}
    rows = []
    for r in recs:
        k = f"{r.get('status')}/{r.get('choice')}"
        report["by_status_choice"][k] = report["by_status_choice"].get(k, 0) + 1
        if REGIONAL == "skip" and r.get("choice") == "regional-match":
            continue
        m = map_record(r)
        m["sis_taxon_id"] = r["sis_taxon_id"]
        rows.append(m)
    # Does the chosen assessment carry the row's published category and year?
    row = {t[0]: t for t in targets()}
    agree = {"same_category_and_year": 0, "same_category_only": 0, "different_category": 0}
    for r in recs:
        a = r.get("assessment")
        if not a:
            continue
        _, year, cat, _ = row[r["sis_taxon_id"]]
        acat = (a.get("red_list_category") or {}).get("code")
        if acat == cat and str(a.get("year_published")) == str(year):
            agree["same_category_and_year"] += 1
        elif acat == cat:
            agree["same_category_only"] += 1
        else:
            agree["different_category"] += 1
    report["chosen_vs_row"] = agree
    try:
        report["red_list_version"] = get("/information/red_list_version")["red_list_version"]
    except Exception as e:  # no key / API down: leave it for the publish step to refuse
        print(f"  red_list_version unavailable: {e}", file=sys.stderr)
        report["red_list_version"] = None
    fetched = sorted(r["fetched"] for r in recs if r.get("fetched"))
    report["fetched_first"], report["fetched_last"] = (fetched[0], fetched[-1]) if fetched else (None, None)
    missing = want - {r["sis_taxon_id"] for r in recs}
    report["not_cached"] = len(missing)
    print(json.dumps(report, indent=1), flush=True)

    schema = pa.schema(
        [("sis_taxon_id", pa.int64())]
        + [(c, pa.list_(pa.string()) if c in LIST_COLS else pa.bool_() if c in BOOL_COLS
            else pa.string()) for c in FILL])
    fill = pa.Table.from_pylist(rows, schema=schema)

    con = duckdb.connect()
    con.register("fill_tbl", fill)
    con.execute(f"CREATE TABLE src AS SELECT *, row_number() OVER () AS _rn FROM read_parquet('{SRC}')").fetchall()
    cols = [r[0] for r in con.execute("DESCRIBE src").fetchall() if r[0] != "_rn"]
    sel = [f'CASE WHEN s.assessment_date IS NULL THEN COALESCE(s."{c}", f."{c}") ELSE s."{c}" END AS "{c}"'
           if c in FILL else f's."{c}"' for c in cols]
    con.execute(f"CREATE TABLE out AS SELECT {', '.join(sel)} FROM src s "
                f"LEFT JOIN fill_tbl f ON s.sis_taxon_id = f.sis_taxon_id ORDER BY s._rn").fetchall()
    n_src = con.execute("SELECT count(*) FROM src").fetchone()[0]
    n_out = con.execute("SELECT count(*) FROM out").fetchone()[0]
    assert n_src == n_out, (n_src, n_out)
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY (SELECT * FROM out) TO '{OUT}' (FORMAT parquet, COMPRESSION zstd)").fetchall()
    # Same column names and types as the published file, in the same order.
    sig = lambda sch: [(f.name, str(f.type)) for f in sch]
    assert sig(pq.read_schema(OUT)) == sig(pq.read_schema(SRC)), (pq.read_schema(OUT), pq.read_schema(SRC))
    report["rows"] = n_out
    report["filled_rows"] = con.execute(
        "SELECT count(*) FROM out o JOIN (SELECT sis_taxon_id FROM src WHERE assessment_date IS NULL) "
        "USING (sis_taxon_id) WHERE o.assessment_date IS NOT NULL").fetchone()[0]
    Path(OUT).with_suffix(".report.json").write_text(json.dumps(report, indent=1))
    print(f"wrote {OUT}: {n_out} rows; {report['filled_rows']} of {len(want)} target rows "
          f"now carry an assessment_date", flush=True)


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    if step in ("fetch", "all"):
        fetch()
    if step in ("build", "all"):
        build()
