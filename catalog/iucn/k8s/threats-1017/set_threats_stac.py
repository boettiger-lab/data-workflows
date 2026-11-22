#!/usr/bin/env python3
"""Add the threats table to the live iucn-taxonomy-2025 collection and README, in place (#1017).

    set_threats_stac.py COLLECTION.json README.md REPORT.json

REPORT.json is the build report written beside the staged parquet by fetch_threats.py. Edits:

  collection: a `threats-parquet` asset with its own column list (names and types); the
              `taxonomy-parquet` asset gets its own list too, since the column dictionary now
              covers both tables (Portolan PORTO-FMT-046/048); the threats columns join the
              dictionary; one provenance paragraph in the description; `updated`.
  README:     a "Threats with scope, severity and timing" section before "Provenance & license".

Idempotent: rerunning rewrites the same asset, columns, paragraph and section.
"""
import datetime as dt
import json
import re
import sys

stac_path, readme_path, report_path = sys.argv[1:4]
doc = json.load(open(stac_path))
rep = json.load(open(report_path))
before = json.loads(json.dumps(doc))
assert rep["not_cached"] == 0, rep
rlv = rep["red_list_version"]
assert rlv, "report carries no red_list_version"
first, last = rep["fetched_first"][:10], rep["fetched_last"][:10]
dates = first if first == last else f"{first} to {last}"
n_target, n_taxa, n_rows = rep["target_taxa"], rep["taxa_with_threats"], rep["rows"]

HREF = "https://s3-west.nrp-nautilus.io/public-iucn/taxonomy/iucn-threats.parquet"
vals = lambda k: [v for v in rep[f"{k}_values"] if v != "None"]
THREAT_COLS = [
    ("assessment_id", "int64", "Red List assessment the threat comes from (threats table)."),
    ("year_published", "string", "Year the assessment was published (threats table)."),
    ("threat_code", "string", "IUCN Threats Classification Scheme code at the most detailed "
     "level the assessment records, e.g. '2.1.3' (threats table)."),
    ("threat_name", "string", "English name of the threat code (threats table)."),
    ("timing", "string", "Timing of the threat as the assessment records it (threats table)."),
    ("scope", "string", "Share of the population the threat affects (threats table). NULL "
     "where the assessment records none."),
    ("severity", "string", "Rate of decline the threat causes within its scope (threats "
     "table). NULL where the assessment records none."),
    ("score", "string", "IUCN impact score text, from timing, scope and severity, e.g. "
     "'Medium Impact: 6' (threats table)."),
    ("invasive_species", "string", "Named invasive species, for threats in class 8 (threats table)."),
    ("virus", "string", "Named virus, for threats in class 8 (threats table)."),
]
CODED = {"timing": vals("timing"), "scope": vals("scope"), "severity": vals("severity")}

cols = [c for c in doc["table:columns"] if c["name"] not in {n for n, _, _ in THREAT_COLS}]
tax_names = [(c["name"], c["type"]) for c in before["table:columns"]
             if c["name"] not in {n for n, _, _ in THREAT_COLS}]
for name, typ, desc in THREAT_COLS:
    col = {"name": name, "type": typ, "description": desc}
    if name in CODED:
        col["values"] = CODED[name]
    cols.append(col)
for c in cols:
    if c["name"] == "sis_taxon_id":
        c["description"] = re.sub(r" Unique key\.( In the threats table.*?\.)?",
                                  " Unique key of the taxonomy table; in the threats table it "
                                  "repeats once per threat.", c["description"])
doc["table:columns"] = cols

tax = doc["assets"]["taxonomy-parquet"]
if not tax.get("table:columns"):
    tax["table:columns"] = [{"name": n, "type": t} for n, t in tax_names]
doc["assets"]["threats-parquet"] = {
    "href": HREF,
    "type": "application/x-parquet",
    "title": "IUCN Red List threats with scope, severity and timing (one row per taxon and threat)",
    "roles": ["data"],
    "table:columns": [{"name": "sis_taxon_id", "type": "int64"}]
                     + [{"name": n, "type": t} for n, t, _ in THREAT_COLS],
    "table:row_count": n_rows,
}

MARK = "iucn-threats.parquet"
para = (
    f"A second table, {MARK}, lists the threats in the assessments of the {n_target:,} taxa "
    f"that STAR scores (a range polygon, category NT to CR and at least one threat code), with "
    f"each threat's timing, scope and severity, which the main table does not keep. They were "
    f"read from the IUCN Red List API v4 on {dates}, when it served Red List version {rlv}, "
    f"choosing for each taxon the global assessment that matches its published category and "
    f"year where one exists. {n_taxa:,} taxa have {n_rows:,} threats in all."
)
desc = doc["description"]
desc = re.sub(r"\n\nA second table, iucn-threats\.parquet,.*?(?=\n\n|$)", "", desc, flags=re.S)
doc["description"] = desc.rstrip() + "\n\n" + para
doc["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

changed = {k for k in set(before) | set(doc) if before.get(k) != doc.get(k)}
assert changed <= {"description", "updated", "assets", "table:columns"}, changed
json.dump(doc, open(stac_path, "w"), indent=2, ensure_ascii=False)
print(f"{doc['id']}: {', '.join(sorted(changed)) or 'unchanged'}")

md = open(readme_path).read()
section = (
    "## Threats with scope, severity and timing\n"
    f"`{HREF}` has one row per taxon and threat for the {n_target:,} taxa with a range polygon, "
    f"category NT to CR and at least one threat code: `sis_taxon_id`, `assessment_id`, "
    f"`year_published`, `threat_code`, `threat_name`, `timing`, `scope`, `severity`, `score`, "
    f"`invasive_species` and `virus`. It was read from the IUCN Red List API v4 ({dates}, "
    f"Red List version {rlv}) for the STAR threat split (Mair et al. 2021); {n_taxa:,} taxa "
    f"have {n_rows:,} threats. Join it to this table on `sis_taxon_id`.\n\n"
)
md = re.sub(r"## Threats with scope, severity and timing\n.*?\n\n", "", md, flags=re.S)
md = md.replace("## Provenance & license", section + "## Provenance & license", 1)
assert section in md, "README has no '## Provenance & license' heading"
open(readme_path, "w").write(md)
print("README: section written")
