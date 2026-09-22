#!/usr/bin/env python3
"""Generate the STAC collections for USGS OFR 97-709 (Kaiparowits Plateau coal).

One leaf collection per coverage plus a grouping collection that links them, per the
scope fixed in issue #707. Column text is written from a single table here and emitted
identically to the GeoParquet, PMTiles and hex assets, so the mcp-data-server per-column
fold can never drop a variant.

Writes to an output directory; nothing is committed. Upload with:

    scripts/verify-stac.py --no-data <file>            # every file, before publishing
    rclone copyto <file> nrp:public-usgs/kaiparowits-coal-resources/<cov>/stac-collection.json

Usage: gen_stac.py --out /tmp/kaiparowits-stac [--counts counts.json]
"""

from __future__ import annotations

import argparse
import json
import os

BUCKET = "public-usgs"
DATASET = "kaiparowits-coal-resources"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
PREFIX = f"{BASE}/{DATASET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
PARENT = f"{PREFIX}/stac-collection.json"

LANDING = "https://pubs.usgs.gov/of/1997/ofr-97-0709/"
APPENDIX = "https://pubs.usgs.gov/of/1997/ofr-97-0709/Appendix1.html"
LICENSE_URL = "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits"
ACCESSED = "2026-09-22"

# The archive fingerprint, recomputed from the staged object by the preprocess job.
RAW = ("`s3://public-usgs/raw/kaiparowits/kaip.tar.gz` (5368079 bytes, md5 "
       "`d680d23c47172d5ee1061728d7cd1632`), and the 14-layer GeoPackage built from it, "
       "`s3://public-usgs/raw/kaiparowits/kaiparowits.gpkg`")

CITATION = (
    "Biewick, L.R.H., Hettinger, R.D., and Roberts, L.N.R., 1997, Selected ARC/INFO "
    "coverages created for investigations of the distribution and resources of coal in "
    "the Kaiparowits Plateau, southern Utah: an accompaniment to Hettinger and others, "
    "1996, version 1: U.S. Geological Survey Open-File Report 97-709, "
    f"{LANDING}. Coverage files dated 1997-11-07; accessed {ACCESSED}."
)

PROVIDERS = [
    {"name": "U.S. Geological Survey", "roles": ["producer", "licensor"], "url": LANDING},
    {"name": "Boettiger Lab", "roles": ["processor"], "url": "https://boettiger-lab.github.io"},
]

# Every coverage was compiled for Hettinger and others (1996); allcoal.meta gives 1995 as
# the compilation date and 1997 as publication. A fixed vintage with no successor.
TEMPORAL = ["1995-01-01T00:00:00Z", "1997-11-07T00:00:00Z"]

# Shared provenance paragraph. The access date and the staged fingerprint are what make
# this resolvable to an edition: USGS publishes no dated archive of this report.
PROVENANCE = (
    "**Provenance.** Landing page: {landing}. Coverage descriptions: {appendix}. Upstream "
    "labels this edition **version 1**; the coverage files are dated 1997-11-07 and the "
    "report is a fixed 1997 vintage that upstream has never revised. Read on "
    "**{accessed}** from the single archive `kaip.tar.gz`, staged as {raw}.\n\n"
    "The shipped `exports/*.e00` files are compressed E00, which GDAL cannot read; the "
    "published assets were built from the native binary ARC/INFO coverages in the same "
    "archive. The coverages are NAD27 / UTM zone 12N (EPSG:26712) but record no datum, so "
    "a reader that assumes NAD83 places them about 212 m off. They were reprojected to "
    "EPSG:4326 through the NADCON grid transformation (NAD27 to NAD83 (1), 0.15 m), and "
    "the build refuses to run on a coarser fallback."
).format(landing=LANDING, appendix=APPENDIX, accessed=ACCESSED, raw=RAW)

# The caveat that governs every tonnage and thickness figure in this report, in the
# authors' own terms.
RESOURCE_CAVEAT = (
    "**These are in-place resource figures, not reserves.** They estimate coal in the "
    "ground at the stated thickness and overburden cutoffs, with no deduction for what "
    "is recoverable, mineable or economic, and the total spans every overburden class "
    "including more than 6,000 ft. The authors state the data set \"cannot be used for "
    "mine planning or to calculate reserves\" and describe it as a guide to where the "
    "thickest net coal areas are likely to be."
)

RELIABILITY_NOTE = (
    "`REL` separates **identified** resources (within three miles of a data point) from "
    "**hypothetical** ones (further than three miles). The two are not interchangeable "
    "and a total that mixes them should say so:\n\n"
    "```sql\n"
    "-- identified resources only, in million short tons\n"
    "SELECT SUM(SHTONS_MIL) FROM read_parquet(\n"
    "  's3://public-usgs/kaiparowits-coal-resources/allcoal.parquet')\n"
    "WHERE REL = 'iden';\n"
    "-- reporting one figure for all 72,129.6 million short tons mixes identified and\n"
    "-- hypothetical resources, which carry different levels of confidence\n"
    "```"
)

SENTINEL_NOTE = (
    "Five polygons are map holes where no coal exists, carrying `OVERB = '-99'`, "
    "`REL = 'hole'` and empty strings for ownership, county, quadrangle, township-range "
    "and dip. They are no-data markers, not measurements of zero."
)

# ---------------------------------------------------------------------------
# Column definitions. One text per column name, emitted identically to every asset
# in a collection. Columns whose meaning differs between coverages are keyed per
# coverage in OVERRIDES.
# ---------------------------------------------------------------------------

COLUMNS = {
    "_cng_fid": dict(type="int64", description=(
        "Universal per-feature id, one per source feature and unique within this "
        "collection. Use it as the join and deduplication key between the GeoParquet "
        "and the H3 hex asset.")),
    "fid": dict(type="int64", description=(
        "Row number carried over from the staged GeoPackage. Provenance only: use "
        "`_cng_fid` as the join and deduplication key.")),
    "geom": dict(type="geometry", description="Feature geometry (GeoParquet), EPSG:4326."),
    "h8": dict(type="int64", description=(
        "H3 cell ID at resolution 8, the native resolution of the hex asset.")),
    "h0": dict(type="int64", description=(
        "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads.")),

    "QUAD": dict(type="string", description=(
        "Name of the USGS 7.5-minute quadrangle the polygon falls in. Empty on the map-hole "
        "polygons.")),
    "CNTY": dict(type="string", description=(
        "County. Values: KANE=Kane County, Utah, GARFIELD=Garfield County, Utah. Empty on "
        "the map-hole polygons.")),
    "OVERB": dict(type="string", description=(
        "Maximum overburden over the coal, as a class in thousands of feet, measured to the "
        "Calico sequence boundary. Values: 0-1=0 to 1,000 ft, 1-2=1,000 to 2,000 ft, "
        "2-3=2,000 to 3,000 ft, 3-6=3,000 to 6,000 ft, >6=more than 6,000 ft, "
        "-99=no-data marker on the map-hole polygons, not an overburden of zero.")),
    "SURF": dict(type="string", description=(
        "Surface management status from the Bureau of Land Management land status mapping. "
        "Values: BLM=Bureau of Land Management, FS=Forest Service, NPS=National Park "
        "Service, NREC=National Recreation Area, STATE=State of Utah, PRIVATE=private, "
        "WATER=water. Empty on the map-hole polygons. This is surface ownership, which is "
        "often not the same as who owns the coal: see COAL_OWN.")),
    "COAL_OWN": dict(type="string", description=(
        "Coal ownership, generalised to the PLSS section, where a whole section takes "
        "whatever status covers 50 percent or more of it. Values: fed=Federal coal, "
        "nonfed=non-Federal coal. Empty on the map-hole polygons.")),
    "TR": dict(type="string", description=(
        "Township and range, as township number, south, range number, east or west; 33S2E "
        "is Township 33 South, Range 2 East. Empty on the map-hole polygons.")),
    "REL": dict(type="string", description=(
        "Reliability of the resource estimate, set by distance from a data point. Values: "
        "iden=identified, within three miles of a data point, hypo=hypothetical, further "
        "than three miles from a data point, hole=no-data marker on the map-hole polygons "
        "where no coal exists.")),
    "DIP": dict(type="string", description=(
        "Inclination of the coal-bearing strata, as a class in degrees, compiled at "
        "1:125,000 from structure contours and dip measurements on 1:24,000 geologic maps. "
        "Values: 0-6=0 to 6 degrees, 6-12=6 to 12 degrees, 12-25=12 to 25 degrees, "
        ">25=more than 25 degrees. Empty on the map-hole polygons.")),
    "INT": dict(type="string", description=(
        "Whether the coal-bearing interval is complete at this location. Values: T=total "
        "interval present, P=partially eroded, so the thickness shown is a restored value "
        "and carries lower accuracy.")),
    "THICK": dict(type="double", description=(
        "Net thickness in feet of coal beds more than 1 ft thick in the Calico and "
        "A-sequences. Interpolated from 209 drill-hole and measured-section data points, "
        "then contoured: each polygon carries the midpoint of the contour interval "
        "bounding it, so a polygon between the 10 and 20 ft contours is given 15.")),
    "SHTONS_MIL": dict(type="double", description=(
        "Coal resource in the polygon, in **million short tons**. Computed rather than "
        "measured, as polygon area in square metres times 0.0002471 acres per square metre "
        "times THICK in feet times 1,800 short tons per acre-foot, divided by one million; "
        "the 1,800 assumes unbroken coal of bituminous rank. In-place resource at the "
        "mapped cutoffs, not a recoverable or economic tonnage. Zero on the map-hole "
        "polygons.")),
    "ELEV": dict(type="double", description=(
        "Elevation in feet of the Calico sequence boundary structure contour bounding the "
        "polygon, from 166 drill sites. -9999 is a no-data marker, not an elevation.")),
    "LINK": dict(type="string", description=(
        "Hotlink target from the ArcView project the coverage shipped with, an authoring "
        "artifact rather than data about the plateau. Values: K2.APR=the ArcView project "
        "file the hotlink opened, empty=no hotlink on this polygon, which is 25 of the 26 "
        "polygons.")),
    "TR_ID": dict(type="int32", description=(
        "Public Land Survey System identifier encoding meridian, quadrant, range and "
        "township, carried over from the Utah Trust Lands PLSS. Source item name TR-ID.")),
    "PTID": dict(type="string", description=(
        "Point identifier for the drill hole or measured section, as used in Hettinger and "
        "others (1996).")),
    "DEPTHCOALTOP": dict(type="int32", description=("Depth in feet to the top of the first coal. -99 is a no-data marker on 51 of the "
        "209 points.")),
    "DEPTHCOALBOT": dict(type="int32", description=("Depth in feet to the bottom of the lowest coal. -99 is a no-data marker on 51 of "
        "the 209 points.")),
    "TOTALCOAL": dict(type="int32", description=("Total thickness in feet of coal beds more than 1 ft thick in the Calico and "
        "A-sequences at this point, ranging 0 to 164. No point carries the -99 no-data "
        "marker here, so a 0 is a measured absence of coal rather than a missing value.")),
    "SURFELEV": dict(type="int32", description=("Surface elevation in feet at the point. -99 is a no-data marker on 45 of the 209 "
        "points.")),
    "ELEVCSB": dict(type="int32", description=("Elevation in feet of the Calico sequence boundary, derived as SURFELEV minus "
        "DEPTHCSB, or minus ESTDEPTHCSB where the boundary was not reached. -99 is a "
        "no-data marker on 51 of the 209 points.")),
    "DEPTHCSB": dict(type="int32", description=("Depth in feet to the Calico sequence boundary. -99 is a no-data marker on 154 of "
        "the 209 points, which is most of them: the boundary was reached in only 55 "
        "holes, and ESTDEPTHCSB carries the inferred value elsewhere.")),
    "ESTDEPTHCSB": dict(type="int32", description=("Estimated depth in feet to the Calico sequence boundary, inferred by correlation "
        "to nearby drill holes where the boundary was not reached. -99 is a no-data "
        "marker on 106 of the 209 points.")),
    "THKC_D": dict(type="int32", description=("Thickness in feet of the Calico and A-sequences. Source item name THKC-D. -99 is "
        "a no-data marker on 174 of the 209 points.")),
    "THKDT": dict(type="int32", description=("Thickness in feet of the Drip Tank Member. Source item name THKDT. -99 is a "
        "no-data marker on 196 of the 209 points, so this column is populated at only "
        "13 of them.")),
    "NUMBEDSTOTALC": dict(type="int32", description=("Number of coal beds more than 1 ft thick in the total coal-bearing interval, "
        "ranging 0 to 30. No point carries the -99 no-data marker here, so a 0 means "
        "no qualifying beds rather than a missing value.")),
    "THK7_14": dict(type="int32", description=("Net thickness in feet of coal beds 7.5 to 14 ft thick, ranging 0 to 66. Source "
        "item name THK7-14. No point carries the -99 no-data marker here, so a 0 means "
        "no coal in this thickness class rather than a missing value.")),
    "NUM7_14": dict(type="int32", description=("Number of coal beds 7.5 to 14 ft thick, ranging 0 to 7. Source item name NUM7-14. "
        "No point carries the -99 no-data marker here, so a 0 is a real count.")),
    "THK14_20": dict(type="int32", description=("Net thickness in feet of coal beds 14.1 to 20 ft thick, ranging 0 to 71. Source "
        "item name THK14-20. No point carries the -99 no-data marker here, so a 0 means "
        "no coal in this thickness class rather than a missing value.")),
    "NUM14_20": dict(type="int32", description=("Number of coal beds 14.1 to 20 ft thick, ranging 0 to 4. Source item name "
        "NUM14-20. No point carries the -99 no-data marker here, so a 0 is a real count.")),
    "THK20_40": dict(type="int32", description=("Net thickness in feet of coal beds 20 to 40 ft thick, ranging 0 to 76. Source "
        "item name THK20-40. No point carries the -99 no-data marker here, so a 0 means "
        "no coal in this thickness class rather than a missing value.")),
    "NUM20_40": dict(type="int32", description=("Number of coal beds 20 to 40 ft thick, ranging 0 to 3. Source item name NUM20-40. "
        "No point carries the -99 no-data marker here, so a 0 is a real count.")),
    "MAP_NO": dict(type="int32", description=("Identification number for the point on the location map and cross sections of "
        "Plate 1 in Hettinger and others (1996), ranging 1 to 225. Source item name "
        "MAP#. No point carries the -99 no-data marker here.")),
}

# Column meanings that differ from the shared text above, keyed by coverage.
OVERRIDES = {
    "fig22": {
        "OVERB": ("Maximum overburden over the coal, as a class in thousands of feet. "
                  "Values: 0-1=0 to 1,000 ft, 1-2=1,000 to 2,000 ft, 2-3=2,000 to 3,000 ft. "
                  "Nothing deeper appears here because the favourable-area criterion is less "
                  "than 3,000 ft. Empty on the single map-hole polygon."),
        "DIP": ("Inclination of the coal-bearing strata, as a class in degrees. Values: "
                "0-6=0 to 6 degrees, 6-12=6 to 12 degrees. Nothing steeper appears here "
                "because the favourable-area criterion is less than 12 degrees. Empty on the "
                "single map-hole polygon."),
        "REL": ("Reliability of the estimate, set by distance from a data point. Values: "
                "iden=identified, within three miles of a data point, hypo=hypothetical, "
                "further than three miles. Empty on the single map-hole polygon."),
        "INT": ("Whether the coal-bearing interval is complete at this location. Values: "
                "T=total interval present. Empty on the single map-hole polygon."),
        "SURF": ("Surface management status from the Bureau of Land Management land status "
                 "mapping. Values: BLM=Bureau of Land Management, FS=Forest Service, "
                 "NREC=National Recreation Area, STATE=State of Utah, PRIVATE=private. Empty "
                 "on the single map-hole polygon. This is surface ownership, which is often "
                 "not the same as who owns the coal: see COAL_OWN."),
        "COAL_OWN": ("Coal ownership, generalised to the PLSS section. Values: fed=Federal "
                     "coal, nonfed=non-Federal coal. Empty on the single map-hole polygon."),
        "CNTY": ("County. Values: KANE=Kane County, Utah, GARFIELD=Garfield County, Utah. "
                 "Empty on the single map-hole polygon."),
        "QUAD": ("Name of the USGS 7.5-minute quadrangle the polygon falls in. Empty on the "
                 "single map-hole polygon."),
        "TR": ("Township and range, as township number, south, range number, east or west; "
               "33S2E is Township 33 South, Range 2 East. Empty on the single map-hole "
               "polygon."),
    },
    "kjh_thk": {
        "THICK": ("Combined thickness in feet of the Calico and A-sequences, as the contour "
                  "interval bounding the polygon. This is the thickness of the stratigraphic "
                  "interval, not of coal within it. -9999 is a no-data marker on 5 polygons, "
                  "not a thickness."),
    },
    "dip": {
        "DIP": ("Inclination of strata, as a class in degrees, compiled at 1:125,000 from "
                "structure contours and dip measurements on 1:24,000 geologic maps. Values: "
                "0-6=0 to 6 degrees, 6-12=6 to 12 degrees, 12-25=12 to 25 degrees, "
                ">25=more than 25 degrees. Empty on 5 polygons where no value was "
                "assigned."),
    },
    "cb_int": {
        "INT": ("Whether the coal-bearing interval is complete. Values: T=total interval "
                "present, P=partially eroded."),
    },
    "twnshp": {
        "QUAD": ("Original survey quadrant code carried over from the Utah Trust Lands Public "
                 "Land Survey System. Values: 3=survey quadrant 3, 4=survey quadrant 4. The "
                 "source names the column but publishes no table saying which ground each "
                 "quadrant number refers to, so the codes are reproduced as found rather than "
                 "interpreted. This is a PLSS quadrant code, not a 7.5-minute quadrangle name."),
    },
}

# Column types that differ from the shared table, keyed by coverage.
TYPE_OVERRIDES = {
    "twnshp": {"QUAD": "int32"},
}

# values arrays for the coded domains, measured from the ingest.
VALUES = {
    "allcoal": {
        "CNTY": ["", "GARFIELD", "KANE"],
        "OVERB": ["-99", "0-1", "1-2", "2-3", "3-6", ">6"],
        "SURF": ["", "BLM", "FS", "NPS", "NREC", "PRIVATE", "STATE", "WATER"],
        "COAL_OWN": ["", "fed", "nonfed"],
        "REL": ["hole", "hypo", "iden"],
        "DIP": ["", "0-6", "12-25", "6-12", ">25"],
        "INT": ["P", "T"],
    },
    "fig22": {
        "CNTY": ["", "GARFIELD", "KANE"],
        "OVERB": ["", "0-1", "1-2", "2-3"],
        "SURF": ["", "BLM", "FS", "NREC", "PRIVATE", "STATE"],
        "COAL_OWN": ["", "fed", "nonfed"],
        "REL": ["", "hypo", "iden"],
        "DIP": ["", "0-6", "6-12"],
        "INT": ["", "T"],
    },
    "dip": {"DIP": ["", "0-6", "12-25", "6-12", ">25"]},
    "cb_int": {"INT": ["P", "T"]},
    "kdak": {"LINK": ["", "K2.APR"]},
    "twnshp": {"QUAD": [3, 4]},
}

# ---------------------------------------------------------------------------
# Per-coverage specification.
#   attrs   thematic columns, in published order (after _cng_fid, fid)
#   geom    polygon | line | point
# ---------------------------------------------------------------------------

ATTRS_ALLCOAL = ["QUAD", "CNTY", "OVERB", "SURF", "COAL_OWN", "TR", "REL", "DIP",
                 "INT", "THICK", "SHTONS_MIL"]
ATTRS_FIG22 = ["QUAD", "CNTY", "OVERB", "SURF", "COAL_OWN", "TR", "REL", "DIP", "INT"]
ATTRS_KAIPCOAL = ["PTID", "DEPTHCOALTOP", "DEPTHCOALBOT", "TOTALCOAL", "SURFELEV",
                  "ELEVCSB", "DEPTHCSB", "ESTDEPTHCSB", "THKC_D", "THKDT",
                  "NUMBEDSTOTALC", "THK7_14", "NUM7_14", "THK14_20", "NUM14_20",
                  "THK20_40", "NUM20_40", "MAP_NO"]

# Sentence appended to a hex asset description when no column on it is safe to SUM.
NO_SUM = ("No column on this asset is safe to add up across hex rows; the H3 indexes and "
          "`_cng_fid` are the only fields meant to be aggregated.")

OUTCROP_NOTE = ("An outline layer of this kind is normally used as a clip or a mask rather "
                "than queried for attributes.")

COVERAGES = {
    "allcoal": dict(
        geom="polygon", n=5222, attrs=ATTRS_ALLCOAL,
        title="Kaiparowits Plateau coal resources, 1:125,000 (USGS OFR 97-709 allcoal)",
        short="Coal resources of the John Henry Member, Kaiparowits Plateau",
        body=(
            "Per-polygon coal resource for the John Henry Member of the Straight Cliffs "
            "Formation, Kaiparowits Plateau, southern Utah, as assessed for the USGS "
            "National Coal Assessment. **5,222 polygons carrying 72,129.6 million short "
            "tons in place**, of which 65,997.6 is Federal coal and 54,878.8 is classed "
            "identified rather than hypothetical. This is the only published source that "
            "carries Kaiparowits coal tonnage as geometry.\n\n"
            "Each polygon is an intersection of ten mapped layers, so it is uniform in net "
            "coal thickness, overburden, reliability, dip, coal ownership, surface "
            "ownership, county, quadrangle and township-range at once, and the tonnage is "
            "computed for that combination. That makes the layer a query surface: any "
            "subtotal the ten attributes can express is a single `GROUP BY`.\n\n"
            + RESOURCE_CAVEAT + "\n\n" + RELIABILITY_NOTE + "\n\n" + SENTINEL_NOTE),
        hex_note=(
            "One row is one (polygon, cell) pair, so every attribute of a polygon, including "
            "`SHTONS_MIL` and `THICK`, is repeated on every cell that polygon covers. A "
            "resource total taken straight off this asset multiplies each polygon by its "
            "cell count.\n\n"
            "```sql\n"
            "-- correct: collapse to one row per polygon before adding tonnage up\n"
            "SELECT SUM(SHTONS_MIL) FROM (\n"
            "  SELECT DISTINCT _cng_fid, SHTONS_MIL\n"
            "  FROM read_parquet('s3://public-usgs/kaiparowits-coal-resources/allcoal/hex/h0=*/data_0.parquet')\n"
            ");\n"
            "-- wrong: SUM(SHTONS_MIL) over hex rows counts each polygon once per cell\n"
            "-- wrong: AVG(THICK) over hex rows weights each polygon by its cell count\n"
            "```\n\n"
            "The polygons are a planar union and do not overlap, but they are often smaller "
            "than a resolution 8 cell: 5,222 polygons resolve to 4,344 cells, and 1,583 of "
            "those cells carry more than one polygon, up to 16. A cell therefore has no "
            "single overburden class, ownership or reliability, and picking one row per cell "
            "silently discards the rest. Aggregate the rows in a cell rather than choosing "
            "among them."),
        keywords=["coal", "coal resources", "coal tonnage", "net coal thickness",
                  "overburden", "coal ownership", "Kaiparowits Plateau", "Utah",
                  "John Henry Member", "Straight Cliffs Formation", "National Coal Assessment"],
    ),
    "fig22": dict(
        geom="polygon", n=815, attrs=ATTRS_FIG22,
        title="Kaiparowits Plateau areas favourable for underground mining, 1:125,000 (USGS OFR 97-709 fig22)",
        short="Areas geologically favourable for current underground mining technology",
        body=(
            "The 815 polygons of the Kaiparowits Plateau where geologic conditions in the "
            "Calico and A-sequences are more favourable for underground mining technology "
            "of the mid-1990s: coal beds thicker than 3.5 ft, less than 3,000 ft deep, and "
            "dipping less than 12 degrees. Figure 22 of Hettinger and others (1996).\n\n"
            "It carries the same intersection attributes as the `allcoal` coverage apart "
            "from `THICK` and `SHTONS_MIL`, so it says where the favourable ground is but "
            "not how much coal is in it. Join to `allcoal` geometrically for tonnage.\n\n"
            "**Favourable here is geologic, not economic.** The authors note that beds "
            "thinner than 3.5 ft were generally not mined with the longwall technology of "
            "the time and that no more than 14 ft of coal can be economically mined from "
            "thicker beds, and state that additional work is required to determine the "
            "mineability and economics of these deposits. The criteria reflect 1996 "
            "technology and say nothing about present-day economics or permitting.\n\n"
            "One polygon is a map hole with every attribute empty; it is a no-data marker."),
        hex_note=("One row is one (polygon, cell) pair, so every attribute of a polygon is "
                  "repeated on every cell that polygon covers. Use `COUNT(DISTINCT _cng_fid)` "
                  "for a polygon count. " + NO_SUM),
        keywords=["coal", "underground mining", "mineability", "Kaiparowits Plateau", "Utah",
                  "John Henry Member", "Straight Cliffs Formation"],
    ),
    "kaipcoal": dict(
        geom="point", n=209, attrs=ATTRS_KAIPCOAL,
        title="Kaiparowits Plateau coal data points, 1:24,000 (USGS OFR 97-709 kaipcoal)",
        short="Drill-hole and measured-section point data behind the coal mapping",
        body=(
            "The **209 drill holes and measured sections** that every thickness and tonnage "
            "figure in this report is interpolated from. Each point carries depth to the top "
            "and bottom of coal, total coal thickness, surface elevation, the elevation and "
            "depth of the Calico sequence boundary, the thickness of the Calico and "
            "A-sequences and of the Drip Tank Member, the number of coal beds thicker than "
            "1 ft, and net thickness and bed counts for three thickness classes.\n\n"
            "This is the measured data; the `allcoal`, `kjh_thk` and `csb_struct` coverages "
            "are surfaces gridded from it. Where the two disagree, these points are the "
            "observation.\n\n"
            "**`-99` marks no data**, and it poisons an unfiltered average because it is not a "
            "depth or a thickness. It occurs in eight of the seventeen numeric columns: "
            "`DEPTHCOALTOP` and `ELEVCSB` (51 of 209 points each), `DEPTHCOALBOT` (51), "
            "`SURFELEV` (45), `DEPTHCSB` (154), `ESTDEPTHCSB` (106), `THKC_D` (174) and "
            "`THKDT` (196).\n\n"
            "```sql\n"
            "-- correct: exclude the no-data marker before averaging\n"
            "SELECT AVG(DEPTHCSB) FROM read_parquet(\n"
            "  's3://public-usgs/kaiparowits-coal-resources/kaipcoal.parquet')\n"
            "WHERE DEPTHCSB <> -99;\n"
            "```\n\n"
            "The other nine columns never use it: `TOTALCOAL`, `NUMBEDSTOTALC` and the six "
            "per-class thickness and bed-count columns hold a real 0 where there is no coal "
            "in that class, and `MAP_NO` is populated on every point. Filtering those on a "
            "sign test would discard measurements.\n\n"
            "**The coverage ships fewer fields than its own metadata describes.** The FGDC "
            "record defines net thickness and bed counts for the 1 to 2.4, 2.5 to 3.4, 3.5 "
            "to 7 and more than 40 ft classes as well; none of them is present in the "
            "shipped point attribute table, which holds only the 7.5 to 14, 14.1 to 20 and "
            "20 to 40 ft classes. Nothing was dropped in processing, and there is no second "
            "table in the coverage. Those figures exist only in the appendix of the printed "
            "report."),
        hex_note=("Each point falls in exactly one resolution 8 cell, about 0.74 km2, so "
                  "several points can share a cell; they are not deduplicated. One row is "
                  "one (point, cell) pair. " + NO_SUM),
        point_note=("Point observations were hexed to H3 resolution 8, so each point resolves "
                    "to one cell of about 0.74 km2. Points that fall in the same cell are not "
                    "deduplicated."),
        keywords=["coal", "drill holes", "measured sections", "coal thickness",
                  "Kaiparowits Plateau", "Utah", "John Henry Member"],
    ),
    "kjh_thk": dict(
        geom="polygon", n=124, attrs=["THICK"],
        title="Kaiparowits Plateau Calico and A-sequence thickness contours, 1:125,000 (USGS OFR 97-709 kjh_thk)",
        short="Thickness contours of the Calico and A-sequences",
        body=(
            "124 contour polygons of the combined thickness of the Calico and A-sequences "
            "across the Kaiparowits Plateau study area, gridded from the 209 data points of "
            "the `kaipcoal` coverage and clipped to the study-area outline.\n\n"
            "**This is the thickness of the stratigraphic interval, not of the coal in it.** "
            "Net coal thickness is the `THICK` column of the `allcoal` coverage, which is a "
            "different quantity measured over the same ground.\n\n"
            "`THICK = -9999` on 5 polygons is a no-data marker, not a thickness."),
        hex_note=("One row is one (polygon, cell) pair, so `THICK` is repeated on every cell "
                  "a contour polygon covers; deduplicate by `_cng_fid` before averaging, and "
                  "exclude the -9999 no-data marker."),
        keywords=["stratigraphic thickness", "isopach", "Calico sequence",
                  "Kaiparowits Plateau", "Utah"],
    ),
    "csb_struct": dict(
        geom="polygon", n=239, attrs=["ELEV"],
        title="Kaiparowits Plateau Calico sequence boundary structure contours, 1:125,000 (USGS OFR 97-709 csb_struct)",
        short="Structure contours on the Calico sequence boundary",
        body=(
            "239 structure-contour polygons on the Calico sequence boundary, which lies 50 "
            "to 100 ft below the base of the coal-bearing John Henry Member and stands in "
            "for it. Elevations are based on 166 drill sites; along the outcrop, where the "
            "John Henry Member was mapped directly, an inferred elevation was used.\n\n"
            "Together with a surface elevation model this is what the overburden classes of "
            "the `allcoal` coverage were derived from.\n\n"
            "`ELEV = -9999` on one polygon is a no-data marker, not an elevation."),
        hex_note=("One row is one (polygon, cell) pair, so `ELEV` is repeated on every cell a "
                  "contour polygon covers; deduplicate by `_cng_fid` before averaging, and "
                  "exclude the -9999 no-data marker."),
        keywords=["structure contours", "Calico sequence boundary", "subsurface elevation",
                  "Kaiparowits Plateau", "Utah"],
    ),
    "dip": dict(
        geom="polygon", n=57, attrs=["DIP"],
        title="Kaiparowits Plateau inclination of strata, 1:125,000 (USGS OFR 97-709 dip)",
        short="Inclination of strata, in classes",
        body=(
            "57 polygons classing the inclination of strata across the Kaiparowits Plateau "
            "into 0 to 6, 6 to 12, 12 to 25 and more than 25 degrees, compiled at 1:125,000 "
            "from structure contour lines and dip measurements on published 1:24,000 "
            "geologic maps. Used in the assessment to judge mineability from the inclination "
            "of the strata, and carried into the `allcoal` and `fig22` coverages as their "
            "`DIP` column.\n\n"
            "`DIP` is empty on 5 polygons where no class was assigned."),
        hex_note=("One row is one (polygon, cell) pair, so `DIP` is repeated on every cell a "
                  "polygon covers. Use `COUNT(DISTINCT _cng_fid)` for a polygon count. " + NO_SUM),
        keywords=["structural dip", "inclination of strata", "Kaiparowits Plateau", "Utah"],
    ),
    "cb_int": dict(
        geom="polygon", n=6, attrs=["INT"],
        title="Kaiparowits Plateau coal-bearing interval completeness, 1:125,000 (USGS OFR 97-709 cb_int)",
        short="Where the coal-bearing interval is complete or partially eroded",
        body=(
            "6 polygons covering the study area and marking where the coal-bearing interval "
            "is present in full and where erosion has removed part of it. Carried into the "
            "`allcoal` and `fig22` coverages as their `INT` column, and the reason thickness "
            "over the eroded ground is a restored value rather than a measured one.\n\n"
            + OUTCROP_NOTE),
        hex_note=("One row is one (polygon, cell) pair, so `INT` is repeated on every cell a "
                  "polygon covers. " + NO_SUM),
        keywords=["coal-bearing interval", "erosion", "Kaiparowits Plateau", "Utah"],
    ),
    "csb": dict(
        geom="polygon", n=6, attrs=[],
        title="Kaiparowits Plateau study area outline, 1:125,000 (USGS OFR 97-709 csb)",
        short="Outcrop of the Calico sequence boundary, the study-area outline",
        body=(
            "6 polygons outlining the outcrop of the Calico sequence boundary, which defines "
            "the base of the coal-bearing John Henry Member of the Straight Cliffs Formation "
            "east of 112 degrees west. This is the extent of the whole assessment: it is the "
            "clipping polygon every other coverage in this report was cut to. The northern "
            "boundary is the Paunsaugunt fault and Tertiary volcanic rocks.\n\n"
            "Geometry only, with no attributes in the source. " + OUTCROP_NOTE),
        hex_note=("One row is one (polygon, cell) pair. " + NO_SUM),
        keywords=["study area", "outcrop", "Calico sequence boundary", "John Henry Member",
                  "Kaiparowits Plateau", "Utah"],
    ),
    "kdak": dict(
        geom="polygon", n=26, attrs=["LINK"],
        title="Kaiparowits Plateau outline, 1:125,000 (USGS OFR 97-709 kdak)",
        short="Outline of the plateau at the base of the Dakota Sandstone",
        body=(
            "26 polygons outlining the Kaiparowits Plateau east of 112 degrees west, "
            "delineated by the base of the Upper Cretaceous rocks at the Dakota Sandstone. "
            "The northern boundary is the Paunsaugunt fault and Tertiary volcanic rocks.\n\n"
            "The source ships a second copy of this outline in geographic coordinates "
            "(`kdak_dd`); it is the same 26 polygons and was not ingested, since both "
            "reproject to the same thing here.\n\n"
            "The only attribute is an ArcView hotlink left over from the project the "
            "coverage shipped with. " + OUTCROP_NOTE),
        hex_note=("One row is one (polygon, cell) pair. " + NO_SUM),
        keywords=["plateau outline", "Dakota Sandstone", "Kaiparowits Plateau", "Utah"],
    ),
    "kjh_bkw": dict(
        geom="polygon", n=20, attrs=[],
        title="Kaiparowits Plateau base of the Wahweap Formation, 1:125,000 (USGS OFR 97-709 kjh_bkw)",
        short="Outcrop of the base of the Wahweap Formation",
        body=(
            "20 polygons outlining the outcrop of the base of the Wahweap Formation (Upper "
            "Cretaceous) east of 112 degrees west. The area also stands for undivided "
            "Tertiary and Cretaceous rocks: the Osiris Tuff and Wasatch Formation "
            "(Tertiary), Pine Hollow Formation (Tertiary?), Canaan Peak Formation (Tertiary? "
            "and Cretaceous), and Kaiparowits and Wahweap Formations (Cretaceous). The "
            "northern boundary is the Paunsaugunt fault and Tertiary volcanic rocks.\n\n"
            "Geometry only, with no attributes in the source. " + OUTCROP_NOTE),
        hex_note=("One row is one (polygon, cell) pair. " + NO_SUM),
        keywords=["outcrop", "Wahweap Formation", "stratigraphy", "Kaiparowits Plateau", "Utah"],
    ),
    "kjh_kdt": dict(
        geom="polygon", n=11, attrs=[],
        title="Kaiparowits Plateau base of the Drip Tank Member, 1:125,000 (USGS OFR 97-709 kjh_kdt)",
        short="Outcrop of the base of the Drip Tank Member",
        body=(
            "11 polygons outlining the outcrop of the base of the Drip Tank Member of the "
            "Straight Cliffs Formation (Upper Cretaceous) east of 112 degrees west. The Drip "
            "Tank Member overlies the coal-bearing John Henry Member, so this outline is the "
            "top of the coal-bearing interval. The northern boundary is the Paunsaugunt "
            "fault and Tertiary volcanic rocks.\n\n"
            "Geometry only, with no attributes in the source. " + OUTCROP_NOTE),
        hex_note=("One row is one (polygon, cell) pair. " + NO_SUM),
        keywords=["outcrop", "Drip Tank Member", "Straight Cliffs Formation", "stratigraphy",
                  "Kaiparowits Plateau", "Utah"],
    ),
    "structure": dict(
        geom="line", n=327, attrs=[],
        title="Kaiparowits Plateau structural features, 1:125,000 (USGS OFR 97-709 structure)",
        short="Synclines, anticlines, folds and faults",
        body=(
            "327 lines showing the structural features of the Kaiparowits Plateau: "
            "synclines, anticlines, folds and faults, as drawn in figure 9 of Hettinger and "
            "others (1996).\n\n"
            "**The source carries no attribute distinguishing one kind of feature from "
            "another.** The arc attribute table holds nothing but ARC/INFO topology, so "
            "which lines are faults and which are fold axes exists only in the printed "
            "figure. Nothing was dropped in processing."),
        hex_note=("One row is one (line, cell) pair. " + NO_SUM),
        line_note=True,
        keywords=["faults", "folds", "synclines", "anticlines", "structural geology",
                  "Kaiparowits Plateau", "Utah"],
    ),
    "m_adit": dict(
        geom="line", n=50, attrs=[],
        title="Kaiparowits Plateau coal mine adits, 1:125,000 (USGS OFR 97-709 m_adit)",
        short="Coal mine adits",
        body=(
            "50 lines marking coal mine adits, the horizontal entries driven into the "
            "hillside to reach a coal bed, within the Kaiparowits Plateau study area, as "
            "shown in figure 1 of Hettinger and others (1996). They are the record of "
            "historical mining on the plateau.\n\n"
            "**The source carries no attributes at all**: no mine name, no date, no status. "
            "The arc attribute table holds nothing but ARC/INFO topology. Nothing was "
            "dropped in processing."),
        hex_note=("One row is one (line, cell) pair. " + NO_SUM),
        line_note=True,
        keywords=["coal mines", "adits", "mining history", "Kaiparowits Plateau", "Utah"],
    ),
    "twnshp": dict(
        geom="polygon", n=190, attrs=["TR_ID", "QUAD"],
        title="Kaiparowits Plateau township and range, 1:24,000 (USGS OFR 97-709 twnshp)",
        short="Public Land Survey System township and range",
        body=(
            "190 township and range polygons in and around the Kaiparowits Plateau, "
            "extracted and dissolved from a Public Land Survey System coverage for the whole "
            "of Utah supplied by the Utah Trust Lands in 1995.\n\n"
            "This is the survey grid the coal ownership of the `allcoal` coverage was "
            "generalised onto, where a whole section takes whatever ownership covers 50 "
            "percent or more of it. It is included as the reference frame for that "
            "generalisation. For current PLSS data, use an authoritative present-day source "
            "rather than this 1995 extract."),
        hex_note=("One row is one (polygon, cell) pair, so `TR_ID` and `QUAD` are repeated on "
                  "every cell a township covers. " + NO_SUM),
        keywords=["Public Land Survey System", "township and range", "PLSS",
                  "Kaiparowits Plateau", "Utah"],
    ),
}

LINE_NOTE = ("Line features were hexed to H3 resolution 8 by buffering each segment by the "
             "H3 cell circumradius before polyfill, so the cells trace a corridor along the "
             "line rather than its exact path.")


def columns_for(cov: str, names: list[str], *, geometry: bool, hexed: bool, lean: bool):
    """Emit table:columns for one asset, identically across assets of a collection."""
    out = []
    order = ["_cng_fid", "fid"] + names
    if geometry:
        order = order + ["geom"]
    if hexed:
        order = order + ["h8", "h0"]
    for name in order:
        spec = COLUMNS[name]
        ctype = TYPE_OVERRIDES.get(cov, {}).get(name, spec["type"])
        col = {"name": name, "type": ctype}
        if not lean:
            desc = OVERRIDES.get(cov, {}).get(name, spec["description"])
            col["description"] = desc
        vals = VALUES.get(cov, {}).get(name)
        if vals is not None:
            col["values"] = vals
        out.append(col)
    return out


def build(cov: str, spec: dict, bbox: list[float], created: dict) -> dict:
    attrs = spec["attrs"]
    geom_kind = spec["geom"]
    desc = spec["body"] + "\n\n"
    if geom_kind == "line":
        desc += LINE_NOTE + "\n\n"
    if spec.get("point_note"):
        desc += spec["point_note"] + "\n\n"
    desc += PROVENANCE

    doc = {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
            "https://stac-extensions.github.io/version/v1.2.0/schema.json",
        ],
        "id": f"usgs-kaiparowits-{cov.replace('_', '-')}",
        "title": spec["title"],
        "description": desc,
        "license": "public-domain",
        "version": "1",
        "sci:citation": CITATION,
        "created": created["collection"],
        "updated": created["collection"],
        "providers": PROVIDERS,
        "extent": {
            "spatial": {"bbox": [bbox]},
            "temporal": {"interval": [TEMPORAL]},
        },
        "keywords": spec["keywords"],
        "links": [
            {"rel": "self", "href": f"{PREFIX}/{cov}/stac-collection.json",
             "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": PARENT, "type": "application/json"},
            {"rel": "license", "href": LICENSE_URL, "type": "text/html",
             "title": "USGS public domain / U.S. Government works"},
            {"rel": "about", "href": LANDING, "type": "text/html",
             "title": "USGS Open-File Report 97-709"},
            {"rel": "describedby", "href": APPENDIX, "type": "text/html",
             "title": "Coverage descriptions (Appendix 1)"},
        ],
        "assets": {
            f"{cov}-parquet": {
                "href": f"{PREFIX}/{cov}.parquet",
                "type": "application/x-parquet",
                "title": f"{spec['short']} (GeoParquet)",
                "roles": ["data"],
                "created": created["parquet"],
                "description": (
                    f"One row per source feature: {spec['n']} rows, {spec['n']} distinct "
                    "`_cng_fid`, so no deduplication is needed before aggregating on this "
                    "asset."),
                "table:columns": columns_for(cov, attrs, geometry=True, hexed=False, lean=False),
            },
            f"{cov}-pmtiles": {
                "href": f"{PREFIX}/{cov}.pmtiles",
                "type": "application/vnd.pmtiles",
                "title": f"{spec['short']} (PMTiles)",
                "roles": ["visual"],
                "created": created["pmtiles"],
                "vector:layers": [cov],
                "table:columns": columns_for(cov, attrs, geometry=False, hexed=False, lean=True),
            },
            f"{cov}-hex": {
                "href": f"{PREFIX}/{cov}/hex/h0=*/data_0.parquet",
                "type": "application/x-parquet",
                "title": f"{spec['short']} as H3 resolution 8 cells",
                "roles": ["data"],
                "created": created["hex"],
                "description": spec["hex_note"],
                "h3:native_resolution": 8,
                "h3:parent_resolutions": [0],
                "table:columns": columns_for(cov, attrs, geometry=False, hexed=True, lean=False),
            },
        },
    }
    return doc


def build_parent(bbox: list[float], created: str) -> dict:
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
            "https://stac-extensions.github.io/version/v1.2.0/schema.json",
        ],
        "id": "usgs-kaiparowits-coal-resources",
        "title": "Kaiparowits Plateau coal resources (USGS Open-File Report 97-709)",
        "description": (
            "The GIS layers behind the USGS National Coal Assessment of the John Henry "
            "Member of the Straight Cliffs Formation, Kaiparowits Plateau, southern Utah. "
            "**14 coverages** from USGS Open-File Report 97-709, each published as its own "
            "collection.\n\n"
            "The layer that carries the numbers is **`allcoal`**: 5,222 polygons holding "
            "**72,129.6 million short tons of coal in place**, attributed by net coal "
            "thickness, overburden, reliability, dip, coal ownership, surface ownership, "
            "county, quadrangle and township-range at once. This is the only published "
            "source that carries Kaiparowits coal tonnage as geometry.\n\n"
            + RESOURCE_CAVEAT + "\n\n"
            "The rest of the report is here too: `fig22` (ground favourable for underground "
            "mining), `kaipcoal` (the 209 drill holes and measured sections everything is "
            "interpolated from), `kjh_thk` and `csb_struct` (thickness and structure "
            "contours), `dip`, `cb_int`, `structure`, `m_adit`, `twnshp`, and the "
            "stratigraphic outlines `csb`, `kdak`, `kjh_bkw` and `kjh_kdt`. The five "
            "basemap coverages the archive also ships (`bb_surf`, `county`, `roads`, "
            "`ut_st_dd`, `ut_fedl_dd`) were not ingested: the catalog already carries "
            "better versions of all of them.\n\n"
            "A fixed 1997 vintage. Upstream has never revised it and will not.\n\n"
            + PROVENANCE),
        "license": "public-domain",
        "version": "1",
        "sci:citation": CITATION,
        "created": created,
        "updated": created,
        "providers": PROVIDERS,
        "extent": {
            "spatial": {"bbox": [bbox]},
            "temporal": {"interval": [TEMPORAL]},
        },
        "keywords": ["coal", "coal resources", "coal tonnage", "energy resources",
                     "National Coal Assessment", "Kaiparowits Plateau", "Utah",
                     "John Henry Member", "Straight Cliffs Formation", "USGS"],
        "links": [
            {"rel": "self", "href": PARENT, "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "license", "href": LICENSE_URL, "type": "text/html",
             "title": "USGS public domain / U.S. Government works"},
            {"rel": "about", "href": LANDING, "type": "text/html",
             "title": "USGS Open-File Report 97-709"},
        ] + [
            {"rel": "child", "href": f"{PREFIX}/{cov}/stac-collection.json",
             "type": "application/json", "title": COVERAGES[cov]["title"]}
            for cov in COVERAGES
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--facts", required=True,
                    help="JSON of measured per-coverage bbox and asset timestamps")
    args = ap.parse_args()

    facts = json.load(open(args.facts))
    os.makedirs(args.out, exist_ok=True)

    for cov, spec in COVERAGES.items():
        f = facts[cov]
        doc = build(cov, spec, f["bbox"], f["created"])
        path = os.path.join(args.out, f"{cov}.json")
        with open(path, "w") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print(f"  wrote {path}")

    parent = build_parent(facts["_parent"]["bbox"], facts["_parent"]["created"])
    path = os.path.join(args.out, "_parent.json")
    with open(path, "w") as fh:
        json.dump(parent, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"  wrote {path}")


if __name__ == "__main__":
    main()
