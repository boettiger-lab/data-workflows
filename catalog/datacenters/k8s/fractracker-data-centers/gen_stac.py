#!/usr/bin/env python3
"""STAC collections and READMEs for the FracTracker data center layers (#931).

  gen_stac.py check DC_CSV MO_CSV [--min-dc N] [--min-mo N]
  gen_stac.py build OUT_DIR [--layers dc,mo] [--merge-live]

`check` vets a freshly downloaded snapshot before anything is rebuilt: the column headers must be
the ones the collections document, every coded value must be one this file describes, every
facility must have coordinates, and the row counts must not fall below --min-dc / --min-mo (a
truncated export). It exits non-zero on anything new, so the weekly sync stops and the last good
version stays published.

`build` writes OUT_DIR/fractracker/{data-centers,moratoriums}/{stac-collection.json,README.md}.
Every count, range, extent and coded-value list is measured from the published GeoParquet and hex
at build time; the provenance (access time, staged snapshot paths, sizes and sha256) is read from
raw/fractracker/CURRENT and raw/fractracker/moratoriums/CURRENT and their snapshot manifests,
written by the sync's stage step (catalog/datacenters/k8s/fractracker-sync/). Queries run in DuckDB
against s3:// when AWS_ACCESS_KEY_ID is set (in a cluster job), otherwise through the MCP query
server (MCP_ENDPOINT; set VERIFY_STAC to scripts/verify-stac.py). --merge-live keeps the live
collection's `created` and its style and thumbnail assets.

Styles and thumbnails are drawn by scripts/default-style.py and scripts/thumbnail.py;
scripts/stac-publish-guard.py keeps them on later republishes.
"""
import argparse
import csv
import importlib.util
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BUCKET = "public-datacenters"
PUB = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
S3 = f"s3://{BUCKET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
PARENT = f"{PUB}/stac-collection.json"
LANDING = "https://www.fractracker.org/data-centers/"
TERMS = "https://www.fractracker.org/terms-of-service/"
DC_SHEET = "https://docs.google.com/spreadsheets/d/1JJ6kcVo-NjlAYtznwHOki2DVl4WWV6lhy-eXhFCdKKU"
DICT_SHEET = "https://docs.google.com/spreadsheets/d/1KVab4niu8X_GGne3WyyH_CdTP9Bt4uJSe6iK0fu9C48"
MOR_SHEET = "https://docs.google.com/spreadsheets/d/1OLJ-EkkxLfX6l4dTBHsIdtn_zRSyOraS02vd3LMfbEI"
# Before the first sync, the 2026-11-15 staging sat at fixed paths with no CURRENT file; the sync's
# stage step archives it to raw/fractracker/snapshots/ and writes CURRENT on its first change.
INITIAL = {
    "dc": {"accessed": "2026-11-15T22:57:10Z", "snapshot": "raw/fractracker"},
    "mo": {"accessed": "2026-11-15T23:25:24Z", "snapshot": "raw/fractracker/moratoriums"},
}
FT_FILES = {  # FracTracker's own files in a snapshot (the rest are Census files or our derived files)
    "dc": ("data-centers.csv", "data-centers-workbook.xlsx", "data-dictionary.xlsx"),
    "mo": ("moratoriums.csv", "moratoriums-workbook.xlsx"),
}
EXT = [
    "https://stac-extensions.github.io/table/v1.2.0/schema.json",
    "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
]
PROVIDERS = [
    {"name": "FracTracker Alliance", "roles": ["producer", "licensor"], "url": LANDING},
    {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor"],
     "url": "https://github.com/boettiger-lab/data-workflows"},
    {"name": "National Research Platform", "roles": ["host"], "url": "https://nationalresearchplatform.org"},
]
H8_NOTE = ("H3 cell ID at resolution 8 (about 0.74 square kilometres on average), the catalog's common join "
           "resolution.")
H0_NOTE = "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."
TILE_TYPE = {"string": "String", "boolean": "Boolean", "date": "String"}
GROUNDED = ("FracTracker compiles the list from news reports and government records, so it is not an "
            "exhaustive record of local action: for scale, Grounded Compute's moratorium tracker "
            "(https://groundedcompute.com/us/moratoriums) counted at least 799 local pauses in force and 71 bans "
            "on 31 October 2026.")

# ---------------------------------------------------------------- coded values
# (value, meaning). A value differing from one of these only in capitalisation is accepted and
# described as such; anything else stops the build until it is added here.
DC_CODES = {
    "status": [("Proposed", None), ("Pre-proposal", None), ("Approved/Permitted/Under construction", None),
               ("Operating", None), ("Expanding", None), ("Suspended", None), ("Cancelled", None)],
    "location_confidence": [("High", "high confidence"), ("Medium", "medium confidence"),
                            ("Low", "low confidence")],
    "sizerank": [("Small (0-10 MW)", None), ("Medium (11-50 MW)", None), ("Large (51-99 MW)", None),
                 ("Hyperscale (100-999 MW)", None), ("Mega campus (>1,000 MW)", None), ("Unknown", None)],
    "cooling_source": [("Air", "air cooled"), ("Water", "water cooled"), ("Hybrid air/water", "both")],
    "cooling_type": [("Closed loop", None), ("Open loop", None), ("Fans", None)],
    "community_pushback": [("Yes", "opposition reported"), ("Unknown", "none reported")],
    "resistance_status": [("Unknown", None), ("Emerging Concern", None), ("Organized Advocacy", None),
                          ("Institutional Support", None)],
}
# information_source joins sources with ", "; each part must be one of these.
INFO_SOURCES = [
    ("Media Monitoring", "FracTracker's scans of media announcements"),
    ("PEC", "Piedmont Environmental Council"),
    ("Sci4GA", "Science for Georgia"),
    ("Crowdsourced", "listings submitted to FracTracker"),
    ("FOIA/ public records request", "public records requests"),
    ("Other", "other sources"),
    ("PEC/WP", None),  # meaning not documented upstream
]
SOURCE_STATES = {"PEC": "Virginia", "Sci4GA": "Georgia"}
STATE_ABBR = {"Virginia": "VA", "Georgia": "GA"}
MO_CODES = {
    "action": [("Moratorium", "a temporary pause on data center approvals"),
               ("Zoning restriction", "zoning rules limiting where or how data centers are built"),
               ("Ban", "a prohibition"),
               ("Curative Amendment", "a Pennsylvania procedure for challenging a zoning ordinance"),
               ("Other", "other actions")],
    "status": [("Enacted", None), ("active", None), ("Proposed", None), ("pending", None),
               ("In development", None), ("Adopted; not yet effective", None), ("expired", None),
               ("Failed", None), ("Retracted", None)],
}
GEO_LEVELS = [("place", None), ("county", None), ("county_subdivision", None), ("state", None), ("aiannh", None)]
DC_STATUS_TEXT = {"proposed": "proposed", "pre-proposal": "pre-proposal",
                  "approved/permitted/under construction": "approved, permitted or under construction",
                  "operating": "operating", "expanding": "expanding", "suspended": "suspended",
                  "cancelled": "cancelled"}
MO_ACTION_TEXT = {"moratorium": "moratoriums", "zoning restriction": "zoning restrictions", "ban": "bans",
                  "curative amendment": "Pennsylvania curative amendments", "other": "other actions"}
MO_STATUS_TEXT = {"enacted": "enacted", "active": "active", "proposed": "proposed", "pending": "pending",
                  "in development": "in development", "adopted; not yet effective": "adopted but not yet effective",
                  "expired": "expired", "failed": "failed", "retracted": "retracted"}
GEO_TEXT = {"state": ("state", "states"), "county": ("county", "counties"),
            "place": ("incorporated place", "incorporated places"),
            "county_subdivision": ("county subdivision", "county subdivisions (townships and New England, New York "
                                   "and Wisconsin towns)"),
            "aiannh": ("American Indian area", "American Indian areas")}

DC_HEADER = ["facility_name", "address", "city", "state", "zip", "county", "lat", "long", "status",
             "location_confidence", "purpose", "operator_name", "tenant", "mw", "sizerank", "power_source",
             "dedicated_power_plant", "number_of_generators", "number_of_buildings", "cooling_source",
             "cooling_type", "facility_size_sqft", "property_size_acres", "project_cost", "expected_date_online",
             "community_pushback", "advocacy_information", "resistance_status", "nda", "community_group_website_1",
             "community_group_website_2", "petition_url", "other_info", "information_source",
             *[f"info_source_{n}" for n in range(1, 9)], "date_created", "date_updated"]
MO_HEADER = ["jurisdiction", "state", "action", "status", "date enacted", "duration", "expiration date",
             "source link 1", "source link 2", "source link 3", "notes"]


def plural(n, one, many=None):
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def classify(name, canon, counts):
    """Map each data value to its canonical value; stop on a value this file does not describe."""
    lc = {v.lower(): v for v, _ in canon}
    bad = sorted(v for v in counts if v.lower() not in lc)
    if bad:
        raise SystemExit(f"{name}: value(s) not described in gen_stac.py: {bad}. Add them, with their meaning, "
                         "before publishing.")
    return {v: lc[v.lower()] for v in counts}


def coded_text(name, canon, counts):
    """'Values: A=..., B=...' plus a note on capitalisation variants present in the data."""
    canon_of = classify(name, canon, counts)
    vals = ", ".join(f"{v}={m}" if m else v for v, m in canon)
    var = [f"'{v}' is {canon_of[v]} with different capitalisation ({plural(n, 'record')})"
           for v, n in sorted(counts.items()) if v != canon_of[v]]
    return f"Values: {vals}." + (" " + "; ".join(var) + "." if var else "")


def info_source_text(counts, outside):
    parts = {p for v in counts for p in v.split(", ")}
    known = dict(INFO_SOURCES)
    bad = sorted(parts - set(known))
    if bad:
        raise SystemExit(f"information_source: part(s) not described in gen_stac.py: {bad}")
    def meaning(v, m):
        st = SOURCE_STATES.get(v)
        return f"{m} (all such records are in {st})" if st and not outside.get(v) else m
    return ("Primary source of the record. Values: " + ", ".join(f"{v}={meaning(v, m)}" for v, m in INFO_SOURCES if m)
            + "; PEC/WP and the comma-joined values combine two sources.")


def ordered(counts):
    return [v for v, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def tally(counts, text, canon):
    """'779 proposed, 14 pre-proposal, ...' in canonical order, case variants folded together."""
    canon_of = classify("tally", canon, counts)
    folded = {}
    for v, n in counts.items():
        folded[canon_of[v].lower()] = folded.get(canon_of[v].lower(), 0) + n
    items = [f"{folded[v.lower()]:,} {text[v.lower()]}" for v, _ in canon if v.lower() in folded]
    return ", ".join(items[:-1]) + " and " + items[-1] if len(items) > 1 else items[0]


def snapdate(ts):
    d = datetime.strptime(ts[:10], "%Y-%m-%d")
    return f"{d.day} {d:%B %Y}"


# ---------------------------------------------------------------- check
def check(args):
    def rows(path, header):
        with open(path, encoding="utf-8") as f:
            r = csv.DictReader(f)
            if r.fieldnames != header:
                raise SystemExit(f"{path}: columns changed.\n  expected {header}\n  found    {r.fieldnames}")
            return list(r)

    def counts(rs, col):
        out = {}
        for r in rs:
            v = (r[col] or "").strip()
            if v:
                out[v] = out.get(v, 0) + 1
        return out

    dc = rows(args.dc_csv, DC_HEADER)
    for c, canon in DC_CODES.items():
        classify(c, canon, counts(dc, c))
    info_source_text(counts(dc, "information_source"), {})
    for i, r in enumerate(dc, 2):
        try:
            lat, lon = float(r["lat"]), float(r["long"])
        except ValueError:
            raise SystemExit(f"{args.dc_csv} line {i}: no coordinates ({r['facility_name']!r})")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise SystemExit(f"{args.dc_csv} line {i}: coordinates out of range ({lat}, {lon})")
    mo = rows(args.mo_csv, MO_HEADER)
    for c, canon in MO_CODES.items():
        classify(c, canon, counts(mo, c))
    for name, n, floor in (("data centers", len(dc), args.min_dc), ("moratoriums", len(mo), args.min_mo)):
        if n < floor:
            raise SystemExit(f"{name}: {n} rows, below the floor of {floor}; refusing a possibly truncated export")
    print(f"check OK: {len(dc)} data centers, {len(mo)} moratorium records")


# ---------------------------------------------------------------- build
class Query:
    def __init__(self):
        if os.environ.get("AWS_ACCESS_KEY_ID"):
            import duckdb
            self.c = duckdb.connect()
            self.c.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;")
            self.c.execute(f"""CREATE SECRET (TYPE s3, KEY_ID '{os.environ["AWS_ACCESS_KEY_ID"]}',
                SECRET '{os.environ["AWS_SECRET_ACCESS_KEY"]}', ENDPOINT '{os.environ["AWS_S3_ENDPOINT"]}',
                URL_STYLE 'path', USE_SSL false)""")
            self.mcp = None
        else:
            spec = importlib.util.spec_from_file_location("verify_stac", os.environ["VERIFY_STAC"])
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            self.mcp = m.MCPClient(m.DEFAULT_MCP)

    def __call__(self, sql):
        if self.mcp:
            return self.mcp.query(sql)
        cur = self.c.execute(sql)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    def one(self, sql):
        return self(sql)[0]

    def counts(self, table, col, where="TRUE"):
        rs = self(f"SELECT {col} AS v, count(*) AS n FROM {table} WHERE {col} IS NOT NULL AND {col} <> '' "
                  f"AND {where} GROUP BY 1")
        return {str(r["v"]): int(r["n"]) for r in rs}


def fetch(url):
    return urllib.request.urlopen(url, timeout=60).read().decode()


def listing(prefix):
    """{key: (size, last_modified)} for every object under prefix."""
    out, token = {}, None
    while True:
        url = f"{PUB}/?list-type=2&prefix={prefix}" + (f"&continuation-token={token}" if token else "")
        x = fetch(url)
        for k, lm, sz in re.findall(r"<Key>([^<]+)</Key><LastModified>([^<]+)</LastModified>.*?<Size>(\d+)</Size>", x):
            out[k] = (int(sz), lm[:19] + "Z")
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", x)
        if not m:
            return out
        token = urllib.parse.quote(m.group(1))


def provenance(layer, current_path):
    """(accessed, [(sha256, size, path)]) for FracTracker's files in the current snapshot."""
    try:
        cur = dict(l.split("=", 1) for l in fetch(f"{PUB}/{current_path}").split() if "=" in l)
    except urllib.error.HTTPError:
        cur = INITIAL[layer]
    files = []
    for line in fetch(f"{PUB}/{cur['snapshot']}/MANIFEST.sha256").splitlines():
        sha, size, name = line.split()
        if name in FT_FILES[layer]:
            files.append((sha, int(size), f"{cur['snapshot']}/{name}"))
    files.sort(key=lambda f: FT_FILES[layer].index(f[2].rsplit("/", 1)[1]))
    if [f[2].rsplit("/", 1)[1] for f in files] != list(FT_FILES[layer]):
        raise SystemExit(f"{layer}: snapshot manifest {cur['snapshot']} lacks some of {FT_FILES[layer]}")
    return cur["accessed"], files


def terms_text(citation):
    return (
        "Licence: no open licence. FracTracker Alliance retains all rights in the data compilation. Its terms of use "
        "(the README tab of the data centers workbook, and its Terms of Service at " + TERMS + ") provide the data "
        "as is, without warranty; require that any use be consistent with and supportive of FracTracker's mission, "
        "\"to map, analyze, and communicate the risks of oil, gas, and petrochemical development to advance just "
        "energy alternatives that protect public health, natural resources, and the climate\", with FracTracker "
        "deciding whether a use fits that mission; and require public-facing materials to cite the source as: "
        + citation + " (with the year the data were accessed). FracTracker publishes the sheets as open downloads "
        "with no login, and this copy is hosted on the same terms."
    )


def raw_text(accessed, raw, what):
    rows = "; ".join(f"`s3://{BUCKET}/{p}` ({n:,} bytes, sha256 `{s}`)" for s, n, p in raw)
    return (f"Provenance: FracTracker updates the sheet continuously and publishes no edition label, so this layer is "
            f"a snapshot. {what} was downloaded on {accessed[:10]} at {accessed[11:16]} UTC and staged unchanged: "
            f"{rows}. Earlier snapshots are kept under s3://{BUCKET}/raw/fractracker/snapshots/.")


def col(name, typ, desc, values=None):
    c = {"name": name, "type": typ, "description": desc}
    if values:
        c["values"] = values
    return c


def cols_of(dic, names):
    d = {c["name"]: c for c in dic}
    return [{"name": n, "type": d[n]["type"]} for n in names]


def tile_cols(dic, names):
    d = {c["name"]: c for c in dic}
    return [{"name": n, "type": TILE_TYPE.get(d[n]["type"], "Number")} for n in names if n != "geom"]


def links(path, pm, extra):
    return [
        {"rel": "self", "href": f"{PUB}/{path}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": ROOT, "type": "application/json"},
        {"rel": "parent", "href": PARENT, "type": "application/json"},
        {"rel": "license", "href": TERMS, "type": "text/html", "title": "FracTracker Alliance Terms of Service"},
        {"rel": "about", "href": LANDING, "type": "text/html", "title": "FracTracker Alliance: U.S. Data Centers Tracker"},
        *extra,
        {"rel": "pmtiles", "href": pm["href"], "type": "application/vnd.pmtiles", "title": pm["title"],
         "pmtiles:layers": pm["vector:layers"]},
    ]


def bbox(q, table):
    r = q.one(f"SELECT min(ST_XMin(geom)) a, min(ST_YMin(geom)) b, max(ST_XMax(geom)) c, max(ST_YMax(geom)) d "
              f"FROM {table} WHERE geom IS NOT NULL")
    return [round(float(r[k]), 6) for k in "abcd"]


def day(v):
    return str(v)[:10]


def collection(cid, title, desc, path, box, interval, dic, assets, keywords, pmkey, extra, citation):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "type": "Collection", "stac_version": "1.0.0", "stac_extensions": EXT, "id": cid,
        "title": title, "description": desc, "keywords": keywords, "license": "other",
        "providers": PROVIDERS, "sci:citation": citation, "created": now, "updated": now,
        "extent": {"spatial": {"bbox": [box]}, "temporal": {"interval": [interval]}},
        "table:columns": dic, "links": links(path, assets[pmkey], extra), "assets": assets,
    }


def merge_live(doc, path):
    try:
        live = json.loads(fetch(f"{PUB}/{path}/stac-collection.json"))
    except urllib.error.HTTPError:
        return doc
    doc["created"] = live.get("created", doc["created"])
    for k, a in live.get("assets", {}).items():
        if k not in doc["assets"] and set(a.get("roles", [])) & {"style", "thumbnail", "overview"}:
            doc["assets"][k] = a
    return doc


def build(args):
    out = Path(args.out)
    layers = set(args.layers.split(","))
    q = Query()
    objs = listing("fractracker/")

    def asset(path, typ, title, desc, **kw):
        if path not in objs:
            raise SystemExit(f"missing object {path}")
        a = {"href": f"{PUB}/{path}", "type": typ, "title": title, "description": desc,
             "roles": ["data"], "created": objs[path][1], "file:size": objs[path][0]}
        a.update(kw)
        return a

    def hexa(path, title, desc, cols):
        parts = [k for k in objs if k.startswith(path + "/hex/h0=")]
        if not parts:
            raise SystemExit(f"no hex under {path}")
        return {"href": f"{PUB}/{path}/hex/h0=*/data_0.parquet", "type": "application/x-parquet",
                "title": title, "description": desc, "roles": ["data"],
                "created": max(objs[k][1] for k in parts), "h3:native_resolution": 8,
                "h3:parent_resolutions": [0], "table:columns": cols}

    def emit(path, doc, text):
        if args.merge_live:
            doc = merge_live(doc, path)
        d = out / path
        d.mkdir(parents=True, exist_ok=True)
        (d / "stac-collection.json").write_text(json.dumps(doc, indent=2) + "\n")
        (d / "README.md").write_text(text)
        print("wrote", d)

    if "dc" in layers:
        build_dc(q, asset, hexa, emit)
    if "mo" in layers:
        build_mo(q, asset, hexa, emit)


def build_dc(q, asset, hexa, emit):
    p = "fractracker/data-centers"
    t = f"read_parquet('{S3}/{p}.parquet')"
    h = f"read_parquet('{S3}/{p}/hex/h0=*/data_0.parquet')"
    accessed, raw = provenance("dc", "raw/fractracker/CURRENT")
    citation = f"Data provided by FracTracker Alliance ({accessed[:4]}). Accessed via {LANDING}"
    s = q.one(f"""SELECT count(*) n, count(geom) g, count(DISTINCT state) states,
        count(*) FILTER (WHERE location_confidence IS NULL OR location_confidence = '') lc_blank,
        count(purpose) FILTER (WHERE purpose <> '') purpose, count(mw) FILTER (WHERE mw <> '') mw,
        count(power_source) FILTER (WHERE power_source <> '') power,
        min(date_created) d0, max(date_created) d1, min(property_size_acres) a0, max(property_size_acres) a1
        FROM {t}""")
    n = int(s["n"])
    if int(s["g"]) != n:
        raise SystemExit(f"data centers: {n - int(s['g'])} facilities have no point")
    hx = q.one(f"SELECT count(*) n, count(DISTINCT h8) cells FROM {h}")
    if int(hx["n"]) != n:
        raise SystemExit(f"data centers hex has {hx['n']} rows for {n} facilities")
    cc = {c: q.counts(t, c) for c in DC_CODES}
    info = q.counts(t, "information_source")
    outside = {src: int(q.one(f"SELECT count(*) n FROM {t} WHERE information_source LIKE '%{src}%' "
                              f"AND state <> '{STATE_ABBR[st]}'")["n"]) for src, st in SOURCE_STATES.items()}
    states = int(s["states"])
    lc = classify("location_confidence", DC_CODES["location_confidence"], cc["location_confidence"])
    lcn = {}
    for v, k in cc["location_confidence"].items():
        lcn[lc[v]] = lcn.get(lc[v], 0) + k

    def cd(name, intro, tail=""):
        return col(name, "string", f"{intro} {coded_text(name, DC_CODES[name], cc[name])}{tail}", ordered(cc[name]))

    def src(i):
        return col(f"info_source_{i}", "string", f"Documentation link {i} of up to 8 (news coverage, permits, "
                   "public records) supporting the record, as entered by FracTracker.")

    lc_blank = int(s["lc_blank"])
    cols = [
        col("_cng_fid", "int64", "Row identifier added during conversion; one per facility record. Use "
            "COUNT(DISTINCT _cng_fid) to count facilities."),
        col("facility_name", "string", "Name of the data center project: the most commonly referenced public name, "
            "or the company or location when the project is unnamed. Names are not unique."),
        col("address", "string", "Street address of the facility. May be blank or approximate, such as an intersection."),
        col("city", "string", "City or municipality."),
        col("state", "string", f"U.S. state, as its two-letter postal abbreviation ({states} states)."),
        col("zip", "string", "ZIP, free text as entered by FracTracker."),
        col("county", "string", "County name, as entered by FracTracker (spelling is not standardised)."),
        col("lat", "double", "Latitude in decimal degrees, as entered by FracTracker; the point geometry is built "
            "from lat and long. Its accuracy is given by location_confidence."),
        col("long", "double", "Longitude in decimal degrees, as entered by FracTracker."),
        cd("status", "Project development stage."),
        cd("location_confidence", "Confidence in the accuracy of the point location.",
           f" Blank for {plural(lc_blank, 'record')}." if lc_blank else ""),
        col("purpose", "string", "Function of the facility, such as AI, cloud or colocation, as free text (filled for "
            f"{int(s['purpose']):,} of {n:,} facilities)."),
        col("operator_name", "string", "Developer or operator, with names standardised by FracTracker (for example "
            "'Amazon' rather than 'AWS')."),
        col("tenant", "string", "Known tenant or tenants. Blank when unknown or when the operator is the user."),
        col("mw", "string", "Power capacity in megawatts, stored as text as entered by FracTracker (filled for "
            f"{int(s['mw']):,} facilities). Estimates come from news reports, permits and comparable facilities; "
            "1,000 MW = 1 GW. Cast before arithmetic: TRY_CAST(mw AS DOUBLE)."),
        cd("sizerank", "Size class by power capacity."),
        col("power_source", "string", "Energy source, from FracTracker's categories (Natural gas, Coal, Nuclear, "
            "Oil/Diesel, Hydroelectric, Wind, Solar, Geothermal, Biomass, Grid (unspecified mix), Hybrid (onsite and "
            f"grid)); several may be listed, comma-separated. Blank when unknown (filled for {int(s['power']):,} "
            "facilities)."),
        col("dedicated_power_plant", "string", "On-site or behind-the-meter power generation: Yes or No, often with "
            "the plant's name (for example 'Yes - Apollo Generating Station'). Free text."),
        col("number_of_generators", "string", "Number of backup generators, as text. Blank when unclear."),
        col("number_of_buildings", "string", "Number of structures, as text."),
        cd("cooling_source", "Cooling source.", " Blank when unknown."),
        cd("cooling_type", "Cooling system.", " Blank when unknown."),
        col("facility_size_sqft", "string", "Building footprint in square feet, summed over buildings where possible; "
            "text as entered."),
        col("property_size_acres", "int64", f"Total land area of the property in acres ({int(s['a0']):,} to "
            f"{int(s['a1']):,})."),
        col("project_cost", "string", "Estimated project cost, free text as reported (for example '$1B')."),
        col("expected_date_online", "string", "Expected operation date, usually a year, as text."),
        cd("community_pushback", "Whether community opposition to the project is known."),
        col("advocacy_information", "string", "Short factual description of community organising around the project."),
        cd("resistance_status", "Level of resistance."),
        col("nda", "string", "Whether a nondisclosure agreement or limited transparency is reported: free text, "
            "often Yes or No with detail."),
        col("community_group_website_1", "string", "Website of a community group involved."),
        col("community_group_website_2", "string", "Website of a second community group involved."),
        col("petition_url", "string", "Link to a petition about the project."),
        col("other_info", "string", "Additional notes, including uncertainty in other fields."),
        col("information_source", "string", info_source_text(info, outside), ordered(info)),
        *[src(i) for i in range(1, 9)],
        col("date_created", "date", f"Date FracTracker created the record ({day(s['d0'])} to {day(s['d1'])})."),
        col("date_updated", "date", "Date FracTracker last updated the record."),
        col("geom", "geometry", "Facility point (WGS84 longitude/latitude), built from long and lat."),
        col("h8", "uint64", H8_NOTE),
        col("h0", "int64", H0_NOTE),
    ]
    flat = [c["name"] for c in cols if c["name"] not in ("h8", "h0")]
    assets = {
        "data-centers-parquet": asset(f"{p}.parquet", "application/vnd.apache.parquet",
            "Data centers (GeoParquet)", f"One point per facility ({n:,} facilities).",
            **{"table:columns": cols_of(cols, flat)}),
        "data-centers-pmtiles": asset(f"{p}.pmtiles", "application/vnd.pmtiles",
            "Data centers (PMTiles)", "Vector tiles of the facility points for web maps; layer data-centers.",
            **{"vector:layers": ["data-centers"], "table:columns": tile_cols(cols, flat)}),
        "data-centers-hex": hexa(p, "Data centers (H3 hex)",
            "Each facility point resolved to one H3 cell at resolution 8 (about 0.74 square kilometres), with its "
            f"resolution 0 parent as the partition key. One row per facility: {n:,} facilities fall in "
            f"{int(hx['cells']):,} distinct cells, and facilities sharing a cell are not merged. Each facility appears "
            "exactly once, so COUNT(DISTINCT _cng_fid) counts facilities and per-facility values are not repeated.",
            cols_of(cols, [c for c in flat if c != "geom"] + ["h8", "h0"])),
    }
    lc_text = ", ".join(f"{k} ({lcn[k]:,})" for k, _ in DC_CODES["location_confidence"] if k in lcn)
    lc_text = re.sub(r", ([^,]+)$", r" or \1", lc_text)
    desc = (
        f"A snapshot of FracTracker's sheet taken {snapdate(accessed)}. FracTracker updates the sheet continuously, "
        "so records and statuses may have changed since.\n\n"
        f"FracTracker Alliance's U.S. Data Centers Tracker: {n:,} existing, permitted and proposed data centers "
        f"in {states} states, with each facility's development status, operator and tenant, power capacity and size "
        "class, power and cooling sources, and the community response to the project (pushback, organising, "
        "nondisclosure agreements, petitions). FracTracker finds sites mainly by monitoring media announcements, "
        "supplemented by public records, permits, parcel data, Freedom of Information Act requests and "
        "crowdsourced listings. Its focus is proposals, the sites relevant for advocacy; existing data centers "
        "are being added gradually, so the operating facilities here are not a complete inventory. Status on the "
        f"snapshot date: {tally(cc['status'], DC_STATUS_TEXT, DC_CODES['status'])}.\n\n"
        f"Every facility has a point location; location_confidence rates it {lc_text}. Field definitions follow "
        "FracTracker's data dictionary (" + DICT_SHEET + "). Values are as entered upstream: several numeric fields "
        "(mw, facility_size_sqft, number_of_buildings, number_of_generators, expected_date_online) are text, and a "
        "few coded values differ only in case. The H3 hex asset places each facility in one resolution 8 cell.\n\n"
        "Companion layer: data center moratoriums, bans and zoning restrictions from the same tracker are in "
        "the collection fractracker-moratoriums.\n\n"
        + terms_text(citation) + "\n\n"
        + raw_text(accessed, raw, "The \"FracTracker Data Centers\" tab of the public sheet (" + DC_SHEET
                   + "), with the whole workbook (including its README tab) and the data dictionary,")
    )
    doc = collection("fractracker-data-centers", f"FracTracker U.S. data centers ({n:,} facilities)", desc, p,
                     bbox(q, t), [f"{day(s['d0'])}T00:00:00Z", f"{accessed[:10]}T00:00:00Z"], cols, assets,
                     ["data centers", "energy", "infrastructure", "community advocacy", "United States",
                      "FracTracker Alliance"], "data-centers-pmtiles",
                     [{"rel": "via", "href": DC_SHEET, "type": "text/html",
                       "title": "FracTracker data centers sheet (source, with README and terms)"},
                      {"rel": "describedby", "href": DICT_SHEET, "type": "text/html",
                       "title": "FracTracker data centers data dictionary"}], citation)
    emit(p, doc, readme(p, "FracTracker U.S. data centers", "data-centers", "circle",
                        f"{n:,} existing, permitted and proposed U.S. data centers, one point per facility, "
                        "with status, operator, power, cooling and community response.",
                        "SELECT status, count(*) AS n, sum(TRY_CAST(mw AS DOUBLE)) AS mw\n"
                        f"FROM read_parquet('{PUB}/{p}.parquet')\nGROUP BY status ORDER BY n DESC;",
                        raw_text(accessed, raw, "The data centers tab"), citation))


def build_mo(q, asset, hexa, emit):
    p = "fractracker/moratoriums"
    t = f"read_parquet('{S3}/{p}.parquet')"
    h = f"read_parquet('{S3}/{p}/hex/h0=*/data_0.parquet')"
    accessed, raw = provenance("mo", "raw/fractracker/moratoriums/CURRENT")
    citation = f"Data provided by FracTracker Alliance ({accessed[:4]}). Accessed via {LANDING}"
    s = q.one(f"""SELECT count(*) n, count(geom) g, count(DISTINCT state) states,
        count(*) FILTER (WHERE date_enacted IS NULL) de_blank, min(date_enacted) de0, max(date_enacted) de1,
        count(expiration_date) ex, min(expiration_date) ex0, max(expiration_date) ex1 FROM {t}""")
    n, g = int(s["n"]), int(s["g"])
    nb = n - g
    hx = q.one(f"SELECT count(*) n, count(*) FILTER (WHERE geo_level = 'state') st FROM {h}")
    cc = {c: q.counts(t, c) for c in MO_CODES}
    geo = q.counts(t, "geo_level")
    classify("geo_level", GEO_LEVELS, geo)
    if sum(geo.values()) != g:
        raise SystemExit(f"moratoriums: {sum(geo.values())} matched records but {g} boundaries")
    tribal = [str(r["census_name"]).replace(" OTSA", " Oklahoma Tribal Statistical Area")
              for r in q(f"SELECT DISTINCT census_name FROM {t} WHERE geo_level = 'aiannh' ORDER BY 1")]
    um = q(f"SELECT state, jurisdiction, count(*) k FROM {t} WHERE geom IS NULL GROUP BY ALL ORDER BY state, jurisdiction")
    by_state = {}
    for r in um:
        k = int(r["k"])
        by_state.setdefault(r["state"], []).append(r["jurisdiction"] + (f" ({k} records)" if k > 1 else ""))
    unmatched = "; ".join(f"{st}: {', '.join(js)}" for st, js in by_state.items())
    states = int(s["states"])
    hex_rows, state_rows = int(hx["n"]), int(hx["st"])
    nstate = geo.get("state", 0)

    def cd(name, intro, tail=""):
        return col(name, "string", f"{intro} {coded_text(name, MO_CODES[name], cc[name])}{tail}", ordered(cc[name]))

    blank = f"Blank for the {plural(nb, 'record')} with no boundary." if nb else ""
    cols = [
        col("_cng_fid", "int64", "Row identifier added during conversion; one per record. Use COUNT(DISTINCT _cng_fid) "
            "to count records."),
        col("jurisdiction", "string", "Jurisdiction that took the action, as named by FracTracker (for example "
            "'Anchorage', 'Loudoun County', 'Caledonia Township', 'State of Oregon')."),
        col("state", "string", f"U.S. state, as its two-letter postal abbreviation ({states} states)."),
        cd("action", "Type of local action."),
        cd("status", "Status of the action as entered by FracTracker, not standardised.",
           " Match case-insensitively: lower(status) = 'expired'."),
        col("date_enacted", "date", f"Date the action was enacted or introduced ({day(s['de0'])} to {day(s['de1'])}; "
            f"blank for {plural(int(s['de_blank']), 'record')})."),
        col("duration", "string", "Length of a moratorium as stated, free text (for example '1 year', '180 days', "
            "'Through December 31, 2026')."),
        col("expiration_date", "date", f"Date the action expires ({day(s['ex0'])} to {day(s['ex1'])}; filled for "
            f"{plural(int(s['ex']), 'record')})."),
        col("source_link_1", "string", "Link to a source documenting the action."),
        col("source_link_2", "string", "Link to a second source."),
        col("source_link_3", "string", "Link to a third source."),
        col("notes", "string", "FracTracker's notes on the action."),
        col("geo_level", "string", "Kind of Census 2024 geography the jurisdiction was matched to: state, county, "
            "place (an incorporated city, town, village or borough), county_subdivision (a township or New England, "
            "New York or Wisconsin town), or aiannh (an American Indian area). " + blank, ordered(geo)),
        col("geoid", "string", "Census 2024 GEOID of the matched geography (state 2 digits, county 5, place 7, "
            "county subdivision 10), or the 4-digit AIANNH code for an American Indian area. Joins to the "
            "census-2024 collections on GEOID."),
        col("census_name", "string", "Census 2024 name of the matched geography (for example 'Caledonia charter "
            "township')."),
        col("geom", "geometry", "Boundary of the matched jurisdiction from Census TIGER/Line 2024 (WGS84 "
            "longitude/latitude)" + (f"; null for the {plural(nb, 'record')} with no boundary." if nb else ".")),
        col("h8", "uint64", H8_NOTE),
        col("h0", "int64", H0_NOTE),
    ]
    flat = [c["name"] for c in cols if c["name"] not in ("h8", "h0")]
    most = (f" (the {plural(nstate, 'statewide record')} alone cover most of them)"
            if state_rows * 2 > hex_rows else "")
    assets = {
        "moratoriums-parquet": asset(f"{p}.parquet", "application/vnd.apache.parquet",
            "Moratoriums and local actions (GeoParquet)",
            f"One row per record ({n:,}), carrying its jurisdiction's boundary"
            + (f"; {plural(nb, 'record has', 'records have')} no boundary." if nb else "."),
            **{"table:columns": cols_of(cols, flat)}),
        "moratoriums-pmtiles": asset(f"{p}.pmtiles", "application/vnd.pmtiles",
            "Moratoriums and local actions (PMTiles)",
            "Vector tiles of the jurisdiction boundaries for web maps; layer moratoriums. Records without a "
            "boundary are not in the tiles.",
            **{"vector:layers": ["moratoriums"], "table:columns": tile_cols(cols, flat)}),
        "moratoriums-hex": hexa(p, "Moratoriums and local actions (H3 hex)",
            "Each jurisdiction boundary filled with H3 cells at resolution 8 (about 0.74 square kilometres), with "
            f"the resolution 0 parent as the partition key: one row per (record, cell) pair, {hex_rows:,} rows for the "
            f"{g:,} records with a boundary{most}. Every column is repeated on every cell a jurisdiction covers, so "
            "count records with COUNT(DISTINCT _cng_fid), not COUNT(*). Jurisdictions overlap (a state, its counties "
            "and its towns can all have records), so one cell can carry several records."
            + (f" The {plural(nb, 'record')} with no boundary have no hex cell and are absent from the hex." if nb else ""),
            cols_of(cols, [c for c in flat if c != "geom"] + ["h8", "h0"])),
    }
    geo_parts = []
    for lvl in ("state", "county", "place", "county_subdivision", "aiannh"):
        if lvl in geo:
            one, many = GEO_TEXT[lvl]
            txt = f"{geo[lvl]:,} {one if geo[lvl] == 1 else many}"
            if lvl == "aiannh":
                txt += " (" + ", ".join(tribal) + ")"
            geo_parts.append(txt)
    geo_text = ", ".join(geo_parts[:-1]) + " and " + geo_parts[-1] if len(geo_parts) > 1 else geo_parts[0]
    unmatched_text = (f"The {plural(nb, 'record')} that could not be matched to one geography keep every attribute "
                      f"and a null geometry: {unmatched}. " if nb else "")
    desc = (
        f"A snapshot of FracTracker's sheet taken {snapdate(accessed)}. FracTracker updates the sheet continuously, "
        "so records and statuses may have changed since.\n\n"
        f"FracTracker Alliance's list of local data center moratoriums, bans and zoning restrictions: {n:,} records "
        f"in {states} states ({tally(cc['action'], MO_ACTION_TEXT, MO_CODES['action'])}), each with its status, "
        "enactment and expiration dates, duration, sources and notes. "
        f"Status on the snapshot date: {tally(cc['status'], MO_STATUS_TEXT, MO_CODES['status'])}. FracTracker's "
        "sheet names each jurisdiction but carries no geometry. " + GROUNDED + "\n\n"
        "Boundaries: each record was matched by name and state to a U.S. Census 2024 geography and takes that "
        f"geography's TIGER/Line 2024 boundary: {geo_text}. "
        "Townships that share a name within a state were told apart by the county named in the record's notes "
        "or sources. " + unmatched_text + "geo_level, geoid and census_name record the match, so a record can be "
        "checked or joined to the census-2024 collections. The boundary is the jurisdiction's whole area; an "
        "action can apply to only part of it (a zoning district, for instance), which the notes describe. "
        "Records overlap: one place can have several records, and a state, its counties and its towns can each "
        "have their own. The H3 hex asset fills each boundary at resolution 8.\n\n"
        "Companion layer: the data centers themselves are in the collection fractracker-data-centers.\n\n"
        + terms_text(citation) + " The moratorium workbook carries no terms of its own; FracTracker's Terms of "
        "Service and the terms published with its Data Centers Tracker are applied to it here.\n\n"
        + raw_text(accessed, raw, "The \"Live Data\" tab of the public sheet (" + MOR_SHEET + ") and the "
                   "whole workbook")
        + " The Census 2024 Gazetteer and TIGER/Line files used for matching are staged in "
        "raw/fractracker/moratoriums/, listed with checksums in its MANIFEST.sha256."
    )
    doc = collection("fractracker-moratoriums",
                     f"FracTracker data center moratoriums and local actions ({n:,} records in {states} states)",
                     desc, p, bbox(q, t), [f"{day(s['de0'])}T00:00:00Z", f"{accessed[:10]}T00:00:00Z"], cols, assets,
                     ["data centers", "moratoriums", "zoning", "local government", "community advocacy",
                      "United States", "FracTracker Alliance"], "moratoriums-pmtiles",
                     [{"rel": "via", "href": MOR_SHEET, "type": "text/html",
                       "title": "FracTracker data center moratoriums sheet (source)"},
                      {"rel": "related", "href": "https://www2.census.gov/geo/tiger/TIGER2024/", "type": "text/html",
                       "title": "U.S. Census TIGER/Line 2024 (source of boundaries)"}], citation)
    emit(p, doc, readme(p, "FracTracker data center moratoriums and local actions", "moratoriums", "fill",
                        f"{n:,} local data center moratoriums, bans and zoning restrictions, each drawn as its "
                        "jurisdiction's Census 2024 boundary"
                        + (f" ({plural(nb, 'record has', 'records have')} none)." if nb else "."),
                        "SELECT state, action, count(*) AS n\n"
                        f"FROM read_parquet('{PUB}/{p}.parquet')\n"
                        "WHERE lower(status) IN ('enacted', 'active')\nGROUP BY ALL ORDER BY n DESC;",
                        raw_text(accessed, raw, "The Live Data tab"), citation))


def readme(p, title, layer, kind, summary, sql, prov, citation):
    paint = ("'circle-radius': 4, 'circle-color': '#C2410C'" if kind == "circle"
             else "'fill-color': '#C2410C', 'fill-opacity': 0.4")
    return f"""# {title}

{summary}

STAC: {PUB}/{p}/stac-collection.json

| File | Contents |
|---|---|
| `{p}.parquet` | GeoParquet |
| `{p}.pmtiles` | Vector tiles, layer `{layer}` |
| `{p}/hex/h0=*/data_0.parquet` | H3 resolution 8, partitioned by `h0` |

## DuckDB

```sql
INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;
{sql}
```

## MapLibre

```js
map.addSource('{layer}', {{ type: 'vector', url: 'pmtiles://{PUB}/{p}.pmtiles' }});
map.addLayer({{
  id: '{layer}', type: '{kind}', source: '{layer}',
  'source-layer': '{layer}',
  paint: {{ {paint} }}
}});
```

## Licence and citation

{terms_text(citation)}

Cite as: {citation}

{prov}
"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("dc_csv")
    c.add_argument("mo_csv")
    c.add_argument("--min-dc", type=int, default=0)
    c.add_argument("--min-mo", type=int, default=0)
    b = sub.add_parser("build")
    b.add_argument("out")
    b.add_argument("--layers", default="dc,mo")
    b.add_argument("--merge-live", action="store_true")
    a = ap.parse_args()
    check(a) if a.cmd == "check" else build(a)
