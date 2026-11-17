#!/usr/bin/env python3
"""Write the STAC collections and READMEs for the FracTracker data center layers (#931).

  gen_stac.py OUT_DIR

Writes OUT_DIR/fractracker/{data-centers,moratoriums}/{stac-collection.json,README.md}. Object
sizes and created times are read from the public bucket listing (#417); the staged-raw
fingerprints are MANIFEST.sha256 as written by the stage-raw and build jobs. Counts, ranges and
coded values below were measured on the published GeoParquet through the duckdb-geo server on
2026-11-16.

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
LANDING = "https://www.fractracker.org/data-centers/"
TERMS = "https://www.fractracker.org/terms-of-service/"
DC_SHEET = "https://docs.google.com/spreadsheets/d/1JJ6kcVo-NjlAYtznwHOki2DVl4WWV6lhy-eXhFCdKKU"
DICT_SHEET = "https://docs.google.com/spreadsheets/d/1KVab4niu8X_GGne3WyyH_CdTP9Bt4uJSe6iK0fu9C48"
MOR_SHEET = "https://docs.google.com/spreadsheets/d/1OLJ-EkkxLfX6l4dTBHsIdtn_zRSyOraS02vd3LMfbEI"
DC_ACCESSED = "2026-11-15T22:57:10Z"
MOR_ACCESSED = "2026-11-15T23:25:24Z"
DC_RAW = [  # raw/fractracker/MANIFEST.sha256
    ("90fbf86cf06e4f8d1918783d5e2a13c902c90ec73c415cbaa2a6d4b5d0cb77d4", 849560, "raw/fractracker/data-centers.csv"),
    ("bf3b1a4456374320989d0adc87f3eb9afa43596e732b5ca2435d765018ba897c", 1726439, "raw/fractracker/data-centers-workbook.xlsx"),
    ("a2186678c52987a70bee5fb9be66dff0a0fcb7f41aa949273be6dcf5be213590", 67597, "raw/fractracker/data-dictionary.xlsx"),
]
MOR_RAW = [  # raw/fractracker/moratoriums/MANIFEST.sha256 (Census files listed there too)
    ("ad30de9ec58a38652d5ced5bcdd098f41ed39ea342f2325739c7bf9486c2d6a2", 318319, "raw/fractracker/moratoriums/moratoriums.csv"),
    ("d363999b961b8e83cbd31526938317be081963067ab61b3c7f2844d90f6dc66a", 624542, "raw/fractracker/moratoriums/moratoriums-workbook.xlsx"),
]
CITATION = "Data provided by FracTracker Alliance (2026). Accessed via https://www.fractracker.org/data-centers/"
EXT = [
    "https://stac-extensions.github.io/table/v1.2.0/schema.json",
    "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
]
PROVIDERS = [
    {"name": "FracTracker Alliance", "roles": ["producer", "licensor"], "url": LANDING},
    {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor"],
     "url": "https://github.com/boettiger-lab/data-workflows"},
    {"name": "National Research Platform", "roles": ["host"], "url": "https://nationalresearchplatform.org"},
]
TERMS_TEXT = (
    "Licence: no open licence. FracTracker Alliance retains all rights in the data compilation. Its terms of use "
    "(the README tab of the data centers workbook, and its Terms of Service at " + TERMS + ") provide the data "
    "as is, without warranty; require that any use be consistent with and supportive of FracTracker's mission, "
    "\"to map, analyze, and communicate the risks of oil, gas, and petrochemical development to advance just "
    "energy alternatives that protect public health, natural resources, and the climate\", with FracTracker "
    "deciding whether a use fits that mission; and require public-facing materials to cite the source as: "
    + CITATION + " (with the year the data were accessed). FracTracker publishes the sheets as open downloads "
    "with no login, and this copy is hosted on the same terms."
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


def src(n):
    return col(f"info_source_{n}", "string", f"Documentation link {n} of up to 8 (news coverage, permits, "
               "public records) supporting the record, as entered by FracTracker.")


DC_COLS = [
    col("_cng_fid", "int64", "Row identifier added during conversion; one per facility record. Use "
        "COUNT(DISTINCT _cng_fid) to count facilities."),
    col("facility_name", "string", "Name of the data center project: the most commonly referenced public name, "
        "or the company or location when the project is unnamed. Names are not unique."),
    col("address", "string", "Street address of the facility. May be blank or approximate, such as an intersection."),
    col("city", "string", "City or municipality."),
    col("state", "string", "U.S. state, as its two-letter postal abbreviation (48 states)."),
    col("zip", "string", "ZIP, free text as entered by FracTracker."),
    col("county", "string", "County name, as entered by FracTracker (spelling is not standardised)."),
    col("lat", "double", "Latitude in decimal degrees, as entered by FracTracker; the point geometry is built "
        "from lat and long. Its accuracy is given by location_confidence."),
    col("long", "double", "Longitude in decimal degrees, as entered by FracTracker."),
    col("status", "string", "Project development stage. Values: Proposed, Pre-proposal, "
        "Approved/Permitted/Under construction, Operating, Expanding, Suspended, Cancelled.",
        ["Proposed", "Operating", "Approved/Permitted/Under construction", "Cancelled", "Suspended",
         "Expanding", "Pre-proposal"]),
    col("location_confidence", "string", "Confidence in the accuracy of the point location. Values: High=high confidence, "
        "Medium=medium confidence, Low=low confidence, high=High written in lower case (one record); 3 are blank.", ["High", "Medium", "Low", "high"]),
    col("purpose", "string", "Function of the facility, such as AI, cloud or colocation, as free text (filled for "
        "103 of 1,733 facilities)."),
    col("operator_name", "string", "Developer or operator, with names standardised by FracTracker (for example "
        "'Amazon' rather than 'AWS')."),
    col("tenant", "string", "Known tenant or tenants. Blank when unknown or when the operator is the user."),
    col("mw", "string", "Power capacity in megawatts, stored as text as entered by FracTracker (filled for 697 "
        "facilities). Estimates come from news reports, permits and comparable facilities; 1,000 MW = 1 GW. "
        "Cast before arithmetic: TRY_CAST(mw AS DOUBLE)."),
    col("sizerank", "string", "Size class by power capacity: Small (0-10 MW), Medium (11-50 MW), Large "
        "(51-99 MW), Hyperscale (100-999 MW), Mega campus (>1,000 MW), or Unknown. One record writes 'Mega Campus'.",
        ["Unknown", "Hyperscale (100-999 MW)", "Medium (11-50 MW)", "Mega campus (>1,000 MW)", "Small (0-10 MW)",
         "Large (51-99 MW)", "Mega Campus (>1,000 MW)"]),
    col("power_source", "string", "Energy source, from FracTracker's categories (Natural gas, Coal, Nuclear, "
        "Oil/Diesel, Hydroelectric, Wind, Solar, Geothermal, Biomass, Grid (unspecified mix), Hybrid (onsite and "
        "grid)); several may be listed, comma-separated. Blank when unknown (filled for 166 facilities)."),
    col("dedicated_power_plant", "string", "On-site or behind-the-meter power generation: Yes or No, often with "
        "the plant's name (for example 'Yes - Apollo Generating Station'). Free text."),
    col("number_of_generators", "string", "Number of backup generators, as text. Blank when unclear."),
    col("number_of_buildings", "string", "Number of structures, as text."),
    col("cooling_source", "string", "Cooling source. Values: Air=air cooled, Water=water cooled, Hybrid air/water=both. Blank when "
        "unknown.",
        ["Water", "Air", "Hybrid air/water"]),
    col("cooling_type", "string", "Cooling system: Closed loop, Open loop or Fans (two records write 'Closed "
        "Loop'). Blank when unknown.", ["Closed loop", "Open loop", "Closed Loop", "Fans"]),
    col("facility_size_sqft", "string", "Building footprint in square feet, summed over buildings where possible; "
        "text as entered."),
    col("property_size_acres", "int64", "Total land area of the property in acres (1 to 40,000)."),
    col("project_cost", "string", "Estimated project cost, free text as reported (for example '$1B')."),
    col("expected_date_online", "string", "Expected operation date, usually a year, as text."),
    col("community_pushback", "string", "Whether community opposition to the project is known. Values: Yes=opposition reported, "
        "yes=the same written in lower case (4 records), Unknown=none reported.", ["Unknown", "Yes", "yes"]),
    col("advocacy_information", "string", "Short factual description of community organising around the project."),
    col("resistance_status", "string", "Level of resistance: Unknown, Emerging Concern, Organized Advocacy or "
        "Institutional Support.", ["Organized Advocacy", "Emerging Concern", "Unknown", "Institutional Support"]),
    col("nda", "string", "Whether a nondisclosure agreement or limited transparency is reported: free text, "
        "often Yes or No with detail."),
    col("community_group_website_1", "string", "Website of a community group involved."),
    col("community_group_website_2", "string", "Website of a second community group involved."),
    col("petition_url", "string", "Link to a petition about the project."),
    col("other_info", "string", "Additional notes, including uncertainty in other fields."),
    col("information_source", "string", "Primary source of the record. Values: Media Monitoring=FracTracker's "
        "scans of media announcements, PEC=Piedmont Environmental Council (all such records are in Virginia), "
        "Sci4GA=Science for Georgia (all such records are in Georgia), Crowdsourced=listings submitted to "
        "FracTracker, FOIA/ public records request=public records requests, Other=other sources; PEC/WP and "
        "the comma-joined values combine two sources.",
        ["Media Monitoring", "PEC", "Sci4GA", "Crowdsourced", "Other", "Media Monitoring, Crowdsourced",
         "FOIA/ public records request", "PEC/WP", "Sci4GA, Crowdsourced", "PEC, Media Monitoring",
         "Other, Media Monitoring"]),
    *[src(n) for n in range(1, 9)],
    col("date_created", "date", "Date FracTracker created the record (2024-04-10 to 2026-10-27)."),
    col("date_updated", "date", "Date FracTracker last updated the record."),
    col("geom", "geometry", "Facility point (WGS84 longitude/latitude), built from long and lat."),
    col("h8", "uint64", H8_NOTE),
    col("h0", "int64", H0_NOTE),
]
DC_FLAT = [c["name"] for c in DC_COLS if c["name"] not in ("h8", "h0")]

UNMATCHED = [
    ("MI", "Caledonia Township (2 records), Garfield Township, Green Charter Township, Lyon Township, Porter "
     "Township, Sylvan Township, Tyrone Township, Ypsilanti Community Utilities Authority (YCUA)"),
    ("NJ", "Monroe Township, Washington Township"),
    ("NV", "Humboldt"),
    ("OH", "Jackson Township, Lake Township, Madison Township, Monroe Township, Plain Township, Scioto Township"),
    ("PA", "Gregg Township, Londonderry Township, Madison Township, Pine Creek Township, "
     "Smithfield Township, Warrington Township"),
    ("WI", "Waterloo Township"),
]

MOR_COLS = [
    col("_cng_fid", "int64", "Row identifier added during conversion; one per record. Use COUNT(DISTINCT _cng_fid) "
        "to count records."),
    col("jurisdiction", "string", "Jurisdiction that took the action, as named by FracTracker (for example "
        "'Anchorage', 'Loudoun County', 'Caledonia Township', 'State of Oregon')."),
    col("state", "string", "U.S. state, as its two-letter postal abbreviation (48 states)."),
    col("action", "string", "Type of local action. Values: Moratorium=a temporary pause on data center "
        "approvals, Ban=a prohibition, Zoning restriction=zoning rules limiting where or how data centers are "
        "built, Curative Amendment=a Pennsylvania procedure for challenging a zoning ordinance, Other=other "
        "actions.",
        ["Moratorium", "Zoning restriction", "Ban", "Curative Amendment", "Other"]),
    col("status", "string", "Status of the action as entered by FracTracker, not standardised: Enacted, active, "
        "Proposed, pending, In development, Adopted; not yet effective, expired, Expired, Failed, Retracted. "
        "Match case-insensitively: lower(status) = 'expired'.",
        ["Enacted", "Proposed", "active", "expired", "pending", "Failed", "In development", "Retracted",
         "Expired", "Adopted; not yet effective"]),
    col("date_enacted", "date", "Date the action was enacted or introduced (2019-01-01 to 2026-11-04; blank for "
        "104 records)."),
    col("duration", "string", "Length of a moratorium as stated, free text (for example '1 year', '180 days', "
        "'Through December 31, 2026')."),
    col("expiration_date", "date", "Date the action expires (2024-11-19 to 2031-08-31; filled for 403 records)."),
    col("source_link_1", "string", "Link to a source documenting the action."),
    col("source_link_2", "string", "Link to a second source."),
    col("source_link_3", "string", "Link to a third source."),
    col("notes", "string", "FracTracker's notes on the action."),
    col("geo_level", "string", "Kind of Census 2024 geography the jurisdiction was matched to: state, county, "
        "place (an incorporated city, town, village or borough), county_subdivision (a township or New England, "
        "New York or Wisconsin town), or aiannh (an American Indian area). Blank for the 25 records with no "
        "boundary.", ["place", "county", "county_subdivision", "state", "aiannh"]),
    col("geoid", "string", "Census 2024 GEOID of the matched geography (state 2 digits, county 5, place 7, "
        "county subdivision 10), or the 4-digit AIANNH code for an American Indian area. Joins to the "
        "census-2024 collections on GEOID."),
    col("census_name", "string", "Census 2024 name of the matched geography (for example 'Caledonia charter "
        "township')."),
    col("geom", "geometry", "Boundary of the matched jurisdiction from Census TIGER/Line 2024 (WGS84 "
        "longitude/latitude); null for the 25 records with no boundary."),
    col("h8", "uint64", H8_NOTE),
    col("h0", "int64", H0_NOTE),
]
MOR_FLAT = [c["name"] for c in MOR_COLS if c["name"] not in ("h8", "h0")]


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


def raw_text(accessed, raw, what):
    rows = "; ".join(f"`s3://{BUCKET}/{p}` ({n:,} bytes, sha256 `{s}`)" for s, n, p in raw)
    return (f"Provenance: FracTracker updates the sheet continuously and publishes no edition label, so this layer is "
            f"a snapshot. {what} was downloaded on {accessed[:10]} at {accessed[11:16]} UTC and staged unchanged: "
            f"{rows}.")


def cols_of(dic, names):
    d = {c["name"]: c for c in dic}
    return [{"name": n, "type": d[n]["type"]} for n in names]


def tile_cols(dic, names):
    d = {c["name"]: c for c in dic}
    return [{"name": n, "type": TILE_TYPE.get(d[n]["type"], "Number")} for n in names if n != "geom"]


def links(path, pm, extra):
    return [
        {"rel": "self", "href": f"{PUB}/{path}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": ROOT, "type": "application/json"},
        {"rel": "parent", "href": PARENT, "type": "application/json"},
        {"rel": "license", "href": TERMS, "type": "text/html", "title": "FracTracker Alliance Terms of Service"},
        {"rel": "about", "href": LANDING, "type": "text/html", "title": "FracTracker Alliance: U.S. Data Centers Tracker"},
        *extra,
        {"rel": "pmtiles", "href": pm["href"], "type": "application/vnd.pmtiles", "title": pm["title"],
         "pmtiles:layers": pm["vector:layers"]},
    ]


def collection(cid, title, desc, path, bbox, interval, dic, assets, keywords, pmkey, extra):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "type": "Collection", "stac_version": "1.0.0", "stac_extensions": EXT, "id": cid,
        "title": title, "description": desc, "keywords": keywords, "license": "other",
        "providers": PROVIDERS, "sci:citation": CITATION, "created": now, "updated": now,
        "extent": {"spatial": {"bbox": [bbox]}, "temporal": {"interval": [interval]}},
        "table:columns": dic, "links": links(path, assets[pmkey], extra), "assets": assets,
    }


def main(out):
    out = Path(out)
    objs = listing("fractracker/")

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

    # ------------------------------------------------------------ data centers
    p = "fractracker/data-centers"
    da = {
        "data-centers-parquet": asset(f"{p}.parquet", "application/vnd.apache.parquet",
            "Data centers (GeoParquet)", "One point per facility (1,733 facilities).",
            **{"table:columns": cols_of(DC_COLS, DC_FLAT)}),
        "data-centers-pmtiles": asset(f"{p}.pmtiles", "application/vnd.pmtiles",
            "Data centers (PMTiles)", "Vector tiles of the facility points for web maps; layer data-centers.",
            **{"vector:layers": ["data-centers"], "table:columns": tile_cols(DC_COLS, DC_FLAT)}),
        "data-centers-hex": hexa(p, "Data centers (H3 hex)",
            "Each facility point resolved to one H3 cell at resolution 8 (about 0.74 square kilometres), with its "
            "resolution 0 parent as the partition key. One row per facility: 1,733 facilities fall in 1,469 distinct "
            "cells, and facilities sharing a cell are not merged. Each facility appears exactly once, so "
            "COUNT(DISTINCT _cng_fid) counts facilities and per-facility values are not repeated.",
            cols_of(DC_COLS, [c for c in DC_FLAT if c != "geom"] + ["h8", "h0"])),
    }
    desc = (
        "A snapshot of FracTracker's sheet taken 15 November 2026. FracTracker updates the sheet continuously, so records "
        "and statuses may have changed since.\n\n"
        "FracTracker Alliance's U.S. Data Centers Tracker: 1,733 existing, permitted and proposed data centers "
        "in 48 states, with each facility's development status, operator and tenant, power capacity and size "
        "class, power and cooling sources, and the community response to the project (pushback, organising, "
        "nondisclosure agreements, petitions). FracTracker finds sites mainly by monitoring media announcements, "
        "supplemented by public records, permits, parcel data, Freedom of Information Act requests and "
        "crowdsourced listings. Its focus is proposals, the sites relevant for advocacy; existing data centers "
        "are being added gradually, so the operating facilities here are not a complete inventory. Status on the "
        "snapshot date: 779 proposed, 14 pre-proposal, 182 approved, permitted or under construction, 536 "
        "operating, 70 expanding, 72 suspended and 80 cancelled.\n\n"
        "Every facility has a point location; location_confidence rates it High (1,349), Medium (332) or Low "
        "(49). Field definitions follow FracTracker's data dictionary (" + DICT_SHEET + "). Values are as "
        "entered upstream: several numeric fields (mw, facility_size_sqft, number_of_buildings, "
        "number_of_generators, expected_date_online) are text, and a few coded values differ only in case. "
        "The H3 hex asset places each facility in one resolution 8 cell.\n\n"
        "Companion layer: data center moratoriums, bans and zoning restrictions from the same tracker are in "
        "the collection fractracker-moratoriums.\n\n"
        + TERMS_TEXT + "\n\n"
        + raw_text(DC_ACCESSED, DC_RAW, "The \"FracTracker Data Centers\" tab of the public sheet (" + DC_SHEET
                   + "), with the whole workbook (including its README tab) and the data dictionary,")
    )
    dc = collection("fractracker-data-centers", "FracTracker U.S. data centers (1,733 facilities)", desc, p,
                    [-158.02138, 21.480452, -67.01703, 70.18478],
                    ["2024-04-10T00:00:00Z", "2026-11-15T00:00:00Z"], DC_COLS, da,
                    ["data centers", "energy", "infrastructure", "community advocacy", "United States",
                     "FracTracker Alliance"], "data-centers-pmtiles",
                    [{"rel": "via", "href": DC_SHEET, "type": "text/html",
                      "title": "FracTracker data centers sheet (source, with README and terms)"},
                     {"rel": "describedby", "href": DICT_SHEET, "type": "text/html",
                      "title": "FracTracker data centers data dictionary"}])
    write(out / p, dc, readme(p, "FracTracker U.S. data centers", "data-centers", "circle",
                              "1,733 existing, permitted and proposed U.S. data centers, one point per facility, "
                              "with status, operator, power, cooling and community response.",
                              "SELECT status, count(*) AS n, sum(TRY_CAST(mw AS DOUBLE)) AS mw\n"
                              f"FROM read_parquet('{PUB}/{p}.parquet')\nGROUP BY status ORDER BY n DESC;",
                              raw_text(DC_ACCESSED, DC_RAW, "The data centers tab")))

    # ------------------------------------------------------------ moratoriums
    p = "fractracker/moratoriums"
    ma = {
        "moratoriums-parquet": asset(f"{p}.parquet", "application/vnd.apache.parquet",
            "Moratoriums and local actions (GeoParquet)",
            "One row per record (841), carrying its jurisdiction's boundary; 25 records have no boundary.",
            **{"table:columns": cols_of(MOR_COLS, MOR_FLAT)}),
        "moratoriums-pmtiles": asset(f"{p}.pmtiles", "application/vnd.pmtiles",
            "Moratoriums and local actions (PMTiles)",
            "Vector tiles of the jurisdiction boundaries for web maps; layer moratoriums. Records without a "
            "boundary are not in the tiles.",
            **{"vector:layers": ["moratoriums"], "table:columns": tile_cols(MOR_COLS, MOR_FLAT)}),
        "moratoriums-hex": hexa(p, "Moratoriums and local actions (H3 hex)",
            "Each jurisdiction boundary filled with H3 cells at resolution 8 (about 0.74 square kilometres), with "
            "the resolution 0 parent as the partition key: one row per (record, cell) pair, 5,062,361 rows for the "
            "816 records with a boundary (the 18 statewide records alone cover most of them). Every column is "
            "repeated on every cell a jurisdiction covers, so count records with COUNT(DISTINCT _cng_fid), not "
            "COUNT(*). Jurisdictions overlap (a state, its counties and its towns can all have records), so one "
            "cell can carry several records. The 25 records with no boundary have no hex cell and are absent from the "
            "hex.",
            cols_of(MOR_COLS, [c for c in MOR_FLAT if c != "geom"] + ["h8", "h0"])),
    }
    unmatched = "; ".join(f"{st}: {names}" for st, names in UNMATCHED)
    desc = (
        "A snapshot of FracTracker's sheet taken 15 November 2026. FracTracker updates the sheet continuously, so records "
        "and statuses may have changed since.\n\n"
        "FracTracker Alliance's list of local data center moratoriums, bans and zoning restrictions: 841 records "
        "in 48 states (571 moratoriums, 149 zoning restrictions, 86 bans, 32 Pennsylvania curative amendments "
        "and 3 other actions), each with its status, enactment and expiration dates, duration, sources and notes. "
        "Status on the snapshot date: 659 enacted, 45 active, 46 proposed, 26 pending, 8 in development, 1 "
        "adopted but not yet effective, 28 expired, 22 failed and 6 retracted. FracTracker's sheet names each "
        "jurisdiction but carries no geometry. FracTracker compiles the list from news reports and government "
        "records, so it is not an exhaustive record of local action: for scale, Grounded Compute's moratorium "
        "tracker (https://groundedcompute.com/us/moratoriums) counted at least 799 local pauses in force and 71 "
        "bans on 31 October 2026.\n\n"
        "Boundaries: each record was matched by name and state to a U.S. Census 2024 geography and takes that "
        "geography's TIGER/Line 2024 boundary: 18 states, 300 counties, 327 incorporated places, 167 county "
        "subdivisions (townships and New England, New York and Wisconsin towns) and 4 American Indian areas "
        "(Fort Peck, Eastern Cherokee, and the Cherokee and Seminole Oklahoma Tribal Statistical Areas). "
        "Townships that share a name within a state were told apart by the county named in the record's notes "
        "or sources. The 25 records that could not be matched to one geography keep every attribute and a null "
        "geometry: " + unmatched + ". geo_level, geoid and census_name record the match, so a record can be "
        "checked or joined to the census-2024 collections. The boundary is the jurisdiction's whole area; an "
        "action can apply to only part of it (a zoning district, for instance), which the notes describe. "
        "Records overlap: one place can have several records, and a state, its counties and its towns can each "
        "have their own. The H3 hex asset fills each boundary at resolution 8.\n\n"
        "Companion layer: the data centers themselves are in the collection fractracker-data-centers.\n\n"
        + TERMS_TEXT + " The moratorium workbook carries no terms of its own; FracTracker's Terms of Service and "
        "the terms published with its Data Centers Tracker are applied to it here.\n\n"
        + raw_text(MOR_ACCESSED, MOR_RAW, "The \"Live Data\" tab of the public sheet (" + MOR_SHEET + ") and the "
                   "whole workbook")
        + " The Census 2024 Gazetteer and TIGER/Line files used for matching are staged beside them, listed with "
        "checksums in raw/fractracker/moratoriums/MANIFEST.sha256."
    )
    mo = collection("fractracker-moratoriums",
                    "FracTracker data center moratoriums and local actions (841 records in 48 states)", desc, p,
                    [-150.424163, 25.837048, -66.885444, 61.484033],
                    ["2019-01-01T00:00:00Z", "2026-11-15T00:00:00Z"], MOR_COLS, ma,
                    ["data centers", "moratoriums", "zoning", "local government", "community advocacy",
                     "United States", "FracTracker Alliance"], "moratoriums-pmtiles",
                    [{"rel": "via", "href": MOR_SHEET, "type": "text/html",
                      "title": "FracTracker data center moratoriums sheet (source)"},
                     {"rel": "related", "href": "https://www2.census.gov/geo/tiger/TIGER2024/", "type": "text/html",
                      "title": "U.S. Census TIGER/Line 2024 (source of boundaries)"}])
    write(out / p, mo, readme(p, "FracTracker data center moratoriums and local actions", "moratoriums", "fill",
                              "841 local data center moratoriums, bans and zoning restrictions, each drawn as its "
                              "jurisdiction's Census 2024 boundary (25 records have none).",
                              "SELECT state, action, count(*) AS n\n"
                              f"FROM read_parquet('{PUB}/{p}.parquet')\n"
                              "WHERE lower(status) IN ('enacted', 'active')\nGROUP BY ALL ORDER BY n DESC;",
                              raw_text(MOR_ACCESSED, MOR_RAW, "The Live Data tab")))


def write(d, doc, text):
    d.mkdir(parents=True, exist_ok=True)
    (d / "stac-collection.json").write_text(json.dumps(doc, indent=2) + "\n")
    (d / "README.md").write_text(text)


def readme(p, title, layer, kind, summary, sql, prov):
    paint = ("'circle-radius': 4, 'circle-color': '#C2410C'" if kind == "circle"
             else "'fill-color': '#C2410C', 'fill-opacity': 0.4")
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
  'source-layer': '{layer}',
  paint: {{ {paint} }}
}});
```

## Licence and citation

{TERMS_TEXT}

Cite as: {CITATION}

{prov}
"""


if __name__ == "__main__":
    main(sys.argv[1])
