#!/usr/bin/env python3
"""Re-read severe_fragmentation and area_restricted from the Red List API v4 (#1013).

The May 2026 build of the IUCN taxonomy table wrote FALSE for every recorded value of these two
Yes/No flags, 'Yes' included, and the #825 backfill left them NULL on the rows it filled. This
script rewrites both columns for exactly those rows and changes nothing else.

Targets: rows with a non-null severe_fragmentation or area_restricted (export values), plus the
rows #825 filled (assessment_date IS NULL in PRE825_PARQUET, the table as it was before #825).

  fetch : the taxa with sis_taxon_id % NSHARDS == SHARD. A row's latest_assessment_id is read
          directly when that assessment is global; otherwise GET /taxa/sis/{id} and pick the
          assessment with backfill_taxonomy.choose(), as #825 did. One JSON per taxon in
          CACHE_DIR (narrative text stripped), synced to S3 and kept there after publishing.
  build : write OUT_PARQUET: the published table with both flags of every target row replaced
          by the API's answer (Yes -> TRUE, No -> FALSE, anything else -> NULL). Rows, row
          order, other columns and types are unchanged. A .report.json goes beside it.

  python3 fix_flags.py fetch|build
Env: IUCN_API_KEY (never logged), SRC_PARQUET, PRE825_PARQUET, OUT_PARQUET, CACHE_DIR,
     SHARD / NSHARDS (fetch; SHARD defaults to JOB_COMPLETION_INDEX), VERSION_FILE (written
     by fetch shard 0, read by build), IUCN_REQUEST_DELAY,
     SYNC_CMD, SYNC_EVERY, ONLY_IDS (comma list, for testing).
backfill_taxonomy.py (#825) must sit beside this file.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backfill_taxonomy as bt  # noqa: E402  get(), choose(), is_global(), _yesno(), STRIP

SRC = os.environ.get("SRC_PARQUET", "/work/src/iucn-taxonomy.parquet")
PRE825 = os.environ.get("PRE825_PARQUET", "/work/src/previous-iucn-taxonomy.parquet")
OUT = os.environ.get("OUT_PARQUET", "/work/out/iucn-taxonomy.parquet")
CACHE = Path(os.environ.get("CACHE_DIR", "/work/api-cache"))
DELAY = float(os.environ.get("IUCN_REQUEST_DELAY", "0.3"))
SYNC_CMD = os.environ.get("SYNC_CMD", "")
SYNC_EVERY = int(os.environ.get("SYNC_EVERY", "500"))
NSHARDS = int(os.environ.get("NSHARDS", "1"))
SHARD = int(os.environ.get("SHARD", os.environ.get("JOB_COMPLETION_INDEX", "0")))
VERSION_FILE = Path(os.environ.get("VERSION_FILE", "/work/out/red_list_version.txt"))
FLAGS = {"severe_fragmentation": "population_severely_fragmented",
         "area_restricted": "area_restricted_is_restricted"}


def targets():
    """[(sis, year, cat, aid, origin)] with origin 'export' or 'api825'."""
    import duckdb
    q = f"""
      WITH pre AS (SELECT sis_taxon_id FROM read_parquet('{PRE825}') WHERE assessment_date IS NULL)
      SELECT s.sis_taxon_id, s.latest_year_published, s.latest_category_code,
             s.latest_assessment_id,
             CASE WHEN p.sis_taxon_id IS NOT NULL THEN 'api825' ELSE 'export' END AS origin
      FROM read_parquet('{SRC}') s LEFT JOIN pre p USING (sis_taxon_id)
      WHERE p.sis_taxon_id IS NOT NULL
         OR s.severe_fragmentation IS NOT NULL OR s.area_restricted IS NOT NULL
      ORDER BY s.sis_taxon_id"""
    return duckdb.connect().execute(q).fetchall()


def strip(a: dict) -> dict:
    for k in bt.STRIP:
        a.pop(k, None)
    a.pop("taxon", None)
    (a.get("supplementary_info") or {}).pop("conservation_actions_in_place", None)
    for k in ("conservation_actions", "researches", "habitats", "threats", "use_and_trade",
              "locations"):
        for x in a.get(k) or []:
            x.pop("note", None)
            x.pop("text", None)
    return a


def fetch_one(sis, year, cat, aid) -> dict:
    rec: dict = {"sis_taxon_id": sis, "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if aid:  # one call instead of two when the row's own assessment is global
        a = bt.get(f"/assessment/{aid}")
        time.sleep(DELAY)
        if a is not None and bt.is_global(a):
            rec.update(choice="id", status="ok", assessment=strip(a))
            return rec
    taxa = bt.get(f"/taxa/sis/{sis}")
    time.sleep(DELAY)
    if taxa is None:
        rec["status"] = "taxon-404"
        return rec
    rec["assessments"] = taxa.get("assessments")
    chosen, how = bt.choose(taxa.get("assessments") or [], year, cat, aid)
    rec["choice"] = how
    if not chosen:
        rec["status"] = "no-assessment"
        return rec
    a = bt.get(f"/assessment/{chosen}")
    time.sleep(DELAY)
    if a is None:
        rec["status"] = "assessment-404"
    else:
        rec.update(status="ok", assessment=strip(a))
    return rec


def fetch() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    if SHARD == 0:  # build runs without the API key, so the version is recorded here
        VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        VERSION_FILE.write_text(bt.get("/information/red_list_version")["red_list_version"] + "\n")
    rows = [r for r in targets() if r[0] % NSHARDS == SHARD]
    only = {int(x) for x in os.environ.get("ONLY_IDS", "").split(",") if x}
    if only:
        rows = [r for r in rows if r[0] in only]
    todo = [r for r in rows if not (CACHE / f"{r[0]}.json").exists()]
    print(f"shard {SHARD}/{NSHARDS}: {len(rows)} target taxa, {len(rows) - len(todo)} cached, "
          f"{len(todo)} to fetch", flush=True)
    for i, (sis, year, cat, aid, _) in enumerate(todo, 1):
        rec = fetch_one(sis, year, cat, aid)
        tmp = CACHE / f".{sis}.json.tmp"
        tmp.write_text(json.dumps(rec))
        tmp.rename(CACHE / f"{sis}.json")
        if i % 500 == 0:
            print(f"  {i}/{len(todo)} fetched", flush=True)
        if SYNC_CMD and i % SYNC_EVERY == 0:
            subprocess.run(SYNC_CMD, shell=True, check=False)
    if SYNC_CMD:
        subprocess.run(SYNC_CMD, shell=True, check=False)


def yesno(v):
    """Yes -> TRUE, No -> FALSE, else NULL. The API also returns 'Y' / 'N' for some assessments
    (89 taxa give 'N' for severe fragmentation, #1013); numeric ranges such as '0.5-1' stay NULL."""
    if isinstance(v, str) and v.strip().upper() in ("Y", "N"):
        return v.strip().upper() == "Y"
    return bt._yesno(v)


def build() -> None:
    import duckdb
    import pyarrow as pa
    import pyarrow.parquet as pq

    tg = {r[0]: r for r in targets()}
    rows, missing = [], []
    report: dict = {"target_rows": len(tg),
                    "by_origin": {}, "by_status_choice": {}, "chosen_vs_row": {},
                    "api_values": {c: {} for c in FLAGS}, "export_vs_api": {}}
    fetched = []
    for sis, (_, year, cat, _aid, origin) in tg.items():
        report["by_origin"][origin] = report["by_origin"].get(origin, 0) + 1
        p = CACHE / f"{sis}.json"
        if not p.exists():
            missing.append(sis)
            continue
        r = json.loads(p.read_text())
        fetched.append(r["fetched"])
        k = f"{r.get('status')}/{r.get('choice')}"
        report["by_status_choice"][k] = report["by_status_choice"].get(k, 0) + 1
        a = r.get("assessment") or {}
        si = a.get("supplementary_info") or {}
        if a:
            acat = (a.get("red_list_category") or {}).get("code")
            agree = ("same_category_and_year" if acat == cat and str(a.get("year_published")) == str(year)
                     else "same_category_only" if acat == cat else "different_category")
            report["chosen_vs_row"][agree] = report["chosen_vs_row"].get(agree, 0) + 1
        row = {"sis_taxon_id": sis}
        for col, key in FLAGS.items():
            raw = si.get(key)
            report["api_values"][col][str(raw)] = report["api_values"][col].get(str(raw), 0) + 1
            row[col] = yesno(raw)
        rows.append(row)
    report["not_cached"] = len(missing)
    if missing:
        print(json.dumps(report, indent=1))
        raise SystemExit(f"{len(missing)} target taxa not cached, e.g. {missing[:5]}")
    fetched.sort()
    report["fetched_first"], report["fetched_last"] = fetched[0], fetched[-1]
    report["red_list_version"] = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else None

    fix = pa.Table.from_pylist(rows, schema=pa.schema(
        [("sis_taxon_id", pa.int64())] + [(c, pa.bool_()) for c in FLAGS]))
    con = duckdb.connect()
    con.register("fix_tbl", fix)
    con.execute(f"CREATE TABLE src AS SELECT *, row_number() OVER () AS _rn FROM read_parquet('{SRC}')").fetchall()
    cols = [r[0] for r in con.execute("DESCRIBE src").fetchall() if r[0] != "_rn"]
    sel = [f'CASE WHEN f.sis_taxon_id IS NOT NULL THEN f."{c}" ELSE s."{c}" END AS "{c}"'
           if c in FLAGS else f's."{c}"' for c in cols]
    con.execute(f"CREATE TABLE out AS SELECT {', '.join(sel)}, s._rn FROM src s "
                f"LEFT JOIN fix_tbl f USING (sis_taxon_id) ORDER BY s._rn").fetchall()
    n_src, n_out = (con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("src", "out"))
    assert n_src == n_out, (n_src, n_out)
    # Every column but the two flags is byte-for-byte the same, row for row.
    other = [f'"{c}"' for c in cols if c not in FLAGS]
    diff = con.execute(
        f"SELECT count(*) FROM src s JOIN out o USING (_rn) WHERE "
        f"row({', '.join('s.' + c for c in other)}) IS DISTINCT FROM "
        f"row({', '.join('o.' + c for c in other)})").fetchone()[0]
    assert diff == 0, f"{diff} rows changed outside the two flag columns"
    # Export rows: what the API says where the export had FALSE (the wiped values).
    for col in FLAGS:
        report["export_vs_api"][col] = dict(con.execute(f"""
            SELECT coalesce(o."{col}"::VARCHAR, 'NULL'), count(*) FROM src s JOIN out o USING (sis_taxon_id)
            WHERE s."{col}" IS NOT NULL GROUP BY 1 ORDER BY 1""").fetchall())
        report.setdefault("true_rows", {})[col] = con.execute(
            f'SELECT count(*) FROM out WHERE "{col}"').fetchone()[0]
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY (SELECT * EXCLUDE (_rn) FROM out ORDER BY _rn) TO '{OUT}' (FORMAT parquet, COMPRESSION zstd)").fetchall()
    sig = lambda sch: [(f.name, str(f.type)) for f in sch]
    assert sig(pq.read_schema(OUT)) == sig(pq.read_schema(SRC))
    report["rows"] = n_out
    Path(OUT).with_suffix(".report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1), flush=True)


if __name__ == "__main__":
    {"fetch": fetch, "build": build}[sys.argv[1]]()
