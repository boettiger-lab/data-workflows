#!/usr/bin/env python3
"""Write the osds STAC collection and README to a directory (#837).

Usage: python3 gen_stac.py [out-dir]

Counts, ranges, sentinels and value lists were measured on the published data with the
duckdb-geo MCP on 2026-11-02 (BUILD.md). Field meanings come from the two upstream metadata
documents staged beside the raw (osds_oah.pdf, osds_ni.pdf). Asset `created` and collection
`created`/`updated` are read from the S3 Last-Modified of each published object.
"""
import json
import os
import re
import sys
import urllib.request
from email.utils import parsedate_to_datetime

BUCKET = "public-hawaii"
DATASET = "osds"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
TITLE = "Onsite Sewage Disposal Systems (Hawaiʻi DOH, five islands)"
SERVICE = "https://geodata.hawaii.gov/arcgis/rest/services/Infrastructure/MapServer"
LANDING = "https://geoportal.hawaii.gov/datasets/3d638ed89da245949de574c02b5dc911"
PDF_OAHU = "https://files.hawaii.gov/dbedt/op/gis/data/osds_oah.pdf"
PDF_NI = "https://files.hawaii.gov/dbedt/op/gis/data/osds_ni.pdf"
REPORT_OAHU = "http://health.hawaii.gov/wastewater/files/2015/09/OSDS_OAHU.pdf"
REPORT_NI = "http://health.hawaii.gov/wastewater/files/2015/09/OSDS_NI.pdf"
TERMS = "https://portal.ehawaii.gov/page/terms-of-use/"
RETRIEVED = "2026-11-02"
RAW_DIR = f"s3://{BUCKET}/raw/osds/"
RAW = [  # (object, bytes, sha256) recomputed in the stage-raw job from the staged objects
    ("osds-oahu-service-response.geojson", 12121342, "e9f95286005dfb64c9ed2085638abbd4425717da3c600baf7b31bee0c78b042a"),
    ("osds-molokai-service-response.geojson", 1203731, "2106f55609cd7ad97989cdcbba36a0a181c658cf1f72967dde2eb7246eff884c"),
    ("osds-maui-service-response.geojson", 9054743, "1530ccb012fad27c5a9f866ce5262b3e83f776dc3726c256ce731449e3bc213f"),
    ("osds-kauai-service-response.geojson", 9761754, "97a755e45d3906c6d4bb1eabfe6f5384647d8c3ccaabed7c7441a643c9d4a714"),
    ("osds-hawaii-service-response.geojson", 38784619, "6705ed61f8d645a2c473074c8d5b8b5db272d53c58aebda290070a8976417935"),
    ("osds.geojson", 140900116, "749458ff0ae7a915e489071243d72247e07292861f1e8709fe8695fa176c57da"),
]

N = 94996
N_CELLS = 3930
BBOX = [-159.7588334, 18.96406804, -154.8151891, 22.22763561]


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def last_modified(key):
    req = urllib.request.Request(f"{BASE}/{key}", method="HEAD")
    with urllib.request.urlopen(req) as r:
        return parsedate_to_datetime(r.headers["Last-Modified"])


def first_hex_write():
    url = f"{BASE}?list-type=2&prefix={DATASET}/hex/"
    with urllib.request.urlopen(url) as r:
        stamps = re.findall(r"<LastModified>([^<.]+)", r.read().decode())
    return min(stamps) + "Z"


BLANK = "A single space (' ') where the source left the field empty."
O = "Oʻahu (2008) layer only; null on the other islands."
NI = "Neighbour-island (2010) layers only; null on Oʻahu."
NI_TEXT = ("Neighbour-island (2010) layers only: null on Oʻahu, and null on Maui, where the source "
           "stores this text field as a number that is 0 on every row.")


def per_class(prefix, cls, label):
    q = {"I": "soil_qty", "II": "st_qty_1", "III": "au_qty", "IV": "cp_qty"}[cls]
    sfx = "_1" if prefix == "st" else ""
    return [
        (q, f"Number of Class {cls} systems ({label}) on the parcel. {O}"),
        (f"{prefix}_n{sfx}", f"Nitrogen concentration in the effluent of the parcel's Class {cls} systems, documented upstream as mg/L. {O}"),
        (f"{prefix}_p{sfx}", f"Phosphorus concentration in the effluent of the parcel's Class {cls} systems, documented upstream as mg/L. {O}"),
        (f"{prefix}_fc{sfx}", f"Fecal coliform concentration in the effluent of the parcel's Class {cls} systems, documented upstream as colony-forming units per 100 mL. {O}"),
        (f"{prefix}_eff{sfx}", f"Effluent flow from the parcel's Class {cls} systems, gallons per day. {O}"),
        (f"{prefix}_nflx{sfx}", f"Nitrogen flux from the parcel's Class {cls} systems, kilograms per day. {O}"),
        (f"{prefix}_pflx{sfx}", f"Phosphorus flux from the parcel's Class {cls} systems, kilograms per day. {O}"),
    ]


TEXT_NOTE = (" Stored as text in the source: a number, or a single space where the parcel has no "
             "system of this class.")

COLS = [
    ("_cng_fid", "int64", "Unique row identifier assigned at conversion, one per parcel point. Use COUNT(DISTINCT _cng_fid) to count parcels.", None),
    ("OGC_FID", "int64", "Row number assigned by GDAL when the source was read. Carries no meaning of its own.", None),
    ("objectid", "int32", "Feature identifier in the source map service. Unique within one island's layer only: pair it with layer_island.", None),
    ("fid_1", "int32", f"Feature identifier carried over from the source shapefile. {O}", None),
    ("acres", "double", f"Area of the tax map key (TMK) parcel the point represents, in acres (0.05 to 4,915.77). {O}", None),
    ("tmk8_num", "int32", f"Tax map key without its leading county digit, as a number. {O}", None),
    ("tmk8_alph", "string", f"Tax map key without its leading county digit, as text. {O}", None),
    ("tmk_9", "int32", "Nine-digit tax map key of the parcel. Digit 1 is the county (1 = City and County of Honolulu), digit 2 the zone (1–3 Honolulu, 4 Koolaupoko, 5 Koolauloa, 6 Waialua, 7 Wahiawa, 8 Waianae, 9 Ewa), digit 3 the section, digits 4–6 the plat and digits 7–9 the parcel. " + O, None),
    ("type", "string", "Two different fields share this name. On Oʻahu it is the type of system on the parcel: AEROBIC = aerobic treatment unit discharging to a seepage pit, CESSPOOL = cesspool, untreated discharge to a seepage pit, MULTIPLE = at least two systems with different treatment, SEPTIC = septic tank discharging to a seepage pit, SOIL_TMT = a system using soil as the treatment medium. On Kauaʻi, Molokaʻi and Hawaiʻi it marks wastewater treatment plants: WWTP = wastewater treatment plant, Reuse R1 and Reuse R2 = water-reuse plants, Non-Domestic = non-domestic plant, and a single space (' ') on ordinary parcels. Null on Maui, whose source stores this field as a number that is 0 on every row.",
     [" ", "AEROBIC", "CESSPOOL", "MULTIPLE", "Non-Domestic", "Reuse R1", "Reuse R2", "SEPTIC", "SOIL_TMT", "WWTP"]),
    ("osds_class", "string", "Treatment class of the parcel's systems under Hawaiʻi Administrative Rules Title 11 Chapter 62: Class I = soil treatment, Class II = septic tank to seepage pit, Class III = aerobic unit to seepage pit, Class IV = cesspool, Multiple = more than one class on the parcel. " + O,
     ["Class I", "Class II", "Class III", "Class IV", "Multiple"]),
    ("x", "int32", f"Easting of the parcel centroid, UTM zone 4 (NAD 83, not NAD 83 HARN), metres. {O}", None),
    ("y", "int32", f"Northing of the parcel centroid, UTM zone 4 (NAD 83, not NAD 83 HARN), metres. {O}", None),
    *[(n, "int32" if n in ("soil_qty", "soil_n", "soil_p", "soil_fc", "soil_eff") else "double", d, None)
      for n, d in per_class("soil", "I", "soil treatment")],
    *[(n, "string", d + TEXT_NOTE, None) for n, d in per_class("st", "II", "septic tank to seepage pit")],
    *[(n, "string", d + TEXT_NOTE, None) for n, d in per_class("au", "III", "aerobic unit to seepage pit")],
    *[(n, "string", d + TEXT_NOTE, None) for n, d in per_class("cp", "IV", "cesspool")],
    ("ttl_osds", "int32", f"Total number of onsite systems on the parcel (1 to 21). {O}", None),
    ("ttl_eff", "int32", f"Total effluent flow from the parcel's systems, gallons per day (32 to 14,824). {O}", None),
    ("ttl_n", "double", f"Total nitrogen flux from the parcel's systems, kilograms per day. {O}", None),
    ("ttl_p", "double", f"Total phosphorus flux from the parcel's systems, kilograms per day. {O}", None),
    ("rsk_score", "int32", f"Department of Health risk score for the parcel's systems, 0 to 6; the scoring is defined in the Oʻahu risk-ranking report. {O}", None),
    ("towns", "string", f"Town or community the parcel falls in, as recorded by the source (40 values, mixed case). {BLANK} {O}", None),
    ("island", "string", "Island, as recorded by the source. 147 Kauaʻi parcels carry a single space (' ') here and 0 in tmk; use layer_island instead. " + NI,
     [" ", "Hawaii", "Kauai", "Maui", "Molokai"]),
    ("tmk", "int32", "Nine-digit tax map key of the parcel. Digit 1 is the county (2 = Maui, 3 = Hawaiʻi, 4 = Kauaʻi), digit 2 the zone, digit 3 the section, digits 4–6 the plat and digits 7–9 the parcel. 0 on 147 Kauaʻi rows. " + NI, None),
    ("bldgval", "int32", f"Total building value on the parcel, as listed in the county tax database. {NI}", None),
    ("bldexem", "int32", f"Building value tax exemption on the parcel, as listed in the county tax database. -1 on 41 rows (38 Maui, 3 Molokaʻi); the source does not say what -1 means. {NI}", None),
    ("pittcode", "int32", "County tax-rate (PITT) class of the parcel: 0 = timeshare (Maui only), 100 = improved residential (on Kauaʻi, improved and unimproved residential), 200 = apartment, 300 = commercial, 400 = industrial, 500 = agricultural and rural, 600 = conservation, 700 = hotel and resort, 800 = unimproved residential (on Kauaʻi, homestead), 999 = several classes on one parcel, 1000 = commercialized residential (Maui only). " + NI,
     [0, 100, 200, 300, 400, 500, 600, 700, 800, 999, 1000]),
    ("homeownr", "string", "Whether a homeowner exemption applies to the parcel: Y = yes, N = no, U = unknown, a single space (' ') where not recorded. " + NI, [" ", "N", "U", "Y"]),
    ("gisacres", "double", f"Parcel area in acres, calculated in GIS. {NI}", None),
    ("osds_qty", "int32", f"Number of onsite systems on the parcel (0 to 130). {NI}", None),
    ("class_i", "int32", f"Number of Class I systems (soil treatment) on the parcel. {NI}", None),
    ("class_ii", "int32", f"Number of Class II systems (septic tank to seepage pit) on the parcel. {NI}", None),
    ("class_iii", "int32", f"Number of Class III systems (aerobic unit to seepage pit) on the parcel. {NI}", None),
    ("class_iv", "int32", f"Number of Class IV systems (cesspools) on the parcel. {NI}", None),
    ("effluent", "int32", f"Total effluent flow from the parcel's systems. The source documents the unit as million gallons per day, but the values (0 to 90,500, integers) match gallons per day, the unit of the Oʻahu effluent fields. {NI}", None),
    ("n_flux", "double", f"Total nitrogen flux from the parcel's systems, kilograms per day. {NI}", None),
    ("p_flux", "double", f"Total phosphorus flux from the parcel's systems, kilograms per day. {NI}", None),
    ("commercial", "string", f"Kind of commercial use the parcel's effluent estimate was based on (free text, 63 spellings, such as Small Gov't or Hotel). {BLANK} {NI}", None),
    ("source", "string", "Source database the parcel's system information came from (DWEL = county dwelling data, IWS = Department of Health individual wastewater system records, CP = cesspool records, WWTP = treatment-plant records, TMK = tax records), spelled differently between islands. " + BLANK + " " + NI,
     [" ", "CPOOL", "Cesspool Database", "DWEL/CP_db", "DWELDAT & Cesspool Database", "DWELDAT & IWS Databases", "DWELDAT Database", "DWEL_DAT", "DWEL_IWS", "Dwelling Database", "IWS", "IWS & CP Database", "IWS Database", "IWS and Cesspool Database", "IWS_CP", "IWS_WWTP", "TMK Database", "WWTP", "WWTP Database"]),
    ("no_struct", "int32", f"Number of structures on the parcel. {NI}", None),
    ("ttl_bdrms", "double", f"Number of bedrooms on the parcel; the effluent estimate for non-commercial parcels assumes 200 gallons per day per bedroom. {NI}", None),
    ("no_bath", "int32", f"Number of bathrooms on the parcel. {NI}", None),
    ("prmt_no", "int32", f"Wastewater treatment plant permit number. -9999 on rows with no treatment-plant record (81,100 of 81,312 neighbour-island rows); exclude it before any statistic. {NI}", None),
    ("prmt_id", "int32", f"Wastewater treatment plant permit identifier. -9999 on rows with no treatment-plant record; exclude it before any statistic. {NI}", None),
    ("uic_no", "string", f"Underground Injection Control permit number, for plants that dispose of treated effluent by injection. {BLANK} {NI_TEXT}", None),
    ("inject", "string", f"Whether the treatment plant injects effluent underground. Values: YES=injects, NO=does not inject, ' '=not recorded (all other parcels). {NI_TEXT}", [" ", "NO", "YES"]),
    ("wwtp", "string", f"Wastewater treatment plant name. {BLANK} {NI_TEXT}", None),
    ("class", "int32", f"Wastewater treatment plant class under Hawaiʻi Administrative Rules Title 11 Chapter 61. Values: 1=Class 1, 2=Class 2, 3=Class 3, 0=no class recorded (169 rows, 147 of them the Kauaʻi rows with no island or tax map key), -9999=no treatment-plant record (81,100 rows). {NI}", [-9999, 0, 1, 2, 3]),
    ("ownr_typ", "string", f"Treatment plant owner type: Public, Private, or a single space (' ') on other parcels. {NI_TEXT}", [" ", "Private", "Public"]),
    ("wwtp_ownr", "string", f"Owner of the treatment plant. {BLANK} {NI_TEXT}", None),
    ("contact", "string", f"Point of contact for the treatment plant. {BLANK} {NI_TEXT}", None),
    ("eng", "string", f"Treatment plant engineer. {BLANK} {NI_TEXT}", None),
    ("op_drc", "string", f"Treatment plant operator grade (Hawaiʻi Administrative Rules Title 11 Chapter 61): Grade 1, Grade 3, Grade 4, or a single space (' ') on other parcels. {NI_TEXT}", [" ", "Grade 1", "Grade 3", "Grade 4"]),
    ("comments", "string", f"Comments on the record. {BLANK} {NI_TEXT}", None),
    ("layer_island", "string", "Island layer the point came from. Added at ingest from the source layer, and complete on every row.", ["Hawaii", "Kauai", "Maui", "Molokai", "Oahu"]),
    ("county", "string", "County the island belongs to. Added at ingest from the source layer: Molokaʻi is in Maui County.", ["Hawaii", "Honolulu", "Kauai", "Maui"]),
    ("survey_year", "int32", "Year the island's layer was developed. Values: 2008=Oʻahu layer, 2010=Molokaʻi, Maui, Kauaʻi and Hawaiʻi layers. Added at ingest from the source layer.", [2008, 2010]),
]


def col(name, typ, desc, values):
    c = {"name": name, "type": typ, "description": desc}
    if values is not None:
        c["values"] = values
    return c


ATTRS = [col(*c) for c in COLS]
LEAN = [{k: v for k, v in c.items() if k != "description"} for c in ATTRS]
H3_COLS = [
    {"name": "h8", "type": "uint64", "description": "H3 cell ID at resolution 8, the native resolution of this hex asset and the catalog's universal join key."},
    {"name": "h0", "type": "int64", "description": "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."},
]

RAW_TEXT = "; ".join(f"{name}, {size:,} bytes, sha256 {sha}" for name, size, sha in RAW)

DESCRIPTION = f"""Onsite sewage disposal systems (cesspools, septic tanks, aerobic units and soil-treatment systems) on Oʻahu, Molokaʻi, Maui, Kauaʻi and Hawaiʻi Island, from the Hawaiʻi State Department of Health source water protection program. Each point is the centroid of a tax map key (TMK) parcel with at least one onsite system, and carries the number of systems on that parcel, their treatment class, and the estimated effluent, nitrogen and phosphorus they discharge. A few dozen neighbour-island points are wastewater treatment plants rather than parcels with onsite systems; type and class mark them. {N:,} parcel points: Oʻahu 13,684, Molokaʻi 1,651, Maui 12,780, Kauaʻi 13,351, Hawaiʻi 53,530. Lānaʻi, Niʻihau and Kahoʻolawe are not covered.

Locations are approximate: a point stands for the whole parcel, not for the position of a system on it. The Oʻahu layer was developed in 2008 and the other four in 2010, and the Department of Health notes that many properties may since have replaced a cesspool with a septic system. The layer is for information only; the Department of Health is the contact for a specific property.

The islands were published as five layers with two schemas, merged here into one table. Oʻahu (2008) records systems by class, with a concentration and flux for each class, and a risk score. The neighbour islands (2010) record counts by class, parcel totals, tax attributes and treatment-plant details. Each field is filled only on the islands whose layer has it and is null elsewhere, so check which group a field belongs to before a statewide statistic. Three columns were added from the source layer: layer_island, county and survey_year. Fields of the same name mean different things in the two schemas only in the case of type, which is a system type on Oʻahu and a treatment-plant marker on the other islands. To count systems statewide, add the two parcel totals:

```sql
SELECT layer_island, SUM(COALESCE(ttl_osds, osds_qty)) AS systems,
       SUM(COALESCE(ttl_n, n_flux)) AS nitrogen_kg_per_day
FROM read_parquet('s3://{BUCKET}/{DATASET}.parquet')
GROUP BY layer_island
```

Missing values. Empty text fields hold a single space (' '). On the neighbour islands, class, prmt_no and prmt_id are -9999 on every row with no treatment-plant record; exclude -9999 before any statistic on them. The Maui layer stores ten treatment-plant text fields as numbers that are 0 on every row; they are null here. The source documents the neighbour-island effluent field in million gallons per day, but its values (0 to 90,500) match gallons per day, the unit of the Oʻahu effluent fields.

Converted to cloud-native formats (GeoParquet, PMTiles and H3 hex). Each point was assigned to the one H3 cell at resolution 8 (about 0.7 square kilometres) that contains it, with h0 as the partition key. Points in the same cell are kept as separate rows.

Provenance. Source: Hawaiʻi State Department of Health, Environmental Management Division, source water protection program (metadata dated May 2017), served by the Hawaiʻi Statewide GIS Program as layers 22 (Oʻahu), 23 (Molokaʻi), 24 (Maui), 25 (Kauaʻi) and 26 (Hawaiʻi) of its Infrastructure map service. Upstream publishes no edition label. All five layers were retrieved in full from the map service on {RETRIEVED}. The service responses are kept unmodified in {RAW_DIR}, with each layer definition and the two metadata documents: {RAW_TEXT}. The last of these is the merged table the conversion read. Method and risk scoring are described in the Department of Health risk-ranking reports for Oʻahu ({REPORT_OAHU}) and the neighbour islands ({REPORT_NI}).

Licence: public domain. The State of Hawaiʻi states that the contents of each layer are public domain and exempt from its Terms of Use restrictions, with no warranty of positional or thematic accuracy. Credit: Hawaiʻi State Department of Health; Hawaiʻi Statewide GIS Program."""

HEX_DESC = f"""One row per parcel point, with the H3 cell at resolution 8 that contains it (h8) and h0 as the hive partition key. {N:,} rows in {N_CELLS:,} distinct resolution-8 cells: many parcels share a cell, and none are merged. Each parcel point falls in exactly one cell and appears on exactly one row (COUNT(DISTINCT _cng_fid) equals COUNT(*)), so per-parcel values such as acres, system counts and fluxes are not repeated across cells and can be summed directly. Cell counts are not system counts:

```sql
-- systems and nitrogen per resolution-8 cell
SELECT h8, SUM(COALESCE(ttl_osds, osds_qty)) AS systems, SUM(COALESCE(ttl_n, n_flux)) AS nitrogen_kg_per_day
FROM read_parquet('s3://{BUCKET}/{DATASET}/hex/h0=*/data_0.parquet')
GROUP BY h8
```

The missing-value rules of the collection apply here too: -9999 in class, prmt_no and prmt_id, and fields null on the islands whose layer lacks them. h8 has no null values."""

CITATION = ("Hawaiʻi State Department of Health, Environmental Management Division. Onsite Sewage "
            "Disposal Systems, Oʻahu (2008) and Hawaiʻi, Kauaʻi, Maui and Molokaʻi (2010). Hawaiʻi "
            f"Statewide GIS Program, Infrastructure map service layers 22–26. Retrieved {RETRIEVED} "
            f"from {SERVICE}")

T_PARQUET = iso(last_modified(f"{DATASET}.parquet"))
T_PMTILES = iso(last_modified(f"{DATASET}.pmtiles"))
T_HEX = first_hex_write()

stac = {
    "type": "Collection",
    "stac_version": "1.0.0",
    "stac_extensions": [
        "https://stac-extensions.github.io/table/v1.2.0/schema.json",
        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
    ],
    "id": DATASET,
    "title": TITLE,
    "description": DESCRIPTION,
    "license": "public-domain",
    "keywords": ["onsite sewage disposal systems", "OSDS", "cesspools", "septic systems",
                 "wastewater", "nitrogen", "phosphorus", "land-based pollution", "water quality",
                 "Hawaii", "Oahu", "Maui", "Molokai", "Kauai", "United States"],
    "providers": [
        {"name": "Hawaiʻi State Department of Health, Environmental Management Division",
         "roles": ["producer"], "url": "https://health.hawaii.gov/wastewater/"},
        {"name": "Hawaiʻi Statewide GIS Program, Office of Planning and Sustainable Development",
         "roles": ["licensor", "host"], "url": "https://planning.hawaii.gov/gis/"},
        {"name": "Boettiger Lab", "roles": ["processor", "host"],
         "url": "https://github.com/boettiger-lab"},
    ],
    "sci:citation": CITATION,
    "created": min(T_PARQUET, T_PMTILES, T_HEX),
    "updated": max(T_PARQUET, T_PMTILES, T_HEX),
    "extent": {
        "spatial": {"bbox": [BBOX]},
        "temporal": {"interval": [["2008-01-01T00:00:00Z", "2010-12-31T00:00:00Z"]]},
    },
    "links": [
        {"rel": "self", "href": f"{BASE}/{DATASET}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",
         "type": "application/json"},
        {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
        {"rel": "describedby", "href": f"{BASE}/{DATASET}/README.md", "type": "text/markdown"},
        {"rel": "about", "href": LANDING, "type": "text/html",
         "title": "On-site Sewage Disposal Systems (Hawaiʻi Statewide GIS Program geoportal)"},
        {"rel": "describedby", "href": PDF_OAHU, "type": "application/pdf",
         "title": "Metadata: Onsite Sewage Disposal Systems, Oʻahu (2008)"},
        {"rel": "describedby", "href": PDF_NI, "type": "application/pdf",
         "title": "Metadata: Onsite Sewage Disposal Systems, Hawaiʻi, Kauaʻi, Maui and Molokaʻi (2010)"},
        {"rel": "describedby", "href": REPORT_OAHU, "type": "application/pdf",
         "title": "Human and Environmental Risk Ranking of Onsite Sewage Disposal Systems (Oʻahu)"},
        {"rel": "describedby", "href": REPORT_NI, "type": "application/pdf",
         "title": "Human Health and Environmental Risk Ranking of Onsite Sewage Disposal Systems (Kauaʻi, Molokaʻi, Maui and Hawaiʻi)"},
        {"rel": "via", "href": SERVICE, "title": "Infrastructure map service, layers 22–26"},
        {"rel": "license", "href": TERMS, "type": "text/html",
         "title": "State of Hawaii Terms of Use (contents public domain)"},
    ],
    "assets": {
        f"{DATASET}-parquet": {
            "href": f"{BASE}/{DATASET}.parquet",
            "type": "application/vnd.apache.parquet",
            "title": f"GeoParquet: all {N:,} parcel points",
            "description": "One row per tax map key parcel with onsite systems, at the parcel centroid, with system counts, effluent and nutrient estimates.",
            "roles": ["data"],
            "created": T_PARQUET,
            "table:columns": ATTRS + [
                {"name": "geom", "type": "geometry", "description": "Parcel centroid point, EPSG:4326."}],
        },
        f"{DATASET}-pmtiles": {
            "href": f"{BASE}/{DATASET}.pmtiles",
            "type": "application/vnd.pmtiles",
            "title": "PMTiles vector tiles for web map display",
            "description": f"Vector tiles for MapLibre GL JS. The source layer is {DATASET}.",
            "roles": ["visual"],
            "created": T_PMTILES,
            "vector:layers": [DATASET],
            "table:columns": LEAN,
        },
        f"{DATASET}-hex": {
            "href": f"{BASE}/{DATASET}/hex/h0=*/data_0.parquet",
            "type": "application/vnd.apache.parquet",
            "title": "H3 hexagonal index (resolution 8) of the parcel points",
            "description": HEX_DESC,
            "roles": ["data"],
            "created": T_HEX,
            "h3:native_resolution": 8,
            "h3:parent_resolutions": [0],
            "table:columns": ATTRS + H3_COLS,
        },
    },
}

README = f"""# {TITLE}

Onsite sewage disposal systems (cesspools, septic tanks, aerobic units, soil treatment) on Oʻahu, Molokaʻi, Maui, Kauaʻi and Hawaiʻi Island, from the Hawaiʻi State Department of Health. Each of the {N:,} points is a tax map key parcel centroid carrying the number of systems on the parcel and their estimated effluent, nitrogen and phosphorus discharge. Oʻahu was surveyed in 2008, the other islands in 2010. Locations are approximate (one point per parcel).

## Files

| Asset | URL |
|---|---|
| GeoParquet | `{BASE}/{DATASET}.parquet` |
| PMTiles | `{BASE}/{DATASET}.pmtiles` |
| H3 hex (resolution 8, partitioned by h0) | `{BASE}/{DATASET}/hex/h0=*/data_0.parquet` |

## Two schemas in one table

The five island layers come in two schemas. Oʻahu fields (`ttl_osds`, `ttl_n`, `osds_class`, `rsk_score`, the per-class `soil_*`, `st_*`, `au_*`, `cp_*` fields) are null on the other islands; neighbour-island fields (`osds_qty`, `n_flux`, `class_i` to `class_iv`, tax and treatment-plant fields) are null on Oʻahu. `layer_island`, `county` and `survey_year` are filled on every row. `type` is a system type on Oʻahu and a treatment-plant marker elsewhere. Empty text is a single space; `class`, `prmt_no` and `prmt_id` use -9999 for rows with no treatment-plant record.

## DuckDB

```sql
INSTALL spatial; LOAD spatial;
SELECT layer_island, COUNT(*) AS parcels,
       SUM(COALESCE(ttl_osds, osds_qty)) AS systems,
       SUM(COALESCE(ttl_n, n_flux)) AS nitrogen_kg_per_day
FROM read_parquet('{BASE}/{DATASET}.parquet')
GROUP BY layer_island ORDER BY systems DESC;
```

## MapLibre GL JS

The PMTiles `source-layer` is **`{DATASET}`**.

```js
import {{ Protocol }} from "pmtiles";
maplibregl.addProtocol("pmtiles", new Protocol().tile);

map.addSource("hi-osds", {{
  type: "vector",
  url: "pmtiles://{BASE}/{DATASET}.pmtiles",
}});
map.addLayer({{
  id: "hi-osds-points", type: "circle", source: "hi-osds",
  "source-layer": "{DATASET}",
  paint: {{ "circle-radius": 2, "circle-color": "#8c510a" }},
}});
```

## Provenance and licence

Source: Hawaiʻi State Department of Health, served by the Hawaiʻi Statewide GIS Program ({SERVICE}, layers 22–26; metadata {PDF_OAHU} and {PDF_NI}). Retrieved {RETRIEVED}. Unmodified service responses, with sizes and sha256 checksums, are kept in `{RAW_DIR}` and listed in the STAC collection.

Licence: public domain, per the State of Hawaiʻi ({TERMS}). No warranty of accuracy. The layer is for information only; contact the Department of Health about a specific property.
"""

out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/hi-osds"
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "stac-collection.json"), "w") as f:
    json.dump(stac, f, indent=2, ensure_ascii=False)
with open(os.path.join(out, "README.md"), "w") as f:
    f.write(README)
print(f"wrote {out}/stac-collection.json and README.md")
