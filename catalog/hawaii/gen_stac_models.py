#!/usr/bin/env python3
"""Write the STAC collections for the PacIOOS ROMS and WaveWatch III daily layers (#840, #841).

Usage: gen_stac_models.py <stats.json> <out_dir>

stats.json holds the measured values for each dataset, keyed by dataset id: days, first and last
day (YYYY-MM-DD), partial (days with fewer model steps than a full day), hex rows, hex created,
cog created (RFC 3339), accessed ([first, last] access date), missing (days in the span with no
upstream output) and bbox. Measure them from the published
objects and the days.json markers; do not type them in.
Writes <out_dir>/<dataset>/stac-collection.json.
"""
import json
import os
import sys

B = "public-hawaii"
S3 = f"https://s3-west.nrp-nautilus.io/{B}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
ERDDAP = "https://pae-paha.pacioos.hawaii.edu/erddap/griddap"
META = "https://www.pacioos.hawaii.edu/metadata"
TERMS = ("PacIOOS's terms: the data may be used and redistributed for free but are not intended for legal use, "
         "since they may contain inaccuracies, and come with no warranty of accuracy, completeness or usefulness.")

H6 = "H3 cell ID at resolution 6 (about 36 square kilometres)."
H0 = "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."
TIME = "The UTC day the row describes. Filter on it to select days."

DS = {
    "roms-hiig-reanalysis": {
        "erddap": "roms_hiig_reanalysis",
        "title": "ROMS ocean reanalysis for the Main Hawaiian Islands",
        "short": "ROMS reanalysis",
        "step": "3-hourly",
        "grid": "about 4 km (0.036 by 0.038 degrees)",
        "what": (
            "Daily surface ocean temperature, salinity and currents around the Main Hawaiian Islands from the "
            "Regional Ocean Modeling System (ROMS) data-assimilating reanalysis run by the University of Hawaiʻi "
            "for PacIOOS (version 2). The model assimilates satellite sea surface temperature and height, "
            "high-frequency radar surface currents and Argo and glider profiles over the previous three days, "
            "with HYCOM boundary conditions, WRF atmospheric forcing and TPXO tides. Values here are for the "
            "top model level at 0.25 m depth."
        ),
        "agg": ("Each value is the mean of the day's 3-hourly model steps (normally 8) in UTC, so a day here runs "
                "from 00:00 to 21:00 UTC, which is 14:00 to 11:00 Hawaiʻi Standard Time."),
        "version": "2",
        "creator": ("Brian S. Powell, University of Hawaiʻi at Mānoa", "https://www.soest.hawaii.edu/oceanography/"),
        "citation": ("Powell, B. S. Regional Ocean Modeling System (ROMS): Main Hawaiian Islands: Reanalysis, "
                     "version 2. University of Hawaiʻi at Mānoa, distributed by the Pacific Islands Ocean Observing "
                     "System (PacIOOS), ERDDAP dataset roms_hiig_reanalysis."),
        "vars": [
            ("temp", "Daily mean potential temperature of sea water at 0.25 m depth, in degrees Celsius.",
             "degC", "sea surface temperature"),
            ("salt", "Daily mean salinity at 0.25 m depth, on the practical salinity scale (unitless, about parts "
                     "per thousand).", "1e-3", "salinity"),
            ("u", "Daily mean eastward current velocity at 0.25 m depth, in metres per second; negative values "
                  "flow west.", "m s-1", "eastward current"),
            ("v", "Daily mean northward current velocity at 0.25 m depth, in metres per second; negative values "
                  "flow south.", "m s-1", "northward current"),
        ],
        "placement": ("Each resolution 6 cell holds the mean of the model pixels whose centres fall in it, normally "
                      "two or three."),
        "keywords": ["ROMS", "reanalysis", "ocean model", "sea surface temperature", "salinity", "ocean currents"],
    },
    "ww3-hawaii": {
        "erddap": "ww3_hawaii",
        "title": "WaveWatch III wave model for the Main Hawaiian Islands",
        "short": "WaveWatch III",
        "step": "hourly",
        "grid": "0.05 degrees (about 5 km)",
        "what": (
            "Daily wave height, period and direction around the Main Hawaiian Islands from the University of "
            "Hawaiʻi's regional WaveWatch III (WW3) model, run for PacIOOS with boundary conditions from a global "
            "WW3 run and winds from the University of Hawaiʻi's mesoscale weather model. The model resolves island "
            "shadowing, refraction and local wind waves. It is an operational forecast model, not a reanalysis: "
            "PacIOOS serves it as a best-estimate series in which each hour comes from the most recent model run "
            "that covers it, so past hours are short-range output of successive runs. Totals are given for the "
            "whole sea state and separately for swell and for local wind waves."
        ),
        "agg": ("Each value is a daily summary of the hourly model steps (normally 24) in a UTC day, which runs "
                "from 14:00 to 14:00 Hawaiʻi Standard Time. Heights and periods are daily means, the three _max "
                "columns are daily maxima of wave height, and directions are circular means, so 350 and 10 degrees "
                "average to 0 rather than 180."),
        "version": None,
        "creator": ("Kwok Fai Cheung, University of Hawaiʻi at Mānoa", "https://www.ore.hawaii.edu/"),
        "citation": ("Cheung, K. F. WaveWatch III (WW3) Hawaii Regional Wave Model. University of Hawaiʻi at "
                     "Mānoa, distributed by the Pacific Islands Ocean Observing System (PacIOOS), ERDDAP dataset "
                     "ww3_hawaii."),
        "vars": [
            ("Thgt", "Daily mean significant wave height of the whole sea state, in metres.", "m", "wave height"),
            ("Tper", "Daily mean peak wave period of the whole sea state, in seconds.", "s", "wave period"),
            ("Tdir", "Daily circular mean of the peak wave direction, in degrees clockwise from north, as the "
                     "direction waves come from. It is empty on the few days when the wave height is zero all day.", "deg", "wave direction"),
            ("shgt", "Daily mean significant height of swell, in metres. It is empty when the model reports no swell in the cell at any hour of the day.", "m", "swell height"),
            ("sper", "Daily mean peak period of swell, in seconds. It is empty when the model reports no swell in the cell at any hour of the day.", "s", "swell period"),
            ("sdir", "Daily circular mean of the swell peak direction, in degrees clockwise from north, as the "
                     "direction swell comes from. It is empty when the model reports no swell in the cell at any hour of the day.", "deg", "swell direction"),
            ("whgt", "Daily mean significant height of local wind waves, in metres. It is empty when the model reports no local wind waves in the cell at any hour of the day.", "m", "wind wave height"),
            ("wper", "Daily mean peak period of local wind waves, in seconds. It is empty when the model reports no local wind waves in the cell at any hour of the day.", "s", "wind wave period"),
            ("wdir", "Daily circular mean of the wind wave peak direction, in degrees clockwise from north, as the "
                     "direction wind waves come from. It is empty when the model reports no local wind waves in the cell at any hour of the day.", "deg", "wind wave direction"),
            ("Thgt_max", "Daily maximum significant wave height of the whole sea state, in metres.", "m",
             "maximum wave height"),
            ("shgt_max", "Daily maximum significant height of swell, in metres. It is empty when the model reports no swell in the cell at any hour of the day.", "m", "maximum swell height"),
            ("whgt_max", "Daily maximum significant height of local wind waves, in metres. It is empty when the model reports no local wind waves in the cell at any hour of the day.", "m",
             "maximum wind wave height"),
        ],
        "placement": ("Each resolution 6 cell takes the value of the model pixel under its centre, so directions "
                      "are never averaged across pixels."),
        "keywords": ["WaveWatch III", "WW3", "wave model", "wave height", "swell", "wave period", "wave direction"],
    },
}


def link(rel, href, title=None, typ="application/json"):
    d = {"rel": rel, "href": href, "type": typ}
    if title:
        d["title"] = title
    return d


def leaf(ds, st, bbox):
    p = DS[ds]
    e = p["erddap"]
    first, last = st["first"], st["last"]
    ymd = last.replace("-", "")
    var0 = p["vars"][0][0]
    partial = (f" {st['partial']} days have fewer model steps than a full day, where upstream has gaps or the "
               "record starts or ends mid-day; their values summarise the steps that exist."
               if st["partial"] else "")
    a0, a1 = st["accessed"]  # first and last access dates (UTC), YYYY-MM-DD
    when = f"on {a0} (UTC)" if a0 == a1 else f"between {a0} and {a1} (UTC)"
    cite_when = a0 if a0 == a1 else f"{a0} to {a1}"
    missing = (f" {st['missing']} days in that span have no model output upstream and have no rows here."
               if st.get("missing") else "")
    desc = (
        f"{p['what']}\n\n"
        f"One value per UTC day from {first} to {last} ({st['days']} days) on the model's {p['grid']} grid.{missing} "
        f"{p['agg']}{partial} Land and the area outside the model domain are empty.\n\n"
        "The H3 hexagon table is the layer for queries and joins. A Cloud-Optimized GeoTIFF of each variable and "
        f"day is published at {S3}/{ds}/cog/<variable>/{ds}-<variable>-YYYYMMDD.tif (WGS84, Float32, empty pixels "
        "are NaN), for map display and pixel-level work.\n\n"
        f"Source: PacIOOS ERDDAP dataset {e} ({ERDDAP}/{e}.html). Each calendar month was requested from ERDDAP "
        f"separately {when}; the netCDF file as delivered is staged at "
        f"s3://{B}/raw/{ds}/nc/{ds}-YYYYMM.nc.gz (gzipped), next to a .json file recording its request URL, access "
        "time, size in bytes and SHA-256 checksum before gzipping. The daily cube for each month, used to build "
        f"the hexagon table, is at s3://{B}/raw/{ds}/zarr/{ds}-YYYYMM.zarr, with a .days.json file giving the "
        "number of model steps behind each day.\n\n"
        f"{TERMS}"
    )
    hex_desc = (
        f"H3 hexagon table of daily {p['short']} values at resolution 6, with one row per cell per day and one "
        f"column per variable, partitioned by h0. {p['placement']} Resolution 6 is the finest this "
        "source supports: a model pixel is coarser than a resolution 8 cell, so there is no h8 column; join to "
        "resolution 8 data with h3_cell_to_parent(h8, 6).\n\n"
        "There is one row per cell per day, so nothing needs deduplicating. The values are not amounts, so do not "
        "sum them across cells or days. To summarise a region, take an area-weighted mean, because H3 cells are "
        "not equal-area; for a direction column, average its sine and cosine instead of the degrees.\n\n"
        "```sql\n"
        "-- one year of daily values in the h0 cell holding Oʻahu\n"
        f"SELECT h6, time, {var0}\n"
        f"FROM read_parquet('s3://{B}/{ds}/hex/h0=*/*.parquet')\n"
        "WHERE time BETWEEN DATE '2015-01-01' AND DATE '2015-12-31'\n"
        "  AND h0 = h3_cell_to_parent(h3_latlng_to_cell(21.3, -157.8, 6), 0);\n"
        "```"
    )
    cols = [{"name": "h6", "type": "uint64", "description": H6},
            {"name": "h0", "type": "uint64", "description": H0},
            {"name": "time", "type": "date", "description": TIME}]
    cols += [{"name": v, "type": "double", "description": d} for v, d, _, _ in p["vars"]]
    assets = {
        f"{ds}-hex": {
            "href": f"{S3}/{ds}/hex/h0=*/*.parquet",
            "type": "application/x-parquet",
            "roles": ["data"],
            "title": f"Daily {p['short']} in H3 hexagons at resolution 6",
            "description": hex_desc,
            "created": st["hex_created"],
            "h3:native_resolution": 6,
            "h3:parent_resolutions": [0],
            "table:columns": cols,
        }
    }
    for v, d, unit, name in p["vars"]:
        assets[f"{ds}-{v.lower().replace('_', '-')}-cog"] = {
            "href": f"{S3}/{ds}/cog/{v}/{ds}-{v}-{ymd}.tif",
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "roles": ["data", "visual"],
            "title": f"Daily {name} for {last}",
            "description": (f"Cloud-Optimized GeoTIFF of the last day in the record. Every day has its own file at "
                            f"{S3}/{ds}/cog/{v}/{ds}-{v}-YYYYMMDD.tif. {d} Empty pixels are NaN."),
            "created": st["cog_created"],
            "raster:bands": [{"name": v, "data_type": "float32", "nodata": "nan", "unit": unit}],
        }
    c = {
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
        "license": "other",
        "providers": [
            {"name": p["creator"][0], "roles": ["producer"], "url": p["creator"][1]},
            {"name": "Pacific Islands Ocean Observing System (PacIOOS)", "roles": ["host", "licensor"],
             "url": "https://www.pacioos.hawaii.edu/"},
            {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"],
             "url": "https://boettiger-lab.github.io"},
        ],
        "keywords": ["Hawaii", "Main Hawaiian Islands", "PacIOOS", "daily", "H3"] + p["keywords"],
        "extent": {
            "spatial": {"bbox": [bbox]},
            "temporal": {"interval": [[f"{first}T00:00:00Z", f"{last}T00:00:00Z"]]},
        },
        "created": st["cog_created"],
        "updated": st["hex_created"],
        "sci:citation": f"{p['citation']} Accessed {cite_when}.",
        "links": [
            link("self", f"{S3}/{ds}/stac-collection.json"),
            link("root", ROOT),
            link("parent", f"{S3}/stac-collection.json"),
            link("license", f"{ERDDAP}/{e}.html", "PacIOOS ERDDAP dataset page; its license attribute states the terms",
                 "text/html"),
            link("about", f"{META}/{e}.html", "PacIOOS metadata record", "text/html"),
            link("via", f"{ERDDAP}/{e}.html", f"PacIOOS ERDDAP: {e}", "text/html"),
        ],
        "assets": assets,
    }
    if p["version"]:
        c["version"] = p["version"]
        c["stac_extensions"].append("https://stac-extensions.github.io/version/v1.2.0/schema.json")
    return c


def main():
    stats = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    for ds, st in stats.items():
        c = leaf(ds, st, st["bbox"])
        os.makedirs(f"{out}/{ds}", exist_ok=True)
        json.dump(c, open(f"{out}/{ds}/stac-collection.json", "w"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
