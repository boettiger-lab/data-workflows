"""Replace the WDPA res-8 join sentence (#940) in the live STAC collection and README.

The old sentence ("When the other dataset has only resolution 8 or coarser, the join is
necessarily at that resolution.") was read as permission to count any h8 cell a parcel
touches as protected. The replacement states the fact about the data instead: a small
parcel's h8 is a parent cell, not a covered cell.

Usage: fix_res8.py <stac-collection.json> <README.md>   (both edited in place)
Exits non-zero unless each old sentence occurs exactly once, so a re-run is refused.
"""
import json
import sys

STAC_OLD = ("When the other dataset has only resolution 8 or coarser, "
            "the join is necessarily at that resolution.")
STAC_NEW = ("For a parcel indexed at resolution 9, h8 is the parent of its h9 cells, not a "
            "cell the parcel covers: the parcel may cover only one of that cell's seven h9 "
            "children. Only a large parcel's h8 cell (h9 NULL) is covered in full. WDPA "
            "coverage of a resolution-8 cell is therefore a fraction, the share of its seven "
            "h9 children inside a parcel (all seven for a large parcel's cell), not a "
            "yes-or-no for any parcel touching it.")

README_OLD = ("A dataset indexed only at resolution 8 or coarser can be joined\n"
              "only at that resolution.")
README_NEW = ("For a parcel indexed at resolution 9, `h8` is the parent of its `h9` cells, not a\n"
              "cell the parcel covers: the parcel may cover only one of that cell's seven `h9`\n"
              "children. Only a large parcel's `h8` cell (`h9` NULL) is covered in full. WDPA\n"
              "coverage of a resolution-8 cell is therefore a fraction, the share of its seven\n"
              "`h9` children inside a parcel (all seven for a large parcel's cell), not a\n"
              "yes-or-no for any parcel touching it.")


def main(stac_path, readme_path):
    c = json.load(open(stac_path))
    d = c["assets"]["wdpa-hex"]["description"]
    if d.count(STAC_OLD) != 1:
        sys.exit("wdpa-hex description: old sentence not found exactly once")
    c["assets"]["wdpa-hex"]["description"] = d.replace(STAC_OLD, STAC_NEW)
    blob = json.dumps(c)
    if "necessarily at that resolution" in blob:
        sys.exit("old wording still present elsewhere in the collection")
    with open(stac_path, "w") as f:
        json.dump(c, f, indent=2, ensure_ascii=False)
        f.write("\n")

    r = open(readme_path).read()
    if r.count(README_OLD) != 1:
        sys.exit("README: old sentence not found exactly once")
    with open(readme_path, "w") as f:
        f.write(r.replace(README_OLD, README_NEW))
    print("edited", stac_path, readme_path)


if __name__ == "__main__":
    main(*sys.argv[1:3])
