"""Overture countries: say that a maritime area is the land plus the territorial sea.

The live collection called the maritime area "a separate maritime area ... its territorial
waters", and the `class` column said "maritime=maritime / territorial-waters area". Measured on
countries.parquet (2026-02-18.0): every one of the 159 maritime polygons contains its country's
land polygon (the intersection is 100% of the land area; the median maritime polygon is 1.30x its
land). Edits the LIVE collection in place; refuses unless each old phrase occurs exactly once.

Usage: fix_maritime.py <stac-collection.json>
"""
import json
import sys

DESC_OLD = ("Overture stores every division as a land area (`class = 'land'`) and, for a coastal "
            "division, a separate maritime area (`class = 'maritime'`, its territorial waters) with "
            "the same `division_id`.")
DESC_NEW = ("Overture stores every division as a land area (`class = 'land'`) and, for a coastal "
            "division, a maritime area (`class = 'maritime'`) with the same `division_id`. The "
            "maritime area is the land plus the territorial sea, not the sea alone: each of the 159 "
            "maritime polygons contains its country's land polygon. For the territorial sea alone, "
            "subtract the land polygon from the maritime one.")
HEX_OLD = "the 159 maritime territorial-waters features (class='maritime')"
HEX_NEW = "the 159 maritime features (class='maritime', the land plus the territorial sea)"
CLASS_NEW = "Division class. Values: land=land area, maritime=land area plus territorial sea."


def once(text, old, where):
    if text.count(old) != 1:
        sys.exit(f"{where}: old text not found exactly once")
    return text


def main(path):
    c = json.load(open(path))
    c["description"] = once(c["description"], DESC_OLD, "description").replace(DESC_OLD, DESC_NEW)
    h = c["assets"]["countries-hex"]
    h["description"] = once(h["description"], HEX_OLD, "countries-hex").replace(HEX_OLD, HEX_NEW)
    n = 0
    for col in c.get("table:columns", []):
        if col["name"] == "class":
            col["description"] = CLASS_NEW
            n += 1
    if n != 1:
        sys.exit("class column not found exactly once in the dictionary")
    with open(path, "w") as f:
        json.dump(c, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("edited", path)


if __name__ == "__main__":
    main(sys.argv[1])
