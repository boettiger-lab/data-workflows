#!/usr/bin/env python3
"""Emit the roadless-land-status dataset collection, and patch the live public-usfs bucket
collection and README with it, writing all three to /tmp for rclone upload (AGENTS.md Hard
Boundary 1: this repo never contains STAC JSON or README files).

The bucket collection and README are read live from S3 and patched, not regenerated, because
other ingests (#585, #588, #591) own sections of them.

One source schema (COLUMNS) is written identically to the flat GeoParquet and the hex so the
mcp-data-server#303 per-column fold never drops a variant. PMTiles gets the lean form.
Every number below was measured on the published data on 2026-10-15 (see BUILD.md).
"""
import json
import urllib.request

BUCKET = "public-usfs"
DATASET = "roadless-land-status"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
BBOX = [-150.0079284, 18.03374337, -65.70660199, 61.51899038]
ZENODO = "https://zenodo.org/records/23265719"
DOI = "10.5281/zenodo.23265719"
# The first build used v1.0, Zenodo 23105982; same concept record 23105981.
PREV_ZENODO = "https://zenodo.org/records/23105982"
TITLE = "National Forest System Roadless Land-Status Strata (Roadless Rule exposure)"

STATE_NAMES = {
    "AK": "Alaska", "AL": "Alabama", "AR": "Arkansas", "AZ": "Arizona", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "FL": "Florida", "GA": "Georgia", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "MA": "Massachusetts",
    "ME": "Maine", "MI": "Michigan", "MN": "Minnesota", "MO": "Missouri", "MS": "Mississippi",
    "MT": "Montana", "NC": "North Carolina", "ND": "North Dakota", "NE": "Nebraska",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NV": "Nevada", "NY": "New York", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "PR": "Puerto Rico",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VA": "Virginia", "VT": "Vermont", "WA": "Washington", "WI": "Wisconsin",
    "WV": "West Virginia", "WY": "Wyoming",
}
STATES = sorted(STATE_NAMES)
STATE_LIST = ", ".join(f"{k}={v}" for k, v in sorted(STATE_NAMES.items()))
REGIONS = ["01", "02", "03", "04", "05", "06", "08", "09", "10", "NA"]
STRATA = ["N", "R1", "R1s", "R2", "R3"]

STRATUM_DEF = (
    "Land-status stratum, the main field of this layer. Values: "
    "N=National Forest System land outside any roadless area, "
    "R1=roadless land that is also covered by an independent federal protection (Wilderness, "
    "Wilderness Study Area, Potential Wilderness Area, a river corridor classified Wild under the "
    "Wild and Scenic Rivers Act, National Monument, National Volcanic Monument, or the Tongass "
    "LUD II Management Area), "
    "R1s=Colorado or Idaho roadless land governed by those states' own federal roadless rules and "
    "not already in R1, "
    "R2=2001 inventoried roadless land, outside Colorado and Idaho and not in R1, where the forest "
    "plan in force before 2001 prohibited road construction (Forest Service roadless category 1B or "
    "1B-1), "
    "R3=all remaining 2001 inventoried roadless land, the land exposed to a rescission of the 2001 "
    "Roadless Rule. "
    "Each piece of land falls in exactly one stratum, assigned in the order R1, R1s, R2, R3. "
    "R1, R1s and R2 together are the roadless land that stays protected from new roads without the "
    "2001 rule; R3 is the exposed remainder."
)

COLUMNS = [
    ("_cng_fid", "int64",
     "Stable per-feature identifier assigned during conversion, unique on each of the 702 rows. "
     "Use it as the row key.", None),
    ("OGC_FID", "int64", "Sequential row identifier carried over from the source shapefile.", None),
    ("STATE", "string",
     "Two-letter state or territory abbreviation. 45 states plus Puerto Rico. Connecticut and New "
     "Jersey carry only slivers under 150 acres. Values: " + STATE_LIST,
     STATES),
    ("ST_NAME", "string", "Full state or territory name matching STATE.", None),
    ("FOR_ID", "string",
     "Forest Service identifier of the administrative national forest, a bracketed GUID. 112 "
     "distinct values, one per FOR_NAME, including the one for Unassigned NFS. Treat as a label, "
     "not a number.", None),
    ("FOR_NAME", "string",
     "Name of the administrative national forest or grassland. 111 forest names plus "
     "'Unassigned NFS', which the producer gives to 113 pieces (57,988 acres in all) that fall "
     "outside every administrative forest boundary. One of them is a 55,515-acre N piece in Utah; "
     "the rest are under 65 acres each and are boundary slivers.", None),
    ("REGION", "string",
     "Forest Service region as a two-digit string. Values: 01=Northern, 02=Rocky Mountain, "
     "03=Southwestern, 04=Intermountain, 05=Pacific Southwest, 06=Pacific Northwest, 08=Southern, "
     "09=Eastern, 10=Alaska, NA=no region (the Unassigned NFS rows). There is no region 07.", REGIONS),
    ("STRATUM", "string", STRATUM_DEF, STRATA),
    ("IRA_CAT", "string",
     "Unpopulated: empty on every row. The 2001 inventory's forest-plan field was used to separate "
     "R2 from R3 but was not carried into this layer; use STRATUM instead.", None),
    ("ACRES", "float64",
     "Area of the row's polygon in acres, computed by the producer on an equal-area projection. "
     "Use this, not row counts, for area totals. All 702 rows sum to 193,201,589 acres.", None),
    ("SRC_ID", "int64",
     "Identifier of the producer's original analysis feature, one per state, forest and stratum. "
     "Unique on every row (702 values).", None),
    ("PART_ID", "int64",
     "Part number within SRC_ID, for features the producer splits for the shapefile format. 0 on "
     "every row in this version: no feature is split.", None),
]

H3_COLUMNS = [
    ("h10", "uint64", "H3 cell identifier at resolution 10.", None),
    ("h9", "uint64", "H3 cell identifier at resolution 9.", None),
    ("h8", "uint64", "H3 cell identifier at resolution 8.", None),
    ("h0", "int64",
     "H3 cell identifier at resolution 0, used as the partition key for hive-partitioned reads.", None),
]

GEOM = ("geom", "geometry", "Feature geometry (GeoParquet), in EPSG:4326.", None)


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


HEX_NOTE = (
    "One row per (polygon, resolution 10 cell) pair: 52,916,466 rows for 702 polygons. Every "
    "attribute is repeated on every cell the polygon covers, so totals go through _cng_fid:\n\n"
    "```sql\n"
    "-- correct: exposed roadless acres, 23,848,420\n"
    "SELECT SUM(ACRES) FROM (SELECT DISTINCT _cng_fid, ACRES\n"
    "                        FROM read_parquet('…/hex/h0=*/data_0.parquet')\n"
    "                        WHERE STRATUM = 'R3');\n"
    "-- wrong: COUNT(*) counts cells, not polygons\n"
    "-- wrong: SUM(ACRES) over raw rows multiplies each polygon's acres by its cell count\n"
    "```\n\n"
    "Cells on the boundary between two strata appear once for each, so a cell can carry more than "
    "one stratum (123,243 such cells). For the area of a selection, the H3 footprint of its "
    "distinct cells agrees with ACRES to within 0.75% for every stratum except R1 (2.7% higher, "
    "from many sliver polygons each occupying at least one whole cell). Join to other catalog "
    "datasets on h8."
)

DESCRIPTION = (
    "A single classification of National Forest System land into five strata for analysing the "
    "proposed rescission of the 2001 Roadless Rule: which roadless land would lose its only "
    "protection from new roads, and which stays protected under other authorities. 702 polygons "
    "covering 193,201,589 acres in 45 states and Puerto Rico, produced by Kyle Manley (CIRES, "
    "University of Colorado Boulder) for the recreation part of a Roadless Rule analysis, and "
    "published on Zenodo on 2026-10-09 (doi:" + DOI + "). This version replaces version 1.0 "
    "(Zenodo 23105982), which this catalog published until 2026-10-15; see the end of this "
    "description for what changed.\n\n"
    "STRATUM is the field that carries the analysis; the other columns give state, national forest, "
    "region and area.\n\n"
    "| Stratum | Meaning | Acres |\n"
    "|---|---|---:|\n"
    "| N | National Forest System land outside any roadless area | 135,478,432 |\n"
    "| R1 | Roadless, with an independent federal protection (Wilderness, Wilderness Study Area, "
    "Potential Wilderness Area, Wild river corridor, National Monument, National Volcanic "
    "Monument, Tongass LUD II) | 5,849,268 |\n"
    "| R1s | Colorado and Idaho roadless land under those states' own federal roadless rules | "
    "13,134,206 |\n"
    "| R2 | Roadless, where the pre-2001 forest plan prohibited road construction | 14,891,263 |\n"
    "| R3 | Roadless, exposed to the rescission | 23,848,420 |\n\n"
    "Roadless land in all (R1, R1s, R2 and R3) is 57,723,157 acres. Protected without the 2001 rule "
    "(R1, R1s and R2) is 33,874,737 acres, and exposed (R3) is 23,848,420 acres.\n\n"
    "```sql\n"
    "SELECT CASE WHEN STRATUM = 'R3' THEN 'exposed'\n"
    "            WHEN STRATUM = 'N'  THEN 'not roadless'\n"
    "            ELSE 'roadless, still protected' END AS status,\n"
    "       SUM(ACRES) AS acres\n"
    "FROM read_parquet('" + BASE + "/" + DATASET + ".parquet')\n"
    "GROUP BY status;\n"
    "```\n\n"
    "**R2 is a weaker protection than R1 or R1s.** It rests on the forest plans in force before "
    "2001, recorded as the Forest Service's historical roadless category, and the current plan for "
    "the same forest may say something different. Forest plans can also be changed, including by "
    "Congress under the Congressional Review Act, so R2 land is not necessarily well protected "
    "after a rescission. Treat R2 as protected on the historical record, and report R3 alone and R2 "
    "plus R3 when the distinction matters.\n\n"
    "**R3 measures exposure, not outcome.** It identifies roadless land whose only identified bar on "
    "new roads is the 2001 rule. It does not predict that roads, timber harvest or development will "
    "follow.\n\n"
    "**The strata cover Forest Service-owned land.** Measured against the Forest Service surface "
    "ownership layer in this catalog, 99.4% or more of every stratum, N included, is Forest "
    "Service-owned, and the five strata together (193.2 million acres) match that layer's "
    "Forest Service-owned total. Either works as the base for a share of National Forest System "
    "land:\n\n"
    "```sql\n"
    "-- National Forest System land: 193,174,461 acres\n"
    "SELECT SUM(GIS_ACRES)\n"
    "FROM read_parquet('" + BASE + "/nfs-surface-ownership.parquet')\n"
    "WHERE OWNERCLASS = 'USDA FOREST SERVICE';\n"
    "```\n\n"
    "This layer's roadless total of 57.7 million acres differs from the 58.4 million acres of the "
    "Forest Service's 2001 inventoried roadless areas (roadless-areas-2001 in this catalog), mainly "
    "because Colorado and Idaho are represented here by their state-rule roadless boundaries (R1s "
    "and the Colorado and Idaho part of R1) rather than the superseded 2001 boundaries.\n\n"
    "Sum ACRES after filtering or grouping; row counts are not a measure of area. The IRA_CAT "
    "column is empty on every row. 113 rows (57,988 acres) have FOR_NAME 'Unassigned NFS' and "
    "REGION 'NA': land outside every administrative forest boundary. All but one (55,515 acres of "
    "N in Utah) are slivers under 65 acres, and a few of these carry very many tiny parts "
    "(the Alaska N row is 33 acres in about 1.56 million parts), so filter them out when drawing "
    "or overlaying geometry if speed matters.\n\n"
    "The classification is the producer's analytical construction, not a legal determination of "
    "management authority, current forest plan direction or future project decisions. R1 covers the "
    "protection types listed above and is not a complete inventory of every possible restriction. "
    "Inputs were Forest Service layers for inventoried roadless areas, National Forest System land "
    "units, administrative forests, wilderness, Wild and Scenic Rivers, other designated areas, and "
    "the Colorado and Idaho roadless rules, with Census TIGER state boundaries for state attribution. "
    "The full classification logic is in the FGDC metadata linked from this collection.\n\n"
    "Changes from version 1.0, measured on both: N fell from 173,795,718 to 135,478,432 acres, "
    "because version 1.0's N included about 38.8 million acres of non-Forest Service inholdings "
    "and this version does not; the roadless strata each moved by under 1%, from the producer's "
    "removal of slivers left by projection differences between source layers; the Los Padres "
    "feature split across 119 rows is now one row; 'Unassigned NFS' rows are new. The FGDC "
    "metadata text is unchanged apart from dates and counts.\n\n"
    "Provenance: accessed 2026-10-14 from Zenodo record 23265719 (published 2026-10-09; FGDC "
    "publication date 2026-10-08; no version label). The staged source is "
    "s3://public-usfs/raw/roadless_land_status_shapefile_23265719.zip, 390,739,112 bytes, md5 "
    "a289574b63722aef99ea0c2bf6e57fa7, sha256 "
    "93886dea5c329db494acc29b070c0e3982516c0e0d49affb6a385f5635a2e322. The version 1.0 source "
    "stays staged at s3://public-usfs/raw/roadless_land_status_shapefile.zip, md5 "
    "6a3ef3ac5e8a4bdf9e16dde5bc6d956a."
)

CITATION = (
    "Manley, K. (2026). National Forest System Roadless Land-Status Stratification for Roadless "
    "Rule Exposure Analysis [Data set]. Zenodo. https://doi.org/" + DOI
    + ". Accessed 2026-10-14."
)


def dataset_collection():
    extent = f"({BBOX[0]:.3f}, {BBOX[1]:.3f}, {BBOX[2]:.3f}, {BBOX[3]:.3f})"
    return {
        "stac_version": "1.0.0",
        "type": "Collection",
        "id": DATASET,
        "title": f"{TITLE} — national",
        "description": DESCRIPTION,
        "license": "CC-BY-4.0",
        # Upstream gave this Zenodo version no label; do not synthesise one.
        "sci:doi": DOI,
        "sci:citation": CITATION,
        "created": "2026-10-02T17:49:29Z",
        "updated": "2026-10-15T01:20:07Z",
        "stac_extensions": [
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
            "https://stac-extensions.github.io/version/v1.2.0/schema.json",
        ],
        "keywords": ["roadless rule", "inventoried roadless areas", "national forest system",
                     "forest plans", "wilderness", "policy exposure"],
        "extent": {
            "spatial": {"bbox": [BBOX]},
            "temporal": {"interval": [["2026-10-08T00:00:00Z", "2026-10-08T00:00:00Z"]]},
        },
        "providers": [
            {"name": "Kyle Manley, Cooperative Institute for Research in Environmental Sciences "
                     "(CIRES), University of Colorado Boulder",
             "roles": ["producer", "licensor"], "url": ZENODO},
            {"name": "USDA Forest Service", "roles": ["producer"],
             "description": "Source boundary datasets the strata were derived from.",
             "url": "https://data.fs.usda.gov/geodata/edw/datasets.php"},
            {"name": "Boettiger Lab / cirrus", "roles": ["processor", "host"], "url": f"{BASE}/"},
        ],
        "links": [
            {"rel": "self", "href": f"{BASE}/{DATASET}/stac-collection.json",
             "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/",
             "type": "text/html", "title": "CC-BY-4.0, as stated on the Zenodo record"},
            {"rel": "about", "href": ZENODO, "type": "text/html",
             "title": "Zenodo record (version of 2026-10-09)"},
            {"rel": "predecessor-version", "href": PREV_ZENODO, "type": "text/html",
             "title": "Zenodo record version 1.0, used by the first build"},
            {"rel": "cite-as", "href": f"https://doi.org/{DOI}", "type": "text/html"},
            {"rel": "via", "href": f"{ZENODO}/files/roadless_land_status_shapefile.zip",
             "type": "application/zip", "title": "Source shapefile on Zenodo"},
            {"rel": "describedby", "href": f"{BASE}/raw/roadless_land_status_metadata_23265719.xml",
             "type": "application/xml", "title": "FGDC metadata as published with the source"},
        ],
        "assets": {
            f"{DATASET}-parquet": {
                "href": f"{BASE}/{DATASET}.parquet",
                "type": "application/x-parquet",
                "title": f"{TITLE} {extent} — GeoParquet",
                "description": "One row per polygon (702 rows). Use this asset for acreage "
                               "summaries, which come from ACRES, and for boundary geometry.",
                "roles": ["data"],
                "created": "2026-10-14T20:12:03Z",
                "table:columns": cols(COLUMNS) + cols([GEOM]),
            },
            f"{DATASET}-pmtiles": {
                "href": f"{BASE}/{DATASET}.pmtiles",
                "type": "application/vnd.pmtiles",
                "title": f"{TITLE} {extent} — PMTiles",
                "description": "Vector tiles for web maps. Style on STRATUM.",
                "roles": ["data", "visual"],
                "created": "2026-10-14T20:17:31Z",
                "vector:layers": [DATASET],
                # tippecanoe drops IRA_CAT: it is NULL on every row, so no tile carries it.
                "table:columns": cols([c for c in COLUMNS if c[0] != "IRA_CAT"], lean=True),
            },
            f"{DATASET}-hex": {
                "href": f"{BASE}/{DATASET}/hex/h0=*/data_0.parquet",
                "type": "application/x-parquet",
                "title": f"{TITLE} {extent} — H3 Hex (resolution 10)",
                "description": HEX_NOTE,
                "roles": ["data"],
                "created": "2026-10-15T01:20:07Z",
                "h3:native_resolution": 10,
                "h3:parent_resolutions": [9, 8, 0],
                "table:columns": cols(COLUMNS) + cols(H3_COLUMNS),
            },
        },
    }


def patch_bucket(b):
    href = f"{BASE}/{DATASET}/stac-collection.json"
    b["links"] = [l for l in b["links"] if l.get("href") != href]
    # Children no longer share one licence: this one is CC-BY-4.0, the rest public domain.
    b["license"] = "various"
    b["links"] = [l for l in b["links"] if l["rel"] != "license"]
    b["links"].append({"rel": "child", "href": href, "type": "application/json",
                       "title": f"{TITLE} — national"})
    old = ("Geospatial datasets administered by the USDA Forest Service and published from the "
           "Forest Service Enterprise Data Warehouse: the Inventoried Roadless Areas of the 2001 "
           "Roadless Area Conservation Rule, Forest Service surface ownership, and the "
           "administrative, proclaimed and ranger-district boundaries.")
    added = (" Also derived layers built on them: a roadless land-status classification for "
             "the Roadless Rule rescission (roadless-land-status, CC-BY-4.0, produced at CIRES). "
             "Forest Service datasets are public domain; check each collection's licence.")
    d = b["description"]
    while added + added in d:  # repair a doubled sentence from an earlier non-idempotent run
        d = d.replace(added + added, added)
    if "roadless-land-status" not in d:
        if old not in d:
            raise SystemExit("bucket description changed upstream; patch it by hand")
        d = d.replace(old, old + added)
    b["description"] = d
    return b


README_ROW = ("| `roadless-land-status` | Roadless land-status strata: exposed (R3) vs. still-protected "
              "roadless land (CC-BY-4.0, CIRES) | 193,201,589 (57,723,157 roadless) |\n")

README_SECTION = f"""## Roadless land status: which roadless land the rescission exposes

`roadless-land-status` classifies National Forest System land into five strata (`STRATUM`):
`N` not roadless, `R1` roadless with an independent federal protection such as Wilderness,
`R1s` Colorado and Idaho state-rule roadless land, `R2` roadless where the pre-2001 forest plan
prohibited roads, and `R3` roadless land exposed to a rescission of the 2001 rule. Produced by
Kyle Manley (CIRES) and published on Zenodo (doi:{DOI}), CC-BY-4.0.

```sql
-- exposed 23,848,420 acres; still protected (R1, R1s, R2) 33,874,737 acres
SELECT STRATUM, SUM(ACRES) AS acres
FROM read_parquet('{BASE}/{DATASET}.parquet')
GROUP BY STRATUM ORDER BY STRATUM;
```

- `R2` rests on historical forest plans, which may differ from the current plan and can be
  changed, so it is a weaker protection than `R1` or `R1s`.
- `R3` measures exposure, not a prediction that roads will be built.
- Built from the Zenodo version of 2026-10-09, which replaces version 1.0. `N` no longer
  includes non-Forest Service inholdings (173.8M acres in version 1.0, 135.5M now).
- Sum `ACRES`, not row counts. `IRA_CAT` is empty on every row. `FOR_NAME = 'Unassigned NFS'`
  marks 113 small pieces outside any administrative forest.
- MapLibre `source-layer`: `{DATASET}`. Colour on `STRATUM`:

```js
'fill-color': ['match', ['get', 'STRATUM'],
  'R3', '#d73027', 'R2', '#fc8d59', 'R1s', '#91bfdb', 'R1', '#4575b4', '#cccccc']
```

"""


def patch_readme(r):
    row = f"| `{DATASET}` |"
    if row in r:
        # Already published: replace our row and section in place so a rebuild's numbers land.
        i = r.index(row)
        r = r[:i] + README_ROW + r[r.index("\n", i) + 1:]
        i = r.index("## Roadless land status:")
        j = r.index("\n## ", i) + 1
        return r[:i] + README_SECTION + r[j:]
    anchor = "| `ids-survey-extent-1999-2025`"
    i = r.index(anchor)
    j = r.index("\n", i) + 1
    r = r[:j] + README_ROW + r[j:]
    r = r.replace("## Query with DuckDB", README_SECTION + "## Query with DuckDB", 1)
    r = r.replace("US Government work, public domain.",
                  "Forest Service data is a US Government work, public domain; derived layers from "
                  "other producers carry their own licence, noted in the table.", 1)
    r = r.replace("`proclaimed-forest`, `ranger-district`, `roadless-areas-2001`.",
                  f"`proclaimed-forest`, `ranger-district`, `roadless-areas-2001`, `{DATASET}`.", 1)
    return r


if __name__ == "__main__":
    with open(f"/tmp/{DATASET}-stac.json", "w") as f:
        json.dump(dataset_collection(), f, indent=2)
        f.write("\n")
    bucket = json.load(urllib.request.urlopen(f"{BASE}/stac-collection.json"))
    with open("/tmp/usfs-bucket-stac.json", "w") as f:
        json.dump(patch_bucket(bucket), f, indent=2)
        f.write("\n")
    readme = urllib.request.urlopen(f"{BASE}/README.md").read().decode()
    with open("/tmp/usfs-README.md", "w") as f:
        f.write(patch_readme(readme))
    print(f"wrote /tmp/{DATASET}-stac.json /tmp/usfs-bucket-stac.json /tmp/usfs-README.md")
