"""#832: say which filters reproduce Protected Planet's coverage statistics, on the LIVE
public-wdpa/wdpa collection.

Measured 2026-11-28 on public-wdpa/wdpa.parquet (MCP): STATUS 'Proposed' 1,166 parcels
(no 'Not Reported' in this edition); DESIG_ENG 'UNESCO-MAB Biosphere Reserve' 344 parcels,
all DESIG_TYPE 'International'. Other "biosphere" designations are national and are not
excluded by Protected Planet. The collection is the polygon file only (WDPA_poly).

    python3 set_pp_note.py stac-collection.json
"""
import json
import sys

path = sys.argv[1]
c = json.load(open(path))

ANCHOR = "Three representations share one stable per-parcel key"
NOTE = (
    "**Protected Planet's figures are not a plain union.** Protected Planet's published "
    "coverage statistics leave out sites with `STATUS = 'Proposed'` (1,166 parcels in this "
    "edition) and UNESCO-MAB Biosphere Reserves (`DESIG_ENG = 'UNESCO-MAB Biosphere "
    "Reserve'`, 344 parcels; national biosphere designations stay in). They count "
    "overlapping sites once, and they add WD-OECM sites (collection `wdoecm-may-2026`) and the WDPA "
    "point sites, drawn as circles of their `REP_AREA`. This collection holds the polygon "
    "file only, so the point sites are not here, and a figure built from it will come out "
    "slightly below Protected Planet's. Say which definition you used.\n\n"
    "```sql\n"
    "-- parcels Protected Planet counts\n"
    "WHERE STATUS <> 'Proposed' AND DESIG_ENG <> 'UNESCO-MAB Biosphere Reserve'\n"
    "```\n\n"
)
d = c["description"]
assert "Protected Planet's figures are not a plain union" not in d, "already applied"
assert d.count(ANCHOR) == 1, "anchor paragraph not found"
c["description"] = d.replace(ANCHOR, NOTE + ANCHOR, 1)
json.dump(c, open(path, "w"), indent=2, ensure_ascii=False)
print("ok")
