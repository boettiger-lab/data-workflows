#!/usr/bin/env python3
"""Write the STAC collections and READMEs for the Epoch AI data centers ingest (#933).

  gen_stac.py OUT_DIR

Writes OUT_DIR/epoch/ai-data-centers/{stac-collection.json,README.md} and
OUT_DIR/epoch/ai-data-center-footprints/{stac-collection.json,README.md}. Object sizes and
created times are read from the public bucket listing (#417). The staged-raw fingerprint below
is MANIFEST.sha256 as written by epoch-ai-data-centers-stage-raw (re-checked by the derive job).

Styles and thumbnails are added afterwards by scripts/default-style.py and scripts/thumbnail.py;
scripts/stac-publish-guard.py keeps them on later republishes.
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BUCKET = "public-datacenters"
PUB = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
PARENT = f"{PUB}/stac-collection.json"
ACCESSED = "2026-11-15T23:07:22Z"
RAW = [  # sha256, bytes, path (MANIFEST.sha256 under raw/epoch/)
    ("59815c8952995bfce8d717fc653730e0bae67621f69c32e6435925541e55a784", 120053, "raw/epoch/data_centers.zip"),
    ("7c77745e48e48990bf9b707179e2f9a3382c679be9e4f4b04a66d50c5cf095ae", 3238912, "raw/epoch/ai-data-centers-map.html"),
]
LANDING = "https://epoch.ai/data/ai-data-centers"
DOCS = "https://epoch.ai/data/data-centers-documentation"
MAP = "https://epoch.ai/data/ai-data-centers/map"
ZIP = "https://epoch.ai/data/data_centers/data_centers.zip"
CITATION = ("Epoch AI, 'AI data centers'. Published online at epoch.ai. Retrieved from "
            "'https://epoch.ai/data/ai-data-centers' [online resource]. Accessed 15 November 2026.")
EXT = [
    "https://stac-extensions.github.io/table/v1.2.0/schema.json",
    "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
]
PROVIDERS = [
    {"name": "Epoch AI", "roles": ["producer", "licensor"], "url": LANDING},
    {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor"],
     "url": "https://github.com/boettiger-lab/data-workflows"},
    {"name": "National Research Platform", "roles": ["host"], "url": "https://nationalresearchplatform.org"},
]


def listing(prefix):
    """{key: (size, last_modified)} for every object under prefix."""
    out, token = {}, None
    while True:
        url = f"{PUB}/?list-type=2&prefix={prefix}" + (f"&continuation-token={token}" if token else "")
        x = urllib.request.urlopen(url, timeout=60).read().decode()
        for k, lm, sz in re.findall(r"<Key>([^<]+)</Key><LastModified>([^<]+)</LastModified>.*?<Size>(\d+)</Size>", x):
            out[k] = (int(sz), lm[:19] + "Z")
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", x)
        if not m:
            return out
        token = urllib.parse.quote(m.group(1))


def raw_text():
    rows = "; ".join(f"`s3://{BUCKET}/{p}` ({n:,} bytes, sha256 `{s}`)" for s, n, p in RAW)
    return (f"Provenance: Epoch updates this hub continuously and publishes no edition label, so this "
            f"build is a snapshot. Epoch's download ({ZIP}) and its map page ({MAP}) were retrieved "
            f"on {ACCESSED[:10]} at {ACCESSED[11:16]} UTC and staged unchanged: {rows}.")


def col(name, typ, desc, values=None):
    c = {"name": name, "type": typ, "description": desc}
    if values:
        c["values"] = values
    return c


CONF_NOTE = ("Each name carries Epoch's confidence tag: #confident, #likely or #speculative.")

SITE_COLS = [
    col("_cng_fid", "int64", "Row identifier assigned at conversion, one per site. In the hex table, "
        "COUNT(DISTINCT _cng_fid) counts sites."),
    col("name", "string", "Name of the record: the data center site or campus in the sites table "
        "(Epoch field Name, joined by the data_center column of the timelines and chip quantities "
        "tables), or the chip model in the chip types table (joined by chip_type)."),
    col("current_h100_equivalents", "double", "Most recent estimate of the site's AI compute capacity, "
        "in NVIDIA H100-equivalents based on 8-bit operations per second, as of the snapshot date."),
    col("current_power_mw", "double", "Most recent estimate of the site's IT power capacity in megawatts: "
        "power for GPU servers, networking and storage, excluding cooling and other facility overhead."),
    col("current_total_capital_cost_2025_usd_billions", "double",
        "Most recent estimate of the site's total capital cost, in billions of 2025 US dollars."),
    col("owner", "string", "Chip owner: who owns the AI hardware (not necessarily the owner or operator of "
        "the building). " + CONF_NOTE + " Blank where Epoch records no owner."),
    col("users", "string", "AI labs using the compute, comma-separated. " + CONF_NOTE),
    col("selected_sources", "string", "Epoch's list of the most important sources for the site, as Markdown links."),
    col("calculations_sheet", "string", "Link to Epoch's spreadsheet holding the site's timeline, chip "
        "and cooling calculations."),
    col("project", "string", "Broader project the site belongs to, if any (for example Stargate). " + CONF_NOTE),
    col("current_chip_types", "string", "Chip types Epoch estimates are deployed at the site now, "
        "comma-separated; each matches name in the chip types table."),
    col("all_chip_types", "string", "Every chip type Epoch records at the site over its timeline, comma-separated."),
    col("investors", "string", "Financial backers of the site or project, comma-separated."),
    col("construction_companies", "string", "Companies involved in building the site, comma-separated."),
    col("energy_companies", "string", "Companies supplying power to the site, comma-separated."),
    col("country", "string", "Country the site is in."),
    col("address", "string", "Street address from public records; blank for 14 sites."),
    col("owner_name", "string", "The chip owner without its confidence tag (owner with the trailing "
        "#confident, #likely or #speculative removed), for grouping and map colours."),
    col("city", "string", "City of the site, as given on Epoch's map page."),
    col("state", "string", "State, province or region of the site, as given on Epoch's map page."),
    col("operational", "boolean", "Whether Epoch's map page marks the site as operational (some of its "
        "capacity is running) as of the snapshot."),
    col("longitude", "double", "Longitude of the site's map marker on Epoch's map page (WGS84)."),
    col("latitude", "double", "Latitude of the site's map marker on Epoch's map page (WGS84)."),
    col("geometry", "geometry", "Point at the site's map marker on Epoch's map page (WGS84)."),
    col("h8", "uint64", "H3 cell at resolution 8 holding the site point."),
    col("h0", "uint64", "H3 cell at resolution 0, the partition key for hive-partitioned reads."),
    # --- timelines
    col("data_center", "string", "Name of the data center site the record belongs to; joins to name in "
        "the sites collection (epoch/ai-data-centers)."),
    col("date", "date", "As-of date of the record. Dates after the snapshot date are Epoch's projections "
        "from permits and announcements."),
    col("construction_status", "string", "Epoch's short description of construction progress on that date."),
    col("buildings_operational", "double", "Number of buildings operational by that date."),
    col("it_power_mw", "double", "IT power capacity on that date, in megawatts (GPU servers, networking and storage)."),
    col("power_mw", "double", "Total facility power capacity on that date, in megawatts, including cooling, "
        "lighting and other overhead."),
    col("h100_equivalents", "double", "Compute capacity on that date in NVIDIA H100-equivalents, based on "
        "8-bit operations per second."),
    col("performance_op_s_8bit", "double", "Peak compute capacity on that date, in operations per second at "
        "8-bit or wider precision."),
    col("total_capital_cost_2025_usd_billions", "double", "Total capital cost of the facility by that date, "
        "in billions of 2025 US dollars (compute plus construction)."),
    col("compute_cost_2025_usd_billions", "double", "Capital cost of IT hardware (chips, servers, networking) "
        "by that date, in billions of 2025 US dollars."),
    col("construction_cost_2025_usd_billions", "double", "Capital cost other than compute (building, "
        "mechanical and electrical, land, labour) by that date, in billions of 2025 US dollars."),
    col("annual_operating_cost_2025_usd_billions", "double", "Annual operating cost at that date (energy, "
        "taxes, maintenance, labour, water), in billions of 2025 US dollars."),
    col("water_use_mgd", "double", "Estimated average water consumption in million gallons per day; "
        "blank where Epoch has no estimate."),
    col("current_h100_equivalents_from_data_center", "double", "The site's current H100-equivalents, "
        "repeated on every timeline row of the site (Epoch uses it to sort the table)."),
    # --- chip quantities
    col("handle", "string", "Epoch's record label: chip type, site and date."),
    col("chip_type", "string", "Chip type deployed; joins to name in the chip types table."),
    col("number_of_units", "int64", "Number of chips of this type at the site from this date. Quantities "
        "start at zero and hold until the next record for the same site and chip type, so sum the latest "
        "record per site and chip type, not every row."),
    col("chip_type_source", "string", "How the chip type was determined. Values: Company disclosure=disclosed "
        "by a company involved with the site, Estimate=estimated by Epoch.",
        ["Company disclosure", "Estimate"]),
    col("number_of_units_source", "string", "How the number of chips was determined. Values: Company "
        "disclosure=disclosed by a company involved with the site, Estimate=estimated by Epoch, usually "
        "from IT power divided by power per chip.", ["Company disclosure", "Estimate"]),
    col("user", "string", "User of the chips on that date. " + CONF_NOTE),
    col("notes", "string", "Epoch's free-text notes on the record."),
    col("timeline", "date", "Date of the timeline record this row corresponds to."),
    # --- chip types
    col("ml_hardware_linked", "string", "Full name of the chip in Epoch's machine learning hardware database."),
    col("designer", "string", "Company that designed the chip."),
    col("primarily_for_chinese_market", "boolean", "True where the chip is sold primarily for the Chinese market."),
    col("tdp_w_from_ml_hardware_linked", "int64", "Thermal design power of one chip in watts, from Epoch's "
        "hardware database."),
    col("flop_s_16bit", "int64", "Peak 16-bit floating-point operations per second of one chip."),
    col("op_s_8bit", "int64", "Peak 8-bit operations per second of one chip."),
    col("memory", "int64", "Memory per chip in bytes."),
    col("memory_bandwidth", "int64", "Memory bandwidth per chip in bytes per second."),
    col("h100e", "double", "Compute of one chip in NVIDIA H100-equivalents."),
    col("cost_per_chip_approx", "double", "Approximate cost of one chip in US dollars."),
    col("release_date", "date", "Release date of the chip."),
    col("unofficial_estimated_tdp_w", "double", "Epoch's estimate of thermal design power in watts where no "
        "official figure is published."),
    # --- chillers and cooling towers
    col("model", "string", "Cooling equipment model."),
    col("manufacturer", "string", "Cooling equipment manufacturer."),
    col("type", "string", "Cooling equipment type as Epoch records it (chillers: Air-cooled or Water-cooled; "
        "cooling towers: Wet, or blank)."),
    col("cooling_capacity_kw", "double", "Rated cooling capacity of one chiller in kilowatts."),
    col("number_of_fans", "int64", "Number of fans on one unit."),
    col("length_m", "double", "Unit length in metres."),
    col("width_m", "double", "Unit width in metres."),
    col("height_m", "double", "Unit height in metres."),
    col("area_m2", "double", "Unit footprint area in square metres."),
    col("source", "string", "Source of the specification."),
    col("link", "string", "Link to the specification source."),
    col("spot_check", "string", "Epoch's note from checking the record against its source."),
    col("cooling_capacity_stated_kw", "string", "Cooling capacity in kilowatts as stated by the source, kept "
        "as text (it may carry thousands separators)."),
    col("cooling_capacity_central_estimate_kw", "double", "Epoch's central estimate of cooling capacity in kilowatts."),
    col("fan_diameter_m", "double", "Fan diameter in metres, as stated by the source."),
    col("fan_estimate_diameter_m", "double", "Epoch's estimate of fan diameter in metres."),
    col("motor_horsepower", "double", "Fan motor power in horsepower."),
]

FP_TYPES = ["Building", "Cooling", "Backup generator", "Power substation", "Power generator"]
FP_COLS = [
    col("_cng_fid", "int64", "Row identifier assigned at conversion, one per footprint polygon. In the hex "
        "table, COUNT(DISTINCT _cng_fid) counts polygons."),
    col("data_center", "string", "Name of the data center site the polygon belongs to; joins to name in "
        "the sites collection (epoch/ai-data-centers)."),
    col("feature_index", "int64", "Position of the polygon in Epoch's annotation list for the site, from 0."),
    col("feature_type", "string", "What the polygon outlines. Values: Building=data center building, "
        "Cooling=outdoor cooling equipment such as chillers or cooling towers, Backup generator=backup "
        "generators (usually diesel), Power substation=electrical substation connecting the site to the grid, "
        "Power generator=on-site power generation such as gas turbines.", FP_TYPES),
    col("building_number", "int64", "Epoch's number for the building within the site; set on every building "
        "polygon and on one cooling polygon, blank otherwise."),
    col("building_label", "string", "Epoch's name for a building that carries a label instead of a number "
        "(3 polygons)."),
    col("complete", "boolean", "Epoch's completion flag on the annotation: true where marked complete, false "
        "where not (for example under construction), blank where unset. Epoch does not define the flag "
        "further."),
    col("start_date", "date", "Date set by Epoch on 39 annotations at one site (OpenAI Stargate Abilene), "
        "marking when the structure appears in the site's imagery timeline."),
    col("end_date", "date", "Date set by Epoch on 22 of those annotations, marking when the structure "
        "is no longer present; blank where it remains."),
    col("stated_area_m2", "double", "Area in square metres recorded by Epoch on the annotation (9 polygons "
        "at one site). For other polygons, compute the area from the geometry."),
    col("drawn_as_line", "boolean", "True for the 67 outlines Epoch drew as an open line instead of a polygon. "
        "They were closed into polygons here, using the last vertex (within about 10 m of the first) as the "
        "closing point."),
    col("geometry", "geometry", "Outline polygon drawn by Epoch on satellite imagery (WGS84)."),
    col("h10", "uint64", "H3 cell at resolution 10 (native resolution) covered by the polygon."),
    col("h9", "uint64", "H3 cell at resolution 9, parent of h10."),
    col("h8", "uint64", "H3 cell at resolution 8, parent of h10."),
    col("h0", "uint64", "H3 cell at resolution 0, the partition key for hive-partitioned reads."),
]

TABLES = {  # key -> (file, title, description, columns)
    "ai-data-center-timelines": ("Timelines", "One row per site and date: construction status, buildings "
        "operational, IT and total power, compute, capital and operating cost, and water use. Join to the "
        "sites on data_center = name. Dates after the snapshot are projections.",
        ["data_center", "date", "construction_status", "buildings_operational", "it_power_mw", "power_mw",
         "h100_equivalents", "performance_op_s_8bit", "total_capital_cost_2025_usd_billions",
         "compute_cost_2025_usd_billions", "construction_cost_2025_usd_billions",
         "annual_operating_cost_2025_usd_billions", "water_use_mgd", "current_h100_equivalents_from_data_center"]),
    "ai-data-center-chip-quantities": ("Chip quantities", "Dated records of the type and number of chips at "
        "each site. Join to the sites on data_center = name and to chip types on chip_type = name.",
        ["handle", "date", "chip_type", "number_of_units", "chip_type_source", "number_of_units_source",
         "owner", "user", "notes", "data_center", "timeline"]),
    "ai-chip-types": ("Chip types", "Specifications of the AI chips named in the chip quantities and sites "
        "tables (from Epoch's AI chip sales hub).",
        ["name", "ml_hardware_linked", "designer", "primarily_for_chinese_market", "tdp_w_from_ml_hardware_linked",
         "flop_s_16bit", "op_s_8bit", "notes", "memory", "memory_bandwidth", "h100e", "cost_per_chip_approx",
         "release_date", "unofficial_estimated_tdp_w"]),
    "ai-data-center-chillers": ("Chillers", "Specifications of chiller models that underlie Epoch's cooling "
        "model, which estimates a site's power from the cooling equipment visible in satellite imagery.",
        ["model", "manufacturer", "type", "cooling_capacity_kw", "number_of_fans", "length_m", "width_m",
         "area_m2", "source", "link", "spot_check", "notes"]),
    "ai-data-center-cooling-towers": ("Cooling towers", "Specifications of cooling tower models used in "
        "Epoch's cooling model.",
        ["model", "manufacturer", "length_m", "width_m", "height_m", "area_m2", "cooling_capacity_stated_kw",
         "cooling_capacity_central_estimate_kw", "source", "link", "spot_check", "notes", "fan_diameter_m",
         "number_of_fans", "fan_estimate_diameter_m", "type", "motor_horsepower"]),
}
SITE_FLAT = [c["name"] for c in SITE_COLS[:SITE_COLS.index(next(c for c in SITE_COLS if c["name"] == "h8"))]]
FP_FLAT = [c["name"] for c in FP_COLS if not re.match(r"h\d+$", c["name"])]

TILE_TYPE = {"string": "String", "boolean": "Boolean", "date": "String"}


def cols_of(dic, names):
    d = {c["name"]: c for c in dic}
    return [{"name": n, "type": d[n]["type"]} for n in names]


def tile_cols(dic, names):
    d = {c["name"]: c for c in dic}
    return [{"name": n, "type": TILE_TYPE.get(d[n]["type"], "Number")} for n in names if n != "geometry"]


def links(path, pmtiles_href, pmtiles_title, layer):
    return [
        {"rel": "self", "href": f"{PUB}/{path}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": ROOT, "type": "application/json"},
        {"rel": "parent", "href": PARENT, "type": "application/json"},
        {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/", "type": "text/html",
         "title": "Creative Commons Attribution 4.0 International"},
        {"rel": "about", "href": LANDING, "type": "text/html", "title": "Epoch AI: AI data centers"},
        {"rel": "describedby", "href": DOCS, "type": "text/html", "title": "Epoch AI data centers documentation"},
        {"rel": "via", "href": MAP, "type": "text/html", "title": "Epoch AI data centers map (source of coordinates and footprints)"},
        {"rel": "via", "href": ZIP, "type": "application/zip", "title": "Epoch AI data centers download (all datasets)"},
        {"rel": "pmtiles", "href": pmtiles_href, "type": "application/vnd.pmtiles", "title": pmtiles_title,
         "pmtiles:layers": [layer]},
    ]


def collection(cid, title, desc, path, bbox, interval, dic, assets, keywords, pmkey):
    pm = assets[pmkey]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "type": "Collection", "stac_version": "1.1.0", "stac_extensions": EXT, "id": cid,
        "title": title, "description": desc, "keywords": keywords, "license": "CC-BY-4.0",
        "providers": PROVIDERS, "sci:citation": CITATION, "created": now, "updated": now,
        "extent": {"spatial": {"bbox": [bbox]}, "temporal": {"interval": [interval]}},
        "table:columns": dic, "links": links(path, pm["href"], pm["title"], pm["vector:layers"][0]),
        "assets": assets,
    }


def main(out):
    out = Path(out)
    objs = listing("epoch/")

    def asset(path, typ, title, desc, roles=("data",), **kw):
        if path not in objs:
            raise SystemExit(f"missing object {path}")
        a = {"href": f"{PUB}/{path}", "type": typ, "title": title, "description": desc,
             "roles": list(roles), "created": objs[path][1], "file:size": objs[path][0]}
        a.update(kw)
        return a

    def hexa(path, title, desc, native, parents, cols):
        parts = [k for k in objs if k.startswith(path + "/hex/h0=")]
        if not parts:
            raise SystemExit(f"no hex under {path}")
        return {"href": f"{PUB}/{path}/hex/h0=*/data_0.parquet", "type": "application/x-parquet",
                "title": title, "description": desc, "roles": ["data"],
                "created": max(objs[k][1] for k in parts), "h3:native_resolution": native,
                "h3:parent_resolutions": parents, "table:columns": cols}

    # ---------------------------------------------------------------- sites
    p = "epoch/ai-data-centers"
    site_hex_cols = cols_of(SITE_COLS, [c for c in SITE_FLAT if c != "geometry"] + ["h8", "h0"])
    sa = {
        "ai-data-centers-parquet": asset(f"{p}.parquet", "application/vnd.apache.parquet",
            "AI data center sites (GeoParquet)", "One point per data center site (96 sites).",
            **{"table:columns": cols_of(SITE_COLS, SITE_FLAT)}),
        "ai-data-centers-pmtiles": asset(f"{p}.pmtiles", "application/vnd.pmtiles",
            "AI data center sites (PMTiles)", "Vector tiles of the site points for web maps; layer ai-data-centers.",
            **{"vector:layers": ["ai-data-centers"], "table:columns": tile_cols(SITE_COLS, SITE_FLAT)}),
        "ai-data-centers-hex": hexa(p, "AI data center sites (H3 hex)",
            "Each site point resolved to one H3 cell at resolution 8 (about 0.7 square kilometres), with its "
            "resolution 0 parent as the partition key. One row per site; sites in the same cell are not merged. "
            "Each site is a point in exactly one cell, so per-feature values such as power, compute and capital "
            "cost appear once per site and SUM over the table is the total over sites; COUNT(DISTINCT _cng_fid) "
            "counts sites.",
            8, [0], site_hex_cols),
    }
    for key, (ttl, d, names) in TABLES.items():
        sa[key] = asset(f"epoch/{key}.parquet", "application/vnd.apache.parquet", f"{ttl} (Parquet table)", d,
                        **{"table:columns": cols_of(SITE_COLS, names)})
    desc = (
        "Epoch AI's database of large AI data centers: 96 sites worldwide (77 in the United States, the rest "
        "in China, Malaysia, Norway, the United Arab Emirates, Portugal, Indonesia, the United Kingdom, "
        "Australia, Sweden, Finland and Iceland), with each site's chip owner and users, current IT power, "
        "compute in H100-equivalents and capital cost, built from satellite imagery, permits and company "
        "disclosures. Epoch prioritises sites by compute capacity, mostly ones operational from 2024 or "
        "under construction, and estimates the database covers about 44% of global deployed AI compute as "
        "of November 2026.\n\n"
        "Site locations: Epoch's CSV gives addresses but no coordinates, so each point is the site's marker on "
        f"Epoch's interactive map ({MAP}), matched to the CSV by exact site name. All 96 sites matched and "
        "all have a coordinate; none has a null geometry. City, state and the operational flag also come from "
        "the map page. The annotated building and equipment outlines from the same map are in the companion "
        "collection epoch/ai-data-center-footprints.\n\n"
        "Companion tables (non-spatial Parquet, joined to the sites on data_center = name): timelines "
        "(575 dated records of construction status, power, compute and cost, including projections past the "
        "snapshot date), chip quantities (258), chip types (32), and the chiller (143) and cooling tower (527) "
        "specifications behind Epoch's cooling model. Column names are Epoch's headers in snake_case; values "
        "are unchanged apart from type parsing. Fields marked with #confident, #likely or #speculative carry "
        "Epoch's confidence in that attribution.\n\n"
        "Points were hexed to H3 resolution 8 (each point to one cell of about 0.7 square kilometres), with "
        "resolution 0 as the partition key.\n\n"
        f"{raw_text()} Epoch's download page dated the files: sites and chip quantities 6 November 2026, "
        "timelines and the download package 12 November 2026, chip types 21 October 2026, chillers 8 June 2026, "
        "cooling towers 20 January 2026.\n\n"
        "Licence: Creative Commons Attribution 4.0 (CC-BY-4.0): free to use, distribute and reproduce with "
        f"credit to Epoch AI. Cite as: {CITATION} The satellite imagery shown on Epoch's map is licensed by "
        "its imagery providers, not Epoch, and is not included."
    )
    s = gpd_bounds(f"{PUB}/{p}.parquet")
    sites = collection("epoch-ai-data-centers", "Epoch AI data centers (96 sites, global)", desc, p, s,
                       ["2018-12-18T00:00:00Z", "2030-01-01T00:00:00Z"], SITE_COLS, sa,
                       ["data centers", "AI", "compute", "energy", "infrastructure", "Epoch AI"],
                       "ai-data-centers-pmtiles")
    write(out / p, sites, readme_sites(p))

    # ---------------------------------------------------------------- footprints
    p = "epoch/ai-data-center-footprints"
    fp_hex_cols = cols_of(FP_COLS, [c for c in FP_FLAT if c != "geometry"] + ["h10", "h9", "h8", "h0"])
    fa = {
        "ai-data-center-footprints-parquet": asset(f"{p}.parquet", "application/vnd.apache.parquet",
            "AI data center footprints (GeoParquet)", "One polygon per annotated building or equipment outline "
            "(1,360 polygons at 95 sites).", **{"table:columns": cols_of(FP_COLS, FP_FLAT)}),
        "ai-data-center-footprints-pmtiles": asset(f"{p}.pmtiles", "application/vnd.pmtiles",
            "AI data center footprints (PMTiles)", "Vector tiles of the footprint polygons for web maps; layer "
            "ai-data-center-footprints.", **{"vector:layers": ["ai-data-center-footprints"],
                                            "table:columns": tile_cols(FP_COLS, FP_FLAT)}),
        "ai-data-center-footprints-hex": hexa(p, "AI data center footprints (H3 hex)",
            "One row per polygon and H3 resolution 10 cell it covers, with resolution 9, 8 and 0 parents. A "
            "polygon covering several cells is repeated on each, so its attributes (stated_area_m2 in "
            "particular, a per-polygon total) are repeated on every cell; dedup on _cng_fid before summing "
            "(SELECT DISTINCT _cng_fid, stated_area_m2 ...). Use the cells themselves for area. Small "
            "polygons that fall inside one cell still get that cell.",
            10, [9, 8, 0], fp_hex_cols),
    }
    desc = (
        "Outlines of the buildings and outdoor equipment at large AI data centers, as annotated by Epoch AI on "
        "satellite imagery: 1,360 polygons at 95 of the 96 sites in Epoch's AI data centers database (OpenAI "
        "Stargate New Mexico has no outlines). Each polygon is a data center building (395), outdoor cooling "
        "equipment (417), backup generators (346), a power substation (188) or on-site power generation (14), "
        "with Epoch's building number and completion flag where set. Epoch uses these outlines to estimate "
        "site power from cooling and generator capacity.\n\n"
        f"Source: the polygons are not in Epoch's CSV download; they were read from Epoch's interactive map page "
        f"({MAP}), which embeds each site's annotations. They reflect the annotations as of the snapshot date "
        "and are drawn on imagery of varying dates. Join to the sites collection (epoch/ai-data-centers) on "
        "data_center = name. Processing: 67 outlines Epoch drew as open lines were closed into polygons "
        "(drawn_as_line = true); 4 self-intersecting polygons were repaired into valid multipolygons; two "
        "empty zero-area shapes with no attributes at Amazon Madison Mega Site were dropped. Annotation "
        "properties Epoch spelled several ways (buildingNumber, building, Building) were merged into one "
        "column.\n\n"
        "Polygons were hexed to H3 resolution 10 (about 0.015 square kilometres per cell), with parents at "
        "resolutions 9, 8 and 0.\n\n"
        f"{raw_text()}\n\n"
        "Licence: Creative Commons Attribution 4.0 (CC-BY-4.0): free to use, distribute and reproduce with "
        f"credit to Epoch AI. Cite as: {CITATION} The satellite imagery shown on Epoch's map is licensed by "
        "its imagery providers, not Epoch, and is not included."
    )
    b = gpd_bounds(f"{PUB}/{p}.parquet")
    fps = collection("epoch-ai-data-center-footprints", "Epoch AI data center footprints (95 sites, global)",
                     desc, p, b, [None, "2026-11-15T00:00:00Z"], FP_COLS, fa,
                     ["data centers", "AI", "building footprints", "cooling", "energy", "Epoch AI"],
                     "ai-data-center-footprints-pmtiles")
    write(out / p, fps, readme_fp(p))


def gpd_bounds(url):
    import geopandas as gpd
    import io
    g = gpd.read_parquet(io.BytesIO(urllib.request.urlopen(url, timeout=120).read()))
    return [round(float(x), 6) for x in g.total_bounds]


def write(d, doc, readme):
    d.mkdir(parents=True, exist_ok=True)
    (d / "stac-collection.json").write_text(json.dumps(doc, indent=2) + "\n")
    (d / "README.md").write_text(readme)


def readme_sites(p):
    return f"""# Epoch AI data centers

Epoch AI's database of 96 large AI data centers worldwide: chip owner and users, IT power, compute
(H100-equivalents) and capital cost per site, with dated timelines and chip quantities. Site points
come from Epoch's map page ({MAP}), since the CSV carries addresses only.

STAC: {PUB}/{p}/stac-collection.json

| File | Contents |
|---|---|
| `{p}.parquet` | GeoParquet, one point per site |
| `{p}.pmtiles` | Vector tiles, layer `ai-data-centers` |
| `{p}/hex/h0=*/data_0.parquet` | H3 resolution 8, partitioned by `h0` |
| `epoch/ai-data-center-timelines.parquet` | Dated status, power, compute and cost per site |
| `epoch/ai-data-center-chip-quantities.parquet` | Dated chip counts per site |
| `epoch/ai-chip-types.parquet` | Chip specifications |
| `epoch/ai-data-center-chillers.parquet` | Chiller specifications (cooling model) |
| `epoch/ai-data-center-cooling-towers.parquet` | Cooling tower specifications (cooling model) |

## DuckDB

```sql
INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;
SELECT s.name, s.owner_name, s.current_power_mw, t.date, t.it_power_mw
FROM read_parquet('{PUB}/{p}.parquet') s
JOIN read_parquet('{PUB}/epoch/ai-data-center-timelines.parquet') t ON t.data_center = s.name
ORDER BY s.current_power_mw DESC, t.date;
```

## MapLibre

```js
map.addSource('ai-data-centers', {{ type: 'vector', url: 'pmtiles://{PUB}/{p}.pmtiles' }});
map.addLayer({{
  id: 'ai-data-centers', type: 'circle', source: 'ai-data-centers',
  'source-layer': 'ai-data-centers',
  paint: {{ 'circle-radius': 5, 'circle-color': '#0058DC' }}
}});
```

## Licence and citation

CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/). {CITATION}

{raw_text()}
"""


def readme_fp(p):
    return f"""# Epoch AI data center footprints

Outlines of buildings, cooling equipment, backup generators, substations and on-site power generation
at 95 large AI data centers, as annotated by Epoch AI on satellite imagery and read from Epoch's map
page ({MAP}). Join to the sites (`epoch/ai-data-centers`) on `data_center = name`.

STAC: {PUB}/{p}/stac-collection.json

| File | Contents |
|---|---|
| `{p}.parquet` | GeoParquet, one polygon per annotation |
| `{p}.pmtiles` | Vector tiles, layer `ai-data-center-footprints` |
| `{p}/hex/h0=*/data_0.parquet` | H3 resolution 10 with parents 9, 8, 0, partitioned by `h0` |

## DuckDB

```sql
INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;
SELECT data_center, feature_type, count(*) AS n,
       round(sum(ST_Area_Spheroid(ST_FlipCoordinates(geometry)))) AS area_m2
FROM read_parquet('{PUB}/{p}.parquet')
GROUP BY ALL ORDER BY data_center, feature_type;
```

## MapLibre

```js
map.addSource('footprints', {{ type: 'vector', url: 'pmtiles://{PUB}/{p}.pmtiles' }});
map.addLayer({{
  id: 'footprints', type: 'fill', source: 'footprints',
  'source-layer': 'ai-data-center-footprints',
  paint: {{ 'fill-color': ['match', ['get', 'feature_type'],
    'Building', '#5f5f5f', 'Cooling', '#1f78b4', 'Backup generator', '#6a3d9a',
    'Power substation', '#ff7f00', 'Power generator', '#d01c8b', '#bdbdbd'], 'fill-opacity': 0.7 }}
}});
```

## Licence and citation

CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/). {CITATION}

{raw_text()}
"""


if __name__ == "__main__":
    import urllib.parse  # noqa: F401  (used in listing)
    main(sys.argv[1])
