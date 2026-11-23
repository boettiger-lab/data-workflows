"""Build the final CalEnviroScreen 5.0 collection from the live (draft) one (#975).

  python3 make_collection.py LIVE.json OUT.json HEX_CREATED [README.md]

Column texts follow OEHHA's final data dictionary (final-calenviroscreen-5.0-data-dictionary.pdf).
Null counts and zero counts were measured on the converted GeoParquet on 2026-11-18 and match
OEHHA's table of zeros and missing values; no column carries a numeric sentinel.
"""
import json
import sys

B = "https://s3-west.nrp-nautilus.io/public-calenviroscreen"
D = f"{B}/calenviroscreen-5-0"
PKG = "https://data.ca.gov/dataset/calenviroscreen-5-0"
ACCESSED = "2026-11-18"
RAW = "s3://public-calenviroscreen/raw/ces5-final/"
GDB = ("calenviroscreen50results_f_070126.gdb.zip", 21992716,
       "5bcb8afe5b01f477488339320e12c94d0436245cb21cafca9eaa77c398327f6f")
DICT = "final-calenviroscreen-5.0-data-dictionary.pdf"

NA = "Empty (null) where OEHHA reports NA"
PCT = "percentile among California census tracts (0–100)"
ZERO_PCT = ("Tracts with a raw value of 0 are given percentile 0 and are left out of the "
            "percentile ranking.")

# (name, type, description). Indicator texts are OEHHA's, lightly expanded.
C = [
    ("_cng_fid", "int64", "Synthetic feature ID added during processing; one per census tract."),
    ("OBJECTID", "int64", "Row ID carried over from OEHHA's geodatabase."),
    ("tract", "int64", "Census tract ID from the 2020 Decennial Census (state and county FIPS "
     "without the leading zero, e.g. 6001400100)."),
    ("ZIP", "int32", "Postal ZIP code (5 digits) the census tract falls mostly within, for reference only. "
     "Thirteen tracts in national forests, parks and military land carry values from 20 to 61, "
     "which are not postal ZIP codes."),
    ("ApproxLoc", "string", "Approximate city or unincorporated area where the tract is located, "
     "from Esri Demographics data. For reference only; not a city boundary."),
    ("county", "string", "California county the census tract falls within."),
    ("region", "string", "California region the census tract falls within.", [
        "LA Area", "Bay Area", "Central Valley", "Inland Valley", "SD-Imperial",
        "Sacramento Area", "Central Coast", "North State", "Sierra"]),
    ("Population", "int32", "Total population, 2020–2024 American Community Survey 5-year "
     "estimate. 25 tracts have zero population."),
    ("CIscore", "float64", "CalEnviroScreen 5.0 score: Pollution Burden Score multiplied by "
     f"Population Characteristics Score. {NA}: 73 tracts with too few people or too many "
     "missing population indicators."),
    ("CIscoreP", "float64", f"CalEnviroScreen 5.0 score {PCT}. Higher means a greater cumulative "
     f"burden. {NA} (73 tracts)."),
    ("ozone", "float64", "Ozone: mean of the summer months (May–October) of the daily maximum "
     "8-hour ozone."),
    ("Ozone_Pctl", "float64", f"Ozone {PCT}."),
    ("PM2_5", "float64", "PM2.5: annual mean concentration of fine particulate matter."),
    ("PM2_5_Pctl", "float64", f"PM2.5 {PCT}."),
    ("Diesel_PM", "float64", "Diesel particulate matter emissions from on-road and non-road "
     f"sources within and near populated blocks. {NA} (9 tracts)."),
    ("Diesel_PM_Pctl", "float64", f"Diesel PM {PCT}. {NA} (9 tracts)."),
    ("Pesticides", "float64", "Total pounds of selected active pesticide ingredients (filtered "
     "for hazard and volatility) used in production agriculture per square mile. 0 in 6,074 "
     "tracts."),
    ("Pesticides_Pctl", "float64", f"Pesticide use {PCT}. {ZERO_PCT}"),
    ("Tox_Releases", "float64", "Toxicity-weighted air concentrations from chemical releases by "
     "large facilities."),
    ("Tox_Rel_Pctl", "float64", f"Toxic releases from facilities {PCT}. {ZERO_PCT}"),
    ("traffic", "float64", "Traffic density, in vehicle-kilometers per hour per road length, "
     f"within 150 meters of the census tract boundary. {NA} (9 tracts)."),
    ("Traffic_Pctl", "float64", f"Traffic impacts {PCT}. {NA} (9 tracts)."),
    ("Drinking_Water", "float64", "Drinking water contaminants index for selected contaminants. "
     f"{NA} (9 tracts)."),
    ("DrinkingWaterPctl", "float64", f"Drinking water contaminants {PCT}. {NA} (9 tracts)."),
    ("lead", "float64", "Children's lead risk from housing: potential risk of lead exposure for "
     f"children living in low-income communities with older housing. {NA} (84 tracts)."),
    ("Lead_Pctl", "float64", f"Children's lead risk from housing {PCT}. {ZERO_PCT} {NA} "
     "(84 tracts)."),
    ("cleanups", "float64", "Sum of weighted EnviroStor cleanup sites and National Priorities "
     "List Superfund sites within buffered distances to populated blocks."),
    ("Cleanups_Pctl", "float64", f"Cleanup sites {PCT}. {ZERO_PCT}"),
    ("GroundwaterThreats", "float64", "Sum of weighted GeoTracker cleanup, land disposal, "
     "underground storage tank and produced water pond sites, and dairies and feedlots, within "
     "buffered distances to populated blocks."),
    ("GW_Threats_Pctl", "float64", f"Groundwater threats {PCT}. {ZERO_PCT}"),
    ("Haz_Waste", "float64", "Sum of weighted hazardous waste facilities and large quantity "
     "generators within buffered distances to populated blocks."),
    ("Haz_Waste_Pctl", "float64", f"Hazardous waste {PCT}. {ZERO_PCT}"),
    ("ImpairedWaterBodies", "int32", "Number of pollutants across all impaired water bodies "
     "within buffered distances to populated blocks and the census tract."),
    ("ImpWaterBodPctl", "float64", f"Impaired waters {PCT}. {ZERO_PCT}"),
    ("SolidWaste", "float64", "Sum of weighted solid waste sites and facilities within buffered "
     "distances to populated blocks."),
    ("SolidWastePctl", "float64", f"Solid waste {PCT}. {ZERO_PCT}"),
    ("SmATS", "float64", "Small air toxic sites: sum of CEIDARS emissions sites and oil and "
     "natural gas well sites within buffered distances to populated blocks."),
    ("SmATS_Pctl", "float64", f"Small air toxic sites {PCT}. {ZERO_PCT}"),
    ("Pollution", "float64", "Pollution Burden: average of the Pollution Burden indicator "
     "percentiles, with Environmental Effects indicators weighted by one half."),
    ("PollutionScore", "float64", "Pollution Burden scaled from 0 to 10; used to calculate the "
     "CalEnviroScreen 5.0 score."),
    ("Pollution_Pctl", "float64", f"Pollution Burden {PCT}."),
    ("asthma", "float64", "Age-adjusted rate of emergency department visits for asthma. "
     f"{NA} (33 tracts)."),
    ("Asthma_Pctl", "float64", f"Asthma {PCT}. {NA} (33 tracts)."),
    ("Low_Birth_Weight", "float64", "Percent of infants weighing less than 2,500 grams (about "
     f"5.5 pounds). {NA} (234 tracts with too few births)."),
    ("LowBirthW_Pctl", "float64", f"Low-birth-weight infants {PCT}. {NA} (234 tracts)."),
    ("Cardiovascular", "float64", "Age-adjusted rate of emergency department visits for heart "
     f"attacks per 10,000. {NA} (26 tracts)."),
    ("CVD_Pctl", "float64", f"Cardiovascular disease {PCT}. {NA} (26 tracts)."),
    ("diabetes", "float64", "Model-based prevalence of diabetes in adults aged 18 and older. "
     f"{NA} (36 tracts)."),
    ("DiabetesPctl", "float64", f"Diabetes prevalence {PCT}. {NA} (36 tracts)."),
    ("Education", "float64", "Percent of the population aged 25 and over with less than a high "
     f"school education. {NA} (28 tracts)."),
    ("Education_Pctl", "float64", f"Educational attainment {PCT}. {NA} (28 tracts)."),
    ("Linguistic_Isol", "float64", "Percent of households where no one over age 14 speaks "
     f"English well. {NA} (58 tracts)."),
    ("Linguistic_Pctl", "float64", f"Linguistic isolation {PCT}. {NA} (58 tracts)."),
    ("Poverty", "float64", "Percent of people living below twice the federal poverty level. "
     f"{NA} (50 tracts)."),
    ("Poverty_Pctl", "float64", f"Poverty {PCT}. {NA} (50 tracts)."),
    ("Unemployment", "float64", "Percent of people aged 16 and older who are unemployed and "
     f"eligible for the workforce. {NA} (45 tracts)."),
    ("Unemploy_Pctl", "float64", f"Unemployment {PCT}. {NA} (45 tracts)."),
    ("HousBurd", "float64", "Percent of households that are both low-income and severely "
     f"burdened by housing costs. {NA} (64 tracts)."),
    ("HousBurd_Pctl", "float64", f"Housing burden {PCT}. {NA} (64 tracts)."),
    ("PopChar", "float64", "Population Characteristics: average of the Population "
     f"Characteristics indicator percentiles. {NA} (73 tracts)."),
    ("PopCharScore", "float64", "Population Characteristics scaled from 0 to 10; used to "
     f"calculate the CalEnviroScreen 5.0 score. {NA} (73 tracts)."),
    ("PopCharPctl", "float64", f"Population Characteristics {PCT}. {NA} (73 tracts)."),
]
DEMO = "2020–2024 American Community Survey 5-year estimate"
for name, what in (("pop_und10", "children under 10 years old"),
                   ("pop_10_64", "people aged 10 to 64"),
                   ("pop_ov64", "people aged 65 and older"),
                   ("Hispanic", "people who identify as Hispanic or Latino"),
                   ("white", "people who identify as non-Hispanic white"),
                   ("black", "people who identify as non-Hispanic African American or Black"),
                   ("Native_American", "people who identify as non-Hispanic Native American"),
                   ("asian", "people who identify as non-Hispanic Asian"),
                   ("Pacific_Islander", "people who identify as non-Hispanic Pacific Islander"),
                   ("Other_Multiple", "people who identify as non-Hispanic other or multiple "
                                      "races")):
    C.append((name, "float64", f"Percent of the tract's population who are {what} ({DEMO}). "
              "Empty (null) for the 25 tracts with zero population."))
C += [
    ("Shape_Length", "float64", "Perimeter of the census tract polygon in meters, from OEHHA's "
     "geometry (California Albers, EPSG:3310)."),
    ("Shape_Area", "float64", "Area of the census tract polygon in square meters, from OEHHA's "
     "geometry (California Albers, EPSG:3310)."),
    ("Shape", "geometry", "Census tract polygon (WGS 84)."),
    ("h10", "uint64", "H3 cell ID at resolution 10 (native resolution)."),
    ("h9", "uint64", "H3 cell ID at resolution 9."),
    ("h8", "uint64", "H3 cell ID at resolution 8, the catalog's common join resolution."),
    ("h0", "int64", "H3 cell ID at resolution 0, the partition key for hive-partitioned reads."),
]
H = ("h10", "h9", "h8", "h0")


def col(c):
    d = {"name": c[0], "type": c[1], "description": c[2]}
    if len(c) > 3:
        d["values"] = c[3]
    return d


TILE = {"string": "String", "geometry": None}
attrs = [c for c in C if c[0] not in H]
parquet_cols = [{"name": c[0], "type": c[1]} for c in attrs]
hex_cols = [{"name": c[0], "type": c[1]} for c in C if c[1] != "geometry"]
tile_cols = [{"name": c[0], "type": TILE.get(c[1], "Number")} for c in attrs if c[1] != "geometry"]

DESC = (
    "CalEnviroScreen 5.0 is California's cumulative environmental pollution and health "
    "vulnerability screening tool, published by the Office of Environmental Health Hazard "
    "Assessment (OEHHA). This is the final release (July 2026), which replaces the January 2026 "
    "public-review draft held here before. It scores all 9,106 California census tracts (2020 "
    "geography) on 14 Pollution Burden indicators and 9 Population Characteristics indicators. "
    "The CalEnviroScreen score is the Pollution Burden Score multiplied by the Population "
    "Characteristics Score, and `CIscoreP` is its statewide percentile. 73 tracts have no score "
    "because too few people live there or too many population indicators are missing.\n\n"
    "Column names are OEHHA's from the final geodatabase. Several differ from the draft "
    "(for example the score percentile is `CIscoreP`, not `CIscore_Pctl`). Missing values (NA "
    "in OEHHA's tables) are stored as null. A raw indicator value of 0 means monitoring or "
    "reporting found no impact; such tracts get percentile 0 and are left out of that "
    "indicator's percentile ranking.\n\n"
    "Every attribute is a per-tract value. On the hex asset each tract's row is repeated on "
    "every H3 cell it covers, so count or average tracts after deduplicating by `_cng_fid`:\n\n"
    "```sql\nSELECT county, AVG(CIscoreP) FROM (SELECT DISTINCT _cng_fid, county, CIscoreP "
    "FROM hex WHERE h8 IN (...)) GROUP BY county\n```\n\n"
    "The temporal extent is the 2020–2024 American Community Survey window used for the "
    "population and demographic columns; each indicator draws on its own source years, "
    "described in OEHHA's CalEnviroScreen 5.0 report.\n\n"
    f"Source: the final CalEnviroScreen 5.0 geodatabase, layer CES5_final_results, from the "
    f"California Open Data Portal ({PKG}), accessed {ACCESSED}. Staged copy: "
    f"{RAW}{GDB[0]}, {GDB[1]:,} bytes, sha256 {GDB[2]}. OEHHA's data dictionary is published "
    "beside the data.\n\n"
    "Licence: no licence has been granted. The California Open Data Portal lists the dataset "
    "as \"License not specified\", and OEHHA publishes no terms of use for CalEnviroScreen. "
    "Cite OEHHA as the source."
)

CITE = ("California Office of Environmental Health Hazard Assessment. (2026). CalEnviroScreen "
        f"5.0 [Data set]. California Open Data Portal. {PKG} (accessed {ACCESSED})")


def build(live):
    c = {k: live[k] for k in ("stac_version", "type", "id")}
    c["stac_extensions"] = [
        "https://stac-extensions.github.io/table/v1.2.0/schema.json",
        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
        "https://stac-extensions.github.io/version/v1.2.0/schema.json"]
    c["title"] = "CalEnviroScreen 5.0"
    c["description"] = DESC
    c["version"] = "5.0"
    c["license"] = "other"
    c["extent"] = {"spatial": {"bbox": [[-124.48, 32.53, -114.13, 42.01]]},
                   "temporal": {"interval": [["2020-01-01T00:00:00Z", "2024-12-31T23:59:59Z"]]}}
    c["providers"] = [
        {"name": "California Office of Environmental Health Hazard Assessment (OEHHA)",
         "roles": ["producer"], "url": "https://oehha.ca.gov/calenviroscreen"},
        {"name": "Boettiger Lab", "roles": ["processor", "host"],
         "url": "https://github.com/boettiger-lab"}]
    c["sci:citation"] = CITE
    c["created"] = live.get("created", "2026-02-18T16:11:04Z")
    c["updated"] = "2026-11-18T00:00:00Z"
    c["table:columns"] = [col(x) for x in C]
    c["links"] = [
        {"rel": "self", "href": f"{B}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",
         "type": "application/json"},
        {"rel": "parent", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",
         "type": "application/json"},
        {"rel": "describedby", "href": f"{B}/README.md", "type": "text/markdown"},
        {"rel": "describedby", "href": f"{D}/{DICT}", "type": "application/pdf",
         "title": "CalEnviroScreen 5.0 data dictionary (OEHHA)"},
        {"rel": "about", "href": PKG, "type": "text/html",
         "title": "CalEnviroScreen 5.0 on the California Open Data Portal"},
        {"rel": "about", "href": "https://oehha.ca.gov/calenviroscreen", "type": "text/html",
         "title": "CalEnviroScreen (OEHHA)"},
        {"rel": "license", "type": "application/json",
         "href": "https://data.ca.gov/api/3/action/package_show?id=calenviroscreen-5-0",
         "title": "California Open Data Portal record: license \"License not specified\""},
        {"rel": "pmtiles", "href": f"{D}/ces5.pmtiles", "type": "application/vnd.pmtiles",
         "title": "CalEnviroScreen 5.0 census tracts", "pmtiles:layers": ["ces5"]},
    ]
    a = live["assets"]
    c["assets"] = {
        "ces5-parquet": {
            "href": f"{D}/ces5.parquet", "type": "application/vnd.apache.parquet",
            "title": "CalEnviroScreen 5.0 census tracts (GeoParquet)",
            "description": "One row per census tract with every CalEnviroScreen 5.0 indicator, "
                           "percentile, score and demographic column (WGS 84).",
            "roles": ["data"], "created": "2026-11-18T02:56:40Z", "table:columns": parquet_cols},
        "ces5-pmtiles": {
            "href": f"{D}/ces5.pmtiles", "type": "application/vnd.pmtiles",
            "title": "CalEnviroScreen 5.0 census tracts (PMTiles)",
            "description": "Vector tiles of the census tracts with all attributes, for web maps. "
                           "Source layer ces5.",
            "roles": ["data", "visual"], "vector:layers": ["ces5"],
            "created": "2026-11-18T02:57:57Z", "table:columns": tile_cols},
        "ces5-hex": {
            "href": f"{D}/ces5/hex/h0=*/data_0.parquet", "type": "application/vnd.apache.parquet",
            "title": "CalEnviroScreen 5.0 on H3 cells (resolution 10)",
            "description": "One row per (census tract, H3 resolution 10 cell), with parent cells "
                           "at resolutions 9, 8 and 0, partitioned by h0. Every attribute is a "
                           "per-tract value repeated on every cell the tract covers, so none is "
                           "safe to SUM or AVG on the hex rows; deduplicate by _cng_fid first "
                           "(COUNT(DISTINCT _cng_fid) counts tracts).",
            "roles": ["data"], "h3:native_resolution": 10, "h3:parent_resolutions": [9, 8, 0],
            "created": "HEX_CREATED", "table:columns": hex_cols},
        "data_dictionary": {
            "href": f"{D}/{DICT}", "type": "application/pdf",
            "title": "CalEnviroScreen 5.0 data dictionary (OEHHA)",
            "description": "OEHHA's data dictionary for the final results, with counts of zero "
                           "and missing values per indicator and what they mean.",
            "roles": ["metadata"]},
        "readme": a["readme"],
        "style-ces5-ciscore-pctl": {
            **a["style-ces5-ciscore-pctl"],
            "title": "CalEnviroScreen 5.0 percentile",
            "description": "Census tracts shaded by CalEnviroScreen 5.0 percentile, from green "
                           "(lowest cumulative burden) through yellow to red (highest). Grey "
                           "tracts have no score."},
        "thumbnail": a["thumbnail"],
    }
    return c


README = """# CalEnviroScreen 5.0

CalEnviroScreen is California's cumulative environmental pollution and health vulnerability
screening tool, published by the Office of Environmental Health Hazard Assessment (OEHHA). It
scores all 9,106 California census tracts (2020 geography) on 14 Pollution Burden indicators and
9 Population Characteristics indicators:

> CalEnviroScreen score = Pollution Burden Score × Population Characteristics Score

Both component scores run from 0 to 10, so the score runs from 0 to 100. `CIscoreP` is its
statewide percentile. 73 tracts have no score because too few people live there or too many
population indicators are missing.

This is the final CalEnviroScreen 5.0, released July 2026. It replaces the January 2026
public-review draft that was published here before. OEHHA renamed most columns between the draft
and the final (the score percentile is now `CIscoreP`, not `CIscore_Pctl`), and this dataset uses
the final names.

## Files

Base URL: `https://s3-west.nrp-nautilus.io/public-calenviroscreen/`

| Format | Path | Description |
|--------|------|-------------|
| GeoParquet | `calenviroscreen-5-0/ces5.parquet` | Census tract polygons with all attributes |
| PMTiles | `calenviroscreen-5-0/ces5.pmtiles` | Vector tiles for web maps, source layer `ces5` |
| H3 hex Parquet | `calenviroscreen-5-0/ces5/hex/h0={cell}/data_0.parquet` | H3 resolution 10, with parents 9, 8 and 0 |
| Data dictionary | `calenviroscreen-5-0/final-calenviroscreen-5.0-data-dictionary.pdf` | OEHHA's dictionary and notes on zeros and missing values |

On the hex files each tract's row is repeated on every H3 cell the tract covers. Deduplicate by
`_cng_fid` before counting or averaging tracts.

## MapLibre GL JS

The PMTiles source layer is `ces5`.

```javascript
map.addSource("ces5", {
  type: "vector",
  url: "pmtiles://https://s3-west.nrp-nautilus.io/public-calenviroscreen/calenviroscreen-5-0/ces5.pmtiles",
});
map.addLayer({
  id: "ces5-fill",
  type: "fill",
  source: "ces5",
  "source-layer": "ces5",
  paint: {
    "fill-color": ["case", ["==", ["typeof", ["get", "CIscoreP"]], "number"],
      ["interpolate", ["linear"], ["get", "CIscoreP"],
        0, "#1A9641", 25, "#A6D96A", 50, "#FFFFBF", 75, "#FDAE61", 100, "#D7191C"],
      "#cccccc"],
    "fill-opacity": 0.7,
  },
});
```

## DuckDB

```sql
INSTALL spatial; LOAD spatial;

-- the 10 highest-scoring tracts
SELECT tract, county, ApproxLoc, CIscore, CIscoreP, Population
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-calenviroscreen/calenviroscreen-5-0/ces5.parquet')
ORDER BY CIscore DESC NULLS LAST
LIMIT 10;

-- tracts in the top 25% statewide, by county
SELECT county, COUNT(*) AS tracts, SUM(Population) AS people
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-calenviroscreen/calenviroscreen-5-0/ces5.parquet')
WHERE CIscoreP >= 75
GROUP BY county
ORDER BY people DESC;
```

## Columns

Missing values (NA in OEHHA's tables) are stored as null. A raw indicator value of 0 means
monitoring or reporting found no impact; such tracts get percentile 0 and are left out of that
indicator's percentile ranking.

| Column | Type | Description |
|--------|------|-------------|
COLUMNS

## Source and licence

Final CalEnviroScreen 5.0 geodatabase (`calenviroscreen50results_f_070126.gdb.zip`, layer
`CES5_final_results`) from the California Open Data Portal,
<https://data.ca.gov/dataset/calenviroscreen-5-0>, accessed 2026-11-18. The staged copy is
`s3://public-calenviroscreen/raw/ces5-final/calenviroscreen50results_f_070126.gdb.zip`,
21,992,716 bytes, sha256 `5bcb8afe5b01f477488339320e12c94d0436245cb21cafca9eaa77c398327f6f`.

No licence has been granted. The California Open Data Portal lists the dataset as "License not
specified", and OEHHA publishes no terms of use for CalEnviroScreen.

## Citation

California Office of Environmental Health Hazard Assessment. (2026). CalEnviroScreen 5.0
[Data set]. California Open Data Portal. https://data.ca.gov/dataset/calenviroscreen-5-0

Contact: calenviroscreen@oehha.ca.gov
"""


def readme():
    rows = "\n".join(f"| `{c[0]}` | {c[1]} | {c[2]} |" for c in C)
    return README.replace("COLUMNS", rows)


if __name__ == "__main__":
    live = json.load(open(sys.argv[1]))
    out = build(live)
    out["assets"]["ces5-hex"]["created"] = sys.argv[3]  # the hex objects' LastModified
    json.dump(out, open(sys.argv[2], "w"), indent=2, ensure_ascii=False)
    if len(sys.argv) > 4:
        open(sys.argv[4], "w").write(readme())
