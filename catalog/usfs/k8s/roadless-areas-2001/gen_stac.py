#!/usr/bin/env python3
"""Emit the public-usfs bucket collection, the roadless-areas-2001 dataset collection,
and the bucket README to /tmp for rclone upload (AGENTS.md Hard Boundary 1 — this repo
never contains STAC JSON or README files).

One source schema (COLUMNS) is written identically to the flat GeoParquet and the hex so
the mcp-data-server#303 per-column fold never drops a variant. PMTiles gets the lean
form (name + type + values, no prose).
"""
import copy
import json

BUCKET = "public-usfs"
DATASET = "roadless-areas-2001"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
BBOX = [-150.008, 18.246, -65.707, 61.519]

CATEGORY_DEF = (
    "Land-use category recorded in the forest plan that predates the 2001 Roadless Rule, kept "
    "for historical reference. Values: 1B=Inventoried roadless area where road construction and "
    "reconstruction is prohibited, 1B-1=Inventoried roadless area recommended for wilderness "
    "designation in the forest plan, where road construction and reconstruction is prohibited, "
    "1C=Inventoried roadless area where road construction and reconstruction is not prohibited. "
    "These labels describe pre-rule forest plan direction, not the rule itself: the 2001 Roadless "
    "Rule prohibits road construction across every inventoried roadless area regardless of "
    "category, so category 1C does not identify areas where the rule permits road building."
)

REGION_DEF = (
    "USDA Forest Service administrative region. Values: 1=Northern, 2=Rocky Mountain, "
    "3=Southwestern, 4=Intermountain, 5=Pacific Southwest, 6=Pacific Northwest, 8=Southern, "
    "9=Eastern, 10=Alaska. There is no Region 7."
)

STATE_NAMES = {
    "AK": "Alaska", "AL": "Alabama", "AR": "Arkansas", "AZ": "Arizona", "CA": "California",
    "CO": "Colorado", "FL": "Florida", "GA": "Georgia", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MI": "Michigan",
    "MN": "Minnesota", "MO": "Missouri", "MS": "Mississippi", "MT": "Montana",
    "NC": "North Carolina", "ND": "North Dakota", "NH": "New Hampshire", "NM": "New Mexico",
    "NV": "Nevada", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "PR": "Puerto Rico",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VA": "Virginia", "VT": "Vermont", "WA": "Washington", "WI": "Wisconsin",
    "WV": "West Virginia", "WY": "Wyoming",
}
STATES = sorted(STATE_NAMES)
STATE_LIST = ", ".join(f"{k}={v}" for k, v in sorted(STATE_NAMES.items()))

# name, type, description, values
COLUMNS = [
    ("_cng_fid", "int64",
     "Stable per-feature identifier assigned during conversion, unique for every one of the "
     "11,391 source polygons. Use this as the feature key: the roadless area name is not unique "
     "(1,219 names appear on more than one polygon) and is empty on 4 polygons.", None),
    ("OGC_FID", "int64", "Sequential row identifier carried over from the source shapefile.", None),
    ("REGION", "int32", REGION_DEF, [1, 2, 3, 4, 5, 6, 8, 9, 10]),
    ("FOREST", "string",
     "Name of the national forest or grassland administering the area. 122 distinct names.", None),
    ("STATE", "string",
     "Two-letter state or territory abbreviation, covering 38 states and Puerto Rico. This is the "
     "field that separates the areas the 2026 proposed rescission would affect from the ones it "
     "would not: the proposal excludes Idaho and Colorado, which adopted their own state-specific "
     "roadless rules in 2008 and 2012. There is no separate rule-type attribute, so the split is "
     "made on this column. Values: " + STATE_LIST, STATES),
    ("NAME", "string",
     "Name of the inventoried roadless area. 2,618 distinct names across 11,391 polygons: a "
     "single named area is often split into several polygons, and 4 polygons carry no name. Group "
     "by the feature identifier rather than by name to count areas.", None),
    ("CATEGORY", "string", CATEGORY_DEF, ["1B", "1B-1", "1C"]),
    ("ACRES", "float64",
     "Area of the whole source polygon in acres, as published by the Forest Service. Summing this "
     "column over all 11,391 polygons gives 58,419,694 acres; restricting to polygons outside "
     "Idaho and Colorado gives 44,701,002 acres.", None),
    ("SHAPE_AREA", "float64", "Area of the whole source polygon in the source projection's units.", None),
    ("SHAPE_LEN", "float64", "Perimeter of the whole source polygon in the source projection's units.", None),
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


TITLE = "Inventoried Roadless Areas (2001 Roadless Rule)"

HEX_NOTE = (
    "One row per (polygon, resolution 10 cell) pair — 16,309,549 rows for 11,391 polygons, since a "
    "polygon that covers many cells appears on many rows. Every attribute column is therefore "
    "repeated on every cell the polygon covers, so counts and totals must go through _cng_fid:\n\n"
    "```sql\n"
    "-- correct: 11,391 roadless area polygons, 58,419,694 acres\n"
    "SELECT COUNT(DISTINCT _cng_fid) FROM read_parquet('…/hex/h0=*/data_0.parquet');\n"
    "SELECT SUM(ACRES) FROM (SELECT DISTINCT _cng_fid, ACRES\n"
    "                        FROM read_parquet('…/hex/h0=*/data_0.parquet'));\n"
    "-- wrong: COUNT(*) returns 16,309,549 cells, not polygons\n"
    "-- wrong: SUM(ACRES) over raw rows returns about 1.9 trillion acres\n"
    "```\n\n"
    "For the area of a selection, prefer the H3 footprint of its distinct cells over summing ACRES; "
    "across the whole layer the two agree to within 0.25%."
)

DESCRIPTION = (
    "The official Forest Service boundaries of the Inventoried Roadless Areas designated by the "
    "2001 Roadless Area Conservation Rule (36 CFR 294, Subpart B) — 11,391 polygons covering "
    "58,419,694 acres across 38 states and Puerto Rico.\n\n"
    "**Two different national totals, and choosing the wrong one changes the answer.** All "
    "inventoried roadless areas together come to 58,419,694 acres. The 2026 proposed rescission of "
    "the rule excludes Idaho and Colorado, which adopted their own state-specific roadless rules in "
    "2008 and 2012, and those two states hold 13,718,692 acres. The area the proposal would affect "
    "is therefore 44,701,002 acres. Percentages quoted about the proposal are generally computed "
    "against that smaller base, and the two bases give materially different answers — the ten "
    "Western states of Alaska, Arizona, California, Montana, Nevada, New Mexico, Oregon, Utah, "
    "Washington and Wyoming hold 95.61% of the 44,701,002-acre affected total but 73.16% of the "
    "58,419,694-acre full total. State any figure alongside the base it uses.\n\n"
    "There is no attribute recording which rule governs a given area, so the Idaho and Colorado "
    "split is made on the STATE column:\n\n"
    "```sql\n"
    "-- acres the 2026 proposed rescission would affect\n"
    "SELECT SUM(ACRES) FROM read_parquet('" + BASE + "/" + DATASET + ".parquet')\n"
    "WHERE STATE NOT IN ('ID','CO');\n"
    "```\n\n"
    "Idaho and Colorado are included in this layer rather than removed, for two reasons: they are "
    "part of the denominator for any national percentage, and they serve as a comparison group of "
    "roadless areas the proposal leaves alone. Note that for those two states these are the "
    "superseded 2001 boundaries — the Forest Service publishes the operative Idaho and Colorado "
    "roadless boundaries as separate datasets, which are not included here.\n\n"
    "The CATEGORY column is a frequent source of error. It records forest plan direction from "
    "before the rule took effect, so category 1C reads as though road construction were allowed. "
    "It was not: the 2001 rule prohibits road construction across every inventoried roadless area "
    "regardless of category.\n\n"
    "The Forest Service cautions that source scales vary across this layer and that boundaries "
    "cannot be expected to align with features from other datasets; the National Forest Planning "
    "Record documents remain the official version of the inventory. Treat boundary-adjacency and "
    "buffer-distance results as approximate."
)


def dataset_collection():
    flat_cols = cols(COLUMNS) + cols([GEOM])
    hex_cols = cols(COLUMNS) + cols(H3_COLUMNS)
    pm_cols = cols(COLUMNS, lean=True)
    extent = f"({BBOX[0]}, {BBOX[1]}, {BBOX[2]}, {BBOX[3]})"
    return {
        "stac_version": "1.0.0",
        "type": "Collection",
        "id": DATASET,
        "title": f"{TITLE} — national",
        "description": DESCRIPTION,
        "license": "public-domain",
        "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json"],
        "extent": {
            "spatial": {"bbox": [BBOX]},
            "temporal": {"interval": [["2001-01-12T00:00:00Z", None]]},
        },
        "providers": [
            {"name": "USDA Forest Service, Geospatial Service and Technology Center",
             "roles": ["producer", "licensor"],
             "url": "https://www.fs.usda.gov/managing-land/planning/roadless"},
            {"name": "Boettiger Lab / cirrus", "roles": ["processor", "host"],
             "url": f"{BASE}/"},
        ],
        "links": [
            {"rel": "self", "href": f"{BASE}/{DATASET}/stac-collection.json",
             "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json",
             "type": "application/json"},
            {"rel": "license", "href": "https://www.usa.gov/government-works",
             "type": "text/html", "title": "US Government work — public domain"},
            {"rel": "via",
             "href": "https://data.fs.usda.gov/geodata/edw/edw_resources/shp/S_USA.RoadlessArea_2001.zip",
             "type": "application/zip", "title": "Source shapefile (Forest Service EDW)"},
            {"rel": "describedby", "href": f"{BASE}/raw/S_USA.RoadlessArea_2001.shp.xml",
             "type": "application/xml", "title": "FGDC metadata as published with the source"},
        ],
        "assets": {
            f"{DATASET}-parquet": {
                "href": f"{BASE}/{DATASET}.parquet",
                "type": "application/x-parquet",
                "title": f"{TITLE} {extent} — GeoParquet",
                "description": "One row per source polygon (11,391 rows). Use this asset for "
                               "boundary geometry and for true distance or buffer work.",
                "roles": ["data"],
                "table:columns": flat_cols,
            },
            f"{DATASET}-pmtiles": {
                "href": f"{BASE}/{DATASET}.pmtiles",
                "type": "application/vnd.pmtiles",
                "title": f"{TITLE} {extent} — PMTiles",
                "roles": ["data", "visual"],
                "vector:layers": [DATASET],
                "table:columns": pm_cols,
            },
            f"{DATASET}-hex": {
                "href": f"{BASE}/{DATASET}/hex/h0=*/data_0.parquet",
                "type": "application/x-parquet",
                "title": f"{TITLE} {extent} — H3 Hex (resolution 10)",
                "description": HEX_NOTE + " Use this asset to join roadless areas against other "
                               "hex datasets in the catalog; resolution 8 is the shared join key.",
                "roles": ["data"],
                "h3:native_resolution": 10,
                "h3:parent_resolutions": [9, 8, 0],
                "table:columns": hex_cols,
            },
        },
    }


def bucket_collection():
    return {
        "stac_version": "1.0.0",
        "type": "Collection",
        "id": "usfs-datasets",
        "title": "USDA Forest Service (USFS) Datasets",
        "description":
            "Geospatial datasets administered by the USDA Forest Service and published from the "
            "Forest Service Enterprise Data Warehouse, starting with the Inventoried Roadless "
            "Areas of the 2001 Roadless Area Conservation Rule. Forest Service activity records "
            "(FACTS) are published separately in the public-facts bucket, and Forest Service "
            "wildfire products in public-fire.",
        "license": "public-domain",
        "extent": {
            "spatial": {"bbox": [BBOX]},
            "temporal": {"interval": [["2001-01-12T00:00:00Z", None]]},
        },
        "providers": [
            {"name": "USDA Forest Service", "roles": ["producer", "licensor"],
             "url": "https://data.fs.usda.gov/geodata/edw/datasets.php"},
            {"name": "Boettiger Lab / cirrus", "roles": ["processor", "host"],
             "url": f"{BASE}/"},
        ],
        "links": [
            {"rel": "self", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": ROOT, "type": "application/json"},
            {"rel": "license", "href": "https://www.usa.gov/government-works",
             "type": "text/html", "title": "US Government work — public domain"},
            {"rel": "child", "href": f"{BASE}/{DATASET}/stac-collection.json",
             "type": "application/json", "title": f"{TITLE} — national"},
        ],
    }


README = f"""# `{BUCKET}` — USDA Forest Service datasets

Cloud-native mirrors of USDA Forest Service geospatial data, published as GeoParquet, PMTiles
and H3 hex parquet on NRP S3.

STAC: <{BASE}/stac-collection.json>

## Collections

| Dataset | Description |
|---|---|
| [`{DATASET}`]({BASE}/{DATASET}/stac-collection.json) | Inventoried Roadless Areas designated by the 2001 Roadless Area Conservation Rule (36 CFR 294 Subpart B) — 11,391 polygons, 58,419,694 acres, national |

## `{DATASET}`

### The two national totals

All inventoried roadless areas come to **58,419,694 acres**. The 2026 proposed rescission of the
rule excludes Idaho and Colorado — which adopted their own state-specific roadless rules in 2008
and 2012 — leaving **44,701,002 acres** affected. Percentages about the proposal are generally
computed against the smaller base, and the choice matters: the ten Western states hold 95.61% of
the affected total but 73.16% of the full total. Always state which base a figure uses.

There is no rule-type attribute, so the split is made on `STATE`:

```sql
SELECT
  SUM(ACRES)                                          AS all_ira_acres,          -- 58,419,694
  SUM(ACRES) FILTER (WHERE STATE NOT IN ('ID','CO'))  AS rule_affected_acres     -- 44,701,002
FROM read_parquet('{BASE}/{DATASET}.parquet');
```

### DuckDB

```sql
INSTALL spatial; LOAD spatial;
INSTALL httpfs;  LOAD httpfs;

-- roadless acres by state, largest first
SELECT STATE, ROUND(SUM(ACRES)) AS acres, COUNT(*) AS polygons
FROM read_parquet('{BASE}/{DATASET}.parquet')
GROUP BY STATE ORDER BY acres DESC;
```

The hex asset carries one row per (polygon, resolution 10 cell) pair, so whole-polygon totals
(`ACRES`, `SHAPE_AREA`, `SHAPE_LEN`) repeat across every cell a polygon covers. Deduplicate on
`_cng_fid` before summing them:

```sql
SELECT SUM(ACRES) FROM (
  SELECT DISTINCT _cng_fid, ACRES
  FROM read_parquet('{BASE}/{DATASET}/hex/h0=*/data_0.parquet')
);
```

Native resolution is 10, with parents 9, 8 and 0. Join to other catalog datasets on `h8`.

### MapLibre GL JS

The PMTiles `source-layer` is **`{DATASET}`**.

```js
import * as pmtiles from 'pmtiles';
maplibregl.addProtocol('pmtiles', new pmtiles.Protocol().tile);

map.addSource('roadless', {{
  type: 'vector',
  url: 'pmtiles://{BASE}/{DATASET}.pmtiles'
}});

// affected by the 2026 proposed rescission vs. governed by a state rule
map.addLayer({{
  id: 'roadless-fill',
  type: 'fill',
  source: 'roadless',
  'source-layer': '{DATASET}',
  paint: {{
    'fill-color': [
      'match', ['get', 'STATE'],
      ['ID', 'CO'], '#9e9e9e',
      '#2e7d32'
    ],
    'fill-opacity': 0.6
  }}
}});
```

## Caveats

- `CATEGORY` records forest plan direction from *before* the rule took effect. Category `1C` reads
  as though road construction were permitted; it was not. The 2001 rule prohibits road
  construction across every inventoried roadless area regardless of category.
- `NAME` is not unique — 2,618 distinct names across 11,391 polygons, and 4 polygons are unnamed.
  Count areas with `_cng_fid`, not `NAME`.
- For Idaho and Colorado these are the **superseded** 2001 boundaries. The operative boundaries for
  those two states are published by the Forest Service as separate datasets and are not included.
- The Forest Service notes that source scales vary and that these boundaries cannot be expected to
  align with features from other datasets. Treat adjacency and buffer-distance results as
  approximate.

## License

US Government work — public domain. Produced by the USDA Forest Service, Geospatial Service and
Technology Center. Source: [Forest Service EDW](https://data.fs.usda.gov/geodata/edw/edw_resources/shp/S_USA.RoadlessArea_2001.zip),
landing page <https://www.fs.usda.gov/managing-land/planning/roadless>. The FGDC metadata as
published with the source is retained at `{BASE}/raw/S_USA.RoadlessArea_2001.shp.xml`.
"""

if __name__ == "__main__":
    with open("/tmp/usfs-bucket-stac.json", "w") as f:
        json.dump(bucket_collection(), f, indent=2)
        f.write("\n")
    with open("/tmp/roadless-areas-2001-stac.json", "w") as f:
        json.dump(dataset_collection(), f, indent=2)
        f.write("\n")
    with open("/tmp/usfs-README.md", "w") as f:
        f.write(README)
    print("wrote /tmp/usfs-bucket-stac.json /tmp/roadless-areas-2001-stac.json /tmp/usfs-README.md")
