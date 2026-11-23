"""Write stac-collection.json and README.md for public-coastal/ccn-carbon-cores-v1-7 (#793).

usage: gen_stac.py <outdir> companion_schema.md

companion_schema.md (beside this file) is the DESCRIBE of each companion parquet, measured on the
published files with the duckdb-geo server.

Column definitions and units come from the CCN data dictionary (docs/controlled_attributes.csv
and docs/controlled_variables.csv in Smithsonian/CCN-Data-Library, pinned below). Schemas and
coded values were measured on the published files on 2026-11-23 with the duckdb-geo server.
"""
import csv
import io
import json
import sys
import urllib.request

OUT = sys.argv[1]
B = "https://s3-west.nrp-nautilus.io/public-coastal"
D = f"{B}/ccn-carbon-cores-v1-7"
CCN = "https://raw.githubusercontent.com/Smithsonian/CCN-Data-Library/5972abd40cc29ffaec7f7221aafd1a1fb56e257b/docs"
ACCESSED = "2026-11-23"
CREATED = "2026-11-23T22:00:00Z"


def fetch_csv(name):
    with urllib.request.urlopen(f"{CCN}/{name}") as r:
        return list(csv.DictReader(io.StringIO(r.read().decode("utf-8-sig"))))


ATTR = {r["attribute_name"]: r for r in fetch_csv("controlled_attributes.csv")}
VARS = {}
for r in fetch_csv("controlled_variables.csv"):
    VARS.setdefault(r["attribute_name"], {})[r["variable_name"]] = r["variable_definition"]

UNITS = {"degree": "decimal degrees", "meter": "m", "centimeter": "cm", "centimetersPerYear": "cm/yr",
         "gramsPerCubicCentimeter": "g/cm³", "dimensionless": "fraction 0–1", "year": "years"}

T = {"STRUCT": "struct", "VARCHAR": "string", "DOUBLE": "double", "BIGINT": "int64", "INTEGER": "int32", "BOOLEAN": "boolean"}

CORES = [("_cng_fid", "BIGINT"), ("study_id", "VARCHAR"), ("site_id", "VARCHAR"), ("core_id", "VARCHAR"),
         ("year", "BIGINT"), ("month", "BIGINT"), ("day", "BIGINT"), ("core_notes", "VARCHAR"),
         ("latitude", "DOUBLE"), ("longitude", "DOUBLE"), ("position_accuracy", "DOUBLE"),
         ("position_method", "VARCHAR"), ("position_notes", "VARCHAR"), ("elevation", "DOUBLE"),
         ("elevation_datum", "VARCHAR"), ("elevation_accuracy", "DOUBLE"), ("elevation_method", "VARCHAR"),
         ("elevation_notes", "VARCHAR"), ("salinity_class", "VARCHAR"), ("salinity_method", "VARCHAR"),
         ("salinity_notes", "VARCHAR"), ("vegetation_class", "VARCHAR"), ("vegetation_method", "VARCHAR"),
         ("vegetation_notes", "VARCHAR"), ("inundation_class", "VARCHAR"), ("inundation_method", "VARCHAR"),
         ("inundation_notes", "VARCHAR"), ("core_length_flag", "VARCHAR"),
         ("pb210_cic_accretion_rate", "DOUBLE"), ("pb210_cic_accretion_rate_se", "DOUBLE"),
         ("pb210_cic_notes", "VARCHAR"), ("pb210_cic_max_depth", "DOUBLE"), ("pb210_cic_r2", "DOUBLE"),
         ("country", "VARCHAR"), ("admin_division", "VARCHAR"), ("habitat", "VARCHAR"),
         ("stocks_qual_code", "VARCHAR"), ("dates_qual_code", "VARCHAR"), ("elevation_qual_code", "VARCHAR"),
         ("max_depth", "DOUBLE"), ("stock_0_30cm_mgha", "DOUBLE"), ("cov_0_30cm", "DOUBLE"),
         ("carbon_source_0_30cm", "VARCHAR"), ("stock_0_100cm_mgha", "DOUBLE"), ("cov_0_100cm", "DOUBLE"),
         ("carbon_source_0_100cm", "VARCHAR")]

# Measured on the published cores (2026-11-23); NULL excluded.
CODED = {
    "habitat": ["algal mat", "mangrove", "marsh", "microbial mat", "mudflat", "sabkha", "scrub/shrub",
                "seagrass", "swamp", "unvegetated", "upland"],
    "stocks_qual_code": ["C1", "C2"],
    "dates_qual_code": ["B1", "B2"],
    "elevation_qual_code": ["A1", "A2", "A3"],
    "vegetation_class": ["emergent", "forested", "forested to emergent", "forested to shrub", "mudflat",
                         "scrub shrub", "seagrass", "unvegetated"],
    "inundation_class": ["back", "high", "levee", "low", "mid", "plain", "submerged subtidal"],
    "core_length_flag": ["core depth limited by length of corer", "core depth represents deposit depth",
                         "not specified"],
    "carbon_source_0_30cm": ["measured", "mixed", "organic_matter"],
    "carbon_source_0_100cm": ["measured", "mixed", "organic_matter"],
    "salinity_class": ["brackish", "brackish to fresh", "brackish to saline", "brine", "deltaic", "estuarine",
                       "estuarine C-CAP", "fresh", "mesohaline", "mixoeuhaline", "oligohaline", "palustrine",
                       "polyhaline", "riverine", "saline"],
    "position_method": ["RTK", "handheld", "other high resolution", "other low resolution", "other moderate resolution"],
    "marker_type": ["dredge horizon", "pollen", "pollution"],
    "impact_class": ["agro-industrial deforestation", "canalled", "degraded", "diked and drained", "disturbed",
                     "ditched", "farmed", "firewood extraction", "impounded", "invasive plants removed", "managed",
                     "managed impounded", "natural", "restored", "restoring", "revegetated", "salt impacted",
                     "sediment added", "storm or wind", "tidally restored", "tidally restricted", "wetlands built",
                     "wood harvesting"],
    "age_depth_model_reference": ["CE", "YBP", "core collection date"],
    "c14_counting_method": ["AMS"],
    "carbon_measured_or_modeled": ["measured", "modeled"],
    "compaction_flag": ["compaction qualified", "compaction quantified", "corer limits compaction",
                        "no obvious compaction", "not specified"],
    "coring_method": ["Eijkelkamp peat core sampler", "PVC tube or thin-walled metal tube", "dutch auger",
                      "gouge auger", "hargas corer", "mcauley corer", "mccaffrey peat cutter", "none specified",
                      "other shallow corer", "piston corer", "polycarbonate tube", "push core", "pvc and hammer",
                      "russian corer", "shovel", "shovel core", "soil pit", "surface sample", "vibracore"],
    "cs137_counting_method": ["alpha", "gamma"],
    "excess_pb210_model": ["CFCS", "CIC", "CRS"],
    "excess_pb210_rate": ["accretion", "cumulative mass", "depth", "mass accumulation", "not specified"],
    "fraction_carbon_method": ["Craft regression", "EA", "local regression", "not specified", "wet oxidation"],
    "fraction_carbon_type": ["not specified", "organic carbon", "total carbon"],
    "pb210_counting_method": ["alpha", "gamma"],
    "ra226_assumption": ["at asymptote", "each sample", "selected intervals", "selected samples"],
    "roots_flag": ["roots and rhizomes included", "roots and rhizomes separated"],
    "sediment_sieved_flag": ["sediment not sieved", "sediment sieved"],
    "code_type": ["Genus", "description"],
    "publication_type": ["article", "associated data", "associated source", "combined dataset and manuscript",
                         "database", "primary dataset", "primary source", "synthesis dataset", "synthesis source",
                         "thesis"],
}
EXTRA_VARS = {  # codes in use with no definition in the CCN controlled vocabulary
    "vegetation_class": {"mudflat": "Unvegetated tidal flat."},
    "inundation_class": {"plain": "Study-specific definition of a flat zone in the tidal frame.",
                         "submerged subtidal": "Permanently submerged, below low tide."},
}
SRC = {"measured": "every interval used had a measured carbon fraction",
       "organic_matter": "every interval used had its carbon fraction converted from organic matter",
       "mixed": "some intervals measured, some converted"}

STOCK = ("Soil organic carbon stock from the surface to {d} cm depth, in megagrams of carbon per hectare "
         "(Mg C/ha), computed by us from the core's depth series: dry bulk density × carbon fraction × "
         "interval thickness, summed over the sampled intervals within 0–{d} cm and scaled to the full "
         "{d} cm. Carbon fraction is the measured value where the study reports one; otherwise it is "
         "converted from the organic-matter fraction (loss on ignition, LOI). Seagrass cores use Fourqurean "
         "et al. (2012), OC% = 0.40 × LOI% − 0.21 below 20% LOI and 0.43 × LOI% − 0.33 above it, with "
         "negative values set to 0. All other cores use Craft et al. (1991), OC% = 0.40 × LOI% + "
         "0.0025 × LOI%², an equation fitted to marsh soils. Mangroves use Craft because the published "
         "mangrove equation (Kauffman et al. 2011, fitted in Palau) overestimates carbon by about 3.6 "
         "percentage points on this library's mangrove samples with under 20% organic matter, where "
         "both organic matter and carbon were measured. Empty where the sampled intervals cover less "
         "than 90% of 0–{d} cm.")
OVERRIDE = {
    "_cng_fid": "Unique row id assigned at conversion, one per core.",
    "year": "Year. On cores, the year the core was collected; on study citations, the year of publication.",
    "month": "Month the core was collected (1–12).",
    "day": "Day of the month the core was collected.",
    "stock_0_30cm_mgha": STOCK.format(d=30),
    "stock_0_100cm_mgha": STOCK.format(d=100),
    "cov_0_30cm": "Fraction (0–1) of the 0–30 cm range covered by sampled intervals with usable bulk density and carbon.",
    "cov_0_100cm": "Fraction (0–1) of the 0–100 cm range covered by sampled intervals with usable bulk density and carbon.",
    "carbon_source_0_30cm": "Where the carbon fractions behind stock_0_30cm_mgha came from.",
    "carbon_source_0_100cm": "Where the carbon fractions behind stock_0_100cm_mgha came from.",
    "geometry": "Core location as a point (WGS84), from latitude and longitude.",
    "bbox": "Bounding box of the geometry (xmin, ymin, xmax, ymax), used to speed up spatial filters.",
    "h8": "H3 cell id at resolution 8.",
    "h0": "H3 cell id at resolution 0, used as the partition key for hive-partitioned reads.",
    "article-number": "Article number of the publication, where it has one.",
    "eprint": "E-print identifier of the publication, where it has one.",
    "issn": "ISSN of the journal.",
    "issue": "Journal issue.",
    "note": "Bibliographic note.",
    "type": "Kind of publication (for example Article, Misc, Thesis).",
    "inundation_method": "Method used to determine the inundation class.",
    "site_latitude_min": "Southern edge of the site, in decimal degrees (WGS84).",
    "site_latitude_max": "Northern edge of the site, in decimal degrees (WGS84).",
    "site_longitude_min": "Western edge of the site, in decimal degrees (WGS84).",
    "site_longitude_max": "Eastern edge of the site, in decimal degrees (WGS84).",
    "site_description": "Free-text description of the site, as reported by the study.",
    "species_code": "Scientific name of a dominant plant species (open nomenclature), or a short description where no species was named; code_type says which.",
}


def describe(name):
    if name in OVERRIDE:
        text = OVERRIDE[name]
    else:
        a = ATTR.get(name)
        text = a["attribute_definition"].strip() if a else name.replace("_", " ").capitalize() + "."
        if a and a.get("unit") not in (None, "", "NA") and a["unit"] in UNITS:
            text += f" Units: {UNITS[a['unit']]}."
        if name == "inundation_class":
            text = "Position of the core in the tidal frame, as defined by each study."
    if name in CODED:
        defs = {**VARS.get(name, {}), **EXTRA_VARS.get(name, {}), **(SRC if name.startswith("carbon_source") else {})}
        text += " Values: " + ", ".join(f"{v}={defs.get(v, v).rstrip('.')}" for v in CODED[name])
    return text


COMPANION = {}
for line in open(sys.argv[2]):  # companion_schema.md from DESCRIBE
    p = [x.strip() for x in line.split("|")[1:4]]
    if len(p) == 3 and p[0] not in ("t", "") and not p[0].startswith(":"):
        COMPANION.setdefault(p[0], []).append((p[1], p[2]))

dictionary, seen = [], set()


def add(cols):
    for n, t in cols:
        if n in seen:
            continue
        seen.add(n)
        e = {"name": n, "type": T.get(t, "geometry" if t.startswith("GEOMETRY") else "string"), "description": describe(n)}
        if n in CODED:
            e["values"] = CODED[n]
        dictionary.append(e)


add(CORES + [("geometry", "GEOMETRY"), ("bbox", "STRUCT"), ("h8", "UBIGINT"), ("h0", "BIGINT")])
for t in COMPANION.values():
    add(t)
for e in dictionary:
    if e["name"] in ("h8",):
        e["type"] = "uint64"

cols = lambda cs: [{"name": n, "type": T.get(t, "string")} for n, t in cs]
TABLE_TITLES = {"depthseries": "Depth series: one row per sampled depth interval of each core",
                "sites": "Sites: coring sites and their descriptions",
                "species": "Species: dominant plant species at each coring location",
                "impacts": "Impacts: human or other impacts recorded at each site or core",
                "methods": "Methods: field and laboratory methods of each study",
                "study_citations": "Study citations: the publication behind each study"}

assets = {
    "ccn-carbon-cores-v1-7-parquet": {
        "href": f"{B}/ccn-carbon-cores-v1-7.parquet", "type": "application/x-parquet",
        "title": "Coastal carbon cores — GeoParquet", "roles": ["data"], "created": CREATED,
        "description": "One row per sediment core: location, habitat, study, quality codes and the derived carbon stocks.",
        "table:columns": cols(CORES) + [{"name": "geometry", "type": "geometry"}, {"name": "bbox", "type": "struct"}]},
    "ccn-carbon-cores-v1-7-pmtiles": {
        "href": f"{B}/ccn-carbon-cores-v1-7.pmtiles", "type": "application/vnd.pmtiles",
        "title": "Coastal carbon cores — PMTiles", "roles": ["visual"], "created": CREATED,
        "description": "Vector tiles of the core locations for web maps; the source layer is ccn-carbon-cores-v1-7.",
        "vector:layers": ["ccn-carbon-cores-v1-7"],
        "table:columns": [{"name": n, "type": "Number" if t in ("DOUBLE", "BIGINT") else "String"} for n, t in CORES]},
    "ccn-carbon-cores-v1-7-hex": {
        "href": f"{D}/hex/h0=*/data_0.parquet", "type": "application/x-parquet",
        "title": "Coastal carbon cores — H3 hex (resolution 8)", "roles": ["data"], "created": CREATED,
        "description": ("Each core placed in the one H3 resolution-8 cell (about 0.7 km²) that contains it, one row "
                        "per core with every core attribute. Several cores can share a cell; they are not "
                        "merged. Count cores with COUNT(DISTINCT _cng_fid)."),
        "h3:native_resolution": 8, "h3:parent_resolutions": [0],
        "table:columns": cols(CORES) + [{"name": "h8", "type": "uint64"}, {"name": "h0", "type": "int64"}]},
}
for t, cs in COMPANION.items():
    assets[f"ccn-{t.replace('_', '-')}-parquet"] = {
        "href": f"{D}/{t}.parquet", "type": "application/x-parquet", "title": TABLE_TITLES[t],
        "roles": ["data"], "created": CREATED, "table:columns": cols(cs),
        "description": "Joins to the cores on study_id and core_id (or study_id and site_id)."}
assets["ccn-depthseries-parquet"]["description"] = (
    "One row per sampled depth interval of each core, as reported by the source studies: depth range, "
    "dry bulk density, organic matter and carbon fractions, and dating measurements. Join to the cores "
    "on study_id and core_id; core_id alone is not unique across studies.")
assets["style-ccn-carbon-cores-v1-7-habitat"] = {  # built with scripts/default-style.py, see the publish job
    "href": f"{D}/styles/ccn-carbon-cores-v1-7-habitat.json", "type": "application/vnd.mapbox.style+json",
    "title": "Coastal carbon cores — PMTiles by habitat", "roles": ["style", "default"],
    "description": ("Cores coloured by habitat: light green marsh, dark green mangrove, blue seagrass, brown "
                    "unvegetated, purple swamp, lilac scrub/shrub, tan mudflat, grey for the rarer habitats. "
                    "Habitat is the main way these cores are compared, since carbon densities are calibrated "
                    "per coastal ecosystem.")}
assets["ccn-bibliography"] = {
    "href": f"{D}/bibliography.bib", "type": "application/x-bibtex", "roles": ["metadata"],
    "title": "Bibliography of every study in the library (BibTeX)", "created": CREATED}

DESC = f"""Sediment cores from tidal marshes, mangroves, seagrass meadows and other tidal wetlands worldwide, from the Coastal Carbon Network's Coastal Carbon Data Library (version 1.7.0), with soil carbon stocks to 30 cm and 100 cm computed for every core whose measurements allow it. These are field measurements at points, for calibrating carbon densities by habitat and region; they are not a map of carbon across the coast.

The library holds 16,715 cores from hundreds of studies: 8,746 in marshes, 5,801 in mangroves, 1,294 in seagrass meadows, and smaller numbers in unvegetated flats, swamps, scrub and other tidal habitats. It includes the global seagrass soil carbon compilation of Krause et al. (2025). Three cores without coordinates are left out of the map layers, leaving 16,712.

Carbon stocks come from each core's depth series (dry bulk density × carbon fraction × interval thickness). A stock is computed only where the sampled intervals cover at least 90% of the depth range, so 4,830 cores have a 0–30 cm stock and 2,754 a 0–100 cm stock. Where a study reports organic matter but not carbon, carbon is estimated from organic matter, with Fourqurean et al. (2012) for seagrass and with Craft et al. (1991), fitted to marsh soils, for every other habitat; the carbon_source columns say which cores this applies to. Median 0–100 cm stocks are 285 Mg C/ha for mangroves, 275 for marshes and 134 for seagrass. To compare habitats or regions, filter to cores with a stock:

```sql
SELECT habitat, COUNT(*) AS cores, MEDIAN(stock_0_100cm_mgha) AS median_mg_c_per_ha
FROM read_parquet('{B}/ccn-carbon-cores-v1-7.parquet')
WHERE stock_0_100cm_mgha IS NOT NULL GROUP BY habitat
```

Companion tables hold the full depth series, sites, dominant species, impacts, methods and citations, joinable on study_id and core_id. Each core keeps the identifiers and quality codes of the library, and each study should be cited from the bibliography when its data are used.

Source: Coastal Carbon Network (2025), Coastal Carbon Data Library version 1.7.0, Smithsonian Environmental Research Center, https://doi.org/10.25573/serc.21565671.v9 (figshare version 9, published 2025-11-19), accessed {ACCESSED}. Licensed CC BY 4.0; the network asks users to credit the library version with the date downloaded and to cite the original studies. Staged files (MD5 checked against the figshare record): CCN_cores.csv 5,111,526 bytes, MD5 3c2072b33925f8d2dcf8e54e8db3904f; CCN_depthseries.csv 30,303,567 bytes, MD5 c5304e494ef535c006fba628006dae0f."""

col = {
    "stac_version": "1.0.0",
    "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json",
                        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
                        "https://stac-extensions.github.io/version/v1.2.0/schema.json"],
    "type": "Collection", "id": "ccn-carbon-cores-v1-7",
    "title": "Coastal Carbon Network soil carbon cores (v1.7.0)",
    "description": DESC, "license": "CC-BY-4.0", "version": "1.7.0",
    "keywords": ["blue carbon", "soil carbon", "sediment cores", "tidal marsh", "mangrove", "seagrass",
                 "coastal wetlands", "carbon stock", "global"],
    "sci:doi": "10.25573/serc.21565671.v9",
    "sci:citation": f"Coastal Carbon Network (2025). Database: Coastal Carbon Library (Version 1.7.0). Smithsonian Environmental Research Center. Dataset. https://doi.org/10.25573/serc.21565671.v9. Accessed {ACCESSED}.",
    "sci:publications": [{"doi": "10.1038/s41467-025-59204-4", "citation": "Krause, J. R., et al. (2025). Global seagrass carbon stock variability and emissions from seagrass loss. Nature Communications, 16."},
                         {"citation": "Craft, C. B., Seneca, E. D., & Broome, S. W. (1991). Loss on ignition and Kjeldahl digestion for estimating organic carbon and total nitrogen in estuarine marsh soils: calibration with dry combustion. Estuaries, 14(2), 175–179.", "doi": "10.2307/1351691"},
                         {"citation": "Fourqurean, J. W., Duarte, C. M., Kennedy, H., Marbà, N., Holmer, M., Mateo, M. A., et al. (2012). Seagrass ecosystems as a globally significant carbon stock. Nature Geoscience, 5(7), 505–509.", "doi": "10.1038/ngeo1477"}],
    "providers": [{"name": "Coastal Carbon Network, Smithsonian Environmental Research Center", "roles": ["producer", "licensor"], "url": "https://serc.si.edu/coastalcarbon"},
                  {"name": "Boettiger Lab", "roles": ["processor", "host"], "url": "https://github.com/boettiger-lab"}],
    "extent": {"spatial": {"bbox": [[-180, -51.82623, 180, 72.42798]]},
               "temporal": {"interval": [["1960-01-01T00:00:00Z", "2024-12-31T23:59:59Z"]]}},
    "created": CREATED, "updated": CREATED,
    "table:columns": dictionary,
    "links": [
        {"rel": "self", "href": f"{D}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json"},
        {"rel": "parent", "href": f"{B}/stac-collection.json", "type": "application/json"},
        {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/", "type": "text/html", "title": "CC BY 4.0"},
        {"rel": "license", "href": "https://serc.si.edu/coastalcarbon/principles-and-governance", "type": "text/html", "title": "Coastal Carbon Network data use policy"},
        {"rel": "about", "href": "https://smithsonian.figshare.com/articles/dataset/Database_Coastal_Carbon_Library/21565671", "type": "text/html", "title": "Coastal Carbon Data Library on figshare"},
        {"rel": "via", "href": "https://serc.si.edu/coastalcarbon", "type": "text/html", "title": "Coastal Carbon Network"},
        {"rel": "cite-as", "href": "https://doi.org/10.25573/serc.21565671.v9", "type": "text/html"},
        {"rel": "describedby", "href": f"{D}/README.md", "type": "text/markdown", "title": "README"},
        {"rel": "pmtiles", "href": f"{B}/ccn-carbon-cores-v1-7.pmtiles", "type": "application/vnd.pmtiles",
         "title": "Coastal carbon cores — PMTiles", "pmtiles:layers": ["ccn-carbon-cores-v1-7"]},
    ],
    "assets": assets,
}
json.dump(col, open(f"{OUT}/stac-collection.json", "w"), indent=2, ensure_ascii=False)

README = f"""# Coastal Carbon Network soil carbon cores (v1.7.0)

{DESC}

## Files

| File | Contents |
|---|---|
| `{B}/ccn-carbon-cores-v1-7.parquet` | One row per core (GeoParquet) |
| `{B}/ccn-carbon-cores-v1-7.pmtiles` | Core locations as vector tiles, source layer `ccn-carbon-cores-v1-7` |
| `{D}/hex/h0=*/data_0.parquet` | Cores indexed to H3 resolution 8, partitioned by h0 |
| `{D}/<table>.parquet` | depthseries, sites, species, impacts, methods, study_citations |
| `{D}/bibliography.bib` | Citations for every study |

## DuckDB

```sql
INSTALL httpfs; LOAD httpfs;
SELECT habitat, COUNT(*) AS cores, MEDIAN(stock_0_100cm_mgha) AS median_mg_c_per_ha
FROM read_parquet('{B}/ccn-carbon-cores-v1-7.parquet')
WHERE stock_0_100cm_mgha IS NOT NULL
GROUP BY habitat ORDER BY cores DESC;
```

## MapLibre GL JS

```js
map.addSource('ccn', {{ type: 'vector', url: 'pmtiles://{B}/ccn-carbon-cores-v1-7.pmtiles' }});
map.addLayer({{
  id: 'ccn-cores', type: 'circle', source: 'ccn',
  'source-layer': 'ccn-carbon-cores-v1-7',
  paint: {{ 'circle-radius': 3, 'circle-color': '#1b7837' }}
}});
```

## Columns

| Column | Description |
|---|---|
""" + "\n".join(f"| `{e['name']}` | {e['description']} |" for e in dictionary) + "\n"
open(f"{OUT}/README.md", "w").write(README)
print("wrote", len(assets), "assets,", len(dictionary), "columns")
