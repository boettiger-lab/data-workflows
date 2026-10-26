#!/usr/bin/env python3
"""Emit STAC for the LOCA2-Hybrid daily-tmax exceedance product (data-workflows #669).

Writes to /tmp only -- this repo never contains STAC JSON (AGENTS.md Hard Boundary 1):

    python3 gen_stac.py            # writes /tmp/caladapt-*.json
    rclone copyto /tmp/caladapt-tasmax-exceedance.json nrp:public-caladapt/loca2-hybrid/tasmax-exceedance/stac-collection.json
    rclone copyto /tmp/caladapt-tasmax-annual-max.json nrp:public-caladapt/loca2-hybrid/tasmax-annual-max/stac-collection.json
    rclone copyto /tmp/caladapt-bucket.json            nrp:public-caladapt/stac-collection.json

Measured values below were taken with the duckdb-geo MCP against the published parquet on
2026-10-26, after the clamped-mean rebuild; `created` is the parquet objects' mtime.
"""
from __future__ import annotations

import json

S3 = "https://s3-west.nrp-nautilus.io"
BUCKET = "public-caladapt"
ROOT = f"{S3}/public-data/stac/catalog.json"
PARENT = f"{S3}/{BUCKET}/stac-collection.json"
CREATED = "2026-10-26T17:48:58Z"
ACCESS_DATE = "2026-10-26"
LANDING = "https://analytics.cal-adapt.org/data/catalog/"
CC_BY = "https://creativecommons.org/licenses/by/4.0/"
CMIP6_TERMS = "https://pcmdi.llnl.gov/CMIP6/TermsOfUse/TermsOfUse6-2.html"

# Pixel edges of the LOCA2 d03 grid (centres 29.578125..45.015625 N, -128.421875..-110.984375 E,
# 1/32 degree spacing), decoded from the stores' coordinate arrays.
BBOX = [-128.4375, 29.5625, -110.96875, 45.03125]
INTERVAL = [["1985-01-01T00:00:00Z", "2099-12-31T23:59:59Z"]]

MODELS = ["ACCESS-CM2", "GFDL-ESM4", "MPI-ESM1-2-HR"]
STORES = [f"s3://cadcat/loca2/ucsd/{m.lower()}/{e}/r1i1p1f1/day/tasmax/d03/"
          for m in MODELS for e in ("historical", "ssp370")]

CITATION = (
    "LOCA2-Hybrid statistically downscaled CMIP6 daily maximum air temperature, produced by "
    "UC San Diego Scripps Institution of Oceanography for California's Fifth Climate Change "
    f"Assessment and distributed through the Cal-Adapt Data Catalog ({LANDING}). "
    f"Accessed {ACCESS_DATE}. Licensed CC BY 4.0."
)

PROVIDERS = [
    {"name": "UC San Diego Scripps Institution of Oceanography", "roles": ["producer", "licensor"],
     "url": "https://scripps.ucsd.edu/"},
    {"name": "Cal-Adapt: Analytics Engine", "roles": ["host"], "url": LANDING},
    {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor"],
     "url": "https://github.com/boettiger-lab/data-workflows"},
]

SHARED_COLUMNS = {
    "h7": {"name": "h7", "type": "uint64",
           "description": "H3 cell ID at resolution 7 (about 5.2 square kilometres), the native "
                          "resolution of this product."},
    "scenario": {"name": "scenario", "type": "string",
                 "description": "Climate scenario. Values: historical=CMIP6 historical simulation, "
                                "ssp370=SSP3-7.0 future emissions scenario.",
                 "values": ["historical", "ssp370"]},
    "period": {"name": "period", "type": "string",
               "description": "30-year averaging period, inclusive. Values: 1985-2014=historical "
                              "baseline, 2040-2069=mid-century, 2070-2099=end of century.",
               "values": ["1985-2014", "2040-2069", "2070-2099"]},
    "n_models": {"name": "n_models", "type": "uint8",
                 "description": "Number of climate models in the ensemble statistics for this row "
                                "(3: ACCESS-CM2, GFDL-ESM4 and MPI-ESM1-2-HR)."},
    "h6": {"name": "h6", "type": "uint64", "description": "H3 cell ID at resolution 6."},
    "h0": {"name": "h0", "type": "int64",
           "description": "H3 cell ID at resolution 0, used as the partition key for "
                          "hive-partitioned reads."},
}

FOOTPRINT = (
    "Coverage is the full LOCA2-Hybrid modelling domain: California and Nevada, plus the margins "
    "of Oregon, Idaho, Utah and Arizona and northern Baja California. It is not clipped to "
    "California, so a California-only statistic needs a California mask, for example:\n\n"
    "```sql\n"
    "-- cells inside California, using a resolution-8 California mask rolled up to resolution 7\n"
    "SELECT DISTINCT h3_cell_to_parent(h8, 7) AS h7 FROM <California resolution-8 mask>\n"
    "```\n\n"
    "Ocean cells carry no data and are absent."
)

RESOLUTION = (
    "Values are at H3 resolution 7. The source grid is 1/32 degree (about 3.5 km by 2.8 km, "
    "roughly 9.6 square kilometres per pixel), which is coarser than a resolution-8 cell, so this "
    "product has no h8 column. Each resolution-7 cell takes the value of the source pixel "
    "containing its centre. To join resolution-8 data, roll it up: "
    "`h3_cell_to_parent(h8, 7) = h7` (and match `h0`)."
)

ENSEMBLE = (
    "Three models were chosen to span low, middle and high climate sensitivity: GFDL-ESM4, "
    "MPI-ESM1-2-HR and ACCESS-CM2, each run r1i1p1f1. The historical simulation ends in 2014, so "
    "the baseline is 1985-2014 rather than 1991-2020. Each model's value is its 30-year average; "
    "the mean, min and max columns are the average, lowest and highest of the three models, so "
    "min and max show agreement between models, not year-to-year variability."
)

PROVENANCE = (
    "Source: LOCA2-Hybrid daily maximum air temperature (tasmax), grid d03, read in place from the "
    f"Cal-Adapt Data Catalog Zarr stores on {ACCESS_DATE}: " + ", ".join(f"`{s}`" for s in STORES)
    + ". The stores were not copied, so there is no staged raw file or checksum; Cal-Adapt does "
    "not publish an edition label for LOCA2-Hybrid beyond the product name. Temperatures were "
    "converted from kelvin to degrees Celsius."
)

LICENCE = (
    "Licence: CC BY 4.0, as stated for all Cal-Adapt Data Catalog products, which derive from "
    f"CMIP6 (CMIP6 terms of use: {CMIP6_TERMS}). Credit UC San Diego Scripps Institution of "
    "Oceanography and Cal-Adapt. This table is a derived product: daily values were reduced to "
    "the statistics described here."
)


def links(path: str) -> list:
    return [
        {"rel": "self", "href": f"{S3}/{BUCKET}/{path}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": ROOT, "type": "application/json"},
        {"rel": "parent", "href": PARENT, "type": "application/json"},
        {"rel": "license", "href": CC_BY, "type": "text/html", "title": "CC BY 4.0"},
        {"rel": "about", "href": LANDING, "type": "text/html", "title": "Cal-Adapt Data Catalog"},
    ]


def collection(cid, title, path, description, asset_key, asset_title, asset_desc, columns, keywords):
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
        ],
        "id": cid,
        "title": title,
        "description": description,
        "keywords": keywords,
        "license": "CC-BY-4.0",
        "sci:citation": CITATION,
        "providers": PROVIDERS,
        "created": CREATED,
        "updated": CREATED,
        "extent": {"spatial": {"bbox": [BBOX]}, "temporal": {"interval": INTERVAL}},
        "links": links(path),
        "assets": {
            asset_key: {
                "href": f"{S3}/{BUCKET}/{path}/hex/h0=*/data_0.parquet",
                "type": "application/vnd.apache.parquet",
                "title": asset_title,
                "description": asset_desc,
                "roles": ["data"],
                "created": CREATED,
                "h3:native_resolution": 7,
                "h3:parent_resolutions": [6, 0],
                "table:columns": columns,
            }
        },
    }


def exceedance() -> dict:
    cols = [
        SHARED_COLUMNS["h7"], SHARED_COLUMNS["scenario"], SHARED_COLUMNS["period"],
        {"name": "threshold_c", "type": "float",
         "description": "Daily maximum air temperature threshold in degrees Celsius, from 20.0 to "
                        "60.0 in steps of 0.5."},
        {"name": "days_mean", "type": "float",
         "description": "Average number of days per year with daily maximum air temperature at or "
                        "above threshold_c, averaged over the three models. Range 0 to 358."},
        {"name": "days_min", "type": "float",
         "description": "Lowest of the three models' days per year at or above threshold_c."},
        {"name": "days_max", "type": "float",
         "description": "Highest of the three models' days per year at or above threshold_c."},
        SHARED_COLUMNS["n_models"], SHARED_COLUMNS["h6"], SHARED_COLUMNS["h0"],
    ]
    desc = (
        "How many days a year reach a given temperature, for any threshold from 20 to 60 °C, "
        "across California and its neighbours under historical climate and the SSP3-7.0 "
        "scenario. For each H3 cell, scenario and period, the table gives the average number of "
        "days per year on which the daily maximum air temperature is at or above each threshold, "
        "in 0.5 °C steps, from three downscaled climate models. Read together, the rows for a "
        "cell form a curve that answers \"days per year at or above T\" for any T in range: "
        "interpolate linearly between the two nearest thresholds.\n\n"
        "A day counts when its maximum temperature is greater than or equal to the threshold, so "
        "a day at exactly 30.0 °C counts toward the 30.0 threshold. Leap days are counted, and "
        "the yearly rate divides by the 30 years in each period.\n\n"
        "Rows where no model has any day at or above the threshold are left out, so a missing "
        "threshold means 0 days. A cell's rows always run without gaps from 20.0 °C up to its "
        "highest threshold that any model reaches. A cell that never reaches 20 °C has no rows "
        "here; its annual maximum temperature is in the companion annual-maximum collection. "
        "The grid stops at 60.0 °C: for the few desert cells with days at 60.0 °C under SSP3-7.0 "
        "(at most 0.3 days a year on the three-model average, 0.8 in the hottest model), hotter "
        "thresholds are not available rather than zero.\n\n"
        + FOOTPRINT + "\n\n" + RESOLUTION + "\n\n" + ENSEMBLE + "\n\n" + PROVENANCE + "\n\n" + LICENCE
    )
    asset_desc = (
        "One row per H3 resolution-7 cell, scenario, period and temperature threshold "
        "(22,963,029 rows over 148,902 land cells). Each value is a rate for that cell, so a "
        "regional figure is an area-weighted average over cells, not a sum. Cells with no row at "
        "a threshold have 0 days there and still belong in the average; take the region's full "
        "cell list from the companion annual-maximum collection, which has every land cell."
    )
    return collection(
        "loca2-hybrid-tasmax-exceedance",
        "Days per Year Above Temperature Thresholds (LOCA2-Hybrid, California and Nevada)",
        "loca2-hybrid/tasmax-exceedance", desc,
        "tasmax-exceedance-hex", "Daily maximum temperature exceedance curves, H3 resolution 7",
        asset_desc, cols,
        ["climate", "temperature", "extreme heat", "LOCA2", "CMIP6", "California", "H3"],
    )


def annual_max() -> dict:
    cols = [
        SHARED_COLUMNS["h7"], SHARED_COLUMNS["scenario"], SHARED_COLUMNS["period"],
        {"name": "tmax_mean_annual_max_c", "type": "float",
         "description": "Hottest day of the year in degrees Celsius, averaged over the 30 years of "
                        "the period and then over the three models. Range 17.1 to 58.0."},
        {"name": "tmax_max_c", "type": "float",
         "description": "Hottest single day in the period in degrees Celsius, the highest across "
                        "the three models. Range 20.7 to 63.3."},
        SHARED_COLUMNS["n_models"], SHARED_COLUMNS["h6"], SHARED_COLUMNS["h0"],
    ]
    desc = (
        "The hottest day of the year across California and its neighbours under historical "
        "climate and the SSP3-7.0 scenario, from three downscaled climate models. For each H3 "
        "cell, scenario and period, the table gives the average of each year's highest daily "
        "maximum air temperature, and the single hottest day in the period. It is the companion "
        "to the days-per-year exceedance collection and covers every land cell, including cells "
        "that never reach 20 °C.\n\n"
        + FOOTPRINT + "\n\n" + RESOLUTION + "\n\n" + ENSEMBLE + "\n\n" + PROVENANCE + "\n\n" + LICENCE
    )
    asset_desc = (
        "One row per H3 resolution-7 cell, scenario and period (446,706 rows over 148,902 land "
        "cells). Values are temperatures for that cell; a regional figure is an area-weighted "
        "average or a maximum over cells, never a sum."
    )
    return collection(
        "loca2-hybrid-tasmax-annual-max",
        "Hottest Day of the Year (LOCA2-Hybrid, California and Nevada)",
        "loca2-hybrid/tasmax-annual-max", desc,
        "tasmax-annual-max-hex", "Annual maximum daily temperature, H3 resolution 7",
        asset_desc, cols,
        ["climate", "temperature", "extreme heat", "LOCA2", "CMIP6", "California", "H3"],
    )


def bucket(children: list[dict]) -> dict:
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "id": "caladapt",
        "title": "Cal-Adapt Climate Projections",
        "description": (
            "Climate projections for California from the Cal-Adapt Data Catalog, which supports "
            "California's Fifth Climate Change Assessment, reduced to H3 tables for analysis. "
            "Holdings are derived from LOCA2-Hybrid downscaled CMIP6 daily maximum air "
            "temperature: days per year above temperature thresholds, and the hottest day of the "
            "year, for a 1985-2014 baseline and SSP3-7.0 mid-century and end of century. " + LICENCE
        ),
        "license": "CC-BY-4.0",
        "providers": PROVIDERS,
        "extent": {"spatial": {"bbox": [BBOX]}, "temporal": {"interval": INTERVAL}},
        "links": [
            {"rel": "self", "href": PARENT, "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": ROOT, "type": "application/json"},
            {"rel": "license", "href": CC_BY, "type": "text/html", "title": "CC BY 4.0"},
            {"rel": "about", "href": LANDING, "type": "text/html", "title": "Cal-Adapt Data Catalog"},
        ] + [{"rel": "child", "href": c["links"][0]["href"], "type": "application/json",
              "title": c["title"]} for c in children],
    }


def main() -> None:
    ex, am = exceedance(), annual_max()
    for name, obj in (("tasmax-exceedance", ex), ("tasmax-annual-max", am), ("bucket", bucket([ex, am]))):
        path = f"/tmp/caladapt-{name}.json"
        with open(path, "w") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(path)


if __name__ == "__main__":
    main()
