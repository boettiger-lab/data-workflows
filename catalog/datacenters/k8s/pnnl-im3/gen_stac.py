#!/usr/bin/env python3
"""Write the STAC collections and READMEs for the PNNL IM3 data center layers (#932).

  gen_stac.py OUT_DIR

Writes OUT_DIR/public-datacenters/pnnl-im3/{atlas-point,atlas-building,atlas-campus,projected}/
{stac-collection.json,README.md}. Object sizes and created times are read from the public bucket
listing (#417); the staged-raw fingerprints are the MANIFEST.sha256 files written by
pnnl-im3-stage-raw.yaml. Counts, ranges and coded values below were measured on the upstream files
and checked against the published GeoParquet through the duckdb-geo server on 2026-11-16.

Styles and thumbnails are added afterwards by scripts/default-style.py and scripts/thumbnail.py;
scripts/stac-publish-guard.py keeps them on later republishes.
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BUCKET = "public-datacenters"
PUB = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
PARENT = f"{PUB}/stac-collection.json"

ATLAS_REC = "https://data.msdlive.org/records/qxpk8-yae09"
ATLAS_DOI = "https://doi.org/10.57931/17054299"
ATLAS_ACCESSED = "2026-11-16T03:06:29Z"
ATLAS_RAW = "raw/pnnl-im3/atlas-v2026.11.02"
PROJ_REC = "https://data.msdlive.org/records/r0cga-34g05"
PROJ_DOI = "https://doi.org/10.57931/3020186"
PROJ_ACCESSED = "2026-11-16T03:06:31Z"
PROJ_RAW = "raw/pnnl-im3/projected-v1.1"
ODBL = "https://opendatacommons.org/licenses/odbl/1-0/"
CCBY = "https://creativecommons.org/licenses/by/4.0/legalcode"

ATLAS_CITATION = ("Mongird, K., Vernon, C., Burleyson, C., Akdemir, K. Z., & Rice, J. (2026). IM3 Open Source "
                  "Data Center Atlas (v2026.11.02) [Data set]. MSD-LIVE Data Repository. "
                  "https://doi.org/10.57931/17054299")
PROJ_CITATION = ("Mongird, K., Burleyson, C., Akdemir, K. Z., Vernon, C., & Rice, J. (2026). IM3 Projected US "
                 "Data Center Locations (v1.1) [Data set]. MSD-LIVE Data Repository. "
                 "https://doi.org/10.57931/3020186")
EXT = [
    "https://stac-extensions.github.io/table/v1.2.0/schema.json",
    "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
    "https://stac-extensions.github.io/version/v1.2.0/schema.json",
]
PROCESSORS = [
    {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor"],
     "url": "https://github.com/boettiger-lab/data-workflows"},
    {"name": "National Research Platform", "roles": ["host"], "url": "https://nationalresearchplatform.org"},
]
ATLAS_PROVIDERS = [
    {"name": "Pacific Northwest National Laboratory (IM3 project)", "roles": ["producer", "licensor"],
     "url": "https://im3.pnnl.gov/datacenter-atlas"},
    {"name": "OpenStreetMap contributors", "roles": ["producer"], "url": "https://www.openstreetmap.org/copyright"},
    {"name": "MSD-LIVE Data Repository", "roles": ["host"], "url": ATLAS_REC},
    *PROCESSORS,
]
PROJ_PROVIDERS = [
    {"name": "Pacific Northwest National Laboratory (IM3 project)", "roles": ["producer", "licensor"],
     "url": "https://im3.pnnl.gov/datacenter-atlas"},
    {"name": "MSD-LIVE Data Repository", "roles": ["host"], "url": PROJ_REC},
    *PROCESSORS,
]
ATLAS_TERMS = (
    "Licence: Open Database License (ODbL) 1.0. The atlas is derived from OpenStreetMap, and PNNL publishes it "
    "under the same licence. You may copy, distribute and adapt the data provided you attribute it (cite the "
    "atlas, and credit \"© OpenStreetMap contributors\"), and a database you derive from it and share must be "
    "offered under the ODbL as well. State and county assignments come from U.S. Census Bureau 2024 boundaries. "
    "Cite as: " + ATLAS_CITATION + "."
)
PROJ_TERMS = (
    "Licence: Creative Commons Attribution 4.0 International (CC BY 4.0). Reuse is free with attribution. "
    "Cite as: " + PROJ_CITATION + "."
)
H8_NOTE = ("H3 cell ID at resolution 8 (about 0.74 square kilometres on average), the catalog's common join "
           "resolution.")
H0_NOTE = "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."
TILE_TYPE = {"string": "String", "boolean": "Boolean", "date": "String"}


def col(name, typ, desc, values=None):
    c = {"name": name, "type": typ, "description": desc}
    if values:
        c["values"] = values
    return c


def atlas_cols(kind):
    """Column dictionary for one atlas layer; kind is point, building or campus."""
    geom = {"point": "Facility point (WGS84 longitude/latitude), as mapped in OpenStreetMap.",
            "building": "Building footprint polygon (WGS84 longitude/latitude), as mapped in OpenStreetMap.",
            "campus": "Campus outline (multi)polygon (WGS84 longitude/latitude), as mapped in OpenStreetMap."}[kind]
    sqft = ("Area of the facility polygon in square feet, computed by PNNL from the footprint. Empty for the point "
            "layer, which has no footprint.")
    return [
        col("_cng_fid", "int64", "Row identifier added during conversion; one per row. Rows for a facility that "
            "straddles a county line share an id, so count facilities with COUNT(DISTINCT id)."),
        col("fid", "int64", "Row number of the record in the upstream GeoPackage layer."),
        col("id", "string", "OpenStreetMap element ID of the facility, with the node/way/relation prefix removed "
            "by PNNL. A facility whose footprint crosses a county line appears once per county with the same id."),
        col("state", "string", "Name of the U.S. state (or District of Columbia, or Puerto Rico) the facility is in."),
        col("state_abb", "string", "Two-letter postal abbreviation of the state."),
        col("state_id", "string", "Two-digit Census FIPS code of the state."),
        col("county", "string", "Name of the county (or county equivalent) the facility is in, from Census 2024 "
            "boundaries."),
        col("county_id", "string", "Three-digit Census FIPS code of the county within its state; the 5-digit "
            "county GEOID is state_id || county_id."),
        col("operator", "string", "Company or organisation operating the facility, as tagged in OpenStreetMap. "
            "Often empty."),
        col("ref", "string", "Reference number or site code, as tagged in OpenStreetMap (for example HIL1). "
            "Often empty."),
        col("name", "string", "Facility name, as tagged in OpenStreetMap."),
        col("sqft", "double", sqft),
        col("lon", "double", "Longitude of the facility's centroid in decimal degrees."),
        col("lat", "double", "Latitude of the facility's centroid in decimal degrees."),
        col("type", "string", "Which atlas layer the row comes from. Values: point=mapped as a single point, "
            "building=a mapped building footprint, campus=a mapped site or campus area that is not tagged as a "
            "building.", [kind]),
        col("geom", "geometry", geom),
        col("h8", "uint64", H8_NOTE),
        col("h0", "int64", H0_NOTE),
    ]


PROJ_COLS = [
    col("_cng_fid", "int64", "Row identifier added during conversion; one per projected site per scenario. Use "
        "COUNT(DISTINCT _cng_fid) to count sites across scenarios."),
    col("OGC_FID", "int64", "Row number of the site within its upstream scenario file, starting at 0; repeats "
        "across scenarios."),
    col("id", "string", "Site identifier, unique only within one scenario (growth_scenario and "
        "market_gravity_weight); the same id names different sites in different scenarios."),
    col("growth_scenario", "string", "Data center electricity demand growth scenario, following EPRI (2024). "
        "Values: low=3.71% annual growth from 2023, moderate=5%, high=10%, higher=15%.",
        ["low", "moderate", "high", "higher"]),
    col("market_gravity_weight", "int32", "Weight, in percent, given to proximity to existing data center markets "
        "and population, against locational cost, when choosing sites. Values: 0=locational cost only, "
        "25=25% market proximity and 75% cost, 50=equal weight, 75=75% market proximity and 25% cost, "
        "100=market proximity only.", [0, 25, 50, 75, 100]),
    col("region", "string", "State the site is in, in lower case with underscores (for example new_jersey); 37 "
        "states."),
    col("total_cost_million_usd", "double", "Modelled locational siting cost of the site in millions of US "
        "dollars (472 to 602)."),
    col("campus_size_square_ft", "int32", "Land acquired for the facility in square feet. Every site is modelled "
        "at the same size, 1,000,000 square feet."),
    col("data_center_it_power_mw", "int32", "IT power of the facility in megawatts. Every site is modelled at the "
        "same capacity, 36 MW."),
    col("mechanical_cooling_frac", "double", "Fraction of the year the facility runs mechanical cooling (0, 0.5, "
        "0.75 or 1); the rest of the year it uses evaporative cooling."),
    col("water_cooling_frac", "double", "Fraction of the year the facility runs evaporative (water) cooling (0, "
        "0.25, 0.5 or 1); 1 minus mechanical_cooling_frac."),
    col("cooling_energy_demand_mwh", "double", "Annual facility energy demand for cooling in megawatt-hours (0 to "
        "94,608)."),
    col("cooling_water_demand_mgy", "double", "Annual facility water withdrawal for cooling in millions of "
        "gallons (0 to 43.5)."),
    col("cooling_water_consumption_mgy", "double", "Annual facility water consumed by cooling in millions of "
        "gallons (0 to 34.8)."),
    col("normalized_locational_cost", "double", "Locational cost score of the site, normalised to 0-1."),
    col("normalized_gravity_score", "double", "Market gravity score of the site, normalised to 0-1."),
    col("weighted_siting_score", "double", "Combined siting score of locational cost and market gravity, weighted "
        "by market_gravity_weight."),
    col("geom", "geometry", "Projected site footprint, a polygon of about 100,000 square metres (WGS84 "
        "longitude/latitude, reprojected from the published Albers Equal Area coordinates)."),
    col("h8", "uint64", H8_NOTE),
    col("h0", "int64", H0_NOTE),
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


def manifest(raw):
    """[(sha256, size, path)] from a staged MANIFEST.sha256."""
    txt = urllib.request.urlopen(f"{PUB}/{raw}/MANIFEST.sha256", timeout=60).read().decode()
    return [(s, int(n), f"{raw}/{p}") for s, n, p in (l.split(None, 2) for l in txt.splitlines() if l.strip())]


def raw_text(rec, accessed, raw, which, label):
    rows = [r for r in manifest(raw) if which(r[2])]
    files = "; ".join(f"`s3://{BUCKET}/{p}` ({n:,} bytes, sha256 `{s}`)" for s, n, p in rows)
    return (f"Provenance: {label}, downloaded from the MSD-LIVE record {rec} on {accessed[:10]} at "
            f"{accessed[11:16]} UTC and staged unchanged: {files}. Every file of the record is staged beside them, "
            f"with checksums in s3://{BUCKET}/{raw}/MANIFEST.sha256.")


def cols_of(dic, names):
    d = {c["name"]: c for c in dic}
    return [{"name": n, "type": d[n]["type"]} for n in names]


def tile_cols(dic, names):
    d = {c["name"]: c for c in dic}
    return [{"name": n, "type": TILE_TYPE.get(d[n]["type"], "Number")} for n in names if n != "geom"]


def collection(cid, title, desc, path, bbox, interval, dic, assets, keywords, pmkey, lic, providers, citation,
               doi, version, rec, about):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pm = assets[pmkey]
    lic_link = ({"rel": "license", "href": ODBL, "type": "text/html", "title": "Open Database License (ODbL) 1.0"}
                if lic == "ODbL-1.0" else
                {"rel": "license", "href": CCBY, "type": "text/html",
                 "title": "Creative Commons Attribution 4.0 International"})
    return {
        "type": "Collection", "stac_version": "1.1.0", "stac_extensions": EXT, "id": cid,
        "title": title, "description": desc, "keywords": keywords, "license": lic,
        "providers": providers, "sci:citation": citation, "sci:doi": doi.replace("https://doi.org/", ""),
        "version": version, "created": now, "updated": now,
        "extent": {"spatial": {"bbox": [bbox]}, "temporal": {"interval": [interval]}},
        "table:columns": dic,
        "links": [
            {"rel": "self", "href": f"{PUB}/{path}/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": PARENT, "type": "application/json"},
            lic_link,
            {"rel": "cite-as", "href": doi, "type": "text/html", "title": "Dataset DOI"},
            {"rel": "via", "href": rec, "type": "text/html", "title": "MSD-LIVE record (source of the staged files)"},
            *about,
            {"rel": "pmtiles", "href": pm["href"], "type": "application/vnd.pmtiles", "title": pm["title"],
             "pmtiles:layers": pm["vector:layers"]},
        ],
        "assets": assets,
    }


ATLAS_COMMON = (
    "The IM3 Open Source Data Center Atlas, from Pacific Northwest National Laboratory, locates existing data "
    "centers in the United States from OpenStreetMap, and adds each facility's state, county and footprint area. "
    "It is published as three layers that are not complete across one another: a facility may appear only as a "
    "point, or as a campus outline together with the buildings inside it. Campus and building polygons can "
    "overlap, and both are kept. Because OpenStreetMap is crowd-sourced, facilities nobody has mapped are absent, "
    "and later editions can drop facilities removed from OpenStreetMap. PNNL removed records whose attributes "
    "appeared to contain personal information. Edition: v2026.11.02 (published 2026-11-02)."
)
LAYERS = {
    "point": dict(
        title="IM3 data center atlas: facility points (128 facilities)",
        lead="Data centers mapped in OpenStreetMap as a single point: 128 facilities in 32 states, the District "
             "of Columbia and Puerto Rico, with name and operator where tagged. These points have no footprint, "
             "so sqft is empty.",
        flat_desc="One point per facility (128 rows, 128 distinct ids).",
        hex_desc="Each facility point resolved to one H3 cell at resolution 8 (about 0.74 square kilometres), "
                 "with its resolution 0 parent as the partition key. One row per facility: the 128 facilities fall "
                 "in 108 distinct cells, and facilities sharing a cell are not merged, so COUNT(DISTINCT id) "
                 "counts facilities.",
        kind="circle", bbox=[-123.092978, 18.417436, -66.10899, 47.958754], rows=128, ids=128),
    "building": dict(
        title="IM3 data center atlas: building footprints (1,634 buildings)",
        lead="Data center buildings mapped in OpenStreetMap as footprints: 1,636 rows for 1,634 buildings in 44 "
             "states and Puerto Rico, with name, operator and footprint area (130 to 1,338,261 square feet). "
             "Virginia (377), Texas (205) and Oregon (119) have the most.",
        flat_desc="One footprint polygon per building, plus one extra row for each of the 2 buildings that "
                  "straddle a county line (1,636 rows, 1,634 distinct ids).",
        hex_desc="Each footprint filled with H3 cells at resolution 8 (about 0.74 square kilometres), with the "
                 "resolution 0 parent as the partition key; a footprint smaller than a cell takes the one cell "
                 "it lies in, which is every building here (1,636 rows in 849 distinct cells). sqft is the whole building's area and is repeated on "
                 "every cell the building covers and on both county rows of a straddling building, so dedup "
                 "before summing: SELECT DISTINCT id, sqft first. Count buildings with COUNT(DISTINCT id).",
        kind="fill", bbox=[-123.034164, 18.446631, -66.051438, 48.757376], rows=1636, ids=1634),
    "campus": dict(
        title="IM3 data center atlas: campus outlines (249 campuses)",
        lead="Data center sites mapped in OpenStreetMap as an area that is not tagged as a building (campuses and "
             "site boundaries): 254 rows for 249 campuses in 32 states, with name, operator and area (9,139 to "
             "258,170,325 square feet). Virginia (38), Texas (33) and Arizona (21) have the most.",
        flat_desc="One outline per campus, plus one extra row for each of the 5 campuses that straddle a county "
                  "line (254 rows, 249 distinct ids).",
        hex_desc="Each campus outline filled with H3 cells at resolution 8 (about 0.74 square kilometres), with the "
                 "resolution 0 parent as the partition key; an outline smaller than a cell takes the one cell it "
                 "lies in. One row per (row, cell) pair: 366 rows in 340 distinct cells. sqft is the whole campus's area and is repeated on every "
                 "cell the campus covers and on both county rows of a straddling campus, so dedup before summing: "
                 "SELECT DISTINCT id, sqft first. Count campuses with COUNT(DISTINCT id).",
        kind="fill", bbox=[-123.079674, 29.410218, -74.063748, 48.147448], rows=254, ids=249),
}
STRADDLE = (
    "County lines: as upstream publishes it, a facility whose footprint crosses a county boundary appears once "
    "per county, with the same id and geometry and a different county; every other column is repeated. Count "
    "facilities with COUNT(DISTINCT id), and take one row per id before summing sqft."
)


def main(out):
    out = Path(out)
    objs = listing("pnnl-im3/")

    def asset(path, typ, title, desc, **kw):
        if path not in objs:
            raise SystemExit(f"missing object {path}")
        a = {"href": f"{PUB}/{path}", "type": typ, "title": title, "description": desc,
             "roles": ["data"], "created": objs[path][1], "file:size": objs[path][0]}
        a.update(kw)
        return a

    def hexa(path, title, desc, cols):
        parts = [k for k in objs if k.startswith(path + "/hex/h0=")]
        if not parts:
            raise SystemExit(f"no hex under {path}")
        return {"href": f"{PUB}/{path}/hex/h0=*/data_0.parquet", "type": "application/x-parquet",
                "title": title, "description": desc, "roles": ["data"],
                "created": max(objs[k][1] for k in parts), "h3:native_resolution": 8,
                "h3:parent_resolutions": [0], "table:columns": cols}

    for kind, L in LAYERS.items():
        name = f"atlas-{kind}"
        p = f"pnnl-im3/{name}"
        dic = atlas_cols(kind)
        flat = [c["name"] for c in dic if c["name"] not in ("h8", "h0")]
        assets = {
            f"{name}-parquet": asset(f"{p}.parquet", "application/vnd.apache.parquet",
                                     f"Data center {kind}s (GeoParquet)", L["flat_desc"],
                                     **{"table:columns": cols_of(dic, flat)}),
            f"{name}-pmtiles": asset(f"{p}.pmtiles", "application/vnd.pmtiles", f"Data center {kind}s (PMTiles)",
                                     f"Vector tiles of the {kind} layer for web maps; layer {name}.",
                                     **{"vector:layers": [name],
                                        # tippecanoe drops an all-null column, so the point tiles have no sqft
                                        "table:columns": tile_cols(dic, [c for c in flat
                                                                         if not (kind == "point" and c == "sqft")])}),
            f"{name}-hex": hexa(p, f"Data center {kind}s (H3 hex)", L["hex_desc"],
                                cols_of(dic, [c for c in flat if c != "geom"] + ["h8", "h0"])),
        }
        others = ", ".join(f"pnnl-im3-atlas-{k}" for k in LAYERS if k != kind)
        parts = [L["lead"], ATLAS_COMMON]
        if L["rows"] != L["ids"]:
            parts.append(STRADDLE)
        if kind == "point":
            parts.append("Point features were hexed to H3 resolution 8: each point is resolved to one cell of about "
                         "0.74 square kilometres, and points in the same cell are not merged.")
        parts += [f"Companion layers: the other two atlas layers are the collections {others}; projected future "
                  "sites are in pnnl-im3-projected.",
                  ATLAS_TERMS,
                  raw_text(ATLAS_REC, ATLAS_ACCESSED, ATLAS_RAW, lambda f: f.endswith((".gpkg", ".csv")),
                           f"the GeoPackage (layer \"{kind}\") of the IM3 Open Source Data Center Atlas v2026.11.02 "
                           "and its CSV")]
        doc = collection(f"pnnl-im3-{name}", L["title"], "\n\n".join(parts), p, L["bbox"],
                         ["2026-11-02T00:00:00Z", "2026-11-02T00:00:00Z"], dic, assets,
                         ["data centers", "infrastructure", "energy", "OpenStreetMap", "United States", "IM3",
                          "Pacific Northwest National Laboratory"],
                         f"{name}-pmtiles", "ODbL-1.0", ATLAS_PROVIDERS, ATLAS_CITATION, ATLAS_DOI, "v2026.11.02",
                         ATLAS_REC, [{"rel": "about", "href": "https://im3.pnnl.gov/datacenter-atlas",
                                      "type": "text/html", "title": "IM3 Data Center Atlas"}])
        sql = ("SELECT state_abb, count(DISTINCT id) AS facilities" + (", sum(sqft) AS sqft" if kind != "point" else "")
               + "\nFROM (SELECT DISTINCT ON (id) * FROM read_parquet('" + f"{PUB}/{p}.parquet" + "'))"
               "\nGROUP BY state_abb ORDER BY facilities DESC;")
        write(out / BUCKET / p, doc, readme(p, L["title"], name, L["kind"], L["lead"], sql, ATLAS_TERMS,
                                            raw_text(ATLAS_REC, ATLAS_ACCESSED, ATLAS_RAW,
                                                     lambda f: f.endswith(".gpkg"), "The GeoPackage")))

    # ------------------------------------------------------------ projections
    p = "pnnl-im3/projected"
    flat = [c["name"] for c in PROJ_COLS if c["name"] not in ("h8", "h0")]
    assets = {
        "projected-parquet": asset(f"{p}.parquet", "application/vnd.apache.parquet",
                                   "Projected data center sites, all scenarios (GeoParquet)",
                                   "One polygon per projected site per scenario: 16,645 rows across the 20 "
                                   "scenarios. Filter on growth_scenario and market_gravity_weight to get one "
                                   "scenario.", **{"table:columns": cols_of(PROJ_COLS, flat)}),
        "projected-pmtiles": asset(f"{p}.pmtiles", "application/vnd.pmtiles",
                                   "Projected data center sites, all scenarios (PMTiles)",
                                   "Vector tiles of the projected sites for web maps; layer projected. All 20 "
                                   "scenarios are in the one layer, overlapping where scenarios pick the same "
                                   "place, so filter on growth_scenario and market_gravity_weight to show one.",
                                   **{"vector:layers": ["projected"], "table:columns": tile_cols(PROJ_COLS, flat)}),
        "projected-hex": hexa(p, "Projected data center sites, all scenarios (H3 hex)",
                              "Each projected site (about 0.1 square kilometres) resolved to the one H3 cell at "
                              "resolution 8 (about 0.74 square kilometres) it lies in, with its resolution 0 parent "
                              "as the partition key. One row per site per scenario, so the 20 scenarios overlap: "
                              "filter on growth_scenario and market_gravity_weight before counting, and count sites "
                              "with COUNT(DISTINCT _cng_fid). Sites of one scenario that share a cell are not merged.",
                              cols_of(PROJ_COLS, [c for c in flat if c != "geom"] + ["h8", "h0"])),
    }
    desc = "\n\n".join([
        "Projected locations of new data centers in the contiguous United States through 2035, from Pacific "
        "Northwest National Laboratory's CERF-Data Centers siting model, for every combination of four demand "
        "growth scenarios and five market gravity weights (20 scenarios, 16,645 projected sites in all). The "
        "growth scenarios follow EPRI (2024): annual growth in data center electricity demand from 2023 of 3.71% "
        "(low, 222 sites per gravity weight), 5% (moderate, 328), 10% (high, 909) and 15% (higher, 1,870), across "
        "37 states. The market gravity weight (0, 25, 50, 75 or 100%) sets how much siting favours proximity to "
        "existing data center markets and population over locational cost; at 0% sites are chosen on cost alone. "
        "Locational cost depends on the facility's cooling type, electricity cost, taxes and other factors; "
        "facilities in water-stressed or hot, humid places are assumed to run mechanical rather than evaporative "
        "cooling for more of the year. Every site is modelled as a 36 MW facility on 1,000,000 square feet of land, "
        "so differences between sites are in cost, cooling, energy and water.",
        "Sites are placed only on land judged feasible from open data: away from airports, water, steep slopes, "
        "sinkholes, flood-risk areas, parks, protected areas (PAD-US GAP 1-3), national parks, wetlands, critical "
        "habitat, tribal (BIA) land, transport corridors, military land and developed land; within 2 km of a "
        "substation and of high-speed fibre service, 5 km of a municipal water supplier and 0.8 km of developed "
        "land. The model does not see proprietary factors such as local tax agreements, fibre routes or grid "
        "capacity agreements. Upstream describes the sites as regional representations of feasible locations for "
        "assessing grid and water stress, and advises against using individual sites or footprints for local "
        "planning.",
        "All 20 scenarios are combined in one table: select one with growth_scenario and market_gravity_weight, "
        "for example WHERE growth_scenario = 'high' AND market_gravity_weight = 50. The id column repeats across "
        "scenarios. Upstream publishes one GeoJSON per scenario in Albers Equal Area coordinates (ESRI:102003); "
        "they were merged and reprojected to WGS84 here. The H3 hex asset places each site in one resolution 8 "
        "cell, coarser than the site itself, matching the regional intent of the projections. Edition: v1.1 "
        "(published 2026-02-27), which added standalone National Park Service areas, critical habitat, wetland "
        "and BIA land exclusions and updated airport boundaries.",
        "Companion layers: existing data centers from the IM3 Open Source Data Center Atlas are in "
        "pnnl-im3-atlas-point, pnnl-im3-atlas-building and pnnl-im3-atlas-campus.",
        PROJ_TERMS,
        raw_text(PROJ_REC, PROJ_ACCESSED, PROJ_RAW, lambda f: f.endswith(".geojson"),
                 "the 20 scenario GeoJSON files of IM3 Projected US Data Center Locations v1.1"),
    ])
    doc = collection("pnnl-im3-projected",
                     "IM3 projected U.S. data center sites to 2035 (20 growth and market scenarios)", desc, p,
                     [-123.47836, 25.436568, -71.016744, 47.93813], ["2023-01-01T00:00:00Z", "2035-12-31T00:00:00Z"],
                     PROJ_COLS, assets,
                     ["data centers", "projections", "scenarios", "energy", "water", "siting", "United States",
                      "IM3", "Pacific Northwest National Laboratory"],
                     "projected-pmtiles", "CC-BY-4.0", PROJ_PROVIDERS, PROJ_CITATION, PROJ_DOI, "v1.1", PROJ_REC,
                     [{"rel": "about", "href": "https://im3.pnnl.gov/datacenter-atlas", "type": "text/html",
                       "title": "IM3 Data Center Atlas"}])
    sql = ("SELECT growth_scenario, market_gravity_weight, count(*) AS sites,\n"
           "       sum(cooling_water_consumption_mgy) AS water_mgy\n"
           f"FROM read_parquet('{PUB}/{p}.parquet')\nGROUP BY ALL ORDER BY ALL;")
    write(out / BUCKET / p, doc, readme(p, "IM3 projected U.S. data center sites to 2035", "projected", "fill",
                                        "16,645 projected data center sites across 20 demand growth and market "
                                        "gravity scenarios, one polygon per site per scenario.", sql, PROJ_TERMS,
                                        raw_text(PROJ_REC, PROJ_ACCESSED, PROJ_RAW,
                                                 lambda f: f.endswith(".geojson"), "The 20 scenario GeoJSON files"),
                                        filt=True))


def write(d, doc, text):
    d.mkdir(parents=True, exist_ok=True)
    (d / "stac-collection.json").write_text(json.dumps(doc, indent=2) + "\n")
    (d / "README.md").write_text(text)


def readme(p, title, layer, kind, summary, sql, terms, prov, filt=False):
    paint = ("'circle-radius': 4, 'circle-color': '#1D4ED8'" if kind == "circle"
             else "'fill-color': '#1D4ED8', 'fill-opacity': 0.5")
    flt = ("\n  filter: ['all', ['==', ['get', 'growth_scenario'], 'high'],\n"
           "                 ['==', ['get', 'market_gravity_weight'], 50]]," if filt else "")
    return f"""# {title}

{summary}

STAC: {PUB}/{p}/stac-collection.json

| File | Contents |
|---|---|
| `{p}.parquet` | GeoParquet |
| `{p}.pmtiles` | Vector tiles, layer `{layer}` |
| `{p}/hex/h0=*/data_0.parquet` | H3 resolution 8, partitioned by `h0` |

## DuckDB

```sql
INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;
{sql}
```

## MapLibre

```js
map.addSource('{layer}', {{ type: 'vector', url: 'pmtiles://{PUB}/{p}.pmtiles' }});
map.addLayer({{
  id: '{layer}', type: '{kind}', source: '{layer}',
  'source-layer': '{layer}',{flt}
  paint: {{ {paint} }}
}});
```

## Licence and citation

{terms}

{prov}
"""


if __name__ == "__main__":
    main(sys.argv[1])
