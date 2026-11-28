"""#1077: state the matching hex columns on the live ca30x30-ecoregion collection.

Run after ecoregion-hex-parents.yaml (#1077) has flipped the three hex assets. Edits the
LIVE collection in place; every replaced passage is asserted present, so a collection
that has drifted since this was written fails loudly instead of being half-edited.

    python3 set_columns.py stac-collection.json
"""
import json
import sys

path = sys.argv[1]
c = json.load(open(path))
A = c["assets"]


def replace(text, old, new, where):
    assert old in text, f"{where}: expected passage not found: {old[:80]!r}"
    return text.replace(old, new, 1)


# --- collection description: the columns no longer differ between levels.
c["description"] = replace(
    c["description"],
    "Columns differ between the three hex assets. `CA_Ecoregi` (the ecoregion) is only on "
    "the resolution-10 asset, `ecoregion-hex`. `land_area_km2` is only on the resolution-9 "
    "and resolution-8 assets; at resolution 10 a cell is all land, so its land area is the "
    "cell's own area. An ecoregion's cells:",
    "All three hex assets (resolutions 10, 9 and 8) carry `CA_Ecoregi` (the ecoregion) and "
    "`land_area_km2` (the California land area in the row, km²), so an ecoregion's area "
    "is the same query at any level. An ecoregion's cells:",
    "description",
)
c["description"] = replace(
    c["description"],
    "SELECT DISTINCT h10, h0 FROM read_parquet('s3://public-ca30x30/ecoregion/hex/h0=*/data_0.parquet') WHERE CA_Ecoregi = 'Sierra Nevada'",
    "SELECT DISTINCT h10, h0 FROM read_parquet('s3://public-ca30x30/ecoregion/hex/h0=*/data_0.parquet') WHERE CA_Ecoregi = 'Sierra Nevada'\n"
    "-- its land area, at any level (hex, hex-res9, hex-res8):\n"
    "SELECT SUM(land_area_km2) FROM read_parquet('s3://public-ca30x30/ecoregion/hex-res8/h0=*/data_0.parquet') WHERE CA_Ecoregi = 'Sierra Nevada'",
    "description",
)

# --- res 10: one new column.
h10 = A["ecoregion-hex"]
names = [x["name"] for x in h10["table:columns"]]
assert "land_area_km2" not in names
h10["table:columns"].insert(names.index("h0"), {"name": "land_area_km2", "type": "double"})
h10["description"] = replace(
    h10["description"],
    "Cells along the coast and the state border reach a little past the boundary.",
    "`land_area_km2` is the cell's own area (each resolution-10 cell is counted as all "
    "land), so `SUM(land_area_km2)` over distinct cells is their California land area.\n\n"
    "Cells along the coast and the state border reach a little past the boundary.",
    "ecoregion-hex",
)

# --- res 9 and 8: CA_Ecoregi, and one row per (cell, ecoregion).
for res, cap, straddle in ((9, 7, "about 30,000 of 3.66 million"), (8, 49, "about 15,000 of 525,000")):
    a = A[f"ecoregion-hex-res{res}"]
    names = [x["name"] for x in a["table:columns"]]
    assert "CA_Ecoregi" not in names
    a["table:columns"].insert(names.index("nland"), {"name": "CA_Ecoregi", "type": "string"})
    d = a["description"]
    d = replace(
        d,
        f"One row per resolution-{res} cell containing California land, giving how many "
        f"resolution-10 land cells it holds (up to {cap}) and their combined land area in "
        "square kilometres.",
        f"One row per resolution-{res} cell and ecoregion (`CA_Ecoregi`), giving how many of "
        f"the cell's resolution-10 land cells lie in that ecoregion (up to {cap}) and their "
        f"combined land area in square kilometres. A cell on an ecoregion boundary "
        f"({straddle} cells) has one row per ecoregion, each holding only that "
        "ecoregion's part, so the rows of a cell add up to its whole land area.",
        f"res{res}",
    )
    d = replace(
        d,
        "One row per cell, so `land_area_km2` is that cell's own land area and adding it "
        "across a set of distinct cells gives the California land area of that set.",
        "`SUM(land_area_km2)` over all rows gives California's land area, and with "
        "`WHERE CA_Ecoregi = …` an ecoregion's. To weight a per-cell share, sum over the "
        "rows as above; the per-ecoregion rows split each cell's area without overlap. To "
        "list cells, use `SELECT DISTINCT h" + str(res) + ", h0`.",
        f"res{res}",
    )
    a["description"] = d

json.dump(c, open(path, "w"), indent=2, ensure_ascii=False)
print("ok")
