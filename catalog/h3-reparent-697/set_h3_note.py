"""Edit a LIVE collection after the #697 re-derivation of its coarser H3 columns.

  set_h3_note.py <collection.json> obis|gbif

obis: the hex asset's sentence on comparing with GBIF at resolution 8 now states that GBIF's
      resolution 8 is the parent of its resolution 10 cell, and that resolution 0 is the parent
      of the resolution 8 cell.
both: `updated` is set to now, since the hex files were rewritten.
Idempotent: a collection already carrying the new text is left as it is.
"""
import datetime
import json
import sys

path, which = sys.argv[1], sys.argv[2]
c = json.load(open(path))

if which == "obis":
    a = c["assets"]["obis-hex-2026-09-09"]
    old = ("Resolution 8 is also the resolution at which this data can be compared with the GBIF "
           "occurrence collection, which carries resolution 8 as one of its rollup levels.")
    new = ("Each record's resolution 0 cell is the parent of its resolution 8 cell. "
           "Resolution 8 is also the resolution at which this data can be compared with the GBIF "
           "occurrence collection. GBIF places each record in a resolution 10 cell and uses that "
           "cell's resolution 8 parent, so a record within about a hundred metres of a resolution 8 "
           "cell edge can sit in the neighbouring cell there. Cell-by-cell comparisons differ only "
           "at that margin.")
    if new not in a["description"]:
        assert old in a["description"], "expected sentence not found in the live description"
        a["description"] = a["description"].replace(old, new)
elif which != "gbif":
    sys.exit(f"unknown collection {which}")

c["updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
json.dump(c, open(path, "w"), indent=2, ensure_ascii=False)
print(f"{which}: updated {c['updated']}")
