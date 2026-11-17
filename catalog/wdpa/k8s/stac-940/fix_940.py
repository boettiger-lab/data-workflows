"""#940 items 2 and 4: metadata-only edits to two LIVE collections.

  fix_940.py wdpa   <stac-collection.json>   Ramsar cross-reference + flat GeoParquet CRS
  fix_940.py ramsar <stac-collection.json>   Ramsar cross-reference to WDPA

Each edit refuses unless its anchor occurs exactly once and the new text is not yet present,
so a re-run changes nothing.
"""
import json
import sys

WDPA_RAMSAR = (
    "\n\nWDPA includes Ramsar sites as records with `DESIG_ENG = 'Wetland of International "
    "Importance (Ramsar Site)'` (`DESIG_TYPE = 'International'`): 2,179 sites with polygon "
    "boundaries in the June 2026 edition. The separate `wetlands-ramsar` collection is the "
    "Ramsar Convention Secretariat's own site list (2,551 sites, 445 of them recorded only as "
    "points). The two share no identifier. WDPA's records are Ramsar sites as counted in "
    "protected-area statistics; `wetlands-ramsar` is the complete list of Ramsar sites.")
RAMSAR_WDPA = (
    "\n\nWDPA (collection `wdpa`) also records Ramsar sites, as `DESIG_ENG = 'Wetland of "
    "International Importance (Ramsar Site)'`: 2,179 sites with polygon boundaries in its June "
    "2026 edition. This collection is the Ramsar Secretariat's site list (2,551 sites). The two "
    "share no identifier. For Ramsar sites within WDPA or protected-area statistics, use the "
    "WDPA records.")
CRS_OLD = "Full WDPA attribute table with geometry (CRS OGC:CRS84, WKB)."
CRS_NEW = (
    "Full WDPA attribute table with geometry: column `SHAPE`, WKB, longitude/latitude order. "
    "The GeoParquet metadata declares the CRS as EPSG:4326, so DuckDB reads `SHAPE` as "
    "`GEOMETRY('EPSG:4326')`. Layers declared `OGC:CRS84`, such as `wetlands-ramsar`, hold the "
    "same kind of coordinates, but DuckDB will not compare the two types until one is cast "
    "with `ST_SetCRS`.")
WDPA_ANCHOR = "See the hex asset notes."


def append_after(text, anchor, new):
    if new.strip() in text:
        sys.exit("already applied")
    if text.count(anchor) != 1:
        sys.exit(f"anchor not found exactly once: {anchor!r}")
    return text.replace(anchor, anchor + new)


def main(which, path):
    c = json.load(open(path))
    if which == "wdpa":
        c["description"] = append_after(c["description"], WDPA_ANCHOR, WDPA_RAMSAR)
        a = c["assets"]["wdpa-parquet"]
        if a["description"].count(CRS_OLD) != 1:
            sys.exit("wdpa-parquet: CRS sentence not found exactly once")
        a["description"] = a["description"].replace(CRS_OLD, CRS_NEW)
    elif which == "ramsar":
        if RAMSAR_WDPA.strip() in c["description"]:
            sys.exit("already applied")
        c["description"] = c["description"].rstrip() + RAMSAR_WDPA
    else:
        sys.exit("usage: fix_940.py wdpa|ramsar <stac-collection.json>")
    with open(path, "w") as f:
        json.dump(c, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("edited", which, path)


if __name__ == "__main__":
    main(*sys.argv[1:3])
