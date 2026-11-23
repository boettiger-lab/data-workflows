#!/usr/bin/env python3
"""Citation and edition fixes left open on #949, applied to LIVE files in place.

    fix949.py BUCKET_PATH LOCAL_FILE

- PAD-US 4.1 (5 collections): USGS's suggested citation for the 4.1 Full Inventory Database
  (ScienceBase item 652d4fc5d34e44db0e2ee45e) and its DOI.
- roo-cjest: the hex asset said CEJST v2.0. The source layer was created 2023-11-09
  (ArcGIS item 0580f8dd5a7944aa8689a9d15e8ec3f0), before CEJST 2.0 (December 2024): v1.0.
- NCP: NCP_biod_nathab_sum.tif and NCP_only_2km_sum.tif are byte-identical (MD5) to Zenodo
  10.5281/zenodo.7853188 (v3.0), the data for Chaplin-Kramer et al. 2023, not the 2019 paper.

Each edit asserts the text it replaces, or that it is already applied, so a second run is a no-op.
"""
import json
import sys

SCI = "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"
PADUS_CIT = ("U.S. Geological Survey (USGS) Gap Analysis Project (GAP), 2024, Protected Areas "
             "Database of the United States (PAD-US) 4.1: U.S. Geological Survey data release, "
             "https://doi.org/10.5066/P96WBCHS.")
NCP_DATA_CIT = ("Neugarten, R. A., Chaplin-Kramer, R., Sharp, R. P., Schuster, R., Strimas-Mackey, M., "
                "Roehrdanz, P. R., Mulligan, M., van Soesbergen, A., Hole, D., Kennedy, C. M., "
                "Oakleaf, J. R., Johnson, J. A., Kiesecker, J., Polasky, S., Hanson, J. O., & "
                "Rodewald, A. D. (2022). Mapping the planet's critical areas for biodiversity and "
                "people (Version 3.0) [Dataset]. Zenodo. https://doi.org/10.5281/zenodo.7853188")
NCP_PAPER = {
    "citation": ("Chaplin-Kramer, R., Neugarten, R. A., Sharp, R. P., Collins, P. M., Polasky, S., "
                 "Hole, D., Schuster, R., Strimas-Mackey, M., Mulligan, M., Brandon, C., Diaz, S., "
                 "Fluet-Chouinard, E., Gorenflo, L. J., Johnson, J. A., Kennedy, C. M., Keys, P. W., "
                 "Longley-Wood, K., McIntyre, P. B., Noon, M., et al. (2023). Mapping the planet's "
                 "critical natural assets. Nature Ecology & Evolution, 7(1), 51–61."),
    "doi": "10.1038/s41559-022-01934-5",
}
NCP_OLD = "derived from Chaplin-Kramer et al. (2019)"
NCP_NEW = ("derived from Chaplin-Kramer et al. (2023), Mapping the planet's critical natural assets "
           "(data: Neugarten et al. 2022, Zenodo v3.0)")
NCP_DEAD = "https://doi.org/10.1126/science.awx9597"   # 404
NCP_2019 = "https://doi.org/10.1126/science.aaw3372"
NCP_SRC = {"rel": "source", "href": "https://doi.org/10.5281/zenodo.7853188", "type": "text/html",
           "title": "Zenodo data release v3.0 (Neugarten et al. 2022)"}


def swap(text, old, new, what):
    if new in text:
        return text
    assert old in text, f"{what}: expected text not found: {old!r}"
    return text.replace(old, new)


def set_source(doc, old_hrefs):
    links = [l for l in doc["links"] if not (l["rel"] == "source" and l["href"] in old_hrefs)]
    if not any(l["href"] == NCP_SRC["href"] for l in links):
        links.append(dict(NCP_SRC))
    doc["links"] = links


path, local = sys.argv[1], sys.argv[2]

if path.endswith("README.md"):
    t = open(local).read()
    t = swap(t, "Global NCP indicators from Chaplin-Kramer et al. (2019)",
             "Global NCP indicators from Chaplin-Kramer et al. (2023)", path)
    t = swap(t, "Chaplin-Kramer, R., et al. (2019). Global modeling of nature's contributions to people.\n"
                "*Science*, 366(6462), 255–258. doi:10.1126/science.aaw3372",
             "Neugarten, R. A., et al. (2022). Mapping the planet's critical areas for biodiversity and\n"
             "people (Version 3.0) [Dataset]. Zenodo. doi:10.5281/zenodo.7853188\n\n"
             "Chaplin-Kramer, R., et al. (2023). Mapping the planet's critical natural assets.\n"
             "*Nature Ecology & Evolution*, 7(1), 51–61. doi:10.1038/s41559-022-01934-5", path)
    open(local, "w").write(t)
    sys.exit(0)

doc = json.load(open(local))
if path.startswith("public-padus/padus-4-1/"):
    assert doc.get("sci:citation") in (None, PADUS_CIT), f"{path}: has another citation"
    doc["sci:citation"] = PADUS_CIT
    doc["sci:doi"] = "10.5066/P96WBCHS"
elif path == "public-rivers/american-rivers/roo-cjest/stac-collection.json":
    a = doc["assets"]["roo-cjest-hex"]
    a["description"] = swap(a["description"], "(CEJST v2.0 indicators)", "(CEJST v1.0 indicators)", path)
elif path == "public-ncp/biodiversity-indicators/stac-collection.json":
    doc["description"] = swap(doc["description"], NCP_OLD, NCP_NEW, path)
    doc["sci:citation"] = NCP_DATA_CIT
    doc["sci:doi"] = "10.5281/zenodo.7853188"
    doc["sci:publications"] = [NCP_PAPER]
    set_source(doc, {NCP_2019})
elif path == "public-ncp/stac-collection.json":
    doc["description"] = swap(doc["description"], NCP_OLD, NCP_NEW, path)
    set_source(doc, {NCP_DEAD})
else:
    sys.exit(f"{path}: no fix listed")

if "sci:citation" in doc and SCI not in doc.setdefault("stac_extensions", []):
    doc["stac_extensions"].append(SCI)
open(local, "w").write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
