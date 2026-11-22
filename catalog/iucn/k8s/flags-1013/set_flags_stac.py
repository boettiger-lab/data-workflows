#!/usr/bin/env python3
"""Record the corrected Yes/No flags on the live taxonomy collection and README, in place (#1013).

    set_flags_stac.py COLLECTION.json README.md REPORT.json

REPORT.json is the build report fix_flags.py writes beside the staged parquet. Edits:

  collection: one provenance paragraph in the description, `updated`, the API access dates in
              `sci:citation`, and the descriptions of severe_fragmentation and area_restricted
              (which today warn that no row is TRUE).
  README:     drops the "never TRUE" warning from "Backfilled assessment fields" and adds a
              "Fragmentation and area-restricted flags" section before "Provenance & license".

Idempotent: a rerun rewrites the same text.
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
n = rep["target_rows"]
sf_true, ar_true = rep["true_rows"]["severe_fragmentation"], rep["true_rows"]["area_restricted"]

MARK = "severe_fragmentation and area_restricted were re-read"
para = (
    f"The Yes/No flags severe_fragmentation and area_restricted were re-read from the IUCN Red "
    f"List API v4 on {dates} (Red List version {rlv}) for the {n:,} taxa that recorded either "
    f"flag in the tabular export or whose assessment fields were filled from the API, because "
    f"the first build of this table had written every recorded value, Yes included, as FALSE. "
    f"{sf_true:,} taxa are now flagged as severely fragmented and {ar_true:,} as area-restricted. "
    f"Where the API gives no answer (Unknown or blank), the flag is empty."
)
desc = doc["description"]
if MARK in desc:
    desc = re.sub(r"The Yes/No flags severe_fragmentation and area_restricted were re-read.*?(?=\n\n|$)",
                  para, desc, flags=re.S)
else:  # after the #825 paragraph, which is the second one
    parts = desc.split("\n\n")
    parts.insert(2, para)
    desc = "\n\n".join(parts)
doc["description"] = desc
doc["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

cit = doc["sci:citation"]
tail = f" Severe-fragmentation and area-restricted flags from the IUCN Red List API v4 (version {rlv}), accessed {dates}."
cit = re.sub(r" Severe-fragmentation and area-restricted flags from the IUCN Red List API v4.*$", "", cit)
doc["sci:citation"] = cit + tail

COLS = {
    "severe_fragmentation": ("Latest assessment flags the population as severely fragmented "
                             "(Red List API v4 'population severely fragmented': Yes = TRUE, "
                             "No = FALSE). Empty where the assessment does not say."),
    "area_restricted": ("Latest assessment flags the taxon as area-restricted (Red List API v4 "
                        "'area restricted': Yes = TRUE, No = FALSE). Empty where the assessment "
                        "does not say."),
}
for c in doc["table:columns"]:
    if c["name"] in COLS:
        c["description"] = COLS[c["name"]]
assert all(any(c["name"] == k for c in doc["table:columns"]) for k in COLS)

changed = {k for k in set(before) | set(doc) if before.get(k) != doc.get(k)}
assert changed <= {"description", "updated", "sci:citation", "table:columns"}, changed
json.dump(doc, open(stac_path, "w"), indent=2, ensure_ascii=False)
print(f"{doc['id']}: {', '.join(sorted(changed)) or 'unchanged'}")

md = open(readme_path).read()
md = re.sub(r" `severe_fragmentation` and `area_restricted` are never TRUE in this edition[^\n]*", "", md)
section = (
    "## Fragmentation and area-restricted flags\n"
    f"`severe_fragmentation` and `area_restricted` were re-read from the IUCN Red List API v4 "
    f"(read {dates}, Red List version {rlv}) for the {n:,} taxa that recorded either flag in the "
    f"tabular export or whose assessment fields came from the API. The first build had written "
    f"every recorded value as FALSE. {sf_true:,} taxa are now TRUE for severe fragmentation and "
    f"{ar_true:,} for area-restricted; the flag is empty where the assessment does not say.\n\n"
)
md = re.sub(r"## Fragmentation and area-restricted flags\n.*?\n\n", "", md, flags=re.S)
md = md.replace("## Provenance & license", section + "## Provenance & license", 1)
assert section in md, "README has no '## Provenance & license' heading"
assert "never TRUE" not in md
open(readme_path, "w").write(md)
print("README: section written")
