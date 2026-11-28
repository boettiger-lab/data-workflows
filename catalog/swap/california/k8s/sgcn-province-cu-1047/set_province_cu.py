"""#1047: state the truncation and both forms of Province_CU on the LIVE sgcn-ranges collection.

Measured 2026-11-28 on public-swap/california/swap-2025/sgcn-ranges.parquet (MCP): 1,436
records; 948 'not available'; 150 values exactly 255 characters (106 birds, 33 mammals,
5 reptiles, 5 amphibians, 1 fish); 79 in the 'Province not specified.' form; Central
California Coast LIKE 215, whole-item 186.

    python3 set_province_cu.py stac-collection.json
"""
import json
import sys

path = sys.argv[1]
c = json.load(open(path))

OLD = ("SWAP provinces and conservation units where the species occurs, e.g. 'Desert Province "
       "(Colorado Desert, Mojave Desert)'; 'Province/Conservation Unit not available' for 948 "
       "records. A comma-separated list; filter with LIKE, e.g. Province_CU LIKE '%Mojave Desert%'.")
NEW = ("SWAP provinces and conservation units where the species occurs, as text in one of two "
       "forms: 'Desert Province (Colorado Desert, Mojave Desert)', units in parentheses after "
       "each province; or, for 79 records, 'Province not specified. Conservation Units: HUC "
       "1802 Sacramento, …'. 'Province/Conservation Unit not available' for 948 records.\n\n"
       "Truncated: 150 values stop at 255 characters, mid-name (106 birds, 33 mammals, 5 "
       "reptiles, 5 amphibians, 1 fish), so units late in a long list are missing from the "
       "text. The range geometry is complete: to find where a species occurs, overlay its hex "
       "with the conservation-units layer instead of reading this column. Unit names here are "
       "short forms that do not equal conservation-units `Name` ('Mojave Desert', 'HUC 1802 "
       "Sacramento').\n\n"
       "Match a whole unit, not a substring: `LIKE '%Central California Coast%'` also matches "
       "'Central California Coast Ranges' (215 records, against 186 for the unit itself). "
       "Whole-unit match: `regexp_matches(Province_CU, '(^|[(,:]) *Central California Coast "
       "*([,);]|$)')`.")

hits = 0
for cols in [c.get("table:columns", [])] + [a.get("table:columns", []) for a in c["assets"].values()]:
    for col in cols:
        if col.get("name") == "Province_CU" and "description" in col:
            assert col["description"] == OLD, col["description"]
            col["description"] = NEW
            hits += 1
assert hits >= 1, "Province_CU description not found"
json.dump(c, open(path, "w"), indent=2, ensure_ascii=False)
print("ok", hits)
