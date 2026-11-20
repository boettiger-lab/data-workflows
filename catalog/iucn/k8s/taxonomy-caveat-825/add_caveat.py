#!/usr/bin/env python3
"""Add the missing-assessment-details caveat to the LIVE iucn-taxonomy-2025 collection and README.

usage: add_caveat.py <stac-collection.json> <README.md>   (both edited in place)

Every bird and 6,657 other taxa in iucn-taxonomy.parquet carry taxonomy and Red List category
only: the IUCN tabular export used in the May 2026 build held no assessment rows for them.
Counts measured on the published parquet 2026-11-20 (rows with assessment_date IS NULL).
Idempotent: a second run changes nothing.
"""
import json
import sys

MARK = "Coverage of the assessment details."

PARA = (
    MARK + " 17,842 taxa (about 10%) carry taxonomy and Red List category only: their "
    "assessment details (assessment date, criteria, population trend, measures such as "
    "elevation limits, and the threat, habitat, country and other code lists) are empty, "
    "because the Red List tabular export this table was built from did not include their "
    "assessments. They are every bird (all 11,185 taxa in class Aves), 3,511 insects, "
    "2,624 plants, 520 other animals and 2 fungi. For these taxa an empty code list means "
    "the details are not available in this table, not that IUCN recorded none; the Red List "
    "species pages carry them. To list them:\n"
    "  SELECT class, COUNT(*) FROM read_parquet('https://s3-west.nrp-nautilus.io/public-iucn/"
    "taxonomy/iucn-taxonomy.parquet') WHERE assessment_date IS NULL GROUP BY 1;"
)

COL_NOTE = (" Empty for taxa whose assessment details are not in this table, which includes "
            "every bird; see the collection description.")
COLS = {"assessment_date", "population_trend", "elevation_lower_m", "elevation_upper_m",
        "threat_codes", "habitat_codes", "country_codes"}

README_SECTION = (
    "## Missing assessment details\n"
    "17,842 taxa (about 10%) carry taxonomy and Red List category only. Their assessment "
    "details (assessment date, criteria, population trend, elevation limits, and the threat, "
    "habitat, country and other code lists) are empty, because the Red List tabular export "
    "this table was built from did not include their assessments. They are **every bird** "
    "(all 11,185 taxa in class Aves), 3,511 insects, 2,624 plants, 520 other animals and "
    "2 fungi. For these taxa an empty `habitat_codes` means not available here, not that IUCN "
    "recorded none.\n"
    "```sql\n"
    "SELECT class, COUNT(*)\n"
    "FROM read_parquet('https://s3-west.nrp-nautilus.io/public-iucn/taxonomy/iucn-taxonomy.parquet')\n"
    "WHERE assessment_date IS NULL GROUP BY 1 ORDER BY 2 DESC;\n"
    "```\n\n"
)

stac_path, readme_path = sys.argv[1], sys.argv[2]

c = json.load(open(stac_path))
assert c["id"] == "iucn-taxonomy-2025", c["id"]
if MARK not in c["description"]:
    # Insert before the trailing DuckDB example, after the in_holdings paragraph.
    head, sep, tail = c["description"].partition("\n\nExample (DuckDB):")
    c["description"] = head + "\n\n" + PARA + sep + tail
seen = set()
for col in c["table:columns"]:
    if col["name"] in COLS:
        seen.add(col["name"])
        if COL_NOTE.strip() not in col["description"]:
            d = col["description"].rstrip()
            col["description"] = (d if d.endswith(".") else d + ".") + COL_NOTE
assert seen == COLS, COLS - seen
json.dump(c, open(stac_path, "w"), indent=2, ensure_ascii=False)
open(stac_path, "a").write("\n")

r = open(readme_path).read()
if "## Missing assessment details" not in r:
    anchor = "## DuckDB examples"
    assert anchor in r
    r = r.replace(anchor, README_SECTION + anchor, 1)
    open(readme_path, "w").write(r)
print("ok")
