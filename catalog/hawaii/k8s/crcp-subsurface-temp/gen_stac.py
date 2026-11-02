"""STAC collection + README for public-hawaii/crcp-subsurface-temp (#817)."""
import json, os

OUT = os.environ.get("STAC_OUT", "/tmp/crcp-subsurface-temp-stac"); os.makedirs(OUT, exist_ok=True)
S3 = "https://s3-west.nrp-nautilus.io/public-hawaii"
NAME = "crcp-subsurface-temp"
ERDDAP = "https://www.ncei.noaa.gov/erddap/tabledap/CRCP_Subsurface_Temp_Hawaii.html"
INFO = "https://www.ncei.noaa.gov/erddap/info/CRCP_Subsurface_Temp_Hawaii/index.html"
PD = "https://www.noaa.gov/information-technology/public-domain"

REGIONS = ["Main Hawaiian Islands", "Northwestern Hawaiian Islands"]
REGIONS_RAW = ["MHI", "Main Hawaiian Islands", "NWHI", "Northwestern Hawaiian Islands"]
LOCS = sorted(["Pearl & Hermes", "Kure", "Lisianski", "French Frigate", "Oahu", "Hawaii", "Kauai",
               "Molokai", "Maui", "Lanai", "Niihau", "Laysan", "Molokini", "Lehua"])


def col(name, typ, desc, values=None):
    c = {"name": name, "type": typ, "description": desc}
    if values is not None:
        c["values"] = values
    return c


SITEID = col("OCC_SITEID", "string", "NOAA site identifier for the logger site (for example OCC-OAH-001). Each site has one logger position.")
DEPTH = col("DEPTH_M", "double", "Logger depth in metres below the surface, as recorded for this deployment (0.3 to 38.6). Re-measured at each deployment, so it differs slightly between deployments at one site.")
LOC = col("LOCATION", "string", "Island or atoll where the site is.", LOCS)
LAT = col("latitude", "double", "Latitude of the logger (decimal degrees, WGS 84).")
LON = col("longitude", "double", "Longitude of the logger (decimal degrees, WGS 84).")
DEPID = col("INSTFIELDSUMMARYID", "string", "NOAA identifier for one logger deployment (one instrument, one site, deploy to retrieve). Joins readings to the deployments table.")
SN = col("INSTRUMENTSN", "string", "Serial number of the logger.")

site_cols = [
    col("_cng_fid", "int64", "Feature identifier added during processing; one per site, so COUNT(DISTINCT _cng_fid) counts sites."),
    SITEID,
    col("depth_min_m", "double", "Shallowest logger depth recorded at this site over its deployments, metres. Depth is re-measured at each deployment, so it varies slightly (at most 3.5 m within a site)."),
    col("depth_max_m", "double", "Deepest logger depth recorded at this site over its deployments, metres."),
    col("REGION", "string", "Region, as one of two names. Upstream spells each region two ways (MHI and Main Hawaiian Islands, NWHI and Northwestern Hawaiian Islands); this layer uses the long form.", REGIONS),
    LOC,
    col("latitude", "double", "Latitude of the site (decimal degrees, WGS 84): the median over its deployments, which sit within a few metres of each other."),
    col("longitude", "double", "Longitude of the site (decimal degrees, WGS 84): the median over its deployments."),
    col("n_deployments", "int64", "Number of logger deployments at this site (1 to 5)."),
    col("instrument_types", "string", "Logger types used at this site. Values: STR=Subsurface Temperature Recorder.", ["STR"]),
    col("n_obs", "int64", "Number of temperature readings at this site over the whole record."),
    col("first_time", "timestamp", "Time of the first reading at this site (UTC)."),
    col("last_time", "timestamp", "Time of the last reading at this site (UTC)."),
    col("temp_min_c", "double", "Lowest temperature recorded at this site, °C."),
    col("temp_mean_c", "double", "Mean of all readings at this site, °C. Readings are evenly spaced within a deployment but deployments cover different periods, so this is not a climatological mean."),
    col("temp_max_c", "double", "Highest temperature recorded at this site, °C."),
    col("geometry", "geometry", "Point at the site (WGS 84 / OGC:CRS84)."),
]

obs_cols = [
    SITEID, DEPTH,
    col("time", "timestamp", "Time of the reading (UTC). Loggers record every 5 minutes on most deployments."),
    col("TEMP_C", "double", "Water temperature at the logger, °C (16.0 to 32.9; no missing values)."),
    DEPID, SN, LAT, LON,
    col("REGION", "string", "Region as recorded upstream, which spells each region two ways. Normalise before grouping: CASE WHEN REGION IN ('MHI', 'Main Hawaiian Islands') THEN 'Main Hawaiian Islands' ELSE 'Northwestern Hawaiian Islands' END.", REGIONS_RAW),
    LOC,
]

dep_cols = [
    DEPID, SITEID, DEPTH,
    col("REGION", "string", "Region as recorded upstream, which spells each region two ways. Normalise before grouping: CASE WHEN REGION IN ('MHI', 'Main Hawaiian Islands') THEN 'Main Hawaiian Islands' ELSE 'Northwestern Hawaiian Islands' END.", REGIONS_RAW),
    LOC, LAT, LON,
    col("INSTRUMENT_TYPE", "string", "Logger type. Values: STR=Subsurface Temperature Recorder.", ["STR"]),
    SN,
    col("DEPLOY_CRUISE", "string", "Research cruise on which the logger was deployed."),
    col("DEPLOY_UTC", "timestamp", "Time the logger was deployed (UTC)."),
    col("RETRIEVE_CRUISE", "string", "Research cruise on which the logger was retrieved."),
    col("RETRIEVE_UTC", "timestamp", "Time the logger was retrieved (UTC)."),
    col("VALID_DATA_START", "timestamp", "Start of the period NOAA marks as valid data for this deployment (UTC)."),
    col("VALID_DATA_END", "timestamp", "End of the period NOAA marks as valid data for this deployment (UTC)."),
    col("accession_url", "string", "NCEI archive accession that holds this deployment's original data."),
    col("n_obs", "int64", "Number of readings in this deployment."),
    col("first_time", "timestamp", "Time of the deployment's first reading (UTC)."),
    col("last_time", "timestamp", "Time of the deployment's last reading (UTC)."),
    col("temp_min_c", "double", "Lowest temperature in this deployment, °C."),
    col("temp_mean_c", "double", "Mean temperature over this deployment, °C."),
    col("temp_max_c", "double", "Highest temperature in this deployment, °C."),
]


# One text per column name across every asset (verify-stac #303 fold); grain lives in asset descriptions.
REGION_DESC = ("Region. Values: MHI=Main Hawaiian Islands, NWHI=Northwestern Hawaiian Islands; upstream also "
               "writes each in full (Main Hawaiian Islands, Northwestern Hawaiian Islands). The site layer uses only "
               "the full names. On readings and deployments, normalise before grouping: CASE WHEN REGION IN "
               "('MHI', 'Main Hawaiian Islands') THEN 'Main Hawaiian Islands' ELSE 'Northwestern Hawaiian Islands' END.")
SHARED = {
    "latitude": "Latitude (decimal degrees, WGS 84). On the site layer, the median over the site's deployments, which sit within a few metres of each other.",
    "longitude": "Longitude (decimal degrees, WGS 84). On the site layer, the median over the site's deployments.",
    "n_obs": "Number of temperature readings in the row's scope: the whole site record on the site layer, one deployment on deployments.",
    "first_time": "Time of the first reading in the row's scope (UTC).",
    "last_time": "Time of the last reading in the row's scope (UTC).",
    "temp_min_c": "Lowest temperature in the row's scope, °C.",
    "temp_mean_c": "Mean of the readings in the row's scope, °C. Readings are evenly spaced within a deployment but deployments cover different periods, so a site mean is not a climatological mean.",
    "temp_max_c": "Highest temperature in the row's scope, °C.",
}


def unify(cols):
    for c in cols:
        if c["name"] == "REGION":
            c["description"] = REGION_DESC
        elif c["name"] in SHARED:
            c["description"] = SHARED[c["name"]]
    return cols


site_cols, obs_cols, dep_cols = unify(site_cols), unify(obs_cols), unify(dep_cols)

def pm(cols):
    out = []
    for c in cols:
        if c["type"] == "geometry":
            continue
        t = "number" if c["type"] in ("int64", "double") else "string"
        d = {"name": c["name"], "type": t}
        if "values" in c:
            d["values"] = c["values"]
        out.append(d)
    return out


hex_cols = [c for c in site_cols if c["type"] != "geometry"] + [
    col("h8", "uint64", "H3 cell ID at resolution 8 (native resolution) containing the logger."),
    col("h0", "int64", "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."),
]

desc = (
    "In-water temperature records from NOAA's National Coral Reef Monitoring Program subsurface "
    "temperature recorders (STRs) at permanent coral reef monitoring sites across the Main and "
    "Northwestern Hawaiian Islands, March 2005 to August 2024: 145 logger sites (0.3 to 38.6 m deep) "
    "and 88,808,469 readings, mostly every 5 minutes. "
    "This is the in-situ companion to satellite sea surface temperature: it records the temperature "
    "the reef experiences at depth.\n\n"
    "**Three tables.** The site layer (GeoParquet, PMTiles and hex) has one point per site, with its "
    "recorded depth range, number of deployments, first and last reading and temperature range. "
    "`observations` has "
    "every reading. `deployments` has one row per logger deployment, with instrument, cruises, "
    "deploy and retrieve times, recorded depth and NOAA's valid-data window. Readings and deployments "
    "join to the site layer on `OCC_SITEID`, and to each other on `INSTFIELDSUMMARYID`. Logger depth "
    "is re-measured at each deployment and varies by up to 3.5 m within a site; each reading carries "
    "its deployment's depth.\n\n"
    "```sql\n-- daily mean temperature at one site\n"
    "SELECT date_trunc('day', time) AS day, avg(TEMP_C)\n"
    "FROM read_parquet('<observations>')\nWHERE OCC_SITEID = 'OCC-OAH-001'\nGROUP BY 1 ORDER BY 1\n```\n\n"
    "**Region names.** Upstream spells each region two ways (`MHI` and `Main Hawaiian Islands`, `NWHI` "
    "and `Northwestern Hawaiian Islands`), so filtering on one spelling drops sites such as Niʻihau "
    "and Molokini. The site layer uses the long form; the readings and deployments keep the upstream "
    "value, and their `REGION` description gives the expression that normalises it.\n\n"
    "**Changes from upstream.** Upstream serves about a third of its rows more than once: 136,474,266 "
    "rows hold 88,808,469 distinct readings. The extra copies are dropped. Five deployments "
    "(2306–2309, 2311, Hawaiʻi Island 2016–2019) are served twice, the second copy with the serial "
    "number in scientific notation and times cut to the minute; the full-precision values are kept. "
    "The date-part columns upstream repeats beside `time` (year, month, day, hour, minute, second and "
    "two timestamp copies) are dropped. 344 readings share a site, depth and time but come from two "
    "different deployments with different temperatures; both are kept.\n\n"
    "**Licence.** A US Government work by NOAA, in the public domain. NOAA's metadata state: \"No "
    "access constraints are applicable\" and \"No use constraints are applicable\".\n\n"
    "**Provenance.** Pulled in full from NCEI ERDDAP dataset `CRCP_Subsurface_Temp_Hawaii` "
    "(`date_created` 2026-06-12) on 2026-11-02, one site at a time. Staged copy: "
    "`s3://public-hawaii/raw/crcp-subsurface-temp/` (145 per-site files, 2,597,090,082 bytes in all), "
    "with per-file sizes and sha256 in `MANIFEST.sha256` (sha256 "
    "88355806aca4a2b83f10e529f41b7af881626b41d35a037a9cd8ec9a4bba1f5b). The original data are held in "
    "NCEI accessions 0162216, 0162219, 0210383 and 0300489."
)

hex_desc = (
    "H3 index of the 145 logger sites at resolution 8 (each point falls in one cell of about "
    "0.74 km²), hive-partitioned by h0. One row per site: a point covers a single cell, so per-site "
    "values such as n_obs are not repeated and can be summed directly. Some neighbouring sites share "
    "a cell (145 sites fall in 109 cells), so count sites with COUNT(DISTINCT _cng_fid), not by "
    "cells. Point data at resolution 8; it carries no finer resolution."
)

links = [
    {"rel": "self", "href": f"{S3}/{NAME}/stac-collection.json", "type": "application/json"},
    {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json"},
    {"rel": "parent", "href": f"{S3}/stac-collection.json", "type": "application/json"},
    {"rel": "describedby", "href": f"{S3}/{NAME}/README.md", "type": "text/markdown"},
    {"rel": "about", "href": INFO, "type": "text/html", "title": "NCEI ERDDAP: CRCP_Subsurface_Temp_Hawaii (metadata)"},
    {"rel": "via", "href": ERDDAP, "type": "text/html", "title": "NCEI ERDDAP tabledap access form"},
    {"rel": "license", "href": PD, "type": "text/html", "title": "NOAA: public domain"},
]

stac = {
    "type": "Collection", "stac_version": "1.0.0",
    "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json",
                        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"],
    "id": NAME,
    "title": "NOAA Subsurface Temperature Loggers, Hawaiian Islands (2005–2024)",
    "description": desc,
    "license": "public-domain",
    "keywords": ["Hawaii", "coral reef", "water temperature", "in situ", "NCRMP", "NOAA", "HI-GLEN"],
    "providers": [
        {"name": "NOAA Coral Reef Conservation Program (National Coral Reef Monitoring Program)", "roles": ["producer"], "url": "https://www.coris.noaa.gov/monitoring/biological.html"},
        {"name": "NOAA National Centers for Environmental Information (NCEI)", "roles": ["host"], "url": "https://www.ncei.noaa.gov/"},
        {"name": "Boettiger Lab", "roles": ["processor", "host"], "url": "https://github.com/boettiger-lab/data-workflows"},
    ],
    "sci:citation": ("NOAA Coral Reef Conservation Program. National Coral Reef Monitoring Program: subsurface "
                     "temperature recorder data for the Hawaiian Islands. NCEI ERDDAP dataset "
                     "CRCP_Subsurface_Temp_Hawaii. Accessed 2026-11-02 from " + ERDDAP),
    "created": "2026-11-02T17:40:43Z", "updated": "2026-11-02T17:43:45Z",
    "extent": {"spatial": {"bbox": [[-178.384244, 18.92253, -154.8176, 28.459226]]},
               "temporal": {"interval": [["2005-03-02T21:30:00Z", "2024-08-25T19:59:59Z"]]}},
    "links": links,
    "assets": {
        f"{NAME}-parquet": {
            "href": f"{S3}/{NAME}.parquet", "type": "application/vnd.apache.parquet",
            "title": "GeoParquet: 145 logger sites", "roles": ["data"],
            "created": "2026-11-02T17:42:07Z",
            "description": "One point per logger site, with recorded depth range, deployment count, first and last reading and temperature range.",
            "table:columns": site_cols,
        },
        f"{NAME}-pmtiles": {
            "href": f"{S3}/{NAME}.pmtiles", "type": "application/vnd.pmtiles",
            "title": "PMTiles vector tiles of logger sites", "roles": ["visual"],
            "created": "2026-11-02T17:42:43Z",
            "description": f"Vector tiles of the logger sites for web maps. MapLibre source-layer name: '{NAME}'.",
            "vector:layers": [NAME], "table:columns": pm(site_cols),
        },
        f"{NAME}-hex": {
            "href": f"{S3}/{NAME}/hex/h0=*/data_0.parquet", "type": "application/vnd.apache.parquet",
            "title": "H3 hexagonal index (resolution 8) of logger sites", "roles": ["data"],
            "created": "2026-11-02T17:43:45Z", "description": hex_desc,
            "h3:native_resolution": 8, "h3:parent_resolutions": [0],
            "table:columns": hex_cols,
        },
        f"{NAME}-observations": {
            "href": f"{S3}/{NAME}/observations.parquet", "type": "application/vnd.apache.parquet",
            "title": "Observations: every temperature reading, 2005–2024 (non-spatial table)", "roles": ["data"],
            "created": "2026-11-02T17:40:43Z",
            "description": "One row per reading (88,808,469 rows), sorted by site, depth and time. Join to the site layer on OCC_SITEID, or to deployments on INSTFIELDSUMMARYID.",
            "table:columns": obs_cols,
        },
        f"{NAME}-deployments": {
            "href": f"{S3}/{NAME}/deployments.parquet", "type": "application/vnd.apache.parquet",
            "title": "Deployments: one row per logger deployment (non-spatial table)", "roles": ["data"],
            "created": "2026-11-02T17:40:47Z",
            "description": "One row per logger deployment (308 rows), with instrument, cruises, deploy and retrieve times, NOAA's valid-data window and summary statistics of its readings.",
            "table:columns": dep_cols,
        },
    },
}

json.dump(stac, open(os.path.join(OUT, "stac-collection.json"), "w"), indent=2, ensure_ascii=False)

readme = f"""# NOAA Subsurface Temperature Loggers, Hawaiian Islands (2005–2024)

In-water temperature from NOAA National Coral Reef Monitoring Program subsurface temperature
recorders at coral reef monitoring sites in the Main and Northwestern Hawaiian Islands: 145 logger
sites (0.3–38.6 m deep) and 88.8 million readings, mostly every 5 minutes, from
March 2005 to August 2024. Public domain (NOAA).

| File | Contents |
|---|---|
| `{NAME}.parquet` | GeoParquet, one point per logger site |
| `{NAME}.pmtiles` | Vector tiles of the same points (source-layer `{NAME}`) |
| `{NAME}/hex/h0=*/data_0.parquet` | H3 resolution 8 index of the points |
| `{NAME}/observations.parquet` | Every reading |
| `{NAME}/deployments.parquet` | One row per logger deployment |

Upstream spells each region two ways (`MHI` / `Main Hawaiian Islands`, `NWHI` /
`Northwestern Hawaiian Islands`). The site layer uses the long form; normalise the other tables
before grouping by region. Repeated rows upstream (about a third) were dropped; see the STAC
collection for details and provenance.

## DuckDB

```sql
INSTALL httpfs; LOAD httpfs;
SELECT date_trunc('month', time) AS month, avg(TEMP_C) AS mean_c
FROM read_parquet('{S3}/{NAME}/observations.parquet')
WHERE OCC_SITEID = 'OCC-OAH-001'
GROUP BY 1 ORDER BY 1;
```

## MapLibre GL JS

```js
map.addSource('{NAME}', {{
  type: 'vector',
  url: 'pmtiles://{S3}/{NAME}.pmtiles'
}});
map.addLayer({{
  id: '{NAME}',
  type: 'circle',
  source: '{NAME}',
  'source-layer': '{NAME}',
  paint: {{ 'circle-radius': 4, 'circle-color': '#0b6e99' }}
}});
```

Source: NOAA Coral Reef Conservation Program, via NCEI ERDDAP
[`CRCP_Subsurface_Temp_Hawaii`]({ERDDAP}), accessed 2026-11-02.
"""
open(os.path.join(OUT, "README.md"), "w").write(readme)
print("wrote", OUT)
