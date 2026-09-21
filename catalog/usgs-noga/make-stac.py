#!/usr/bin/env python3
"""Write the STAC collection and README for usgs-noga-assessment-units (issue #700).

Numbers are never typed in by hand: they come from `build-report.json` (written by
k8s/noga-preprocess.py) and `stats.json` (measured from the published parquet with
the duckdb-geo MCP). Run it, check the output, then upload:

  python3 catalog/usgs-noga/make-stac.py --report /tmp/build-report.json \
      --stats /tmp/stats.json --out-dir /tmp
  scripts/verify-stac.py --no-data /tmp/stac-collection.json
  rclone copyto /tmp/stac-collection.json nrp:public-usgs/noga-assessment-units/stac-collection.json
  rclone copyto /tmp/README.md nrp:public-usgs/noga-assessment-units/README.md
"""

import argparse
import json
import os

BUCKET = "public-usgs"
DATASET = "noga-assessment-units"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
SELF = f"{BASE}/{DATASET}/stac-collection.json"
LANDING = (
    "https://www.usgs.gov/centers/central-energy-resources-science-center/science/"
    "united-states-assessments-undiscovered-oil"
)
COMMUNITY = "https://www.sciencebase.gov/catalog/item/59cab03de4b017cf314094df"
ACCESS_DATE = "2026-09-21"

FRACTILE = {
    "F95": "95th-percentile (F95) estimate, the low end of the assessed range",
    "F50": "median (F50) estimate",
    "F5": "5th-percentile (F5) estimate, the high end of the assessed range",
    "MN": "mean estimate",
}

COMMODITY = {
    "OIL": ("undiscovered oil", "million barrels"),
    "GAS": ("undiscovered gas, associated and nonassociated combined", "billion cubic feet"),
    "AG": ("undiscovered associated gas, the gas dissolved in oil accumulations", "billion cubic feet"),
    "NAGAS": ("undiscovered nonassociated gas, the gas in accumulations without oil", "billion cubic feet"),
    "NGL": ("undiscovered natural gas liquids, from associated and nonassociated gas combined", "million barrels"),
    "AGL": ("undiscovered natural gas liquids from associated gas", "million barrels"),
    "NAGL": ("undiscovered natural gas liquids from nonassociated gas", "million barrels"),
}

NOT_ASSESSED = (
    "Null means this commodity was not assessed for this assessment unit, or the unit's "
    "release publishes no results table; it is not an estimate of zero. A stored 0 is a "
    "real estimate, which is common at the F95 fractile."
)


def volume_columns():
    cols = []
    for prefix, (what, unit) in COMMODITY.items():
        suffix = "MMB" if unit == "million barrels" else "BCF"
        for fractile, phrase in FRACTILE.items():
            cols.append(
                {
                    "name": f"{prefix}_{fractile}_{suffix}",
                    "type": "double",
                    "description": (
                        f"Technically recoverable {what} at the {phrase}, in {unit}. "
                        f"{NOT_ASSESSED}"
                    ),
                }
            )
    return cols


def code_list(name, text, stats, mapping_key):
    """A coded column: the description carries the full CODE=Name list."""
    mapping = stats[mapping_key]
    pairs = ", ".join(f"{code}={mapping[code]}" for code in sorted(mapping))
    return {
        "name": name,
        "type": "string",
        "description": f"{text} Values: {pairs}.",
        "values": sorted(mapping),
    }


def categorical(name, ctype, text, stats, key):
    values = stats["values"].get(key)
    col = {"name": name, "type": ctype, "description": text}
    if values:
        col["values"] = values
    return col


def columns(stats):
    cols = [
        {
            "name": "_cng_fid",
            "type": "int64",
            "description": (
                "Universal per-feature id, one per assessment unit polygon and unique across "
                "the collection. Use it as the join key between the GeoParquet and the hex "
                "asset, and as the dedup key for COUNT(DISTINCT)."
            ),
        },
        {
            "name": "fid",
            "type": "int64",
            "description": (
                "Row number carried over from the merged GeoPackage. Provenance only: use "
                "`_cng_fid` as the join and dedup key."
            ),
        },
        {
            "name": "REGNUM",
            "type": "string",
            "description": (
                "USGS world energy region number; 5 for North America. Null on the 30 "
                "assessment units whose source release omits the region fields."
            ),
        },
        {
            "name": "REGNAME",
            "type": "string",
            "description": (
                "USGS world energy region name. Null on the 30 assessment units whose source "
                "release omits the region fields."
            ),
            "values": ["North America", "Central and North America"],
        },
        code_list(
            "PROVCODE",
            "Four-digit USGS geologic province code, the stable identifier for the province: "
            "the accompanying PROVNAME is missing on 30 assessment units and spelled two ways "
            "for two codes, so group on the code.",
            stats,
            "provcode_names",
        ),
        {
            "name": "PROVNAME",
            "type": "string",
            "description": (
                "Geologic province name, for example Permian Basin, Gulf Coast Mesozoic or "
                "Northern Alaska. Upstream spelling is inconsistent, so this is not a reliable "
                "grouping key: it is null on 30 of the 240 assessment units, province 5034 "
                "appears as both Big Horn Basin and Bighorn Basin, and province 5049 appears as "
                "both Gulf Coast Mesozoic and Gulf Coast Cenozoic. Group on PROVCODE instead."
            ),
            "values": stats["values"]["PROVNAME"],
        },
        code_list(
            "TPSCODE",
            "Six-digit USGS Total Petroleum System code; the first four digits are the province "
            "code. Three codes carry two upstream spellings of their name (503102, 503107, "
            "503108), so group on the code rather than TPSNAME.",
            stats,
            "tpscode_names",
        ),
        {
            "name": "TPSNAME",
            "type": "string",
            "description": (
                "Total Petroleum System name. A Total Petroleum System groups the source rock, "
                "the reservoirs and the traps that share one hydrocarbon charge; a province "
                "usually contains several, and each is assessed as one or more assessment "
                "units. Null on 2 of the 240 assessment units."
            ),
        },
        {
            "name": "ASSESSCODE",
            "type": "string",
            "description": (
                "Eight-digit USGS assessment unit code, the identifier of the assessed area. "
                "Codes are reused when a province is reassessed, and this collection keeps only "
                "the newest release of each code."
            ),
        },
        {
            "name": "ASSESSNAME",
            "type": "string",
            "description": (
                "Assessment unit name, for example Barnett Delaware Basin Continuous Gas."
            ),
        },
        {
            "name": "ASSESSYEAR",
            "type": "int32",
            "description": (
                "Year the assessment was completed. Present only for assessment units whose "
                "release publishes a results table."
            ),
        },
    ]
    cols.append(
        categorical(
            "ASSESSMETHOD",
            "string",
            "Assessment method. Values: Conventional = discrete accumulations held in "
            "structural or stratigraphic traps, Continuous = a pervasive accumulation such as "
            "shale oil, shale gas, tight gas or coalbed gas. Present only where a results "
            "table was published.",
            stats,
            "ASSESSMETHOD",
        )
    )
    cols.append(
        categorical(
            "ACCUMTYPE",
            "string",
            "Type of accumulation assessed. Values: Oil = the assessment unit was assessed for "
            "oil and its associated gas, Gas = assessed for gas and its natural gas liquids, "
            "Oil and Gas = both were assessed. Present only where a results table was published.",
            stats,
            "ACCUMTYPE",
        )
    )
    cols.append(
        categorical(
            "RESERVOIRTYPE",
            "string",
            "Reservoir type assessed. Present only where a results table was published.",
            stats,
            "RESERVOIRTYPE",
        )
    )
    cols.append(
        categorical(
            "STATUS",
            "string",
            "Publication status of the assessment. Values: CURRENT = the USGS fact sheet is "
            "final, PENDING = the assessment is complete but its fact sheet is not yet final. "
            "Present only where a results table was published.",
            stats,
            "STATUS",
        )
    )
    cols += volume_columns()
    cols += [
        {
            "name": "sciencebase_id",
            "type": "string",
            "description": (
                "ScienceBase item id of the data release this polygon came from; resolves to "
                "https://www.sciencebase.gov/catalog/item/<sciencebase_id>."
            ),
        },
        {
            "name": "release_pubdate",
            "type": "string",
            "description": (
                "Publication date of that release, YYYY-MM-DD. This is the edition stamp for "
                "the row: the merged national layer has no version of its own."
            ),
        },
        {
            "name": "source_shapefile",
            "type": "string",
            "description": "Name of the assessment unit layer inside the source release.",
        },
    ]
    return cols


def geom_columns(stats):
    return columns(stats) + [
        {
            "name": "geom",
            "type": "geometry",
            "description": (
                "Assessment unit boundary polygon (GeoParquet, EPSG:4326), reprojected from the "
                "NAD83 source."
            ),
        },
    ]


def hex_columns(stats):
    return columns(stats) + [
        {
            "name": "h8",
            "type": "uint64",
            "description": (
                "H3 cell ID at resolution 8, the native resolution of this hex asset and the "
                "catalog's common join key."
            ),
        },
        {
            "name": "h0",
            "type": "int64",
            "description": (
                "H3 cell ID at resolution 0, used as the partition key for hive-partitioned "
                "reads."
            ),
        },
    ]


def pmtiles_columns(stats):
    lean = []
    for col in columns(stats):
        entry = {"name": col["name"], "type": col["type"]}
        if "values" in col:
            entry["values"] = col["values"]
        lean.append(entry)
    return lean


def description(report, stats):
    rel = report["releases"]
    with_results = [r for r in rel if r["results_csv"]]
    return (
        "USGS estimates of **undiscovered, technically recoverable oil, gas and natural gas "
        "liquids** for the onshore and state-water United States, as Assessment Unit (AU) "
        "polygons. An assessment unit is a geologic area that USGS assesses as a whole: the "
        "polygon plus its probability distribution (F95, F50, F5 and mean) is the finest-grained "
        f"record USGS publishes, and there is no point layer of undiscovered oil. **{stats['rows']} "
        f"assessment units** covering **{stats['distinct_provinces']} geologic provinces**.\n\n"
        "**This is a merged layer.** USGS publishes the national assessment one province or "
        f"formation release at a time; there is no national compilation upstream. It was built by "
        f"merging the **{report['us_releases']} United States releases** in the USGS National and "
        f"Global Oil and Gas Assessment Project ScienceBase community "
        f"({report['excluded_non_us_releases']} non-US releases in the same community were "
        "excluded, and every published polygon was checked to intersect a US state or territory "
        "boundary). A merged compilation has no upstream edition, so this collection carries no "
        "version number: the edition record is the release manifest, and every row names its own "
        "release in `sciencebase_id` and `release_pubdate`. Where two releases assess the same "
        f"`ASSESSCODE`, the newer one is kept ({stats['superseded']} superseded polygons dropped).\n\n"
        f"**Volume estimates cover part of the layer.** Only {len(with_results)} of the "
        f"{report['us_releases']} releases publish a per-AU results table; the rest, published "
        "2018 to 2022, publish the boundaries and the assessment input forms only. So "
        f"{stats['rows_with_volumes']} of the {stats['rows']} assessment units carry oil, gas and "
        "NGL fractiles and the remainder carry nulls. A null is always \"not published\" or \"not "
        "assessed\", never an estimate of zero.\n\n"
        "**Assessment units overlap.** Conventional and continuous units, and different Total "
        "Petroleum Systems, cover the same ground, so several polygons can stack over one "
        "location. Volumes are per-unit totals, not densities:\n\n"
        "```sql\n"
        "-- correct: one row per assessment unit before summing\n"
        "SELECT SUM(OIL_MN_MMB) FROM (\n"
        "  SELECT DISTINCT ASSESSCODE, OIL_MN_MMB\n"
        f"  FROM read_parquet('s3://{BUCKET}/{DATASET}.parquet')\n"
        ");\n"
        "-- wrong: summing across overlapping units counts the same ground several times\n"
        "-- wrong: summing F95, F50 or F5 across units — only the mean is additive\n"
        "```\n\n"
        f"**Provenance.** Landing page: {LANDING}. Read from the ScienceBase community "
        f"{COMMUNITY} on **{ACCESS_DATE}**; the release manifest, the staged raw files for each "
        f"release and the per-release build report are under "
        f"`s3://{BUCKET}/raw/{DATASET}/`. The merged GeoPackage the published assets were built "
        f"from is `{report['gpkg']['path']}` ({report['gpkg']['bytes']} bytes, sha256 "
        f"`{report['gpkg']['sha256']}`). Eleven releases serve no shapefile bytes and were read "
        "from the ScienceBase GeoServer GeoJSON export of the same layer; one 2020 Alaska release "
        "publishes Esri JSON instead of a shapefile."
    )


def hex_description(stats):
    return (
        "Assessment unit boundaries as H3 cells at resolution 8, with resolution 0 as the "
        "partition key. One row is one (assessment unit, cell) pair, so every attribute of an "
        "assessment unit, including all the volume columns, is repeated on every cell the unit "
        "covers. Assessment units also overlap one another, so a single cell can carry several "
        "rows from different units.\n\n"
        "```sql\n"
        "-- correct: collapse the cell expansion and the overlap before summing a volume\n"
        "SELECT SUM(OIL_MN_MMB) FROM (\n"
        "  SELECT DISTINCT ASSESSCODE, OIL_MN_MMB\n"
        f"  FROM read_parquet('s3://{BUCKET}/{DATASET}/hex/h0=*/data_0.parquet')\n"
        ");\n"
        "-- correct: which units touch a cell\n"
        "SELECT DISTINCT ASSESSNAME\n"
        f"FROM read_parquet('s3://{BUCKET}/{DATASET}/hex/h0=*/data_0.parquet')\n"
        "WHERE h8 = ?;\n"
        "-- wrong: SUM over hex rows, which multiplies each unit by its cell count\n"
        "-- wrong: summing or area-weighting F95, F50 or F5 — only the mean is additive\n"
        "```\n\n"
        f"{stats['hex_rows']:,} rows over {stats['distinct_h8']:,} distinct resolution 8 cells: "
        "assessment units overlap, so a cell carries 3.6 rows on average. Resolution 8 matches "
        "the source, because assessment unit boundaries are basin-scale interpretive lines drawn "
        "by the province geologist and a finer resolution would assert a precision the source "
        "does not have."
    )


def collection(report, stats):
    bbox = stats["bbox"]
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
        ],
        "id": "usgs-noga-assessment-units",
        "title": "USGS Undiscovered Oil and Gas Assessment Units (United States)",
        "description": description(report, stats),
        "license": "public-domain",
        "sci:citation": (
            "U.S. Geological Survey National and Global Oil and Gas Assessment Project, "
            f"{report['us_releases']} United States assessment unit data releases "
            f"({stats['pubdate_min']} to {stats['pubdate_max']}), ScienceBase community "
            f"{COMMUNITY}. Merged national layer; accessed {ACCESS_DATE}."
        ),
        "created": stats["created"],
        "updated": stats["created"],
        "providers": [
            {
                "name": "U.S. Geological Survey",
                "roles": ["producer", "licensor"],
                "url": LANDING,
            },
            {"name": "ScienceBase", "roles": ["host"], "url": COMMUNITY},
            {
                "name": "Boettiger Lab",
                "roles": ["processor"],
                "url": "https://boettiger-lab.github.io",
            },
        ],
        "extent": {
            "spatial": {"bbox": [bbox]},
            "temporal": {
                "interval": [
                    [f"{stats['pubdate_min']}T00:00:00Z", f"{stats['pubdate_max']}T00:00:00Z"]
                ]
            },
        },
        "keywords": [
            "oil",
            "natural gas",
            "natural gas liquids",
            "undiscovered resources",
            "assessment unit",
            "petroleum geology",
            "energy resources",
            "USGS",
            "United States",
        ],
        "links": [
            {"rel": "self", "href": SELF, "type": "application/json"},
            {
                "rel": "root",
                "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",
                "type": "application/json",
            },
            {
                "rel": "parent",
                "href": f"{BASE}/stac-collection.json",
                "type": "application/json",
            },
            {
                "rel": "license",
                "href": "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits",
                "type": "text/html",
                "title": "USGS public domain / U.S. Government works",
            },
            {"rel": "about", "href": LANDING, "type": "text/html", "title": "USGS assessments of undiscovered oil and gas"},
            {"rel": "source", "href": COMMUNITY, "type": "text/html", "title": "ScienceBase community holding the source releases"},
            {
                "rel": "describedby",
                "href": f"{BASE}/{DATASET}/README.md",
                "type": "text/markdown",
            },
        ],
        "assets": {
            f"{DATASET}-parquet": {
                "href": f"{BASE}/{DATASET}.parquet",
                "type": "application/x-parquet",
                "title": "Assessment units with undiscovered oil, gas and NGL volumes (GeoParquet)",
                "roles": ["data"],
                "description": (
                    "One row per assessment unit: 240 rows, 240 distinct `ASSESSCODE`, so no "
                    "dedup is needed before aggregating on this asset. `sciencebase_id` and "
                    "`release_pubdate` are provenance, not feature keys, and repeat across the "
                    "units that came from the same release. Assessment units still overlap one "
                    "another in space, so a spatial join can return several units for one "
                    "location."
                ),
                "created": stats["created_parquet"],
                "table:columns": geom_columns(stats),
            },
            f"{DATASET}-pmtiles": {
                "href": f"{BASE}/{DATASET}.pmtiles",
                "type": "application/vnd.pmtiles",
                "title": "Assessment units (PMTiles)",
                "roles": ["visual"],
                "created": stats["created_pmtiles"],
                "vector:layers": [DATASET],
                "table:columns": pmtiles_columns(stats),
            },
            f"{DATASET}-hex": {
                "href": f"{BASE}/{DATASET}/hex/h0=*/data_0.parquet",
                "type": "application/x-parquet",
                "title": "Assessment units as H3 resolution 8 cells",
                "roles": ["data"],
                "created": stats["created_hex"],
                "description": hex_description(stats),
                "h3:native_resolution": 8,
                "h3:parent_resolutions": [0],
                "table:columns": hex_columns(stats),
            },
        },
    }


def readme(report, stats):
    return f"""# USGS Undiscovered Oil and Gas Assessment Units (United States)

USGS estimates of undiscovered, technically recoverable oil, gas and natural gas liquids for the
onshore and state-water United States, published as Assessment Unit (AU) polygons with a
probability distribution (F95, F50, F5, mean) per unit.

- **{stats['rows']} assessment units**, merged from the **{report['us_releases']} United States
  releases** of the USGS National and Global Oil and Gas Assessment Project
  ([ScienceBase community]({COMMUNITY})), accessed **{ACCESS_DATE}**.
- **No version number.** There is no national compilation upstream, so the edition record is the
  release manifest; each row names its release in `sciencebase_id` and `release_pubdate`.
- **{stats['rows_with_volumes']} of {stats['rows']} units carry volume estimates.** Only
  {len([r for r in report['releases'] if r['results_csv']])} releases publish a results table; the
  others publish boundaries and assessment input forms only. Null is never zero.
- **Units overlap.** Conventional and continuous units and different Total Petroleum Systems cover
  the same ground. Dedup by `ASSESSCODE` before summing, and only the mean is additive across
  units.
- License: **US federal public domain**
  ([USGS copyright and credits](https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits)).

## Assets

| Asset | URL |
|---|---|
| GeoParquet | `{BASE}/{DATASET}.parquet` |
| PMTiles | `{BASE}/{DATASET}.pmtiles` |
| H3 hex (res 8) | `{BASE}/{DATASET}/hex/h0=*/data_0.parquet` |
| STAC | `{SELF}` |

## DuckDB

```sql
INSTALL httpfs; LOAD httpfs;
INSTALL spatial; LOAD spatial;

-- largest mean undiscovered oil estimates
SELECT ASSESSNAME, PROVNAME, ASSESSYEAR, OIL_MN_MMB
FROM read_parquet('{BASE}/{DATASET}.parquet')
WHERE OIL_MN_MMB IS NOT NULL
ORDER BY OIL_MN_MMB DESC
LIMIT 10;

-- national mean undiscovered gas, deduped by assessment unit
SELECT SUM(GAS_MN_BCF) AS bcf FROM (
  SELECT DISTINCT ASSESSCODE, GAS_MN_BCF
  FROM read_parquet('{BASE}/{DATASET}.parquet')
);
```

`F95`, `F50` and `F5` are fractiles of a probability distribution: they describe one unit's range
and must not be summed across units. Only the mean (`*_MN_*`) is additive.

## MapLibre GL JS

The PMTiles `source-layer` is **`{DATASET}`**.

```js
import * as pmtiles from 'pmtiles';
maplibregl.addProtocol('pmtiles', new pmtiles.Protocol().tile);

map.addSource('noga', {{
  type: 'vector',
  url: 'pmtiles://{BASE}/{DATASET}.pmtiles'
}});

map.addLayer({{
  id: 'assessment-units',
  type: 'fill',
  source: 'noga',
  'source-layer': '{DATASET}',
  paint: {{
    'fill-color': '#b35806',
    'fill-opacity': 0.35,
    'fill-outline-color': '#7f3b08'
  }}
}});
```

## H3 hex

Native resolution **8**, partitioned on **h0**. One row is one (assessment unit, cell) pair, so
every attribute is repeated on every cell the unit covers, and overlapping units put several rows
on the same cell.

```sql
-- assessment units touching one cell
SELECT DISTINCT ASSESSNAME, ASSESSMETHOD
FROM read_parquet('{BASE}/{DATASET}/hex/h0=*/data_0.parquet')
WHERE h8 = 613196570331971583;
```

## Provenance

- Landing page: {LANDING}
- Source releases: {COMMUNITY} (accessed {ACCESS_DATE})
- Staged raw, per release: `s3://{BUCKET}/raw/{DATASET}/<sciencebase-id>/`
- Per-release build report: `s3://{BUCKET}/raw/{DATASET}/build-report.json`
- Merged GeoPackage: `{report['gpkg']['path']}`, {report['gpkg']['bytes']} bytes,
  sha256 `{report['gpkg']['sha256']}`
- Build recipe: [`catalog/usgs-noga/`](https://github.com/boettiger-lab/data-workflows/tree/main/catalog/usgs-noga)
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--stats", required=True)
    ap.add_argument("--out-dir", default="/tmp")
    args = ap.parse_args()

    report = json.load(open(args.report))
    stats = json.load(open(args.stats))

    stac_path = os.path.join(args.out_dir, "stac-collection.json")
    with open(stac_path, "w") as fh:
        json.dump(collection(report, stats), fh, indent=2)
        fh.write("\n")
    readme_path = os.path.join(args.out_dir, "README.md")
    with open(readme_path, "w") as fh:
        fh.write(readme(report, stats))
    print(stac_path)
    print(readme_path)


if __name__ == "__main__":
    main()
