#!/usr/bin/env python3
"""Emit the two derived #588 collections to /tmp for rclone upload (AGENTS.md Hard Boundary
1 — this repo never contains STAC JSON or README files):

  ira-road-proximity  — non-spatial fact table: acres of Inventoried Roadless Area within
                        each buffer distance of each road stratum, on each denominator.
                        This is the artifact behind every number in the write-up.
  ira-road-distance   — res-10 hex carrying distance-to-nearest-road per cell, the join
                        product #587 needs for its ignition-density gradient.

Counts and headline figures come from `_measured.json`, written from the consolidation job's
output. verify-stac.py checks declared `values` against SELECT DISTINCT in the data.
"""
import json
import os

BUCKET = "public-usfs"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
IRA = f"{BASE}/roadless-areas-2001/stac-collection.json"

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "_measured.json")) as f:
    M = json.load(f)

BBOX = [-150.008, 18.246, -65.707, 61.519]      # the IRA layer's extent (#584)
LADDER = [50.0, 100.0, 200.0, 400.0, 804.672, 1000.0, 1609.344, 2414.016, 3218.688]
STRATA = ["roadcore-all", "roadcore-ml1only", "roadcore-ml2to5",
          "tiger-all", "tiger-drivable", "union-deis"]
REGIONS = ["AK", "CONUS", "PR"]
BANDS = ["0-50m", "50-100m", "100-200m", "200-400m", "400-805m", "805-1000m",
         "1000-1609m", "1609-2414m", "2414-3219m", ">3218m"]

STRATUM_DEF = (
    "Which set of roads the buffer was built from. This is the column that decides what a "
    "proximity figure means, so no number from this table should be quoted without it. "
    "Valid values: "
    "roadcore-all=every National Forest System road with geometry (359,259 segments); "
    "roadcore-ml2to5=NFS roads at operational maintenance level 2-5, i.e. excluding the "
    "closed level-1 network — the defensible reading of 'existing road'; "
    "roadcore-ml1only=level-1 NFS roads alone, which are closed to motor vehicles and held "
    "in storage between intermittent uses (103,945 mi, 28.2% of the system); "
    "tiger-drivable=Census TIGER/Line 2025 roads excluding the four pedestrian MTFCC classes "
    "S1710/S1720/S1820/S1830; "
    "union-deis=roadcore-all combined with tiger-drivable — the closest reproducible "
    "equivalent of the road set the 2026 Roadless Rule DEIS buffered, namely 'National Forest "
    "System roads and other authorized public roads' (Vol I fn. 10). This is the stratum the "
    "agency's 11.3M and 13.3M figures should be compared against; "
    "tiger-all=every TIGER road including the pedestrian classes — informational only, since "
    "36 CFR 294.11 defines a road as a motor vehicle travelway."
)

D_DEF = (
    "Buffer distance in metres, measured either side of the road centreline. The ladder "
    "brackets the two distances the agency published, so a result does not hinge on one "
    "reverse-engineered number, and doubles as the distance bands for the ignition-density "
    "gradient in #587. Valid values: "
    "50=50 m; 100=100 m; 200=200 m; 400=400 m; "
    "804.672=0.5 mile, the agency's own definition of 'near' (DEIS Vol I p. 41 fn. 10); "
    "1000=1 km; "
    "1609.344=1 mile, the Economic Analysis's second published figure; "
    "2414.016=1.5 miles; 3218.688=2 miles, the widest distance computed."
)

PROX_COLUMNS = [
    ("road_stratum", "string", STRATUM_DEF, STRATA),
    ("region", "string",
     "Equal-area projection region the geometry was computed in. Valid values: "
     "CONUS=conterminous United States, EPSG:5070 NAD83 Conus Albers; "
     "AK=Alaska, EPSG:3338 NAD83 Alaska Albers; "
     "PR=Puerto Rico, EPSG:32161 NAD83 Puerto Rico and Virgin Islands. "
     "Buffering and area were both computed in these projections, never in degrees.",
     REGIONS),
    ("_cng_fid", "int64",
     "Feature identifier of the INVENTORIED ROADLESS AREA polygon this row describes, joining "
     "to _cng_fid in the roadless-areas-2001 collection. It is not an identifier of this "
     "table's own rows: this table's grain is (road_stratum, region, _cng_fid, d_m), so "
     "_cng_fid repeats once per stratum and distance.", None),
    ("STATE", "string",
     "Two-letter state or territory code of the roadless area, carried from "
     "roadless-areas-2001. The 2026 proposed rescission excludes Idaho and Colorado, so this "
     "is the column the rule_affected flag is derived from.", None),
    ("CATEGORY", "string",
     "Pre-2001 forest-plan category of the roadless area, carried from roadless-areas-2001. "
     "Valid values: 1B=road construction and reconstruction prohibited, 1B-1=recommended for "
     "wilderness designation and prohibited, 1C=not prohibited under the pre-rule plan. "
     "Category 1C does NOT mean the 2001 rule permitted road construction — it records forest "
     "plan direction that predates the rule.", ["1B", "1B-1", "1C"]),
    ("rule_affected", "bool",
     "True where the roadless area lies outside Idaho and Colorado, which adopted their own "
     "state-specific roadless rules in 2008 and 2012 and are excluded from the 2026 proposed "
     "rescission. Filtering on this gives the 44,701,002-acre rule-affected base.", None),
    ("ira_acres", "float64",
     "Total acreage of the whole roadless area polygon, as published by the Forest Service. "
     "**Repeated on every row for that polygon** — one per stratum and distance — so it must "
     "be deduplicated on _cng_fid before summing. Present so a per-polygon share can be "
     "computed without a join back to roadless-areas-2001.", None),
    ("d_m", "float64", D_DEF, LADDER),
    ("acres_within", "float64",
     "Acres of this roadless area polygon lying within d_m of a road in this stratum, computed "
     "as ST_Area(ST_Intersection(polygon, ST_Buffer(union_of_roads, d))) in the region's "
     "equal-area projection. Roads are unioned before buffering, so overlapping buffers are "
     "not double-counted. Summing this column over rule_affected polygons at one "
     "(stratum, d_m) gives the acreage against the 44,701,002-acre base.", None),
    ("pae_acres_within", "float64",
     "The same measurement taken against the DEIS's 'potentially affected environment' rather "
     "than the whole polygon: the polygon intersected with National Forest System surface "
     "ownership, minus PAD-US 4.1 wilderness, wilderness study areas and wild and scenic "
     "river designations. That reconstruction totals 39,962,728 acres against the DEIS's "
     "stated 40,049,537 (-0.22%). This is the base the agency's 11.3M-acre figure uses. NULL "
     "where the polygon has no reconstructed PAE geometry.", None),
    ("road_miles_inside", "float64",
     "Miles of road in this stratum lying inside the roadless area polygon itself. **Repeated "
     "on every distance row** for a (stratum, polygon) pair — it does not vary with d_m — so "
     "deduplicate before summing. The Economic Analysis reports about 17,000 miles inside "
     "roadless areas outside Idaho and Colorado, which this column tests.", None),
]

DIST_COLUMNS = [
    ("_cng_fid", "int64",
     "Feature identifier of the roadless area polygon containing this cell, joining to "
     "_cng_fid in the roadless-areas-2001 collection. One polygon covers many cells, so this "
     "repeats; it is the dedup key for any per-polygon attribute.", None),
    ("STATE", "string", "Two-letter state or territory code of the roadless area.", None),
    ("rule_affected", "bool",
     "True where the roadless area lies outside Idaho and Colorado and is therefore within "
     "the scope of the 2026 proposed rescission.", None),
    ("dist_m_roadcore", "float64",
     "Metres from the cell centre to the nearest National Forest System road of any "
     "maintenance level, measured in the region's equal-area projection. NULL where no NFS "
     "road lies within 3,380 m of the containing roadless area.", None),
    ("dist_m_roadcore_ml2to5", "float64",
     "Metres to the nearest NFS road at maintenance level 2-5 — the network excluding closed, "
     "stored level-1 roads. Comparing this against dist_m_roadcore is the cleanest way to see "
     "how much apparent road access depends on roads that are closed to motor vehicles.", None),
    ("dist_m_all", "float64",
     "Metres to the nearest road in the DEIS-equivalent set: NFS roads plus Census TIGER "
     "drivable roads. This is the column the band label is derived from and the one to use "
     "for a road-proximity gradient.", None),
    ("band", "string",
     "Distance band label derived from dist_m_all, for grouping without re-binning. The "
     "400-805m band closes at 804.672 m = 0.5 mile, the agency's definition of 'near'; the "
     "1000-1609m band closes at 1609.344 m = 1 mile. Valid values: 0-50m, 50-100m, 100-200m, "
     "200-400m, 400-805m, 805-1000m, 1000-1609m, 1609-2414m, 2414-3219m, >3218m=beyond the "
     "widest distance computed, including cells with no road in range.", BANDS),
]

H3_COLUMNS = [
    ("h10", "uint64", "H3 cell identifier at resolution 10 (native resolution).", None),
    ("h9", "uint64", "H3 cell identifier at resolution 9.", None),
    ("h8", "uint64",
     "H3 cell identifier at resolution 8 — the catalog's universal join key. Join on this to "
     "reach the FPA-FOD ignition hex, MTBS severity, or any other res-8 catalog layer.", None),
    ("h0", "int64",
     "H3 cell identifier at resolution 0, used as the partition key for hive-partitioned "
     "reads.", None),
]


def cols(entries, lean=False):
    out = []
    for name, typ, desc, values in entries:
        c = {"name": name, "type": typ}
        if not lean:
            c["description"] = desc
        if values is not None:
            c["values"] = values
        out.append(c)
    return out


def links(dataset, title):
    return [
        {"rel": "self", "href": f"{BASE}/{dataset}/stac-collection.json",
         "type": "application/json"},
        {"rel": "root", "href": ROOT, "type": "application/json"},
        {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
        {"rel": "license", "href": "https://www.usa.gov/government-works",
         "type": "text/html", "title": "US Government work — public domain"},
        {"rel": "related", "href": IRA, "type": "application/json",
         "title": "Inventoried Roadless Areas (2001 Roadless Rule) — the polygons measured"},
        {"rel": "related", "href": f"{BASE}/roadcore-fs/stac-collection.json",
         "type": "application/json", "title": "USFS RoadCore — the NFS road input"},
        {"rel": "related",
         "href": "https://s3-west.nrp-nautilus.io/public-census/census-2025/roads/stac-collection.json",
         "type": "application/json", "title": "Census TIGER/Line Roads 2025 — the non-NFS road input"},
    ]


METHOD = (
    "**Method.** Every acreage is true-geometry: "
    "`ST_Area(ST_Intersection(polygon, ST_Buffer(ST_Union_Agg(roads), d)))`, computed in an "
    "equal-area projection chosen per region (EPSG:5070 conterminous, 3338 Alaska, 32161 "
    "Puerto Rico), never in degrees and never on H3 adjacency — a resolution-8 cell is about "
    "0.7 km2, far coarser than the 805 m buffer the question turns on. The projections were "
    "gated before any buffering by reconciling computed polygon area against the Forest "
    "Service's published ACRES column: the deviation is under 0.001% in all three regions. "
    "Roads are unioned before buffering, so overlapping buffers are never double-counted.\n\n"
    "**What this cannot cover.** 36 CFR 294.11 defines a road more broadly than the layer the "
    "DEIS buffered — it includes unclassified and temporary roads — and the Forest Service "
    "maintains no national database of temporary roads (DEIS fn. 20). A buffer built from the "
    "regulatory definition would cover more ground than any figure here. Separately, 8,204 "
    "RoadCore records (4,745 official miles, 1.3% of the system) have no geometry in the "
    "source and cannot be buffered by anyone, the agency included."
)


def proximity_collection():
    ds = "ira-road-proximity"
    return {
        "stac_version": "1.0.0",
        "type": "Collection",
        "id": ds,
        "title": "Roadless Area road-proximity acreage by distance, road stratum and denominator",
        "description":
            "Acres of Inventoried Roadless Area lying within each of nine buffer distances of "
            "each of six road strata, on three different denominators — the fact table behind "
            "the reproduction of the 2026 Roadless Rule rescission's claim that "
            "\"more than a quarter of these lands — 11.3 million acres — are already near "
            "existing roads\".\n\n"
            "**Three numbers, three different bases, and they are not interchangeable.** The "
            "DEIS reports 11.3M acres within 0.5 mile against a 40,049,537-acre potentially "
            "affected environment; the Economic Analysis reports 13.3M acres for the same "
            "buffer against the 44,701,002-acre rule-affected base, and 22.3M within 1 mile. "
            "Both bases are carried here (acres_within and pae_acres_within) so a figure can "
            "never be quoted against the wrong denominator.\n\n"
            "**Maintenance level changes the answer.** Level-1 National Forest System roads "
            "are closed to motor vehicles and held in storage between intermittent uses — "
            "103,945 miles, 28.2% of the system. The roadcore-ml1only and roadcore-ml2to5 "
            "strata exist so the effect of counting them as 'existing roads' is measurable "
            "rather than assumed.\n\n" + METHOD,
        "license": "public-domain",
        "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json"],
        "extent": {"spatial": {"bbox": [BBOX]},
                   "temporal": {"interval": [["2001-01-12T00:00:00Z", None]]}},
        "providers": [
            {"name": "Boettiger Lab / cirrus", "roles": ["producer", "processor", "host"],
             "url": f"{BASE}/"},
            {"name": "USDA Forest Service", "roles": ["licensor"],
             "url": "https://data.fs.usda.gov/geodata/edw/datasets.php"},
        ],
        "links": links(ds, "road proximity"),
        "assets": {
            f"{ds}-parquet": {
                "href": f"{BASE}/{ds}.parquet",
                "type": "application/x-parquet",
                "title": "Roadless area road-proximity acreage — Parquet",
                "description":
                    "Non-spatial fact table. Grain is (road_stratum, region, _cng_fid, d_m). "
                    "ira_acres and road_miles_inside are per-polygon values repeated across "
                    "every distance row, so deduplicate on _cng_fid before summing them; "
                    "acres_within and pae_acres_within vary per row and are safe to SUM within "
                    "a single (road_stratum, d_m).",
                "roles": ["data"],
                "table:columns": cols(PROX_COLUMNS),
            },
        },
    }


def distance_collection():
    ds = "ira-road-distance"
    n_rows = M.get("n_dist_hex_rows")
    return {
        "stac_version": "1.0.0",
        "type": "Collection",
        "id": ds,
        "title": "Distance to nearest road within Inventoried Roadless Areas — H3 resolution 10",
        "description":
            "Distance from each H3 resolution-10 cell inside an Inventoried Roadless Area to "
            "the nearest road, for three road definitions. Built as the join product for the "
            "ignition-density gradient in #587: h8 is present, so this joins directly to the "
            "FPA-FOD ignition hex and to any other resolution-8 catalog layer.\n\n"
            "**Built by joining onto the published roadless-areas-2001 hex, not by a new "
            "polyfill** — the cell set is exactly #584's, so the two layers align by "
            "construction.\n\n"
            "**This asset is a cross-check and a join key, not the source of the headline "
            "acreage.** A resolution-10 cell is about 0.015 km2, fine enough to integrate area "
            "to roughly 0.25%, but the authoritative acreage lives in the ira-road-proximity "
            "collection and is computed on true geometry. Use dist_m_all for a gradient; use "
            "the other collection for a number anyone will quote.\n\n" + METHOD,
        "license": "public-domain",
        "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json"],
        "extent": {"spatial": {"bbox": [BBOX]},
                   "temporal": {"interval": [["2001-01-12T00:00:00Z", None]]}},
        "providers": [
            {"name": "Boettiger Lab / cirrus", "roles": ["producer", "processor", "host"],
             "url": f"{BASE}/"},
            {"name": "USDA Forest Service", "roles": ["licensor"],
             "url": "https://data.fs.usda.gov/geodata/edw/datasets.php"},
        ],
        "links": links(ds, "road distance"),
        "assets": {
            f"{ds}-hex": {
                "href": f"{BASE}/{ds}/hex/h0=*/data_0.parquet",
                "type": "application/x-parquet",
                "title": "Distance to nearest road within roadless areas — H3 resolution 10",
                "description":
                    (f"One row per resolution-10 cell inside a roadless area"
                     + (f" ({n_rows:,} rows)." if n_rows else ".")
                     + " Distances are per-cell and vary row to row, so they are safe to "
                     "aggregate directly (MIN, AVG, histogram by band) — unlike a per-feature "
                     "total, there is no repeated-value trap here. The one repeated column is "
                     "_cng_fid, which identifies the containing roadless area and is the dedup "
                     "key if you need per-polygon rather than per-cell statistics. "
                     "For the area of a selection use the H3 footprint of its distinct cells, "
                     "not a count of rows."),
                "roles": ["data"],
                "h3:native_resolution": 10,
                "h3:parent_resolutions": [9, 8, 0],
                "table:columns": cols(DIST_COLUMNS) + cols(H3_COLUMNS),
            },
        },
    }


if __name__ == "__main__":
    for name, obj in (("ira-road-proximity", proximity_collection()),
                      ("ira-road-distance", distance_collection())):
        out = f"/tmp/{name}-stac.json"
        with open(out, "w") as f:
            json.dump(obj, f, indent=2)
            f.write("\n")
        print("wrote", out)
