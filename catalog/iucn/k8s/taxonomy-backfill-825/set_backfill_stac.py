#!/usr/bin/env python3
"""Record the Red List API backfill on the live taxonomy collection and README, in place (#825).

    set_backfill_stac.py COLLECTION.json README.md REPORT.json

REPORT.json is the build report written beside the staged parquet by backfill_taxonomy.py
(target and filled row counts, fetch dates, settings). Edits:

  collection: description (one provenance paragraph), `updated`, `sci:citation` (API access
              dates), a `rel: via` link to the API, and the descriptions of the columns whose
              meaning the backfill touches (assessment_date, year_last_seen,
              severe_fragmentation, area_restricted).
  README:     a "Backfilled assessment fields" section before "Provenance & license".

Idempotent: a file already carrying the paragraph is rewritten only where text differs.
"""
import datetime as dt
import json
import re
import sys

stac_path, readme_path, report_path = sys.argv[1:4]
doc = json.load(open(stac_path))
rep = json.load(open(report_path))
before = json.loads(json.dumps(doc))

first, last = rep["fetched_first"][:10], rep["fetched_last"][:10]
dates = first if first == last else f"{first} to {last}"
n_target, n_filled = rep["target_rows"], rep["filled_rows"]
assert rep["not_cached"] == 0, rep
regional = rep.get("regional", "fill") == "fill"
rlv = rep["red_list_version"]
assert rlv, "report carries no red_list_version"

MARK = "Red List API v4"
para = (
    f"Assessment fields for {n_target:,} taxa were filled from the IUCN {MARK} rather than the "
    f"tabular export, which held no bird assessments (BirdLife International assesses birds "
    f"for the Red List) and omitted taxa assessed only regionally. The API was read on {dates}, "
    f"when it served Red List version {rlv}; for each taxon the assessment matching its "
    f"published category and year was used where one exists (otherwise the latest global "
    f"assessment), so the filled fields describe the same assessment as the status columns. {n_filled:,} of the {n_target:,} taxa now carry an assessment date. "
    + ("For taxa assessed only at regional scope (mostly European Red List bees, beetles, "
       "mosses and plants), the fields describe that regional assessment, as the status "
       "columns already do. " if regional else "")
    + "The API does not report year_last_seen, so it is empty for these taxa."
)
desc = doc["description"]
if MARK in desc:
    desc = re.sub(r"Assessment fields for [\d,]+ taxa were filled.*?(?=\n\n|$)", para, desc, flags=re.S)
else:
    head, sep, tail = desc.partition("\n\n")
    desc = head + "\n\n" + para + sep + tail
doc["description"] = desc

doc["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
doc["sci:citation"] = (
    "IUCN. 2025. The IUCN Red List of Threatened Species. Version 2025-2. "
    f"https://www.iucnredlist.org. Assessment fields for birds and regionally assessed taxa "
    f"from the IUCN Red List API v4 (version {rlv}), accessed {dates}."
)
links = [l for l in doc["links"] if not (l.get("rel") == "via" and "api.iucnredlist.org" in l.get("href", ""))]
links.append({"rel": "via", "href": "https://api.iucnredlist.org/", "type": "text/html",
              "title": "IUCN Red List API v4 (source of the backfilled assessment fields)"})
doc["links"] = links

COLS = {
    "assessment_date": "Date of the latest assessment, written as 'YYYY-MM-DD 00:00:00 UTC'.",
    "year_last_seen": ("Year the taxon was last recorded (for extinct/possibly-extinct taxa). "
                       "Usually NULL, and always NULL for taxa whose assessment fields came from "
                       "the Red List API, which does not report it."),
    "severe_fragmentation": ("Latest assessment flags the population as severely fragmented. "
                             "In this edition no row is TRUE: taxa from the tabular export carry "
                             "FALSE whenever the field was recorded, including those assessed as "
                             "severely fragmented, and taxa filled from the Red List API carry NULL. "
                             "Do not use this column to find fragmented taxa."),
    "area_restricted": ("Latest assessment flags the taxon as area-restricted. In this edition no "
                        "row is TRUE: taxa from the tabular export carry FALSE whenever the field "
                        "was recorded, including area-restricted ones, and taxa filled from the "
                        "Red List API carry NULL. Do not use this column to find area-restricted taxa."),
}
if rep.get("bool_flags") == "api":
    del COLS["severe_fragmentation"], COLS["area_restricted"]
for c in doc["table:columns"]:
    if c["name"] in COLS:
        c["description"] = COLS[c["name"]]

changed = {k for k in set(before) | set(doc) if before.get(k) != doc.get(k)}
assert changed <= {"description", "updated", "sci:citation", "links", "table:columns"}, changed
json.dump(doc, open(stac_path, "w"), indent=2, ensure_ascii=False)
print(f"{doc['id']}: {', '.join(sorted(changed)) or 'unchanged'}")

# README
md = open(readme_path).read()
section = (
    "## Backfilled assessment fields\n"
    f"The IUCN tabular export held no bird assessments and omitted taxa assessed only "
    f"regionally, so {n_target:,} taxa had taxonomy and status but empty assessment fields. "
    f"Those fields were filled from the IUCN Red List API v4 (read {dates}, Red List version "
    f"{rlv}), using for each taxon the assessment that matches its published category and "
    f"year where one exists. {n_filled:,} of the {n_target:,} now carry an assessment date. `year_last_seen` is "
    f"not reported by the API and stays empty for these taxa. "
    + ("`severe_fragmentation` and `area_restricted` are never TRUE in this edition (export rows "
       "carry FALSE whenever recorded; API-filled rows carry NULL), so do not filter on them.\n\n"
       if rep.get("bool_flags") != "api" else "\n\n")
)
md = re.sub(r"## Backfilled assessment fields\n.*?\n\n", "", md, flags=re.S)
md = md.replace("## Provenance & license", section + "## Provenance & license", 1)
assert section in md, "README has no '## Provenance & license' heading"
open(readme_path, "w").write(md)
print("README: section written")
