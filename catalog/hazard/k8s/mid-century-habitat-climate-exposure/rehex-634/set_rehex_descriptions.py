#!/usr/bin/env python3
"""Describe the re-hexed CNRM-CM5 hex of mid-century-habitat-climate-exposure (#634).

  set_rehex_descriptions.py stac  <stac-collection.json>   # edits in place
  set_rehex_descriptions.py readme <README.md>             # edits in place

The CNRM-CM5 hex was rebuilt with non-analog pixels (-1) counted as 1 before the mean, and
gained a column `non_analog_frac`, the share of the cell's area that is non-analog. The COGs
and the MIROC5 hex are unchanged. Edits only the fields named below, on the LIVE files, and
refuses (exit 2) if a field no longer holds the text it replaces (the text published by
../describe-634/set_descriptions.py), so a later edit is never silently overwritten.
"""
import json
import sys

OLD_DESC = (
    "An average is not meaningful across the non-analog code, so a hex cell that mixes "
    "non-analog and other pixels takes a value that matches neither; the hex asset descriptions "
    "say how to handle this. "
)
NEW_DESC = (
    "The COGs keep the source codes, -1 included. The CNRM-CM5 hex counts non-analog pixels as "
    "1, the most exposed class, before averaging, so its exposure runs from 0.05 to 1 and "
    "higher always means more exposed, and its non_analog_frac column gives the share of each cell "
    "that is non-analog. "
)

HEX = (
    "CNRM-CM5 exposure for each H3 resolution 9 cell: the area-weighted mean of the 90 m "
    "source classes, one row per cell, ranging from -1 to 1. A negative value means "
    "non-analog pixels (-1, among the most exposed conditions) outweigh the rest of the cell. "
    "Non-analog pixels also fall in cells whose mean is positive, where they lower the mean "
    "and make the cell read as less exposed than it is; the same holds when cells are "
    "averaged up to resolution 8. Count negative cells as exposed:\n"
    "SELECT COUNT(*) FROM read_parquet('s3://public-hazard/mid-century-habitat-climate-"
    "exposure/cnrm/hex/h0=*/data_0.parquet') WHERE exposure >= 0.95 OR exposure < 0\n"
    "For an exact non-analog extent, use the cnrm-cog raster, where non-analog pixels are "
    "exactly -1.",
    "CNRM-CM5 exposure for each H3 resolution 9 cell, one row per cell. `exposure` is the "
    "area-weighted mean of the 90 m source classes after non-analog pixels (-1 in the COG) are "
    "counted as 1, the most exposed class, so it ranges from 0.05 to 1 and higher always means "
    "more exposed. `non_analog_frac` is the share of the cell's area that is non-analog, from "
    "0 to 1; it is above 0 in the few thousand cells along non-analog patches. Roll up to "
    "resolution 8 with AVG for both columns. Non-analog cells:\n"
    "SELECT h9, non_analog_frac FROM read_parquet('s3://public-hazard/mid-century-habitat-"
    "climate-exposure/cnrm/hex/h0=*/data_0.parquet') WHERE non_analog_frac > 0",
)

COL_EXPOSURE = (
    "Mid-century habitat climate-exposure index per H3 cell (Thorne et al. 2016): the "
    "area-weighted mean of the source percentile classes. 0.05 to 0.80 is within the "
    "vegetation's current climate envelope and above 0.95 is highly stressed; -1 is non-analog "
    "climate, among the most exposed conditions, so a negative value means more exposed, not "
    "less. Ranges from -1 to 1 under CNRM-CM5 and from 0.05 to 1 under MIROC5. One value per "
    "cell, with no per-feature duplication.",
    "Mid-century habitat climate-exposure index per H3 cell (Thorne et al. 2016): the "
    "area-weighted mean of the source percentile classes, where 0.05 to 0.80 is within the "
    "vegetation's current climate envelope and above 0.95 is highly stressed. Non-analog "
    "climate (-1 in the COGs, which the source treats as most exposed) is counted as 1 before "
    "averaging, so the value ranges from 0.05 to 1 and higher always means more exposed. One "
    "value per cell, with no per-feature duplication.",
)
COL_NON_ANALOG = {
    "name": "non_analog_frac",
    "type": "double",
    "description": (
        "Share of the H3 cell's area whose projected mid-century climate is non-analog (-1 in "
        "the COG), from 0 to 1. CNRM-CM5 only; MIROC5 has no non-analog pixels and no such "
        "column. One value per cell, with no per-feature duplication."
    ),
}
# MIROC5 hex keeps the old schema, so it carries its own list (names and types only).
MIROC_COLUMNS = [
    {"name": "exposure", "type": "double"},
    {"name": "h9", "type": "uint64"},
    {"name": "h8", "type": "uint64"},
    {"name": "h0", "type": "int64"},
]

README = [
    (
        "  reducer (never `sum`). Rollup parent resolutions: 8, 0. An average is not meaningful across\n"
        "  the non-analog code: a CNRM-CM5 cell that mixes −1 pixels with others takes a mean that\n"
        "  matches neither, and reads as less exposed than it is. MIROC5 is unaffected.\n",
        "  reducer (never `sum`). Rollup parent resolutions: 8, 0. The CNRM-CM5 hex counts non-analog\n"
        "  pixels as 1, the most exposed class, before averaging, so its `exposure` runs from 0.05 to 1\n"
        "  and higher always means more exposed; its `non_analog_frac` column gives the share of each\n"
        "  cell that is non-analog. The COGs keep the source codes, −1 included.\n",
    ),
    (
        "One row per H3 resolution 9 cell; `exposure` is the per-cell mean (no per-feature duplication).\n"
        "Roll up to resolution 8 with `AVG`, never `SUM`. For CNRM-CM5, a negative value means non-analog\n"
        "climate (among the most exposed) outweighs the rest of the cell, so count it as exposed:\n"
        "\n"
        "```sql\n"
        "SELECT COUNT(*) AS exposed_cells\n"
        "FROM read_parquet('https://s3-west.nrp-nautilus.io/public-hazard/mid-century-habitat-climate-exposure/cnrm/hex/h0=*/data_0.parquet')\n"
        "WHERE exposure >= 0.95 OR exposure < 0;\n"
        "```\n"
        "\n"
        "Non-analog pixels can also sit in cells with a positive mean; for an exact non-analog extent\n"
        "use the COG, where they are exactly −1.\n",
        "One row per H3 resolution 9 cell; `exposure` is the per-cell mean (no per-feature duplication).\n"
        "Roll up to resolution 8 with `AVG`, never `SUM`. In the CNRM-CM5 hex, `non_analog_frac` is the\n"
        "share of the cell that is non-analog (0 to 1); MIROC5 has no non-analog pixels and no such column.\n"
        "\n"
        "```sql\n"
        "SELECT COUNT(*) AS non_analog_cells\n"
        "FROM read_parquet('https://s3-west.nrp-nautilus.io/public-hazard/mid-century-habitat-climate-exposure/cnrm/hex/h0=*/data_0.parquet')\n"
        "WHERE non_analog_frac > 0;\n"
        "```\n",
    ),
]


def swap(where, cur, old, new):
    if cur == new:
        return new  # already applied
    if cur != old:
        sys.exit(f"refusing: {where} no longer holds the expected text:\n{cur!r}")
    return new


def stac(path):
    c = json.load(open(path))
    d = c["description"]
    if NEW_DESC not in d:
        if OLD_DESC not in d:
            sys.exit(f"refusing: collection description changed:\n{d!r}")
        c["description"] = d.replace(OLD_DESC, NEW_DESC)
    a = c["assets"]["cnrm-hex"]
    a["description"] = swap("cnrm-hex description", a.get("description"), *HEX)
    cols = c["table:columns"]
    exp = next(x for x in cols if x["name"] == "exposure")
    exp["description"] = swap("table:columns exposure", exp["description"], *COL_EXPOSURE)
    if not any(x["name"] == "non_analog_frac" for x in cols):
        cols.insert(cols.index(exp) + 1, COL_NON_ANALOG)
    c["assets"]["miroc-hex"]["table:columns"] = MIROC_COLUMNS
    json.dump(c, open(path, "w"), indent=2, ensure_ascii=False)
    open(path, "a").write("\n")


def readme(path):
    t = open(path, encoding="utf-8").read()
    for old, new in README:
        if new in t:
            continue
        if t.count(old) != 1:
            sys.exit(f"refusing: README no longer holds:\n{old}")
        t = t.replace(old, new)
    open(path, "w", encoding="utf-8").write(t)


if __name__ == "__main__":
    {"stac": stac, "readme": readme}[sys.argv[1]](sys.argv[2])
