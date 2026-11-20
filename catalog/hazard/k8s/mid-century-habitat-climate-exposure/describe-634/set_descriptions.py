#!/usr/bin/env python3
"""Correct the value semantics of mid-century-habitat-climate-exposure (#634).

  set_descriptions.py stac  <stac-collection.json>   # edits in place
  set_descriptions.py readme <README.md>             # edits in place

Edits only the fields named below, on the LIVE files, and refuses (exit 2) if a field no
longer holds the text it is replacing, so a later edit is never silently overwritten.

Source semantics: CDFW BIOS metadata for the same Thorne et al. exposure product
(ds2653-ds2656): "-100 = non-analog; 0-80 = remaining within current climate envelope;
>95 = highly stressed"; non-analog areas are "equivalent to highly exposed (>99%)".
Our layers are on that scale divided by 100. Measured classes in the published COGs:
CNRM -1 (17,178 px) and 0.05..0.95 by 0.05, 0.99, 1; MIROC the same without -1.
"""
import json
import sys

OLD_DESC_TAIL = (
    "aggregated to H3 resolution 9 using an area-weighted **mean** reducer (the pixel value is a "
    "continuous, normalized exposure index in [-1, 1], not a count or amount). Higher values "
    "indicate greater projected mid-century climate exposure. "
)
NEW_DESC_TAIL = (
    "aggregated to H3 resolution 9 using an area-weighted mean. Each source pixel is ranked "
    "against the 1981–2010 climate of its vegetation macrogroup across the state and coded as a "
    "percentile class: 0.05 to 0.80 remains within the macrogroup's current climate envelope, "
    "0.85 to 0.95 lies toward its edge, and the classes above 0.95 (0.99 and 1) are highly "
    "stressed. A value of -1 is non-analog climate: a projected combination of conditions outside "
    "the range of all sampled historic conditions for that vegetation, which the source treats as "
    "equivalent to the most exposed class. The scale is therefore not monotonic in exposure: -1 "
    "is among the most exposed values, not the least. Non-analog pixels occur only under CNRM-CM5 "
    "(about 0.03% of pixels), so CNRM-CM5 ranges from -1 to 1 and MIROC5 from 0.05 to 1. An "
    "average is not meaningful across the non-analog code, so a hex cell that mixes non-analog "
    "and other pixels takes a value that matches neither; the hex asset descriptions say how to "
    "handle this. "
)

BAND = {
    "cnrm-cog": (
        "Continuous mid-century (2040–2069) climate-exposure index for natural vegetation under "
        "CNRM-CM5. Range -1 to 1 (source min -1, max 1, mean 0.76). Higher = greater exposure.",
        "Mid-century (2040–2069) climate-exposure class for natural vegetation under CNRM-CM5, as "
        "a percentile of the vegetation macrogroup's 1981–2010 climate: 0.05 to 0.80 within the "
        "current climate envelope, above 0.95 highly stressed, and -1 non-analog climate (no "
        "historic analogue, treated by the source as most exposed). Values: -1, 0.05 to 0.95 in "
        "steps of 0.05, 0.99 and 1. Not monotonic in exposure: -1 is among the most exposed "
        "values.",
    ),
    "miroc-cog": (
        "Continuous mid-century (2040–2069) climate-exposure index for natural vegetation under "
        "MIROC5. Source range ~0.05 to 1. Higher = greater exposure.",
        "Mid-century (2040–2069) climate-exposure class for natural vegetation under MIROC5, as a "
        "percentile of the vegetation macrogroup's 1981–2010 climate: 0.05 to 0.80 within the "
        "current climate envelope and above 0.95 highly stressed. Values: 0.05 to 0.95 in steps "
        "of 0.05, 0.99 and 1. This model has no non-analog (-1) pixels, so higher always means "
        "more exposed.",
    ),
}

HEX = {
    "cnrm-hex": (
        "Exposure computed from the CNRM-CM5 climate model.",
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
    ),
    "miroc-hex": (
        "Exposure computed from the MIROC5 climate model.",
        "MIROC5 exposure for each H3 resolution 9 cell: the area-weighted mean of the 90 m source "
        "classes, one row per cell, ranging from 0.05 to 1. This model has no non-analog (-1) "
        "pixels, so the mean is an average percentile class and higher always means more "
        "exposed.",
    ),
}

COL = (
    "Area-weighted mean mid-century habitat climate-exposure index per H3 cell (Thorne et al. "
    "2016); continuous, range [-1, 1]. One value per cell — safe to aggregate.",
    "Mid-century habitat climate-exposure index per H3 cell (Thorne et al. 2016): the "
    "area-weighted mean of the source percentile classes. 0.05 to 0.80 is within the "
    "vegetation's current climate envelope and above 0.95 is highly stressed; -1 is non-analog "
    "climate, among the most exposed conditions, so a negative value means more exposed, not "
    "less. Ranges from -1 to 1 under CNRM-CM5 and from 0.05 to 1 under MIROC5. One value per "
    "cell, with no per-feature duplication.",
)

README = [
    (
        "- **Value:** a continuous, normalized climate-exposure **index** (range ≈ −1 to 1; higher = greater\n"
        "  projected mid-century exposure). It is *not* a count or amount.\n",
        "- **Value:** a climate-exposure class for each 90 m pixel: the percentile of the vegetation\n"
        "  macrogroup's 1981–2010 climate that the projected mid-century climate falls in. 0.05 to 0.80\n"
        "  remains within the current climate envelope, 0.85 to 0.95 lies toward its edge, and 0.99 and 1\n"
        "  are highly stressed. **−1 is non-analog climate**: conditions outside the range of all sampled\n"
        "  historic conditions for that vegetation, which the source treats as equivalent to the most\n"
        "  exposed class. The scale is therefore **not monotonic**: −1 is among the most exposed values,\n"
        "  not the least. It is *not* a count or amount.\n"
        "- **Range by model:** CNRM-CM5 −1 to 1 (non-analog in about 0.03% of pixels); MIROC5 0.05 to 1\n"
        "  (no non-analog pixels).\n",
    ),
    (
        "  reducer (correct for a continuous index; never `sum`). Rollup parent resolutions: 8, 0.\n",
        "  reducer (never `sum`). Rollup parent resolutions: 8, 0. An average is not meaningful across\n"
        "  the non-analog code: a CNRM-CM5 cell that mixes −1 pixels with others takes a mean that\n"
        "  matches neither, and reads as less exposed than it is. MIROC5 is unaffected.\n",
    ),
    (
        "One row per H3 res-9 cell; `exposure` is the per-cell mean (safe to aggregate — no per-feature\n"
        "duplication). Roll up to res 8 with `AVG`, never `SUM`.\n",
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
    if NEW_DESC_TAIL not in d:
        if OLD_DESC_TAIL not in d:
            sys.exit(f"refusing: collection description changed:\n{d!r}")
        c["description"] = d.replace(OLD_DESC_TAIL, NEW_DESC_TAIL)
    for k, (old, new) in BAND.items():
        b = c["assets"][k]["raster:bands"][0]
        b["description"] = swap(f"{k} band", b.get("description"), old, new)
    for k, (old, new) in HEX.items():
        a = c["assets"][k]
        a["description"] = swap(f"{k} description", a.get("description"), old, new)
    col = next(x for x in c["table:columns"] if x["name"] == "exposure")
    col["description"] = swap("table:columns exposure", col["description"], *COL)
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
