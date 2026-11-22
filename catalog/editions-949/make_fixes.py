"""Writes fixes.json, collections.txt and readme-fixes.json (#949, editions). Run from this directory."""
import json

F = []

# IUCN richness: "Version 2025.1" on the description, "Version 2025-2" in the citation; neither is
# recorded on the files, and IUCN's download pages refuse automated reads, so state what is known.
IUCN_CITE = "IUCN. 2025. The IUCN Red List of Threatened Species. https://www.iucnredlist.org."
F.append({
    "collection": "public-iucn/stac-collection.json",
    "evidence": "s3://public-iucn/raw/richness/*_2025.tif, staged 2025-12-19; file names carry the year only; "
                "the description said Version 2025.1 and the citation Version 2025-2, with no record of either",
    "description_replace": [[
        "IUCN Red List of Threatened Species (Version 2025.1)",
        "IUCN Red List of Threatened Species (IUCN's 2025 richness maps, staged 2025-12-19; the files carry "
        "the year only, and the Red List version they were built from is not recorded)"]],
    "set": {"sci:citation": IUCN_CITE},
})

# NLCD: USGS's own suggested citation for the release we hold.
F.append({
    "collection": "public-land-cover/nlcd/stac-collection.json",
    "evidence": "https://www.sciencebase.gov/catalog/item/655ceb8ad34ee4b6e05cc51a (citation field; revision 2026-06-30); "
                "doi.org/10.5066/P143HE8T resolves to the Collection 1 Land Cover page",
    "set": {"sci:citation": "U.S. Geological Survey, 2024, Annual NLCD Collection 1 Science Products (ver. 1.2, "
                            "June 2026): U.S. Geological Survey data release, https://doi.org/10.5066/P94UXNTS."},
    "links_add": [{"rel": "related", "href": "https://doi.org/10.5066/P143HE8T", "type": "text/html",
                   "title": "Annual NLCD Collection 1 Land Cover, Conterminous United States (product DOI)"}],
})

# SILVIS WUI: we hold the 50-state v4 file; the cited archive is CONUS only; no CC BY grant.
SILVIS_META = ("https://geoserver.silvis.forest.wisc.edu/geodata/wui_change_2020_v4/"
               "CONUS_WUI_block_1990_2020_change_v4_FGDC_MetadataUpdate.xml")
F.append({
    "collection": "public-wui/stac-collection.json",
    "evidence": "https://silvis.forest.wisc.edu/data/wui-change/ ('Version 4 – last updated February 2025', "
                "'United States (50 States) FileGDB'); our source zip Last-Modified 2025-02-21; "
                f"{SILVIS_META} (useconst 'None. Acknowledgment ... would be appreciated.'); "
                "RDS-2015-0012-4 metadata (bounding box conterminous US; useconst 'can be used without "
                "additional permissions or fees')",
    "license": "other",
    "license_links": [
        {"rel": "license", "href": SILVIS_META, "type": "application/xml",
         "title": "SILVIS WUI v4 metadata: use constraints 'None'"},
        {"rel": "license", "href": "https://doi.org/10.2737/RDS-2015-0012-4", "type": "text/html",
         "title": "Forest Service Research Data Archive: usable without additional permissions or fees"}],
    "links_add": [{"rel": "via", "href": "https://silvis.forest.wisc.edu/data/wui-change/", "type": "text/html",
                   "title": "SILVIS Lab WUI change 1990-2020 downloads (v4, last updated February 2025)"}],
    "description_append": (
        "**Edition and coverage:** this is SILVIS Lab's 50-state v4 geodatabase "
        "(US_WUI_block_1990_2020_change_v4_gdb.zip, \"last updated February 2025\"). The Forest Service "
        "archive cited here (RDS-2015-0012-4, 2023) holds the same v4 method for the conterminous US only; "
        "blocks outside it come from the SILVIS release.\n\n"
        "**Terms:** no licence is granted. The SILVIS metadata states use constraints \"None\" and asks that "
        "the USDA Forest Service Northern Research Station be acknowledged; the Forest Service archive says "
        "the data \"can be used without additional permissions or fees\" and asks that the citation be used."),
})

# ParkServe: ids say 2025, the data is TPL's 2026 release.
for c in ("parks", "service-areas", "places", "urban-areas", "priority-areas-place",
          "priority-areas-urban-area", "parkscore"):
    F.append({
        "collection": f"public-tpl/parkserve-2025/{c}/stac-collection.json",
        "evidence": "https://parkserve.tpl.org/downloads/ParkServe_Documentation_2026.pdf (Last-Modified 2026-05-18); "
                    "retrieved 2026-07 from the ParkServe FeatureServer",
        "description_append": (
            "**Edition:** this is Trust for Public Land's 2026 ParkServe release (documentation "
            "https://parkserve.tpl.org/downloads/ParkServe_Documentation_2026.pdf). The \"2025\" in the "
            "collection id and path is a naming artifact, kept so existing links keep working."),
    })

# CA SGCN v4: the source service now needs a token; CDFW's public layer is SGCN_Final_red_gdb.
NEW_SGCN = "https://www.arcgis.com/home/item.html?id=ab68287bb4b2492ea39a313b52746a2b"
for c in ("sgcn-ranges", "sgcn-species", "sgcn-species-units"):
    F.append({
        "collection": f"public-swap/california/swap-2025/{c}/stac-collection.json",
        "evidence": "services2.arcgis.com/Uq9r85Potqm3MfRV/.../SWAP_SGCN_V4_gdb/FeatureServer returns 499 Token "
                    f"Required (2026-11-17); {NEW_SGCN} (SGCN_Final_red_gdb, created 2026-06-24, 1,436 ranges, "
                    "CC BY 4.0)",
        "description_append": (
            "**Edition:** built from CDFW's SGCN v4 service (SWAP_SGCN_V4_gdb), which is no longer public. "
            "CDFW now publishes SGCN_Final_red_gdb (June 2026; 1,436 range polygons that add plants and "
            f"invertebrates; {NEW_SGCN}). This collection does not yet reflect that final release."),
        "links_add": [{"rel": "related", "href": NEW_SGCN, "type": "text/html",
                       "title": "CDFW SWAP 2025 SGCN ranges, final release (SGCN_Final_red_gdb)"}],
    })

json.dump(F, open("fixes.json", "w"), indent=1, ensure_ascii=False)
open("collections.txt", "w").write("".join(x["collection"] + "\n" for x in F))

R = [
    {"path": "public-iucn/README.md", "replace": [
        ["**Version**: 2025.1\n",
         "**Edition**: IUCN's 2025 richness maps, staged 2025-12-19. The files carry the year only; the Red List "
         "version they were built from is not recorded.\n"],
        ["IUCN 2025. The IUCN Red List of Threatened Species. Version 2025.1. <https://www.iucnredlist.org>",
         "IUCN. 2025. The IUCN Red List of Threatened Species. <https://www.iucnredlist.org>"]]},
    {"path": "public-wui/README.md", "replace": [
        ["- **License:** CC-BY-4.0",
         "- **Terms:** no licence granted; use constraints \"None\", acknowledgment of the USDA Forest Service "
         "Northern Research Station requested"],
        ["https://silvis.forest.wisc.edu/data/wui-change/ (CC-BY-4.0).",
         "https://silvis.forest.wisc.edu/data/wui-change/ (v4, last updated February 2025).\n\n"
         "Radeloff, V. C., D. P. Helmers, M. H. Mockrin, A. R. Carlson, T. J. Hawbaker, S. Martinuzzi. 2023. "
         "The 1990-2020 wildland-urban interface of the conterminous United States - geospatial data. "
         "4th Edition. Fort Collins, CO: Forest Service Research Data Archive. "
         "https://doi.org/10.2737/RDS-2015-0012-4"]]},
]
json.dump(R, open("readme-fixes.json", "w"), indent=1, ensure_ascii=False)
print(len(F), "collections,", len(R), "READMEs")
