"""Writes fixes.json, collections.txt and readme-fixes.json (#949). Run from this directory."""
import json

F = []
ITEM = "https://www.arcgis.com/home/item.html?id=6d74d3f1f8d047dd9295467d7671b774"
F2F = "https://data.fs.usda.gov/geodata/edw/edw_resources/meta/Hydro_F2F2_HUC12.xml"
UNDOC = "Not defined by American Rivers or by Forests to Faucets 2.0; meaning unknown."
F.append({
    "collection": "public-rivers/american-rivers/ira-watersheds/stac-collection.json",
    "evidence": f"{ITEM} (item summary: 'USFS inventoried roadless areas (IRA) ... and IRA-influenced "
                f"watersheds'; FeatureServer layers 0-4); {F2F} (field definitions, edition 2.0.14); "
                "FeatureServer statistics 2026-11-17 (9,991 rows, 37 states plus 7 blank)",
    "title": "Drinking Water Watersheds Influenced by Inventoried Roadless Areas (HUC12)",
    "description": (
        "HUC12 watersheds that supply surface drinking water and are influenced by USDA Forest Service "
        "Inventoried Roadless Areas (IRAs, the areas covered by the 2001 Roadless Area Conservation Rule), "
        "compiled by American Rivers. Here IRA means Inventoried Roadless Area, not the Inflation "
        "Reduction Act. 9,991 watersheds in 37 states (7 have no state recorded). American Rivers "
        "publishes this layer with the 2001 roadless areas, national forests and wilderness areas, but "
        "with no field definitions.\n\n"
        "HUC12, APCW, IMP, POP_DS and SUM_POP carry the names of USDA Forest Service Forests to Faucets "
        "2.0 fields: ability to produce clean water, importance for surface drinking water, the surface "
        "drinking-water population downstream, and the surface-water consumers served by intakes in the "
        "watershed. American Rivers does not say whether these values are carried over from Forests to "
        "Faucets unchanged. BG, BW, FF, MB, SR and IDX, and the _NR and _SR variants of every score, are "
        "not defined by either source, so their meaning is unknown."),
    "providers": {"US EPA / American Rivers": {
        "name": "American Rivers", "roles": ["producer"], "url": "https://www.americanrivers.org"}},
    "links_replace": {
        "https://services9.arcgis.com/90v9hhDSTUTen7c9/arcgis/rest/services/IRA_influenced_drinking_water/FeatureServer/0": {
            "rel": "source",
            "href": "https://services9.arcgis.com/90v9hhDSTUTen7c9/arcgis/rest/services/IRA_influenced_drinking_water/FeatureServer/0",
            "title": "ArcGIS FeatureServer source (American Rivers)"},
        "https://www.epa.gov/cwsrf/inflation-reduction-act-clean-water-state-revolving-fund": {
            "rel": "about", "href": ITEM, "type": "text/html",
            "title": "American Rivers: IRA_influenced_drinking_water (ArcGIS item)"}},
    "links_add": [{"rel": "about", "href": F2F, "type": "application/xml",
                   "title": "Forests to Faucets 2.0 field definitions (USDA Forest Service metadata)"}],
    "columns": {
        "HUC_12_NPR": "Hydrologic Unit Code (12 digits) as text; equal to HUC12 in the rows checked. Not defined by American Rivers. High-cardinality key, not an enumerable class.",
        "POP_DS": "Name matches the Forests to Faucets 2.0 field: surface drinking-water population downstream of the HUC12. Cannot be summed across watersheds, since downstream populations are counted once per upstream watershed.",
        "SUM_POP": "Name matches the Forests to Faucets 2.0 field: surface-water consumers served by drinking-water intakes in the HUC12 (surface plus Great Lakes intakes).",
        "APCW": "Name matches the Forests to Faucets 2.0 field Ability to Produce Clean Water, (natural cover + agriculture + impervious + riparian ranks) × water-yield rank. Values here run 4 to 64.",
        "IMP": "Name matches the Forests to Faucets 2.0 field Important Areas for Surface Drinking Water (raw value), drinking-water protection × water yield.",
        **{c: UNDOC for c in ("APCW_NR", "APCW_SR", "IMP_NR", "IMP_SR", "BG", "BG_NR", "BG_SR", "BW",
                              "BW_NR", "BW_SR", "FF", "FF_NR", "FF_SR", "MB", "MB_NR", "MB_SR", "SR",
                              "SR_NR", "SR_SR", "IDX", "IDX_NR", "IDX_SR")}},
    "asset_text_replace": {"ira-watersheds-hex": [[
        "the six indicator scores (APCW, IMP, BG, BW, FF, MB, SR) and their non-rural (_NR) / super-rural (_SR) variants, the composite IDX/IDX_NR/IDX_SR",
        "the score columns (APCW, IMP, BG, BW, FF, MB, SR), their _NR and _SR variants, IDX/IDX_NR/IDX_SR"]]},
})
F.append({
    "collection": "public-rivers/american-rivers/roo-cjest/stac-collection.json",
    "evidence": "CEQ names the tool the Climate and Economic Justice Screening Tool (CEJST), https://screeningtool.geoplatform.gov/",
    "title": "Rivers of Opportunity — CEJST Census Tract Scores",
    "description_replace": [["Screening Tool (CJEST)", "Screening Tool (CEJST)"]],
    "providers": {"CEQ / EPA (CJEST data)": {
        "name": "Council on Environmental Quality (CEJST data)", "roles": ["producer"],
        "url": "https://screeningtool.geoplatform.gov/"}},
    "asset_text_replace": {"style-roo-cjest-tc": [["(CJEST)", "(CEJST)"]]},
})
F.append({
    "collection": "public-barred-owl/stac-collection.json",
    "evidence": "https://barredowltool.russell.wisc.edu/pages/background/ (name) and /pages/methods/ ('We used the prioritizr package in R')",
    "title": "Barred Owl Prioritization Platform (Northern Spotted Owl range)",
    "description_replace": [["Cloud-native mirror of the Barred Owl Tool (", "Cloud-native mirror of the Barred Owl Prioritization Platform ("]],
})
F.append({
    "collection": "public-calenviroscreen/stac-collection.json",
    "evidence": "CES 4.0 results already carry Lead / Lead Pctl (calenviroscreen40resultsdatadictionary_f_2021.xlsx); "
                "final CalEnviroScreen 5.0 published on data.ca.gov 2026-06-16 (package calenviroscreen-5-0, files dated 070126)",
    "description_replace": [["Version 5.0 adds two new indicators (Children's Lead Risk from Housing and Small Air Toxic Sites)",
                             "Version 5.0 adds two new indicators (Small Air Toxic Sites and Diabetes Prevalence)"]],
    "description_append": "**Draft, not final:** OEHHA published the final CalEnviroScreen 5.0 on 2026-06-16 "
        "(https://data.ca.gov/dataset/calenviroscreen-5-0). This collection holds the January 2026 public-review "
        "draft, whose scores may differ from the final.",
    "links_add": [{"rel": "related", "href": "https://data.ca.gov/dataset/calenviroscreen-5-0", "type": "text/html",
                   "title": "CalEnviroScreen 5.0 (final, June 2026)"}],
    "columns": {
        "ChildLead": "Potential risk for lead exposure in children in low-income communities with older housing (carried over from CES 4.0)",
        "DiabetesPrev": "Model-based prevalence of diabetes in adults ≥18 (new in v5.0)"},
})
json.dump(F, open("fixes.json", "w"), indent=1, ensure_ascii=False)
open("collections.txt", "w").write("".join(x["collection"] + "\n" for x in F))

IRA_README = "# Drinking Water Watersheds Influenced by Inventoried Roadless Areas\n\nHUC12 watersheds that supply surface drinking water and are influenced by USDA Forest Service\nInventoried Roadless Areas (IRAs, the areas covered by the 2001 Roadless Area Conservation\nRule), compiled by American Rivers. Here IRA means Inventoried Roadless Area, not the Inflation\nReduction Act.\n\n**9,991 HUC12 watersheds** | Polygon | 37 states (7 records have no state)\n\nSource: American Rivers, ArcGIS item\n<https://www.arcgis.com/home/item.html?id=6d74d3f1f8d047dd9295467d7671b774>, published with the\n2001 roadless areas, national forests and wilderness areas.\n\n## Files\n\n| Format | URL |\n|--------|-----|\n| GeoParquet | `https://s3-west.nrp-nautilus.io/public-rivers/american-rivers/ira-watersheds.parquet` |\n| PMTiles | `https://s3-west.nrp-nautilus.io/public-rivers/american-rivers/ira-watersheds.pmtiles` |\n| H3 hex (res 8) | `https://s3-west.nrp-nautilus.io/public-rivers/american-rivers/ira-watersheds/hex/h0=*/data_0.parquet` |\n\n**PMTiles source-layer name:** `ira-watersheds`\n\n## Columns\n\nAmerican Rivers publishes no field definitions. Five columns carry the names of USDA Forest\nService Forests to Faucets 2.0 fields\n([field definitions](https://data.fs.usda.gov/geodata/edw/edw_resources/meta/Hydro_F2F2_HUC12.xml));\nwhether American Rivers carried their values over unchanged is not documented.\n\n| Column | Forests to Faucets 2.0 meaning |\n|--------|--------------------------------|\n| HUC12 | 12-digit Hydrologic Unit Code |\n| APCW | Ability to Produce Clean Water (values here run 4 to 64) |\n| IMP | Important Areas for Surface Drinking Water, raw value |\n| POP_DS | Surface drinking-water population downstream of the HUC12; cannot be summed across watersheds |\n| SUM_POP | Surface-water consumers served by intakes in the HUC12 |\n\n`HUC_12_NPR` holds the HUC12 code as text. **BG, BW, FF, MB, SR, IDX**, and the `_NR` and `_SR`\nvariants of every score, are not defined by either source; their meaning is unknown.\n\n## DuckDB example\n\n```sql\nINSTALL httpfs; LOAD httpfs;\nSELECT STATE, COUNT(*) AS watersheds\nFROM read_parquet('https://s3-west.nrp-nautilus.io/public-rivers/american-rivers/ira-watersheds.parquet')\nGROUP BY STATE ORDER BY watersheds DESC;\n```\n"

R = [
    {"path": "public-barred-owl/README.md", "replace": [
        ["# Barred Owl Prioritization Tool — cloud-native mirror", "# Barred Owl Prioritization Platform — cloud-native mirror"],
        ["Cloud-native mirror of the **Barred Owl Tool**", "Cloud-native mirror of the **Barred Owl Prioritization Platform**"],
        ["**Zonation** systematic-conservation-planning algorithm.", "**prioritizr** R package for systematic conservation planning."],
        ["The Zonation **priority score**", "The prioritizr **priority score**"],
        ["| `prio_score` | Zonation priority rank for the cell under this scenario |",
         "| `prio_score` | prioritizr relative importance (0–1, from `eval_rank_importance`) for the cell under this scenario |"]]},
    {"path": "public-calenviroscreen/README.md", "replace": [
        ["indicators (Children's Lead Risk from Housing and Small Air Toxic Sites) compared to\nversion 4.1.",
         "indicators (Small Air Toxic Sites and Diabetes Prevalence) compared to version 4.0.\n\n"
         "**Draft, not final:** OEHHA published the final CalEnviroScreen 5.0 on 2026-06-16\n"
         "(<https://data.ca.gov/dataset/calenviroscreen-5-0>). This is the January 2026 draft, whose\n"
         "scores may differ from the final."]]},
    {"path": "public-rivers/american-rivers/ira-watersheds/README.md", "content": IRA_README},
]
json.dump(R, open("readme-fixes.json", "w"), indent=1, ensure_ascii=False)
print(len(F), "collections,", len(R), "READMEs")
