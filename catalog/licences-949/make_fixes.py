"""Writes fixes.json and collections.txt (#949). Run from this directory."""
import json
F = []
ODBL = {"rel": "license", "href": "https://opendatacommons.org/licenses/odbl/1-0/", "type": "text/html",
        "title": "Open Database License (ODbL) 1.0"}
OVT = {"rel": "license", "href": "https://docs.overturemaps.org/attribution/", "type": "text/html",
       "title": "Overture Maps attribution and per-theme licences"}
for c in ("countries", "regions", "counties"):
    F.append({
        "collection": f"public-overturemaps/2026-02-18.0/{c}/stac-collection.json",
        "license": "ODbL-1.0", "license_links": [ODBL, OVT],
        "description_append": "**Licence:** Overture publishes the Divisions theme under the Open Database "
            "License (ODbL 1.0), not CDLA-Permissive-2.0, which covers other Overture themes. Attribution is "
            "owed to © OpenStreetMap contributors (ODbL), and to geoBoundaries, Esri Community Maps "
            "contributors and Land Information New Zealand (LINZ), each under CC BY 4.0.",
        "evidence": "https://docs.overturemaps.org/attribution/ (Divisions: 'License for theme: ODbL', checked 2026-11-17)"})
BYSA = {"rel": "license", "href": "https://creativecommons.org/licenses/by-sa/4.0/", "type": "text/html",
        "title": "CC BY-SA 4.0"}
LMTOS = {"rel": "license", "href": "https://landmark.wridata.org/LandMark/LandMark_Terms_of_Service_202408.pdf",
         "type": "application/pdf", "title": "LandMark Terms of Service (August 2024)"}
for c in ("iplc-poly", "iplc-pt", "indicative-poly", "indicative-pt"):
    F.append({
        "collection": f"public-indigenous/landmark/{c}-stac.json",
        "license": "CC-BY-SA-4.0", "license_links": [BYSA, LMTOS],
        "description_replace": [["License: CC BY 4.0.", "License: CC BY-SA 4.0, under LandMark's Terms of Service."]],
        "evidence": "https://www.landmarkmap.org/data-methods/access-data (both layers link CC BY-SA 4.0 and the Terms of Service PDF, checked 2026-11-17)"})
WA = {"2021": "4914cbc7cacf4173a1bc858f7c7ca514", "2022": "5591faef63534337a7c28beaa73f3bac",
      "2023": "19143af5b1ee410fa9b2808f5aa76820", "2024": "29dd1328c36a467991a1a1ad8b1caefa",
      "2025": "b040aa24bd91472282f47d24be0302de", "all-years": "b040aa24bd91472282f47d24be0302de"}
for y, item in WA.items():
    F.append({
        "collection": f"public-ca30x30/williamson-act/{y}/stac-collection.json",
        "license": "other",
        "license_links": [{"rel": "license", "href": f"https://www.arcgis.com/home/item.html?id={item}",
                           "type": "text/html", "title": "California Department of Conservation terms of use (item licence)"}],
        "description_append": "**Terms of use:** the Department of Conservation publishes this data as copyright, "
            "all rights reserved, not in the public domain. Its terms say that fair use for non-commercial, "
            "educational, research or scientific purposes is not a violation of copyright, and that no part of the "
            "data may be reproduced, transmitted or distributed for any purpose without the express written "
            "permission of the Department of Conservation, Division of Land Resource Protection.",
        "evidence": f"https://www.arcgis.com/sharing/rest/content/items/{item}?f=json licenseInfo (checked 2026-11-17)"})
ICCA = {"rel": "license", "href": "https://www.iccaregistry.org/en/terms-conditions", "type": "text/html",
        "title": "ICCA Registry Terms and Conditions"}
for c in ("icca-polygon", "icca-point"):
    F.append({
        "collection": f"public-icca/icca-registry/{c}/stac-collection.json",
        "license": "other", "license_links": [ICCA],
        "description_append": "**Terms of use:** the ICCA Registry's own Terms and Conditions apply, not the "
            "Protected Planet terms. They prohibit commercial use without UNEP-WCMC's prior written permission, "
            "and prohibit redistributing the Registry data, including as web downloads or web services, without "
            "permission from UNEP-WCMC.",
        "evidence": "https://www.iccaregistry.org/en/terms-conditions (checked 2026-11-17)"})
json.dump(F, open("fixes.json", "w"), indent=1, ensure_ascii=False)
open("collections.txt", "w").write("".join(x["collection"] + "\n" for x in F))
print(len(F), "fixes")
