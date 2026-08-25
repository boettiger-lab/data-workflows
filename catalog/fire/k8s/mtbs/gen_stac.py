#!/usr/bin/env python3
"""Emit the three MTBS collections, the patched public-fire bucket collection and the patched
bucket README to /tmp for rclone upload (AGENTS.md Hard Boundary 1 — this repo never contains
STAC JSON or README files).

Three collections:

  mtbs-perimeters-1984-2024        vector, one polygon per mapped fire, 1984-2024, national
  mtbs-severity-1984-2024-conus    raster, annual thematic burn severity, 39 years
  mtbs-severity-1984-2024-ak       raster, annual thematic burn severity, 36 years

Severity is split by domain rather than mosaicked nationally because MTBS ships CONUS, Alaska
and Hawaii in different Albers projections; one national 30 m grid would be ~86 gigapixels per
year. Every collection carries `h8`, so they still join cell for cell to each other, to
`whp-2023-*` in this bucket and to `roadless-areas-2001`.

The bucket collection and README are FETCHED and PATCHED rather than rewritten, so fields this
script does not model survive.
"""
import json
import urllib.request

BUCKET = "public-fire"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"

LANDING = "https://www.mtbs.gov/"
PAPER = "https://doi.org/10.1186/s42408-020-00076-y"
SB_PERIMS = "https://www.sciencebase.gov/catalog/item/5e7229b8e4b01d509268afba"
SB_MOSAICS = "https://www.sciencebase.gov/catalog/item/5e91dee782ce172707f02cdd"

# Access date: when the raw was pulled from ScienceBase and staged to raw/mtbs/. Unrecoverable
# after the fact -- publishers overwrite in place -- so it is recorded here and in sci:citation
# (#417).
ACCESSED = "2026-08-21"

# ── Editions, exactly as upstream labels them. Never synthesised from a temporal extent, a
# ── product-line name or a file mtime (#417).
ED_PERIMS = "Burned Areas Boundaries, version 12.0, April 2025"
ED_MOSAICS = ("Thematic Burn Severity Mosaics, version 9.0 (August 2024) for 1984-2022 and "
              "version 12.0 (April 2025) for 2023-2024")

# ══════════════════════════════════════════════════════════════════════════════════════════
# MEASURED VALUES -- filled in from the completed builds, never estimated. Everything here is
# read back off the published artifacts; see BUILD.md for the queries.
# ══════════════════════════════════════════════════════════════════════════════════════════
MEASURED = {
    "perimeters": {
        "features": 30730,      # COUNT(*) on the flat parquet
        "event_ids": 30730,     # COUNT(DISTINCT Event_ID)
        "hex_rows": 57552314,   # COUNT(*) on the hex
        "hex_cells": 45128351,  # COUNT(DISTINCT h10)
        "h0_count": 10,
        "acres": 215921856,     # SUM over DISTINCT (_cng_fid, BurnBndAc)
        "bbox": [-166.188, 17.947, -65.338, 70.159],
        "ig_first": "1984-01-26",
        "ig_last": "2024-12-17",
        "raw_size": 374092911,
        "raw_md5": "65278fcb893f94cd0eaf66d966ee7125",   # recomputed from the staged object
    },
    "conus": {"hex_rows": None, "frac_rows": None, "h0_count": 6, "bbox": None,
              "cells_burned": None},
    # Alaska, read back 2026-08-24 off the completed `mode` hex through the duckdb-geo MCP.
    # h0_count is 1 and not 3: MTBS Alaska fires fall entirely inside base cell
    # 576707042908045311, which the measured bbox below confirms (see BUILD.md).
    "ak": {"hex_rows": 12270403,     # COUNT(*) on hex/
           "frac_rows": 30679520,    # COUNT(*) on hex-fractions/ (incl. the code-0 rows)
           "h0_count": 1,
           "bbox": [-166.191, 56.730, -140.157, 70.159],   # h3_cell_to_lng/lat over hex/
           "cells_burned": 11429727},                      # COUNT(DISTINCT h10) on hex/
}


def num(v, fallback="see the asset"):
    return f"{v:,}" if isinstance(v, int) else fallback


# ── Severity class codes and the published palette, both transcribed from the source rasters
# ── rather than from documentation or memory (#294). The codes come from the FGDC attribute
# ── domain shipped with each mosaic; the colours are the GeoTIFF's own colour table, which is
# ── identical in the CONUS and Alaska rasters.
CLASSES = [
    (1, "Unburned to Low",
     "Unburned, or burned at a severity too low to separate from unburned.", "006400"),
    (2, "Low", "Low burn severity.", "7FFFD4"),
    (3, "Moderate", "Moderate burn severity.", "FFFF00"),
    (4, "High", "High burn severity.", "FF0000"),
    (5, "Increased Greenness",
     "Increased greenness / increased post-fire vegetation response. Not a burn severity level.",
     "7FFF00"),
    (6, "Non-Processing Area Mask",
     "Area excluded from severity mapping (cloud, shadow, missing imagery). Not a burn severity "
     "level.", "FFFFFF"),
]
CLASS_LIST = ", ".join(f"{v}={n}" for v, n, _, _ in CLASSES)
CLASS_VALUES = [v for v, _, _, _ in CLASSES]

# ── Code 0 is REAL in two of the three asset kinds, and omitting it broke the STAC's own
# ── consistency check. The source rasters are mostly code 0 -- it is the background outside any
# ── mapped fire, declared as `nodata` in raster:bands -- so the COG carries it. The `fractions`
# ── reducer keeps it as an explicit category: measured on the completed Alaska build,
# ── hex-fractions/ holds 1,376,671 code-0 rows carrying 5.53% of the total `frac` mass, and that
# ── is exactly what makes every one of the 12,270,403 (year, cell) pairs sum to 1.0 -- `frac` is a
# ── share of the WHOLE cell, not of its burned part. Only `mode` genuinely excludes it (verified:
# ── the Alaska hex holds 1-6 and no 0), because a majority vote drops no-data outright.
# ──
# ── So: COG and fractions declare 0-6, `mode` declares 1-6. `values` must match what each asset
# ── actually contains -- verify-stac.py both checks values against the ingested DISTINCT and
# ── cross-checks that the hex codes are a subset of the COG's classification:classes.
CLASSES_WITH_BACKGROUND = [
    (0, "Background / Not Mapped",
     "Ground that is not mapped burned area -- outside any MTBS fire perimeter, or source "
     "no-data. This is the raster's no-data value and the large majority of every source mosaic. "
     "In the fractional-coverage asset it is the share of the cell lying outside any mapped fire, "
     "which is what makes each cell's shares sum to 1. It is absent from the dominant-class "
     "asset, where no-data is dropped. Not a severity level: exclude it from every severity "
     "denominator.",
     "000000"),
] + CLASSES
CLASS_LIST_FRACTIONS = ", ".join(f"{v}={n}" for v, n, _, _ in CLASSES_WITH_BACKGROUND)
CLASS_VALUES_FRACTIONS = [v for v, _, _, _ in CLASSES_WITH_BACKGROUND]

# Years actually built, per domain. CONUS is 1984-2024 and Alaska 1984-2023, each less the
# years whose source object is broken upstream (see MISSING_NOTE).
CONUS_YEARS = [y for y in range(1984, 2025) if y not in (2004, 2017)]
AK_YEARS = [y for y in range(1984, 2024) if y not in (1987, 1995, 2001, 2013)]
MISSING = {"conus": [2004, 2017], "ak": [1987, 1995, 2001, 2013]}

# ══════════════════════════════════════════════════════════════════════════════════════════
# Shared prose. These strings are user-facing copy: the geo-agent quotes them nearly verbatim
# into answers, so they read as product copy, carry no issue numbers, and express constraints
# as short SQL rather than as imperatives.
# ══════════════════════════════════════════════════════════════════════════════════════════

NOT_A_CENSUS = (
    "**This is not a complete fire census, and a count of fires here is not a count of fires.** "
    "MTBS maps only fires above a size threshold: 1,000 acres in the western United States and "
    "500 acres in the east. Smaller fires are absent by design, not by omission, and they are the "
    "large majority of ignitions. For ignition counts and small-fire statistics use a fire "
    "occurrence database rather than this collection."
)

REBURN = (
    "**The same ground burns more than once, and that is signal rather than duplication.** Over "
    "four decades a great deal of land in the fire-prone West has burned two, three or more "
    "times. Any total acreage therefore has to say which of two different quantities it means, "
    "and the two differ substantially:\n\n"
    "```sql\n"
    "-- unique ground: area that burned at least once, each place counted once\n"
    "SELECT COUNT(DISTINCT h10) FROM read_parquet('...');\n"
    "-- fire-years: each (place, year) pair counted separately, so a reburn counts twice\n"
    "SELECT COUNT(DISTINCT (h10, year)) FROM read_parquet('...');\n"
    "-- how often each place burned, and where reburns are\n"
    "SELECT h10, COUNT(DISTINCT year) AS times_burned\n"
    "FROM read_parquet('...') GROUP BY h10 HAVING times_burned > 1;\n"
    "```\n\n"
    "Measured on this release: 45,128,351 resolution 10 cells burned at least once, against "
    "57,552,314 (fire, cell) pairs — 27.5 percent more fire-years than unique ground. "
    "8,365,073 cells burned more than once and the most-burned cell burned 19 times. "
    "Deduplicating across years to make a total \"clean\" destroys that record, which for many "
    "questions is the interesting part."
)

SEV_DENOM = (
    "**Codes 5 and 6 are not severity levels and belong outside any severity denominator, and in "
    "the fractional-coverage asset neither does code 0.** Code 5 is increased post-fire greenness; "
    "code 6 is area the program excluded from mapping because of cloud, shadow or missing "
    "imagery; code 0, which appears only in the fractional-coverage asset, is the part of a cell "
    "that is not mapped burned ground at all and typically carries several percent of the total "
    "coverage. A \"share burned at high severity\" figure that leaves any of them in the "
    "denominator is diluted by ground that was never assigned a severity at all — which is why "
    "the query below names the classes it wants rather than dividing by a bare `SUM(frac)`:\n\n"
    "```sql\n"
    "-- share of burned area at high severity, codes 1-4 as the denominator\n"
    "SELECT SUM(frac) FILTER (WHERE severity = 4) / SUM(frac) FILTER (WHERE severity BETWEEN 1 AND 4)\n"
    "FROM read_parquet('...');\n"
    "```"
)

MODE_VS_FRACTIONS = (
    "**Two hex assets, and the choice between them changes the answer.** The `mode` asset gives "
    "each cell its single dominant severity class. The `fractions` asset gives, for every cell, "
    "the share of the cell in each class. Use `mode` for a map of dominant severity; use "
    "`fractions` for any statistic about how much area burned at a given severity. A cell that is "
    "40 percent high severity and 60 percent moderate becomes entirely moderate under `mode`, so "
    "a share computed from `mode` alone loses that 40 percent."
)

CLAMP_NOTE = (
    "**One source raster carried 23 undefined pixel values, and they were removed.** "
    "`mtbs_CONUS_2005.tif` holds 23 pixels — out of 12.7 billion — with values outside the "
    "published class list, in the range 32 to 124. Nearest-neighbour resampling cannot invent "
    "values, so these are an upstream defect rather than something this processing introduced. "
    "They are set to no-data here, because a code the class list does not define is not a severity "
    "observation. Every other year is clean, and the effect on any 2005 statistic is far below "
    "rounding: 23 pixels is two thousandths of a hectare in a year that burned 21.7 million pixels "
    "at a severity level."
)

AREA_TRUTH = (
    "**Area truth comes from the source grid, not from pixel counts on the published COG.** The "
    "source is an equal-area Albers grid, so counting its pixels measures area. The COG published "
    "here is geographic (EPSG:4326) and therefore is not equal-area, so counting its pixels does "
    "not. H3 cells at a fixed resolution are near-equal-area, so cell counts and fractional "
    "coverage on the hex assets are a valid area proxy."
)


def missing_note(dom):
    yrs = MISSING[dom]
    dom_name = "CONUS" if dom == "conus" else "Alaska"
    last = CONUS_YEARS[-1] if dom == "conus" else AK_YEARS[-1]
    return (
        f"**Missing years: {', '.join(str(y) for y in yrs)}.** The published source archive lists "
        f"a {dom_name} mosaic for each of these years, with a size and a checksum, but the stored "
        f"objects could not be retrieved — every request returns a not-found response, and no "
        f"alternative direct-download route for the annual mosaics exists. These years are absent "
        f"from this collection rather than empty. A time series across "
        f"1984 to {last} must skip them, and a query filtering on one of them returns no "
        f"rows: that means the severity mapping is unavailable, not that nothing burned. "
        f"The perimeters collection does cover all 41 years, so whether a place burned in a "
        f"missing year remains answerable there; only the severity classes are gone."
    )


H3_DESC = {
    10: "H3 cell identifier at resolution 10.",
    9: "H3 cell identifier at resolution 9.",
    8: ("H3 cell identifier at resolution 8. This is the shared join key across the catalog — "
        "use it to join this layer to the wildfire hazard potential collections in this bucket "
        "and to inventoried roadless areas."),
    0: ("H3 cell identifier at resolution 0, used as the partition key for hive-partitioned "
        "reads."),
}
YEAR_DESC = ("Calendar year of the annual severity composite, used as a partition key. Filter one "
             "year with WHERE year = 2020. A year absent from this column had no retrievable "
             "source mosaic and is listed in the collection description.")


def h3_cols(native, parents):
    return [{"name": f"h{r}", "type": "int64" if r == 0 else "uint64",
             "description": H3_DESC[r]} for r in [native] + parents]


# ══════════════════════════════════════════════════════════════════════════════════════════
# Perimeters
# ══════════════════════════════════════════════════════════════════════════════════════════
PERIM = "mtbs-perimeters-1984-2024"

# Single authority for the perimeter schema: written identically to the flat GeoParquet and the
# hex (minus geometry), and in lean form to PMTiles. Definitions are transcribed from the FGDC
# entity/attribute section published with the source, not paraphrased.
# (name, type, description, values)
PERIM_COLUMNS = [
    ("_cng_fid", "int64",
     "Row-unique feature identifier assigned during conversion. Use it for feature counts and "
     "for deduplicating before any total.", None),
    ("OGC_FID", "int64",
     "Sequential feature number carried over from the source shapefile. Present for traceability; "
     "use _cng_fid or Event_ID as the feature key.", None),
    ("Event_ID", "string",
     "MTBS event identifier for the fire, unique per mapped fire and stable across MTBS "
     "products. Measured on this release: 30,730 fires, 30,730 distinct values, none blank, so it "
     "is one row per fire on the flat table. Use it to join to other MTBS data or to group the "
     "perimeter with its severity mapping.", None),
    ("irwinID", "string",
     "IRWIN (Integrated Reporting of Wildland-Fire Information) incident identifier, where the "
     "fire could be matched to an IRWIN record. Blank where no match exists.", None),
    ("Incid_Name", "string",
     "Fire name as recorded in the source fire occurrence databases. UNNAMED where the fire "
     "could not be identified.", None),
    ("Incid_Type", "string",
     "Documented type of fire. Values: Wildfire, Prescribed Fire, Wildland Fire Use, Unknown. "
     "Prescribed fire and wildland fire use are intentional management burning, so a total across "
     "all rows mixes them with unplanned wildfire and answers neither question on its own. Of the "
     "30,730 mapped fires, 16,960 are wildfire, 8,870 prescribed fire, 211 wildland fire use and "
     "4,689 unknown.",
     ["Wildfire", "Prescribed Fire", "Wildland Fire Use", "Unknown"]),
    ("Map_ID", "int64", "Internal MTBS mapping identifier for the assessment.", None),
    ("Map_Prog", "string",
     "Mapping program or protocol under which the fire was mapped. Values: "
     "MTBS=Monitoring Trends in Burn Severity. Every fire in this release carries the same "
     "value, so the column does not discriminate between fires.", ["MTBS"]),
    ("Asmnt_Type", "string",
     "Assessment type, which controls what the severity classes mean for this fire. Initial "
     "assessments use imagery from immediately after the fire and suit grassland and low-biomass "
     "systems; extended assessments use imagery from the following growing season and suit "
     "forests. SS marks a single-scene assessment. Values: Initial, Initial (SS), Extended, "
     "Extended (SS).",
     ["Initial", "Initial (SS)", "Extended", "Extended (SS)"]),
    ("BurnBndAc", "int64",
     "Acres inside the mapped fire perimeter, as published for the whole fire.", None),
    ("BurnBndLat", "string",
     "Latitude of the centroid of the mapped fire perimeter, stored as text in the source. Cast "
     "it before comparing numerically: CAST(BurnBndLat AS DOUBLE).", None),
    ("BurnBndLon", "string",
     "Longitude of the centroid of the mapped fire perimeter, stored as text in the source. Cast "
     "it before comparing numerically: CAST(BurnBndLon AS DOUBLE).", None),
    ("Ig_Date", "date",
     "Fire ignition date from the source fire occurrence databases. Extract the fire year with "
     "EXTRACT(year FROM Ig_Date).", None),
    ("Pre_ID", "string", "Identifier of the pre-fire Landsat or Sentinel scene used.", None),
    ("Post_ID", "string", "Identifier of the post-fire Landsat or Sentinel scene used.", None),
    ("Perim_ID", "string",
     "Identifier of the Landsat or Sentinel scene used to help delineate the perimeter of an "
     "extended assessment. Populated only for some fires.", None),
    ("dNBR_offst", "int64",
     "Mean differenced Normalized Burn Ratio sampled from unburned area outside the perimeter, "
     "used as the offset for this fire's severity thresholds.", None),
    ("dNBR_stdDv", "int64",
     "Standard deviation of the differenced Normalized Burn Ratio sampled from unburned area "
     "outside the perimeter.", None),
    ("NoData_T", "int64",
     "No-data threshold for this fire, in differenced Normalized Burn Ratio index values (index "
     "values of the Normalized Burn Ratio for single-scene assessments).", None),
    ("IncGreen_T", "int64",
     "Increased-greenness threshold for this fire, in the same index units as NoData_T.", None),
    ("Low_T", "int64",
     "Unburned-to-low severity threshold for this fire, in the same index units as NoData_T. "
     "Thresholds are set per fire, which is why severity classes are comparable between fires "
     "even though the underlying index values are not.", None),
    ("Mod_T", "int64",
     "Low-to-moderate severity threshold for this fire, in the same index units as NoData_T.",
     None),
    ("High_T", "int64",
     "Moderate-to-high severity threshold for this fire, in the same index units as NoData_T.",
     None),
    ("Comment", "string", "Notes recorded by the mapping analyst for the end user.", None),
]

PERIM_GEOM = ("geom", "geometry", "Fire perimeter geometry (GeoParquet), in EPSG:4326.", None)


def cols(entries, lean=False):
    out = []
    for name, typ, desc, values in entries:
        c = {"name": name, "type": typ}
        if not lean:
            c["description"] = desc
        if values:
            c["values"] = values
        out.append(c)
    return out


def perim_hex_note():
    m = MEASURED["perimeters"]
    return (
        f"One row per (fire perimeter, resolution 10 cell) pair — {num(m['hex_rows'])} rows for "
        f"{num(m['features'])} perimeters, because a perimeter that covers many cells appears on "
        f"many rows. Every attribute column is therefore repeated on every cell the perimeter "
        f"covers, so fire counts and acreage totals have to go through `_cng_fid`:\n\n"
        "```sql\n"
        "-- correct: number of mapped fires\n"
        "SELECT COUNT(DISTINCT _cng_fid) FROM read_parquet('"
        f"{BASE}/{PERIM}/hex/h0=*/data_0.parquet');\n"
        "-- correct: published acreage, each fire counted once\n"
        "SELECT SUM(BurnBndAc) FROM (SELECT DISTINCT _cng_fid, BurnBndAc\n"
        f"                           FROM read_parquet('{BASE}/{PERIM}/hex/h0=*/data_0.parquet'));\n"
        "-- COUNT(*) and a raw SUM(BurnBndAc) count cells, not fires, and inflate accordingly\n"
        "```\n\n"
        "For the area of a selection, prefer the H3 footprint of its distinct cells over summing "
        "`BurnBndAc`. Overlapping perimeters from different years share cells, which is the "
        "reburn record rather than an error — see the collection description for how to count "
        "unique ground separately from fire-years."
    )


def perimeters_collection():
    m = MEASURED["perimeters"]
    description = "\n\n".join([
        "Burned-area boundaries from the Monitoring Trends in Burn Severity (MTBS) program, a "
        "joint USGS and USDA Forest Service effort that has mapped every large fire in the United "
        "States since 1984. One polygon per mapped fire, covering the conterminous United States, "
        "Alaska, Hawaii and Puerto Rico, with the fire's name, ignition date, type and published "
        "acreage. Published as GeoParquet, PMTiles and H3 hex parquet at native resolution 10 "
        "with parents 9, 8 and 0.",
        NOT_A_CENSUS,
        "**Perimeters record extent, not severity.** Everything inside a perimeter is inside the "
        "fire, but fire effects vary enormously within one boundary — unburned islands sit beside "
        "stand-replacing patches. For per-pixel severity use the companion severity collections "
        f"in this bucket, `mtbs-severity-1984-2024-conus` and `mtbs-severity-1984-2024-ak`, which "
        "join to this layer on the resolution 8 or resolution 10 cell.",
        REBURN,
        "**Wildfire and prescribed fire are both here.** `Incid_Type` separates them: WF is "
        "wildfire, Rx is prescribed fire, UNK is unknown. A total across all rows mixes "
        "intentional management burning with unplanned fire.",
        f"Provenance: retrieved from the USGS ScienceBase release on {ACCESSED}. Edition: "
        f"{ED_PERIMS}. The source package is staged unmodified at "
        f"`{BASE}/raw/mtbs/perims/mtbs_perims_DD.zip` "
        f"({num(m['raw_size'])} bytes"
        + (f", MD5 {m['raw_md5']}" if m["raw_md5"] else "")
        + "). Coordinates are decimal degrees on NAD83, read as EPSG:4326.",
    ])

    return {
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
            "https://stac-extensions.github.io/version/v1.2.0/schema.json",
        ],
        "type": "Collection",
        "id": PERIM,
        "title": "MTBS Burned Area Perimeters, United States 1984-2024",
        "description": description,
        "license": "public-domain",
        "version": ED_PERIMS,
        "sci:citation": (
            "Eidenshink, J., Schwind, B., Brewer, K., Zhu, Z.-L., Quayle, B., and Howard, S. "
            "2007. A project for monitoring trends in burn severity. Fire Ecology 3(1): 3-21. "
            "Data: USGS/USFS Monitoring Trends in Burn Severity, Burned Areas Boundaries, "
            f"version 12.0 (April 2025). Accessed {ACCESSED} from {SB_PERIMS}."
        ),
        "sci:publications": [{"doi": "10.1186/s42408-020-00076-y",
                              "citation": "Picotte, J.J., et al. 2020. Changes to the Monitoring "
                                          "Trends in Burn Severity program mapping production "
                                          "procedures and data products. Fire Ecology 16:16."}],
        "keywords": ["wildfire", "fire perimeters", "burn severity", "MTBS", "H3",
                     "United States", "USGS", "USDA Forest Service"],
        "extent": {
            "spatial": {"bbox": [m["bbox"] or [-179.0, 17.6, -65.2, 71.4]]},
            "temporal": {"interval": [["1984-01-01T00:00:00Z", "2024-12-31T23:59:59Z"]]},
        },
        "providers": [
            {"name": "USGS EROS and USDA Forest Service Geospatial Technology and Applications "
                     "Center (Monitoring Trends in Burn Severity)",
             "roles": ["producer", "licensor"], "url": LANDING},
            {"name": "USGS ScienceBase", "roles": ["host"], "url": SB_PERIMS},
            {"name": "Boettiger Lab / cirrus", "roles": ["processor", "host"], "url": f"{BASE}/"},
        ],
        "links": [
            {"rel": "self", "href": f"{BASE}/{PERIM}/stac-collection.json",
             "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "license", "href": "https://www.usa.gov/government-works", "type": "text/html",
             "title": "US Government work - public domain"},
            {"rel": "about", "href": LANDING, "type": "text/html",
             "title": "Monitoring Trends in Burn Severity program"},
            {"rel": "source", "href": SB_PERIMS, "type": "text/html",
             "title": "USGS ScienceBase release read on " + ACCESSED},
            {"rel": "cite-as", "href": PAPER,
             "title": "Picotte et al. 2020, Fire Ecology 16:16"},
        ],
        "assets": {
            f"{PERIM}-parquet": {
                "href": f"{BASE}/{PERIM}.parquet",
                "type": "application/x-parquet",
                "title": "MTBS burned area perimeters - GeoParquet",
                "description": (
                    "One row per mapped fire, with its perimeter geometry in EPSG:4326. This is "
                    "the authoritative grain: `COUNT(*)` here is the number of mapped fires and "
                    "`SUM(BurnBndAc)` here is the published acreage, no deduplication required."
                ),
                "roles": ["data"],
                "table:columns": cols(PERIM_COLUMNS) + cols([PERIM_GEOM]),
            },
            f"{PERIM}-pmtiles": {
                "href": f"{BASE}/{PERIM}.pmtiles",
                "type": "application/vnd.pmtiles",
                "title": "MTBS burned area perimeters - PMTiles",
                "description": "Vector tiles for web maps. Source layer: "
                               f"`{PERIM}`.",
                "roles": ["visual"],
                "vector:layers": [PERIM],
                "table:columns": cols(PERIM_COLUMNS, lean=True),
            },
            f"{PERIM}-hex": {
                "href": f"{BASE}/{PERIM}/hex/h0=*/data_0.parquet",
                "type": "application/x-parquet",
                "title": "MTBS burned area perimeters - H3 hex (resolution 10)",
                "description": perim_hex_note(),
                "roles": ["data"],
                "h3:native_resolution": 10,
                "h3:parent_resolutions": [9, 8, 0],
                "table:columns": cols(PERIM_COLUMNS) + h3_cols(10, [9, 8, 0]),
            },
        },
    }


# ══════════════════════════════════════════════════════════════════════════════════════════
# Severity, one collection per domain
# ══════════════════════════════════════════════════════════════════════════════════════════
SEVERITY = {
    "conus": {
        "id": "mtbs-severity-1984-2024-conus",
        "name": "CONUS",
        "title": "MTBS Annual Thematic Burn Severity, conterminous United States 1984-2024",
        "years": CONUS_YEARS,
        "default_bbox": [-124.8, 24.4, -66.9, 49.4],
        "clip": None,
    },
    "ak": {
        "id": "mtbs-severity-1984-2024-ak",
        "name": "Alaska",
        "title": "MTBS Annual Thematic Burn Severity, Alaska 1984-2023",
        "years": AK_YEARS,
        "default_bbox": [-173.2, 54.6, -130.0, 71.4],
        "clip": "180 degrees west to 129 degrees west, 48.8 to 71.6 degrees north",
    },
}

# The single authority for the `severity` column's prose. It must be IDENTICAL on every asset
# that carries the column: verify-stac.py HARD-fails divergent text, because the mcp-data-server
# fold (#303) keeps the first-seen description and silently drops the others. The two hex assets
# therefore differ only in `values`, which the fold does not touch and which has to stay true to
# what each asset actually contains. Anything asset-specific belongs in that asset's own
# `description`, not here.
SEVERITY_DESCRIPTION = (
    "Thematic burn severity class. Values: " + CLASS_LIST_FRACTIONS + ". Classes 1 to 4 are "
    "severity levels; class 5 is increased post-fire greenness and class 6 is area excluded from "
    "severity mapping, so neither is a severity level. Labels are those published with the source "
    "rasters. Code 0 is background — ground outside any mapped fire — and whether it is present "
    "depends on the asset: the dominant-class (`mode`) asset drops source no-data, so it holds "
    "only codes 1 to 6 and every row is burned ground, while the fractional-coverage asset keeps "
    "code 0 as the unburned share of each cell, which is what makes a cell's shares sum to 1. "
    "Exclude 0, 5 and 6 from any severity denominator."
)

SEVERITY_COLUMN = {
    "name": "severity",
    "type": "uint8",
    "description": SEVERITY_DESCRIPTION,
    "values": CLASS_VALUES,          # `mode`: 1-6, verified against the built Alaska hex
}

SEVERITY_COLUMN_FRACTIONS = {
    "name": "severity",
    "type": "uint8",
    "description": SEVERITY_DESCRIPTION,
    "values": CLASS_VALUES_FRACTIONS,   # `fractions`: 0-6, verified against the built Alaska hex
}

FRAC_COLUMN = {
    "name": "frac",
    "type": "double",
    "description": (
        "Share of the whole H3 cell covered by this severity class, between 0 and 1 — a share of "
        "the cell's full ground area, not of its burned part. One row per (year, cell, class). "
        "The shares within one cell and year sum to exactly 1, but only because class 0 (the "
        "unburned remainder of the cell) is included; summing only classes 1 to 6 gives the share "
        "of the cell that is mapped burned ground. Multiply by the cell's ground area for the "
        "area in that class."
    ),
}


def severity_collection(dom):
    cfg = SEVERITY[dom]
    m = MEASURED[dom]
    name = cfg["id"]
    years = cfg["years"]
    other = "ak" if dom == "conus" else "conus"

    parts = [
        f"Annual thematic burn severity from the Monitoring Trends in Burn Severity (MTBS) "
        f"program for {cfg['name']}, at the source resolution of 30 metres. One composite per "
        f"calendar year, covering {len(years)} years from {years[0]} to {years[-1]}, published as "
        f"a WGS84 cloud-optimized GeoTIFF per year plus two H3 hex products at native resolution "
        f"10 with parents 9, 8 and 0. This is the observational record of what burned and how "
        f"severely, as distinct from a model of where fire is likely.",
        f"**Both hex products are one dataset partitioned by year**, so a single year is a filter "
        f"rather than a separate table, and change over time is a join on the cell:\n\n"
        "```sql\n"
        "-- one year\n"
        f"SELECT * FROM read_parquet('{BASE}/{name}/hex/year=*/h0=*/data_0.parquet')\n"
        "WHERE year = 2020;\n"
        "-- how many times each place burned across the record\n"
        "SELECT h10, COUNT(DISTINCT year) AS times_burned\n"
        f"FROM read_parquet('{BASE}/{name}/hex/year=*/h0=*/data_0.parquet')\n"
        "GROUP BY h10;\n"
        "```",
        NOT_A_CENSUS,
        SEV_DENOM,
        MODE_VS_FRACTIONS,
        REBURN,
        missing_note(dom),
        AREA_TRUTH,
    ]
    if dom == "conus":
        parts.append(CLAMP_NOTE)
    parts += [
        "**Native resolution 10 is the closest H3 resolution to a 30 metre pixel, and it is still "
        "coarser than the source.** A resolution 10 cell holds roughly 17 source pixels, so the "
        "`mode` product's dominant class discards a real mix within each cell; that is what the "
        "`fractions` product is for.",
    ]

    if cfg["clip"]:
        parts.append(
            f"**Alaska extent.** Clipped to {cfg['clip']}, which drops the far-western Aleutians "
            "where the source grid wraps the antimeridian. No National Forest System land lies in "
            "the dropped area — the Alaska units are the Tongass and the Chugach, far to the "
            "east — but this is therefore not a complete Alaska mosaic and should not be "
            "described as one."
        )

    parts.append(
        "**Hawaii and Puerto Rico are not included in either severity collection.** MTBS "
        "publishes Hawaii mosaics for 17 years and Puerto Rico for only 2005, 2007 and 2013; both "
        "are staged unmodified under "
        f"`{BASE}/raw/mtbs/mosaics/` but are not processed here. Puerto Rico is the only National "
        "Forest System gap this creates, at El Yunque. The perimeters collection covers both."
    )
    parts.append(
        f"The other domain is published separately as `{SEVERITY[other]['id']}` because MTBS "
        "ships each domain on its own Albers grid. Severity classes mean the same thing in both, "
        "so unlike a domain-relative hazard classification these two are directly comparable — "
        "join them on the resolution 8 cell."
    )
    parts.append(
        f"Provenance: retrieved from the USGS ScienceBase release on {ACCESSED}. Editions: "
        f"{ED_MOSAICS}. Source mosaics are staged unmodified under "
        f"`{BASE}/raw/mtbs/mosaics/`, with the per-file size, published MD5 and recomputed MD5 "
        f"recorded in `{BASE}/raw/mtbs/mosaic-manifest.tsv`."
    )

    assets = {}
    for y in years:
        assets[f"mtbs-severity-{dom}-cog-{y}"] = {
            "href": f"{BASE}/{name}/mtbs-severity-{dom}-{y}-cog.tif",
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "title": f"MTBS burn severity {y} ({cfg['name']}, 30 m COG)",
            "description": (
                f"Thematic burn severity for fires mapped in {y}, reprojected from the source "
                "equal-area Albers grid to EPSG:4326 with nearest-neighbour resampling — required, "
                "because the values are class codes and any other resampling invents classes the "
                "source does not contain. Geographic and therefore not equal-area: use the hex "
                "assets for area statistics."
            ),
            "roles": ["data"],
            "raster:bands": [{
                "name": "burn_severity",
                "data_type": "uint8",
                "nodata": 0,
                "spatial_resolution": 30,
                "unit": "class code",
                "classification:classes": [
                    {"value": v, "name": n, "description": d, "color_hint": c}
                    for v, n, d, c in CLASSES_WITH_BACKGROUND
                ],
            }],
        }

    assets[f"mtbs-severity-{dom}-hex"] = {
        "href": f"{BASE}/{name}/hex/year=*/h0=*/data_0.parquet",
        "type": "application/x-parquet",
        "title": f"MTBS burn severity, {cfg['name']} - H3 hex, dominant class, all years",
        "description": (
            f"One row per (year, populated resolution 10 cell) — {num(m['hex_rows'])} rows across "
            f"{len(years)} years and {m['h0_count']} resolution 0 partitions, covering "
            f"{num(m['cells_burned'])} distinct cells of ground. Rows exceed distinct cells because "
            "ground that burned in more than one year appears once per year; that difference is "
            "the reburn record, so which of the two a total means has to be stated. The `mode` "
            "reducer gives each cell the majority severity class of the source pixels inside it, "
            "which preserves classes that exist in the source where an average would fabricate "
            "ones that do not. Cells with no burned pixel are dropped, so this asset covers burned "
            "ground only. No attribute is repeated across cells here, so `COUNT(*)` counts cells "
            "and cells are a valid area proxy. For the share of an area at a given severity, use "
            "the fractional-coverage asset instead — `mode` keeps only the dominant class."
        ),
        "roles": ["data"],
        "h3:native_resolution": 10,
        "h3:parent_resolutions": [9, 8, 0],
        "classification:classes": [{"value": v, "name": n, "description": d}
                                   for v, n, d, _ in CLASSES],
        "table:columns": ([SEVERITY_COLUMN] + h3_cols(10, [9, 8, 0])
                          + [{"name": "year", "type": "int64", "description": YEAR_DESC}]),
    }

    assets[f"mtbs-severity-{dom}-hex-fractions"] = {
        "href": f"{BASE}/{name}/hex-fractions/year=*/h0=*/data_0.parquet",
        "type": "application/x-parquet",
        "title": f"MTBS burn severity, {cfg['name']} - H3 hex, per-class coverage, all years",
        "description": (
            "Long format: one row per (year, resolution 10 cell, severity class), with `frac` "
            f"giving that class's share of the cell — {num(m['frac_rows'])} rows across "
            f"{len(years)} years and {m['h0_count']} resolution 0 partitions. This is the asset "
            "for any question about how much area burned at a given severity, because it keeps "
            "the mix within each cell instead of collapsing it to a single dominant class. "
            "Shares within one cell and year sum to approximately 1. Class codes 5 and 6 are "
            "present and should be left out of a severity denominator; see the collection "
            "description for the query."
        ),
        "roles": ["data"],
        "h3:native_resolution": 10,
        "h3:parent_resolutions": [9, 8, 0],
        "classification:classes": [{"value": v, "name": n, "description": d}
                                   for v, n, d, _ in CLASSES_WITH_BACKGROUND],
        "table:columns": ([SEVERITY_COLUMN_FRACTIONS, FRAC_COLUMN] + h3_cols(10, [9, 8, 0])
                          + [{"name": "year", "type": "int64", "description": YEAR_DESC}]),
    }

    return {
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/classification/v2.0.0/schema.json",
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
        ],
        "type": "Collection",
        "id": name,
        "title": cfg["title"],
        "description": "\n\n".join(parts),
        "license": "public-domain",
        "sci:citation": (
            "Eidenshink, J., Schwind, B., Brewer, K., Zhu, Z.-L., Quayle, B., and Howard, S. "
            "2007. A project for monitoring trends in burn severity. Fire Ecology 3(1): 3-21. "
            f"Data: USGS/USFS Monitoring Trends in Burn Severity, {ED_MOSAICS}. "
            f"Accessed {ACCESSED} from {SB_MOSAICS}."
        ),
        "sci:publications": [{"doi": "10.1186/s42408-020-00076-y",
                              "citation": "Picotte, J.J., et al. 2020. Changes to the Monitoring "
                                          "Trends in Burn Severity program mapping production "
                                          "procedures and data products. Fire Ecology 16:16."}],
        "keywords": ["wildfire", "burn severity", "fire effects", "MTBS", "H3", cfg["name"],
                     "United States", "USGS", "USDA Forest Service"],
        "extent": {
            "spatial": {"bbox": [m["bbox"] or cfg["default_bbox"]]},
            "temporal": {"interval": [[f"{years[0]}-01-01T00:00:00Z",
                                       f"{years[-1]}-12-31T23:59:59Z"]]},
        },
        "providers": [
            {"name": "USGS EROS and USDA Forest Service Geospatial Technology and Applications "
                     "Center (Monitoring Trends in Burn Severity)",
             "roles": ["producer", "licensor"], "url": LANDING},
            {"name": "USGS ScienceBase", "roles": ["host"], "url": SB_MOSAICS},
            {"name": "Boettiger Lab / cirrus", "roles": ["processor", "host"], "url": f"{BASE}/"},
        ],
        "links": [
            {"rel": "self", "href": f"{BASE}/{name}/stac-collection.json",
             "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "license", "href": "https://www.usa.gov/government-works", "type": "text/html",
             "title": "US Government work - public domain"},
            {"rel": "about", "href": LANDING, "type": "text/html",
             "title": "Monitoring Trends in Burn Severity program"},
            {"rel": "source", "href": SB_MOSAICS, "type": "text/html",
             "title": "USGS ScienceBase release read on " + ACCESSED},
            {"rel": "cite-as", "href": PAPER,
             "title": "Picotte et al. 2020, Fire Ecology 16:16"},
        ],
        "assets": assets,
    }


# ══════════════════════════════════════════════════════════════════════════════════════════
# Bucket collection and README, patched rather than rewritten
# ══════════════════════════════════════════════════════════════════════════════════════════
BUCKET_TITLE = "Wildfire: hazard potential, observed burn severity, and fire perimeters"

BUCKET_DESCRIPTION = (
    "Wildfire datasets published as cloud-native GeoParquet, PMTiles, cloud-optimized GeoTIFF and "
    "H3 hex parquet. Three kinds of layer live here and they answer different questions. Fire "
    "perimeters (CAL FIRE FRAP, USGS Combined, MTBS) record WHERE fire has burned. MTBS thematic "
    "burn severity records HOW SEVERELY it burned, per 30 metre pixel, for every large fire since "
    "1984 — an observation. Wildfire Hazard Potential records where fire is LIKELY to burn and how "
    "intensely given fuels, topography and weather — a modelled surface, and hazard rather than "
    "risk, since it does not account for what is exposed to loss. Modelled hazard and observed "
    "outcome can diverge, and comparing them is a question this bucket can answer directly: every "
    "collection carries the resolution 8 H3 cell as a join key.\n\n"
    "Licenses differ by dataset — the CAL FIRE and USGS perimeter collections are CC-BY-4.0, the "
    "Forest Service and USGS federal products are US Government works in the public domain. Each "
    "child collection carries its own license; check there rather than assuming a bucket-wide term."
)

MTBS_README_SECTION = f"""
## MTBS burned area and burn severity 1984–2024 (`mtbs-*`) — the observational record

Three collections from the Monitoring Trends in Burn Severity program, a joint USGS and USDA
Forest Service effort that has mapped every large fire in the United States since 1984.

| Collection | Kind | Native H3 | Reducer | Value column |
|---|---|---|---|---|
| [`{PERIM}`]({BASE}/{PERIM}/stac-collection.json) | vector, national | 10 (parents 9, 8, 0) | — | — |
| [`{SEVERITY['conus']['id']}`]({BASE}/{SEVERITY['conus']['id']}/stac-collection.json) | raster, {len(CONUS_YEARS)} annual years | 10 (parents 9, 8, 0) | `mode` + `fractions` | `severity` |
| [`{SEVERITY['ak']['id']}`]({BASE}/{SEVERITY['ak']['id']}/stac-collection.json) | raster, {len(AK_YEARS)} annual years | 10 (parents 9, 8, 0) | `mode` + `fractions` | `severity` |

Severity classes: {CLASS_LIST}. **Classes 5 and 6 are not severity levels** — 5 is increased
post-fire greenness, 6 is area excluded from mapping — so leave them out of any
"share at high severity" denominator.

**Not a fire census.** MTBS maps only fires over 1,000 acres in the West and 500 acres in the
East. Small fires are absent by design and they are most ignitions.

**Reburns are signal, not duplication.** The same ground burns repeatedly over four decades, so
"total acres burned" has to say whether it means unique ground or fire-years.

**Use `hex-fractions`, not `hex`, for shares.** The `mode` asset keeps only each cell's dominant
class; a cell that is 40% high severity and 60% moderate reads as entirely moderate.

### DuckDB

```sql
INSTALL httpfs; LOAD httpfs;

-- share of burned area at high severity, CONUS, 2020, codes 1-4 as the denominator
SELECT ROUND(100.0 * SUM(frac) FILTER (WHERE severity = 4)
             / SUM(frac) FILTER (WHERE severity BETWEEN 1 AND 4), 2) AS pct_high
FROM read_parquet('{BASE}/{SEVERITY['conus']['id']}/hex-fractions/year=*/h0=*/data_0.parquet')
WHERE year = 2020;

-- burn severity inside inventoried roadless areas. Both collections are native resolution 10,
-- so join on h10 and the boundary is exact. Joining these two on h8 instead would count every
-- cell whose resolution 8 parent merely touches a roadless area -- 49 resolution 10 cells per
-- parent -- which inflates the roadless footprint along every edge. Use h8 to reach collections
-- that are not native resolution 10.
SELECT s.severity, SUM(s.frac) AS cell_shares
FROM read_parquet('{BASE}/{SEVERITY['conus']['id']}/hex-fractions/year=*/h0=*/data_0.parquet') s
JOIN (SELECT DISTINCT h10 FROM read_parquet(
        'https://s3-west.nrp-nautilus.io/public-usfs/roadless-areas-2001/hex/h0=*/data_0.parquet')) r
  USING (h10)
GROUP BY s.severity ORDER BY s.severity;

-- how often each place burned: unique ground versus fire-years
SELECT COUNT(DISTINCT h10) AS unique_ground_cells,
       COUNT(DISTINCT (h10, year)) AS fire_year_cells
FROM read_parquet('{BASE}/{SEVERITY['conus']['id']}/hex/year=*/h0=*/data_0.parquet');

-- named fires and their published acreage, deduplicated to one row per fire
SELECT Incid_Name, Ig_Date, BurnBndAc FROM (
  SELECT DISTINCT _cng_fid, Incid_Name, Ig_Date, BurnBndAc
  FROM read_parquet('{BASE}/{PERIM}/hex/h0=*/data_0.parquet'))
ORDER BY BurnBndAc DESC LIMIT 10;
```

### MapLibre GL JS

```javascript
map.addSource('mtbs-perimeters', {{
  type: 'vector',
  url: 'pmtiles://{BASE}/{PERIM}.pmtiles'
}});
map.addLayer({{
  id: 'mtbs-perimeters-fill',
  type: 'fill',
  source: 'mtbs-perimeters',
  'source-layer': '{PERIM}',
  paint: {{ 'fill-color': '#b03a2e', 'fill-opacity': 0.45 }}
}});
```

⚠️ **Missing years.** Six source mosaics could not be retrieved from the publisher, so severity is
absent for CONUS {', '.join(str(y) for y in MISSING['conus'])} and Alaska
{', '.join(str(y) for y in MISSING['ak'])}. A query filtering on one of those years returns no
rows, which means the severity mapping is unavailable — not that nothing burned. Perimeters cover
all 41 years.
"""


def patch_bucket_collection():
    """Fetch the published bucket collection and add the three MTBS children.

    Patched rather than rewritten so fields this script does not model survive. Beyond the child
    links, the title and description are rewritten: the published pair describes hazard potential
    and perimeters, which stops being the whole story once an observed per-pixel severity record
    lives in the bucket. `license` stays `various` (the perimeter children are CC-BY-4.0, the
    federal products public domain) with no bucket-level license link, which is what a
    meta-collection with child links is allowed to do. The `id` is deliberately left alone: it is
    consumer-visible and renaming it is out of scope.
    """
    with urllib.request.urlopen(f"{BASE}/stac-collection.json", timeout=60) as r:
        doc = json.load(r)

    before = len([l for l in doc.get("links", []) if l.get("rel") == "child"])

    doc["title"] = BUCKET_TITLE
    doc["description"] = BUCKET_DESCRIPTION

    links = list(doc.get("links", []))
    have = {l.get("href") for l in links if l.get("rel") == "child"}
    children = [(PERIM, "MTBS Burned Area Perimeters, United States 1984-2024")] + [
        (SEVERITY[d]["id"], SEVERITY[d]["title"]) for d in ("conus", "ak")
    ]
    for cid, title in children:
        href = f"{BASE}/{cid}/stac-collection.json"
        if href not in have:
            links.append({"rel": "child", "href": href, "type": "application/json",
                          "title": title})
    doc["links"] = links

    after = len([l for l in doc["links"] if l.get("rel") == "child"])
    assert after == before + 3, f"expected {before}+3 children, got {after}"

    # MTBS starts in 1984, well inside the published interval, so the temporal extent only needs
    # widening if the published end predates the last severity year.
    extent = doc.setdefault("extent", {}).setdefault("temporal", {})
    interval = extent.get("interval") or [[None, None]]
    if interval[0][1] and interval[0][1] < "2024-12-31T23:59:59Z":
        interval[0][1] = "2024-12-31T23:59:59Z"
        extent["interval"] = interval

    kw = doc.setdefault("keywords", [])
    for k in ("burn severity", "MTBS", "fire effects", "reburn"):
        if k not in kw:
            kw.append(k)

    return doc


def patch_readme():
    """Fetch the published bucket README, add MTBS to the contents list and append its section.

    Each anchor is asserted rather than searched loosely: a silent no-op replace would publish a
    README that omits the new dataset while looking like it succeeded.
    """
    with urllib.request.urlopen(f"{BASE}/README.md", timeout=60) as r:
        text = r.read().decode("utf-8")

    old_intro = ("This bucket contains two kinds of wildfire layer. **Fire perimeters** record "
                 "where fire has burned. **Wildfire Hazard Potential** is a modelled surface "
                 "describing where fire is likely to burn and how intensely — not an observation, "
                 "and not a map of risk to people or property.")
    new_intro = ("This bucket contains three kinds of wildfire layer. **Fire perimeters** record "
                 "where fire has burned. **Burn severity** records how severely it burned, per 30 "
                 "metre pixel, for every large fire since 1984. **Wildfire Hazard Potential** is "
                 "a modelled surface describing where fire is likely to burn and how intensely — "
                 "not an observation, and not a map of risk to people or property. Modelled "
                 "hazard and observed outcome can diverge; every collection here carries the "
                 "resolution 8 H3 cell, so comparing them is a join.")
    assert old_intro in text, "README intro anchor not found"
    text = text.replace(old_intro, new_intro)

    whp_bullet = ("- **Wildfire Hazard Potential 2023** — modelled 270 m hazard surface, CONUS "
                  "and Alaska, classified and continuous (`whp-2023-*`)")
    assert whp_bullet in text, "README WHP bullet anchor not found"
    text = text.replace(
        whp_bullet,
        whp_bullet
        + "\n- **MTBS Burned Area Perimeters** — every large US fire 1984–2024, one polygon per "
          f"fire (`{PERIM}`)"
          "\n- **MTBS Annual Thematic Burn Severity** — observed 30 m per-pixel severity by year, "
          "CONUS and Alaska (`mtbs-severity-1984-2024-*`)",
    )

    old_all = ("The perimeter datasets are polygon geometries processed into GeoParquet, PMTiles "
               "and H3 hex Parquet (resolution 10). Wildfire Hazard Potential is raster, "
               "published as a WGS84 COG plus H3 hex Parquet (resolution 9 classified, 8 "
               "continuous).")
    new_all = ("The perimeter datasets are polygon geometries processed into GeoParquet, PMTiles "
               "and H3 hex Parquet (resolution 10). Wildfire Hazard Potential is raster, "
               "published as a WGS84 COG plus H3 hex Parquet (resolution 9 classified, 8 "
               "continuous). MTBS burn severity is raster, published as one WGS84 COG per year "
               "plus two H3 hex Parquet products at resolution 10 — dominant class and per-class "
               "fractional coverage — partitioned by year.")
    assert old_all in text, "README 'processed into' anchor not found"
    text = text.replace(old_all, new_all)

    assert "\n## Citation\n" in text, "README citation anchor not found"
    text = text.replace("\n## Citation\n", MTBS_README_SECTION + "\n---\n\n## Citation\n", 1)

    text = text.rstrip("\n") + (
        "\n\n**MTBS datasets:**\n"
        "Eidenshink, J., Schwind, B., Brewer, K., Zhu, Z.-L., Quayle, B., and Howard, S. 2007. "
        "A project for monitoring trends in burn severity. Fire Ecology 3(1): 3-21. "
        "Picotte, J.J., et al. 2020. Changes to the Monitoring Trends in Burn Severity program "
        "mapping production procedures and data products. Fire Ecology 16:16. "
        "https://doi.org/10.1186/s42408-020-00076-y. "
        f"Data accessed {ACCESSED}: {ED_PERIMS}; {ED_MOSAICS}. https://www.mtbs.gov/\n"
    )
    return text


if __name__ == "__main__":
    written = []

    for path, doc in [
        (f"/tmp/{PERIM}-stac.json", perimeters_collection()),
        (f"/tmp/{SEVERITY['conus']['id']}-stac.json", severity_collection("conus")),
        (f"/tmp/{SEVERITY['ak']['id']}-stac.json", severity_collection("ak")),
        ("/tmp/fire-bucket-stac.json", patch_bucket_collection()),
    ]:
        with open(path, "w") as f:
            json.dump(doc, f, indent=2)
            f.write("\n")
        written.append(path)

    with open("/tmp/fire-README.md", "w") as f:
        f.write(patch_readme())
    written.append("/tmp/fire-README.md")

    print("wrote:")
    for p in written:
        print(" ", p)

    unfilled = [f"{k}.{kk}" for k, v in MEASURED.items() for kk, vv in v.items() if vv is None]
    if unfilled:
        print("\n!! MEASURED values still unfilled -- do NOT publish until these are read back "
              "off the completed builds:")
        for u in unfilled:
            print("   ", u)
