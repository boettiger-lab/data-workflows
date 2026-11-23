#!/usr/bin/env python3
"""Document the PAD-US 4.1 marine layer's marine-only columns (#617).

    marine_columns.py <collection.json>          # edits the file in place

PAD-US 4.1 Marine carries 14 fields from the NOAA MPA Inventory schema that are blank in every
feature (empty strings in the source GDB; NULL, blank or 0 in our parquet). The collection
listed them with no description, and the parquet and hex assets did not list them at all
(verify-stac undocumented-column). This adds the descriptions, fixes MarPercent's type
(int32 in the parquet), and lists the columns on both assets in parquet order, after
Comments. Running it twice is a no-op.
"""
import json
import sys

EMPTY = " Blank for every feature in PAD-US 4.1."
ZERO = " 0 for every feature in PAD-US 4.1."
COLS = [  # parquet order
    ("Prot_Lvl", "string", "Level of protection." + EMPTY),
    ("Pri_Con_Fo", "string", "Primary conservation focus." + EMPTY),
    ("Cons_Focus", "string", "Conservation focus." + EMPTY),
    ("Permanence", "string", "Permanence of the protection." + EMPTY),
    ("NS_Full", "string", "Membership of the National System of Marine Protected Areas." + EMPTY),
    ("Mgmt_Plan", "string", "Management plan." + EMPTY),
    ("Fish_Rstr", "string", "Fishing restrictions." + EMPTY),
    ("Prot_Foc", "string", "Protection focus." + EMPTY),
    ("Constancy", "string", "Whether the protection is year-round or seasonal." + EMPTY),
    ("Vessel", "string", "Vessel restrictions." + EMPTY),
    ("Anchor", "string", "Anchoring restrictions." + EMPTY),
    ("MarPercent", "int32", "Percent of the area that is marine." + ZERO),
    ("AreaMar", "double", "Marine area in acres." + ZERO),
    ("Marine", "string", "Marine designation." + EMPTY),
]


def main(path):
    doc = json.load(open(path))
    by = {n: (t, d) for n, t, d in COLS}
    for c in doc.get("table:columns", []):
        if c["name"] in by:
            c["type"], c["description"] = by[c["name"]]
    for key in ("marine-parquet", "marine-hex"):
        cols = doc["assets"][key]["table:columns"]
        have = {c["name"] for c in cols}
        at = next(i + 1 for i, c in enumerate(cols) if c["name"] == "Comments")
        new = [{"name": n, "type": t} for n, t, _ in COLS if n not in have]
        cols[at:at] = new
    json.dump(doc, open(path, "w"), indent=2, ensure_ascii=False)
    print(f"{doc['id']}: marine columns documented")


if __name__ == "__main__":
    main(sys.argv[1])
