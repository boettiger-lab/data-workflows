"""Writes fixes.json, collections.txt, readme-fixes.json and files.txt (#949, Other). Run from this directory.

ecs-pol-type.json was built by
  scripts/default-style.py build https://s3-west.nrp-nautilus.io/public-high-seas/ecs/stac-collection.json \
    --asset ecs-pmtiles --column POL_TYPE --kind categorical \
    --tooltip GEONAME,POL_TYPE,SOVEREIGN1,TERRITORY1,AREA_KM2 --out DIR
"""
import json

F = []

# ECS: the default style was one colour with no reason; POL_TYPE (8 claim types) is the variable.
F.append({
    "collection": "public-high-seas/ecs/stac-collection.json",
    "evidence": "verify-stac style-single-colour-default (HARD); POL_TYPE has 8 values in the GeoParquet "
                "(Overlapping claim 63, CLCS Submission 42, CLCS Recommendation 24, DOALOS Deposit 10, "
                "Non-UNCLOS Claim 3, Joint CLCS Recommendation 2, Joint CLCS Submission 2, Joint DOALOS Deposit 1)",
    "assets_set": {"style-ecs-pol-type": {
        "href": "https://s3-west.nrp-nautilus.io/public-high-seas/ecs/styles/ecs-pol-type.json",
        "type": "application/vnd.mapbox.style+json",
        "title": "Extended Continental Shelf PMTiles by POL_TYPE",
        "description": "Features coloured by POL_TYPE, 8 values.",
        "roles": ["style", "default"]}},
    "asset_roles": {"style-ecs": ["style"]},
})

# Missouri CCS: the licence link and the strategy PDF are 404. No data licence exists; the PI
# cleared redistribution with attribution (#384, 2026-10-12).
CCS = "https://gisblue.mdc.mo.gov/arcgis/rest/services/Land_Cover/CCS/MapServer"
CCS_PDF = "https://mdc.mo.gov/sites/default/files/2024-03/CCS.pdf"
for c in ("cave-karst-coa", "forest-woodland-coa", "glade-coa", "grassland-prairie-savanna-coa",
          "priority-geographies", "stream-reach-coa", "wetland-coa"):
    F.append({
        "collection": f"public-swap/missouri/ccs-2022/{c}/stac-collection.json",
        "evidence": "mdc.mo.gov/your-property/improve-your-property/conservation-planning-missouri and "
                    "mdc.mo.gov/sites/default/files/2022-04/2022-Missouri-CCS.pdf return 404 (2026-11-17); "
                    f"{CCS} copyrightText 'Missouri Department of Conservation (MDC)', no licence; {CCS_PDF} "
                    "(200, the same strategy document); redistribution cleared by the PI in #384",
        "license": "other",
        "license_links": [{"rel": "license", "href": f"{CCS}?f=pjson", "type": "application/json",
                           "title": "MDC CCS map service: credits MDC and states no data licence"}],
        "description_replace": [[
            "The source agency publishes no formal data licence for this layer. It may be used and "
            "redistributed with attribution to the Missouri Department of Conservation.",
            "The Missouri Department of Conservation publishes no data licence for this layer; its map "
            "service credits \"Missouri Department of Conservation (MDC)\". We redistribute it with "
            "attribution to MDC, as cleared by the lab's PI (boettiger-lab/data-workflows#384)."]],
        "set": {"sci:publications": [{"citation":
            "Missouri Department of Conservation. (2020). The Missouri Comprehensive Conservation Strategy: "
            "Responsibly addressing the challenges and opportunities of modern conservation through an "
            f"integrated strategic approach. Missouri Department of Conservation. {CCS_PDF}"}]},
    })

# FAO RFMO/VME: both landing pages are gone (404 / soft 404); the WFS services we read are live.
F.append({
    "collection": "public-high-seas/rfmo/stac-collection.json",
    "evidence": "www.fao.org/fishery/en/rfb redirects to a 'Page not found' page; "
                "www.fao.org/in-action/vulnerable-marine-ecosystems/ returns 404 (2026-11-17); both WFS "
                "GetCapabilities documents respond",
    "links_replace": {
        "https://www.fao.org/fishery/en/rfb": {
            "rel": "derived_from", "type": "application/xml",
            "href": "https://www.fao.org/fishery/geoserver/fifao/ows?service=WFS&request=GetCapabilities",
            "title": "FAO FIGIS GeoServer WFS (RFB areas of competence, fifao:RFB_COMP)"},
        "https://www.fao.org/in-action/vulnerable-marine-ecosystems/": {
            "rel": "derived_from", "type": "application/xml",
            "href": "https://www.fao.org/fishery/geoserver/vme/ows?service=WFS&request=GetCapabilities",
            "title": "FAO Vulnerable Marine Ecosystems database GeoServer WFS (VME closures)"}},
    "links_add": [{"rel": "about", "href": "https://www.fao.org/fishery/geoserver/factsheets/vme.html",
                   "type": "text/html", "title": "FAO Vulnerable Marine Ecosystems Database viewer"}],
})

# BLM Utah Federal Minerals: the service we read now needs a token; BLM's public one is renamed.
OLD_UT = "https://gis.blm.gov/utarcgis/rest/services/Lands/BLM_Utah_Federal_Minerals_Map_Service/FeatureServer"
UT_ITEM = "https://www.arcgis.com/home/item.html?id=a9059e4665fe4a8190c6d90fd767a591"
F.append({
    "collection": "public-blm/utah-federal-mineral-estate/stac-collection.json",
    "evidence": f"{OLD_UT}?f=json returns 499 Token Required (2026-11-17); {UT_ITEM} (BLM Utah Federal Minerals "
                "Estate, owner blm_arcgis_hub_ut, service BLM_UT_Federal_Minerals/FeatureServer)",
    "providers": {"U.S. Bureau of Land Management, Utah State Office": {
        "name": "U.S. Bureau of Land Management, Utah State Office", "roles": ["producer", "licensor"],
        "url": UT_ITEM}},
    "links_replace": {OLD_UT: {"rel": "about", "href": UT_ITEM, "type": "text/html",
                               "title": "BLM Utah Federal Minerals Estate (ArcGIS item; current public service)"}},
    "description_append": (
        "The service this snapshot was read from (BLM_Utah_Federal_Minerals_Map_Service) now requires a "
        f"sign-in. BLM's public service is BLM_UT_Federal_Minerals ({UT_ITEM})."),
})

# Missing citations.
F.append({
    "collection": "public-wdpa/wdoecm-may-2026/stac-collection.json",
    "evidence": "the collection's own README citation, matching the WDPA citation form on public-wdpa/wdpa",
    "set": {"sci:citation": "UNEP-WCMC and IUCN (2026), Protected Planet: The World Database on Other Effective "
                            "Area-Based Conservation Measures (WD-OECM) [On-line], May 2026, Cambridge, UK: "
                            "UNEP-WCMC and IUCN. Available at: www.protectedplanet.net."},
})
SGID = ("Utah Geospatial Resource Center. Utah BLM Monuments and NCAs Historic [Data set]. Utah SGID. "
        "https://www.arcgis.com/home/item.html?id=d5560a571a86436fbb3a664c3edd5488")
PADUS = ("U.S. Geological Survey (USGS) Gap Analysis Project (GAP), 2020, Protected Areas Database of the "
         "United States (PAD-US) 2.1: U.S. Geological Survey data release, https://doi.org/10.5066/P92QM3NT; "
         "U.S. Geological Survey (USGS) Gap Analysis Project (GAP), 2024, Protected Areas Database of the "
         "United States (PAD-US) 4.1: U.S. Geological Survey data release, https://doi.org/10.5066/P96WBCHS")
BLM_NM = ("U.S. Bureau of Land Management, Utah State Office. BLM Utah National Monuments and NCAs [Data set]. "
          "https://gis.blm.gov/utarcgis/rest/services/NLCS/BLM_UT_NMNCA/FeatureServer/1")
for coll, proc, fr, title in (
        ("public-utah/bears-ears/stac-collection.json", "11043", "91 FR 45169",
         "Modifying the Bears Ears National Monument",),
        ("public-utah/grand-staircase-escalante/stac-collection.json", "11044", "91 FR 45179",
         "Modifying the Grand Staircase-Escalante National Monument")):
    F.append({
        "collection": coll,
        "evidence": "sources named in the description; DOIs resolved at doi.org; Federal Register API "
                    "(proclamation number, citation, dates)",
        "set": {"sci:citation": f"{SGID}; {PADUS}; {BLM_NM}; Proclamation {proc} of July 13, 2026, {title}, "
                                f"{fr} (July 17, 2026)."},
    })

json.dump(F, open("fixes.json", "w"), indent=1, ensure_ascii=False)
open("collections.txt", "w").write("".join(x["collection"] + "\n" for x in F))
open("files.txt", "w").write("ecs-pol-type.json public-high-seas/ecs/styles/ecs-pol-type.json\n")

# BLM READMEs: gis.blm.gov/nlsdb/.../HUB moved to nlsdbpubgis.blm.gov/arcgishub/.../HUB.
OLD, NEW = "https://gis.blm.gov/nlsdb/rest/services/HUB/", "https://nlsdbpubgis.blm.gov/arcgishub/rest/services/HUB/"
R = [{"path": f"public-blm/{c}/README.md", "replace": [[OLD + s, NEW + s] for s in svcs]} for c, svcs in (
    ("acquisitions", ["BLM_Natl_MLRS_Acquisitions/FeatureServer/1"]),
    ("locatable-operations", ["BLM_Natl_MLRS_Locatable_Notices/FeatureServer/0",
                              "BLM_Natl_MLRS_Locatable_Plans_Of_Operations/FeatureServer/0"]),
    ("lua-row", ["BLM_Natl_MLRS_LUA_ROW/FeatureServer/0"]),
    ("lua-leases-permits-easements", ["BLM_Natl_MLRS_LUA_Leases_Permits_Esmts/FeatureServer/0"]),
    ("mining-claims", ["BLM_Natl_MLRS_Mining_Claims_Not_Closed/FeatureServer/0",
                       "BLM_Natl_MLRS_Mining_Claims_Closed/FeatureServer/0"]),
    ("oil-gas-leases", ["BLM_Natl_MLRS_Oil_and_Gas_Leases/FeatureServer/0"]))]
R.append({"path": "public-blm/utah-federal-mineral-estate/README.md", "replace": [[
    "current as of\n2026-03-01.\n\nThe raw GeoJSON",
    "current as of\n2026-03-01. "
    "That service now requires a sign-in; BLM's public service is\n"
    f"[BLM_UT_Federal_Minerals]({UT_ITEM}).\n\nThe raw GeoJSON"]]})
json.dump(R, open("readme-fixes.json", "w"), indent=1, ensure_ascii=False)
print(len(F), "collections,", len(R), "READMEs")
