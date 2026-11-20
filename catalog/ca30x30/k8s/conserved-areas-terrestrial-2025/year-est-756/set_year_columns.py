#!/usr/bin/env python3
"""Correct the establishment-year column descriptions on one collection, in place (#756).

    set_year_columns.py COLLECTION.json

The 30x30 Conserved Areas layer unions CPAD holdings with CCED easements, and carries an
establishment year from each. The source FGDC metadata defines YR_EST (GreenInfo, CPAD) as
"Year the park or management unit was formed"; the CCED manual defines date_est as "Full
date the easement was established (MM/DD/YYYY) or date of project approval" and year_est as
"Year easement was established (YYYY)". The collection called year_est a numeric duplicate
of YR_EST, which is wrong: they disagree on 24,918 of 45,811 units, and year_est is set
only on easement units (Easement = 1).

Changes the top-level table:columns descriptions of YR_EST, date_est and year_est, and adds
one paragraph to the collection description. Idempotent.
"""
import json
import sys

COLUMNS = {
    "YR_EST": (
        "Year the park or other managed area containing this unit was established, from the "
        "California Protected Areas Database (CPAD), which defines it as the year the park or "
        "management unit was formed. 0 where unknown or where the unit has no CPAD record. "
        "This is not the year a conservation easement was recorded; that is year_est."
    ),
    "date_est": (
        "Date the conservation easement on this unit was established, or the date the "
        "project was approved, from the California Conservation Easement Database (CCED). "
        "Set only on easement units (Easement = 1) and empty everywhere else. CCED records "
        "the date and year_est separately, so for a few easements their years differ."
    ),
    "year_est": (
        "Year the conservation easement on this unit was established, from the California "
        "Conservation Easement Database (CCED). Set only on easement units (Easement = 1); 0 "
        "on all other units and on easements whose year is unknown. Where an easement lies "
        "within a CPAD park, YR_EST holds the park's year and year_est the easement's, so the "
        "two can differ."
    ),
}

MARKER = "ESTABLISHMENT YEAR:"
PARAGRAPH = (
    MARKER + " the layer carries two establishment years that describe different things. "
    "`YR_EST` is the year the park or managed area was formed (from CPAD) and is set on "
    "units covering 90.7% of GAP 1+2 acres. `year_est` and `date_est` are when a "
    "conservation easement was established (from CCED) and are set only on easement units "
    "(`Easement` = 1), 5.6% of GAP 1+2 acres. A value of 0 in either year column means "
    "unknown or not applicable. On an easement inside a park, the two years can differ."
)

path = sys.argv[1]
doc = json.load(open(path))
before = json.loads(json.dumps(doc))

seen = set()
for col in doc.get("table:columns", []):
    if col["name"] in COLUMNS:
        col["description"] = COLUMNS[col["name"]]
        seen.add(col["name"])
missing = set(COLUMNS) - seen
if missing:
    sys.exit(f"{path}: column dictionary lacks {sorted(missing)}, refusing to change it")
for asset in doc.get("assets", {}).values():
    for col in asset.get("table:columns", []):
        if col["name"] in COLUMNS and "description" in col:
            sys.exit(f"{path}: asset carries its own text for {col['name']}, refusing")
if MARKER not in doc.get("description", ""):
    doc["description"] = doc["description"].rstrip() + "\n\n" + PARAGRAPH

changed = {k for k in set(before) | set(doc) if before.get(k) != doc.get(k)}
assert changed <= {"table:columns", "description"}, changed
json.dump(doc, open(path, "w"), indent=2, ensure_ascii=False)
print(f"{doc['id']}: {', '.join(sorted(changed)) or 'unchanged'}")
