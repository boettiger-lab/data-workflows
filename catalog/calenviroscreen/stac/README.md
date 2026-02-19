# CalEnviroScreen 5.0 (Draft)

## Overview

CalEnviroScreen is a mapping tool developed by California's Office of Environmental
Health Hazard Assessment (OEHHA) to identify communities disproportionately burdened
by multiple sources of pollution. It combines environmental exposures, environmental
effects, sensitive population health indicators, and socioeconomic factors into a single
cumulative impact score for every California census tract.

Draft CalEnviroScreen 5.0 was released January 2026. It uses **2020 Decennial Census**
tract geography (9,106 tracts), updates all existing indicators, and adds two new
indicators (Children's Lead Risk from Housing and Small Air Toxic Sites) compared to
version 4.1.

The overall **CES 5.0 Score** is calculated as:

> **CES Score = Pollution Burden Score × Population Characteristics Score**

Both component scores are scaled 0–10, so the overall score ranges from 0–100.

## Data Formats & Access

**Base URL**: `https://s3-west.nrp-nautilus.io/public-calenviroscreen/`

| Format | Path | Description |
|--------|------|-------------|
| GeoParquet | `calenviroscreen-5-0/ces5.parquet` | Census-tract polygons with all attributes |
| PMTiles | `calenviroscreen-5-0/ces5.pmtiles` | Vector tiles for web mapping |
| H3 Hex Parquet | `calenviroscreen-5-0/ces5/hex/h0={cell}/data_0.parquet` | H3 resolution 10 with parent resolutions 9, 8, 0 |

## Usage Examples

### MapLibre GL JS

```javascript
map.addSource("ces5", {
  type: "vector",
  url: "pmtiles://https://s3-west.nrp-nautilus.io/public-calenviroscreen/calenviroscreen-5-0/ces5.pmtiles",
});

map.addLayer({
  id: "ces5-fill",
  type: "fill",
  source: "ces5",
  "source-layer": "ces5",   // ← vector layer name inside the PMTiles
  paint: {
    "fill-color": [
      "interpolate", ["linear"],
      ["get", "CIscore_Pctl"],
      0, "#ffffcc", 50, "#fd8d3c", 100, "#800026"
    ],
    "fill-opacity": 0.7
  }
});
```

### DuckDB

```sql
-- Load spatial extension
INSTALL spatial; LOAD spatial;

-- Query top 10 most burdened tracts by CES score
SELECT tract, county, CIscore, CIscore_Pctl, Population
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-calenviroscreen/calenviroscreen-5-0/ces5.parquet')
ORDER BY CIscore DESC NULLS LAST
LIMIT 10;

-- Find tracts in the top 10% of CES score (above 90th percentile)
SELECT tract, county, AppoxLoc, CIscore, CIscore_Pctl,
       Poverty, Asthma_Pctl, DieselPM_Pctl
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-calenviroscreen/calenviroscreen-5-0/ces5.parquet')
WHERE CIscore_Pctl >= 90
ORDER BY CIscore_Pctl DESC;

-- Summary by county: average CES score and most burdened indicators
SELECT county,
       COUNT(*) AS num_tracts,
       ROUND(AVG(CIscore), 2) AS avg_ces_score,
       ROUND(AVG(Poverty), 2) AS avg_poverty_pct,
       ROUND(AVG(AirPM25), 4) AS avg_pm25
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-calenviroscreen/calenviroscreen-5-0/ces5.parquet')
GROUP BY county
ORDER BY avg_ces_score DESC;
```

### Python (GeoPandas)

```python
import geopandas as gpd

ces = gpd.read_parquet(
    "https://s3-west.nrp-nautilus.io/public-calenviroscreen/calenviroscreen-5-0/ces5.parquet"
)

# Top burdened tracts
top_burden = ces.nlargest(100, "CIscore")[
    ["tract", "county", "CIscore", "CIscore_Pctl", "Poverty", "asthma"]
]
print(top_burden)
```

## Data Dictionary

Data source: [Draft CalEnviroScreen 5.0 Data Dictionary (PDF)](https://data.ca.gov/dataset/b38b4e2c-7ef0-47b3-bff0-29e0a80c8ed8/resource/428d0c6f-88cb-4209-bdd4-b1f44188cf01/download/draft-calenviroscreen-5.0-data-dictionary.pdf)

### Identification & Geography

| Column | Type | Description |
|--------|------|-------------|
| `tract` | DOUBLE | Census Tract ID from 2020 Decennial Census |
| `ZIP` | INTEGER | Postal ZIP code for the census tract |
| `AppoxLoc` | VARCHAR | Approximate city or unincorporated area (Esri Demographics 2024; for reference only) |
| `county` | VARCHAR | California county |
| `region` | VARCHAR | California region |
| `Population` | DOUBLE | 2023 5-year ACS population estimate |

### CES Score

| Column | Type | Description |
|--------|------|-------------|
| `CIscore` | DOUBLE | **Draft CES 5.0 Score** — Pollution Burden Score × Population Characteristics Score (range ~0–100) |
| `CIscore_Pctl` | DOUBLE | Percentile of the CES 5.0 Score (0–100) |

### Pollution Burden — Exposure Indicators

Each indicator has a raw value column and a `_Pctl` percentile column (0–100).

| Column | Type | Description |
|--------|------|-------------|
| `AirOzone` | DOUBLE | Mean of summer months (May–Oct) daily max 8-hour ozone concentration |
| `AirOzone_Pctl` | DOUBLE | Ozone percentile |
| `AirPM25` | DOUBLE | Annual mean PM2.5 concentration (µg/m³) |
| `AirPM25_Pctl` | DOUBLE | PM2.5 percentile |
| `ChildLead` | DOUBLE | Potential risk for lead exposure in children in low-income communities with older housing |
| `ChildLead_Pctl` | DOUBLE | Children's Lead Risk from Housing percentile |
| `DieselPM` | DOUBLE | Diesel PM emissions from on-road and non-road sources within and near populated blocks |
| `DieselPM_Pctl` | DOUBLE | Diesel PM percentile |
| `DrinkingWater` | DOUBLE | Drinking water contaminant index for selected contaminants |
| `DrinkingWater_Pctl` | DOUBLE | Drinking Water Contaminants percentile |
| `Pesticides` | DOUBLE | Total pounds of selected active pesticide ingredients per square mile (production agriculture) |
| `Pesticides_Pctl` | DOUBLE | Pesticide Use percentile |
| `ToxReleases` | DOUBLE | Toxicity-weighted air concentrations from chemical releases by large facilities |
| `ToxReleases_Pctl` | DOUBLE | Toxic Releases from Facilities percentile |
| `TrafficImp` | DOUBLE | Traffic density in vehicle-km/hr per road length within 150m of census tract boundary |
| `TrafficImp_Pctl` | DOUBLE | Traffic Impacts percentile |

### Pollution Burden — Environmental Effects Indicators

| Column | Type | Description |
|--------|------|-------------|
| `CleanupSites` | DOUBLE | Sum of weighted EnviroStor cleanup sites and NPL Superfund sites within buffered distances |
| `CleanupSites_Pctl` | DOUBLE | Cleanup Sites percentile |
| `gwthreats` | DOUBLE | Sum of weighted GeoTracker cleanup, land disposal, UST, produced water pond, dairy/feedlot sites within buffered distances |
| `GWThreats_Pctl` | DOUBLE | Groundwater Threats percentile |
| `HazWaste` | DOUBLE | Sum of weighted hazardous waste facilities and large quantity generators within buffered distances |
| `HazWaste_Pctl` | DOUBLE | Hazardous Waste percentile |
| `ImpWaters` | DOUBLE | Sum of pollutants across impaired water bodies within buffered distances |
| `ImpWaters_Pctl` | DOUBLE | Impaired Waters percentile |
| `SmAirToxSites` | DOUBLE | Sum of CEIDARS emissions sites and oil/gas well sites within buffered distances (new in v5.0) |
| `SmAirToxSites_Pctl` | DOUBLE | Small Air Toxic Sites percentile |
| `SolidWaste` | DOUBLE | Sum of weighted solid waste sites and facilities (SWIS) within buffered distances |
| `SolidWaste_Pctl` | DOUBLE | Solid Waste percentile |

### Pollution Burden — Component Score

| Column | Type | Description |
|--------|------|-------------|
| `Pollution` | DOUBLE | Average of percentiles from Pollution Burden indicators (Environmental Effects weighted at 0.5×) |
| `PollutionScore` | DOUBLE | Pollution Burden variable scaled 0–10 (used to calculate CES 5.0 Score) |
| `Pollution_Pctl` | DOUBLE | Pollution Burden percentile |

### Population Characteristics — Sensitive Population Indicators

| Column | Type | Description |
|--------|------|-------------|
| `asthma` | DOUBLE | Age-adjusted rate of emergency department visits for asthma |
| `Asthma_Pctl` | DOUBLE | Asthma percentile |
| `Cardiovascular` | DOUBLE | Age-adjusted rate of ED visits for heart attacks per 10,000 |
| `Cardiovascular_Pctl` | DOUBLE | Cardiovascular Disease percentile |
| `DiabetesPrev` | DOUBLE | Model-based prevalence of diabetes in adults ≥18 years old |
| `DiabetesPrev_Pctl` | DOUBLE | Diabetes Prevalence percentile |
| `LowBirthWeight` | DOUBLE | Percent of infants weighing less than 2,500g (~5.5 lbs) |
| `LowBirthWeight_Pctl` | DOUBLE | Low-Birth-Weight Infants percentile |

### Population Characteristics — Socioeconomic Factors

| Column | Type | Description |
|--------|------|-------------|
| `Education` | DOUBLE | Percentage of population over 25 with less than a high school education |
| `Education_Pctl` | DOUBLE | Educational Attainment percentile |
| `HousingBurden` | DOUBLE | Percentage of households that are low-income AND severely burdened by housing costs |
| `HousingBurden_Pctl` | DOUBLE | Housing Burden percentile |
| `LinguisticIso` | DOUBLE | Percentage of households where no one over age 14 speaks English well |
| `LinguisticIso_Pctl` | DOUBLE | Linguistic Isolation percentile |
| `Poverty` | DOUBLE | Percentage of people living below twice the federal poverty level |
| `Poverty_Pctl` | DOUBLE | Poverty percentile |
| `Unemployment` | DOUBLE | Percentage of people aged 16+ who are unemployed and eligible for the workforce |
| `Unemployment_Pctl` | DOUBLE | Unemployment percentile |

### Population Characteristics — Component Score

| Column | Type | Description |
|--------|------|-------------|
| `PopChar` | DOUBLE | Average of percentiles from Population Characteristics indicators |
| `PopCharScore` | DOUBLE | Population Characteristics variable scaled 0–10 (used to calculate CES 5.0 Score) |
| `PopChar_Pctl` | DOUBLE | Population Characteristics percentile |

### Demographic Profile

| Column | Type | Description |
|--------|------|-------------|
| `PopUnd_10` | DOUBLE | % of population under 10 years old (2023 5-year ACS) |
| `Pop10_64` | DOUBLE | % of population aged 10–64 years (2023 5-year ACS) |
| `PopOver_65` | DOUBLE | % of population 65 years and older (2023 5-year ACS) |
| `White_Pct` | DOUBLE | % non-Hispanic White |
| `Hispanic_Pct` | DOUBLE | % Hispanic or Latino |
| `Black_Pct` | DOUBLE | % non-Hispanic African American or Black |
| `NatAmeri_Pct` | DOUBLE | % non-Hispanic Native American |
| `Asian_Pct` | DOUBLE | % non-Hispanic Asian or Pacific Islander |
| `OtherMulti_Pct` | DOUBLE | % non-Hispanic "other" or multiple races |

### Geometry

| Column | Type | Description |
|--------|------|-------------|
| `Shape` | GEOMETRY | Census tract polygon (EPSG:4326) |
| `Shape_Length` | DOUBLE | Perimeter length |
| `Shape_Area` | DOUBLE | Area |
| `bbox` | STRUCT | Bounding box (xmin, ymin, xmax, ymax) |

## Notes on Zeros and Missing Values

- **NA (missing)**: Indicator value could not be calculated — due to no monitoring, unreliable estimates, or insufficient population. Census tracts with >4 missing Population Characteristics indicators receive NA for the overall CES score.
- **Zero raw value**: Monitoring occurred but no impact detected (e.g., no hazardous facilities within buffer distance). Zeros are excluded from percentile calculations to avoid inflating ranks.
- **Zero percentile**: Assigned to tracts with a raw value of zero, meaning no measurable impact for that indicator.
- Census tracts with <50 people, or <50 people living outside group quarters, receive NA for Population Characteristics.

See the [data dictionary PDF](https://data.ca.gov/dataset/b38b4e2c-7ef0-47b3-bff0-29e0a80c8ed8/resource/428d0c6f-88cb-4209-bdd4-b1f44188cf01/download/draft-calenviroscreen-5.0-data-dictionary.pdf) for full description of zeros and NAs by indicator.

## Citation

California Office of Environmental Health Hazard Assessment (OEHHA). *Draft CalEnviroScreen 5.0*. Released January 2026. Available at: https://oehha.ca.gov/calenviroscreen/general-info/draft-calenviroscreen-50

Contact: calenviroscreen@oehha.ca.gov

## Resources

- [Draft CalEnviroScreen 5.0 Homepage](https://oehha.ca.gov/calenviroscreen/general-info/draft-calenviroscreen-50)
- [CalEnviroScreen FAQs](https://oehha.ca.gov/calenviroscreen/calenviroscreen-faqs)
- [Data Dictionary PDF](https://data.ca.gov/dataset/b38b4e2c-7ef0-47b3-bff0-29e0a80c8ed8/resource/428d0c6f-88cb-4209-bdd4-b1f44188cf01/download/draft-calenviroscreen-5.0-data-dictionary.pdf)
- [California Open Data Portal](https://data.ca.gov/dataset/draft-calenviroscreen-5-0)
- [OEHHA CalEnviroScreen](https://oehha.ca.gov/calenviroscreen)
