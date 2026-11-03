#!/usr/bin/env python3
"""Write the STAC collections for public-coastwatch (#835, #836).

Usage: gen_stac.py <stats.json> <out_dir>

stats.json holds the measured values for each dataset, keyed by dataset id:
months, first/last time (YYYY-MM-DD), last month label (YYYYMM), hex row count,
created (RFC 3339, the hex build date), accessed (staging date range).
Measure them from the published objects; do not type them in.
"""
import json
import os
import sys

B = "public-coastwatch"
S3 = f"https://s3-west.nrp-nautilus.io/{B}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
NASA_POLICY = "https://science.nasa.gov/earth-science/earth-science-data/data-information-policy/"
ERDDAP = "https://coastwatch.pfeg.noaa.gov/erddap"

PRODUCTS = {
    "erdMH1chlamday": {
        "key": "chlorophyll",
        "var": "chlorophyll",
        "title": "Aqua MODIS monthly chlorophyll-a at 4 km",
        "short": "chlorophyll-a",
        "what": (
            "Monthly mean chlorophyll-a concentration in the surface ocean, from the MODIS sensor on NASA's "
            "Aqua satellite. Chlorophyll-a is the pigment of phytoplankton, so it is the standard satellite "
            "measure of ocean productivity, and a rise near coasts can signal nutrient runoff."
        ),
        "units": "milligrams per cubic metre (mg m-3)",
        "valid": "0.001 to 100",
        "doi": "10.5067/AQUA/MODIS/L3M/CHL/2018",
        "col": (
            "Monthly mean chlorophyll-a concentration in milligrams per cubic metre (mg m-3), the mean of the "
            "4 km pixels in the cell. Upstream's valid range is 0.001 to 100 mg m-3. Concentrations are "
            "skewed, so a geometric mean or a median often summarises a region better than an arithmetic mean."
        ),
        "keywords": ["chlorophyll-a", "phytoplankton", "ocean productivity", "eutrophication"],
    },
    "erdMH1kd490mday": {
        "key": "kd490",
        "var": "k490",
        "title": "Aqua MODIS monthly Kd490 water clarity at 4 km",
        "short": "Kd490",
        "what": (
            "Monthly mean diffuse attenuation coefficient at 490 nanometres (Kd490), from the MODIS sensor on "
            "NASA's Aqua satellite. Kd490 measures how quickly blue-green light fades with depth, so it is a "
            "standard satellite measure of water clarity: higher values mean more turbid water."
        ),
        "units": "per metre (m-1)",
        "valid": "0.01 to 6",
        "doi": "10.5067/AQUA/MODIS/L3M/KD490/2018",
        "col": (
            "Monthly mean diffuse attenuation coefficient at 490 nanometres, in per metre (m-1), the mean of "
            "the 4 km pixels in the cell. Higher values mean more turbid water. Upstream's valid range is "
            "0.01 to 6 m-1."
        ),
        "keywords": ["Kd490", "water clarity", "turbidity", "light attenuation"],
    },
}

COMMON_COLS = {
    "h6": "H3 cell ID at resolution 6 (about 36 square kilometres).",
    "h0": "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads.",
    "time": (
        "The month the row describes, stamped on the 16th as upstream stamps its monthly composites. "
        "Filter on it to select months."
    ),
}


def link(rel, href, title=None, typ="application/json"):
    d = {"rel": rel, "href": href, "type": typ}
    if title:
        d["title"] = title
    return d


def leaf(ds, st):
    p = PRODUCTS[ds]
    k = p["key"]
    first, last = st["first"], st["last"]
    desc = (
        f"{p['what']}\n\n"
        f"Global coverage on a 4 km (1/24 degree) grid, one value per month from {first[:7]} to {last[:7]}: "
        f"all {st['months']} monthly composites NOAA CoastWatch served for this product when it was staged. Pixels are missing where cloud, sun glint, "
        "sea ice or land prevented a valid retrieval during the month, so coverage varies from month to month, "
        "and high latitudes are empty in their winter.\n\n"
        "The H3 hexagon table is the layer for queries and joins. A Cloud-Optimized GeoTIFF of each month is "
        f"published at {S3}/{ds}/cog/{ds}-YYYYMM.tif (WGS84, Float32, missing pixels are NaN), for map display "
        "and pixel-level work.\n\n"
        f"Source: NOAA CoastWatch ERDDAP dataset {ds} ({ERDDAP}/griddap/{ds}.html), which redistributes NASA "
        "Ocean Biology Processing Group Level 3 standard mapped images. ERDDAP reports processing version 2018.1QL "
        f"and product DOI {p['doi']}. Each month was requested from ERDDAP separately on {st['accessed']}; the "
        f"netCDF file as delivered is staged at s3://{B}/raw/{ds}/nc/{ds}-YYYYMM.nc.gz (gzipped), next to a "
        ".json file recording its request URL, access time, size in bytes and SHA-256 checksum before gzipping. "
        f"A Zarr copy of the same array, used to build the hexagon table, is at s3://{B}/raw/{ds}/zarr/.\n\n"
        "NASA's Earth science data policy makes the data free to use and redistribute without restriction. "
        "NOAA's ERDDAP notes that the data are not intended for legal use, since they may contain inaccuracies."
    )
    hex_desc = (
        f"H3 hexagon table of monthly {p['short']} at resolution 6, with one row per cell per month. Each "
        "resolution 6 cell holds one to a few of the 4 km pixels, and its value is their mean. The table is "
        "partitioned by h0. Cells with no valid data in a month are absent rather than stored as a fill value. "
        "Resolution 6 is the finest this source supports: a 4 km pixel is coarser than a resolution 8 cell, so "
        "there is no h8 column; join to resolution 8 data with h3_cell_to_parent(h8, 6).\n\n"
        "There is one row per cell per month, with no per-feature totals, so nothing needs deduplicating. The "
        "values are not amounts, so do not sum them across cells or months. To summarise a region, take an "
        "area-weighted mean, because H3 cells are not equal-area:\n\n"
        "```sql\n"
        "-- the cells and months to summarise: 2015, in the h0 cell holding Hawaii\n"
        f"SELECT h6, time, {p['var']}\n"
        f"FROM read_parquet('s3://{B}/{ds}/hex/h0=*/*.parquet')\n"
        "WHERE time BETWEEN DATE '2015-01-01' AND DATE '2015-12-31'\n"
        "  AND h0 = h3_cell_to_parent(h3_latlng_to_cell(21.3, -157.8, 6), 0);\n"
        "```"
    )
    cols = [
        {"name": "h6", "type": "uint64", "description": COMMON_COLS["h6"]},
        {"name": "h0", "type": "uint64", "description": COMMON_COLS["h0"]},
        {"name": "time", "type": "date", "description": COMMON_COLS["time"]},
        {"name": p["var"], "type": "double", "description": p["col"]},
    ]
    lm = st["last_ym"]
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
        ],
        "id": ds,
        "title": p["title"],
        "description": desc,
        "license": "public-domain",
        "providers": [
            {"name": "NASA Goddard Space Flight Center, Ocean Biology Processing Group", "roles": ["producer", "licensor"],
             "url": "https://oceancolor.gsfc.nasa.gov"},
            {"name": "NOAA CoastWatch West Coast Node", "roles": ["host"], "url": "https://coastwatch.pfeg.noaa.gov"},
            {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"], "url": "https://boettiger-lab.github.io"},
        ],
        "keywords": ["NASA", "MODIS", "Aqua", "ocean colour", "monthly", "H3"] + p["keywords"],
        "extent": {
            "spatial": {"bbox": [[-180.0, -90.0, 180.0, 90.0]]},
            "temporal": {"interval": [[f"{first}T00:00:00Z", f"{last}T00:00:00Z"]]},
        },
        "created": st["created"],
        "updated": st["created"],
        "sci:doi": p["doi"],
        "sci:citation": (
            f"NASA Goddard Space Flight Center, Ocean Ecology Laboratory, Ocean Biology Processing Group. "
            f"Moderate-resolution Imaging Spectroradiometer (MODIS) Aqua Level 3 mapped data, monthly 4 km. "
            f"doi:{p['doi']}. Accessed through NOAA CoastWatch ERDDAP ({ds}) on {st['accessed']}."
        ),
        "links": [
            link("self", f"{S3}/{ds}/stac-collection.json"),
            link("root", ROOT),
            link("parent", f"{S3}/stac-collection.json"),
            link("license", NASA_POLICY, "NASA Earth science data and information policy", "text/html"),
            link("about", f"{ERDDAP}/info/{ds}/index.html", "ERDDAP dataset information", "text/html"),
            link("cite-as", f"https://doi.org/{p['doi']}", "Product DOI", "text/html"),
        ],
        "assets": {
            f"{k}-hex": {
                "href": f"{S3}/{ds}/hex/h0=*/*.parquet",
                "type": "application/x-parquet",
                "roles": ["data"],
                "title": f"Monthly {p['short']} in H3 hexagons at resolution 6",
                "description": hex_desc,
                "created": st["created"],
                "h3:native_resolution": 6,
                "h3:parent_resolutions": [0],
                "table:columns": cols,
            },
            f"{k}-cog": {
                "href": f"{S3}/{ds}/cog/{ds}-{lm}.tif",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "roles": ["data", "visual"],
                "title": f"Monthly {p['short']} for {lm[:4]}-{lm[4:]}",
                "description": (
                    f"Cloud-Optimized GeoTIFF of the last month in the record, {lm[:4]}-{lm[4:]}. Every month has "
                    f"its own file at {S3}/{ds}/cog/{ds}-YYYYMM.tif. Units are {p['units']}; missing pixels are NaN."
                ),
                "created": st["created"],
                "raster:bands": [{"data_type": "float32", "nodata": "nan", "unit": p["units"].split(" (")[-1].rstrip(")")}],
            },
        },
    }


def parent(children):
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "id": "coastwatch",
        "title": "NOAA CoastWatch satellite ocean colour",
        "description": (
            "Satellite ocean-colour products served by NOAA CoastWatch ERDDAP: monthly chlorophyll-a and Kd490 "
            "water clarity from NASA's Aqua MODIS sensor on a global 4 km grid, 2003 to 2022. Each child collection "
            "has an H3 hexagon table at resolution 6 and a Cloud-Optimized GeoTIFF for every month."
        ),
        "license": "public-domain",
        "extent": {
            "spatial": {"bbox": [[-180.0, -90.0, 180.0, 90.0]]},
            "temporal": {"interval": [[min(c["extent"]["temporal"]["interval"][0][0] for c in children),
                                       max(c["extent"]["temporal"]["interval"][0][1] for c in children)]]},
        },
        "links": [
            link("self", f"{S3}/stac-collection.json"),
            link("root", ROOT),
            link("parent", ROOT),
            link("license", NASA_POLICY, "NASA Earth science data and information policy", "text/html"),
        ] + [dict(link("child", f"{S3}/{c['id']}/stac-collection.json", c["title"]), id=c["id"]) for c in children],
    }


def main():
    stats = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    kids = []
    for ds in PRODUCTS:
        if ds not in stats:
            continue
        c = leaf(ds, stats[ds])
        kids.append(c)
        os.makedirs(f"{out}/{ds}", exist_ok=True)
        json.dump(c, open(f"{out}/{ds}/stac-collection.json", "w"), indent=2, ensure_ascii=False)
    json.dump(parent(kids), open(f"{out}/stac-collection.json", "w"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
