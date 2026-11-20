"""Record the Red List version (2025-1) on the IUCN richness collection and README (#949).

The version comes from the person who downloaded the rasters; the files carry none.
usage: set_version.py collection <path> | readme <path>
"""
import json, sys

VER = "2025-1"
CITE = "IUCN. 2025. The IUCN Red List of Threatened Species. Version 2025-1. https://www.iucnredlist.org."
OLD_DESC = ("the files carry the year only, and the Red List version they were built from is "
            "not recorded")
NEW_DESC = ("built from Red List version 2025-1, as recorded by the person who downloaded them; "
            "the files themselves carry no version")
OLD_MD = "The files carry the year only; the Red List version they were built from is not recorded."
NEW_MD = ("Built from Red List version 2025-1, as recorded by the person who downloaded them; "
          "the files themselves carry no version.")
OLD_CITE_MD = "IUCN. 2025. The IUCN Red List of Threatened Species. <https://www.iucnredlist.org>"
NEW_CITE_MD = "IUCN. 2025. The IUCN Red List of Threatened Species. Version 2025-1. <https://www.iucnredlist.org>"
EXT = "https://stac-extensions.github.io/version/v1.2.0/schema.json"


def swap(s, old, new):
    if new in s:
        return s
    assert s.count(old) == 1, f"expected one occurrence of: {old!r}"
    return s.replace(old, new)


mode, path = sys.argv[1], sys.argv[2]
if mode == "collection":
    d = json.load(open(path))
    d["version"] = VER
    d["sci:citation"] = CITE
    d["description"] = swap(d["description"], OLD_DESC, NEW_DESC)
    if EXT not in d["stac_extensions"]:
        d["stac_extensions"].append(EXT)
    json.dump(d, open(path, "w"), indent=2, ensure_ascii=False)
elif mode == "readme":
    s = open(path).read()
    s = swap(swap(s, OLD_MD, NEW_MD), OLD_CITE_MD, NEW_CITE_MD)
    open(path, "w").write(s)
else:
    sys.exit(f"unknown mode {mode}")
