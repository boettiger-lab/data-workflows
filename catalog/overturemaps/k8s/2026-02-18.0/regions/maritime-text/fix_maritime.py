"""Overture regions (and countries `is_territorial`): what a maritime area and the territorial flag are.

Measured on the 2026-02-18.0 GeoParquet:
  * every maritime polygon contains its division's land polygon: 798 of 798 regions (and 159 of
    159 countries), so a maritime area is the land plus the territorial sea, not the sea alone;
  * is_territorial is false only for a coastal division's land polygon. It is true for the
    maritime polygon and for an inland division's land polygon (regions: 798 + 3,110 true,
    798 false; countries: 159 + 60 true, 159 false). It marks the polygon that is the division's
    full territory; it does not mirror is_land.

  fix_maritime.py regions   <stac-collection.json>   description, class, is_territorial
  fix_maritime.py countries <stac-collection.json>   is_territorial only (#955 fixed the rest)

Edits the LIVE collection in place; refuses unless each old text occurs exactly once.
"""
import json
import sys

DESC_OLD = ("Overture stores every division as a land area (`class = 'land'`) and, for a coastal "
            "division, a separate maritime area (`class = 'maritime'`, its territorial waters) with "
            "the same `division_id`.")
DESC_NEW = ("Overture stores every division as a land area (`class = 'land'`) and, for a coastal "
            "division, a maritime area (`class = 'maritime'`) with the same `division_id`. The "
            "maritime area is the land plus the territorial sea, not the sea alone: each of the 798 "
            "maritime polygons contains its region's land polygon. For the territorial sea alone, "
            "subtract the land polygon from the maritime one.")
CLASS = {"regions": ("Region geometry class. Valid values: land=land area of the region, "
                     "maritime=maritime/ocean area of the region.",
                     "Region geometry class. Valid values: land=land area of the region, "
                     "maritime=land area plus territorial sea.")}
TERR = {"regions": ("True if the region is a territorial (maritime) claim.",),
        "countries": ("True for the territorial (land) area; false for the maritime area. "
                      "Mirrors is_land in this dataset.",)}
TERR_NEW = ("True if this polygon is the division's full territory: the maritime polygon (land plus "
            "territorial sea) for a coastal division, the land polygon for an inland one. False only "
            "for a coastal division's land polygon.")


def set_col(c, name, old, new):
    cols = [x for x in c.get("table:columns", []) if x["name"] == name]
    if len(cols) != 1 or cols[0].get("description") != old:
        sys.exit(f"{name}: column text not as expected")
    cols[0]["description"] = new


def main(which, path):
    c = json.load(open(path))
    if which == "regions":
        if c["description"].count(DESC_OLD) != 1:
            sys.exit("description: old text not found exactly once")
        c["description"] = c["description"].replace(DESC_OLD, DESC_NEW)
        set_col(c, "class", *CLASS["regions"])
    elif which != "countries":
        sys.exit("usage: fix_maritime.py regions|countries <stac-collection.json>")
    set_col(c, "is_territorial", TERR[which][0], TERR_NEW)
    with open(path, "w") as f:
        json.dump(c, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("edited", which, path)


if __name__ == "__main__":
    main(*sys.argv[1:3])
