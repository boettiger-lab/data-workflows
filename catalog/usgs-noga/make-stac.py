#!/usr/bin/env python3
"""Write the STAC collection and README for usgs-noga-assessment-units (issue #700).

Numbers are never typed in by hand: they come from `build-report.json` (written by
k8s/noga-preprocess.py) and `stats.json` (written by make-stats.py with the duckdb-geo MCP).
Run it, check the output, then publish with k8s/noga-publish-stac.yaml:

  python3 catalog/usgs-noga/make-stats.py --report /tmp/build-report.json --out /tmp/stats.json
  python3 catalog/usgs-noga/make-stac.py --report /tmp/build-report.json \
      --stats /tmp/stats.json --out-dir /tmp
  scripts/verify-stac.py --no-data /tmp/stac-collection.json
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
PARADOX = "paradox-basin-assessment-units"
WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]


def word(n):
    return WORDS[n] if n < len(WORDS) else str(n)


def series(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + ", and " + items[-1]

FRACTILE = {
    "F95": "95th-percentile (F95) estimate, the low end of the assessed range",
    "F50": "median (F50) estimate",
    "F5": "5th-percentile (F5) estimate, the high end of the assessed range",
    "MN": "mean estimate",
}

COMMODITY = {
    "OIL": ("undiscovered oil", "million barrels"),
    "GAS": ("undiscovered gas, reported as one combined figure", "billion cubic feet"),
    "AG": ("undiscovered associated gas, the gas dissolved in oil accumulations", "billion cubic feet"),
    "NAGAS": ("undiscovered nonassociated gas, the gas in accumulations without oil", "billion cubic feet"),
    "NGL": ("undiscovered natural gas liquids, reported as one combined figure", "million barrels"),
    "AGL": ("undiscovered natural gas liquids from associated gas", "million barrels"),
    "NAGL": ("undiscovered natural gas liquids from nonassociated gas", "million barrels"),
}

NOT_ASSESSED = (
    "Null means this commodity was not assessed for this assessment unit, or the unit's "
    "release publishes no results table; it is not an estimate of zero. A stored 0 is a "
    "real estimate, which is common at the F95 fractile."
)


def combined_note(stats, split_cols, kind, n_combined, n_split):
    """The GAS_*/NGL_* columns hold the unsplit figure; most units report the split instead."""
    return (
        f"Filled on only {n_combined} of the {stats['rows']} assessment units: those whose release "
        f"reports {kind} without splitting it into associated and nonassociated. The other "
        f"{n_split} units with {kind} estimates report it in {split_cols} and are null here, so "
        f"this column alone is not the total {kind}. No unit has both. A stored 0 is a real "
        "estimate."
    )


def volume_columns(stats):
    notes = {
        "GAS": combined_note(stats, "`AG_*_BCF` and `NAGAS_*_BCF`", "gas",
                             stats["rows_combined_gas"], stats["rows_split_gas"]),
        "NGL": combined_note(stats, "`AGL_*_MMB` and `NAGL_*_MMB`", "natural gas liquids",
                             stats["rows_combined_ngl"], stats["rows_split_ngl"]),
    }
    cols = []
    for prefix, (what, unit) in COMMODITY.items():
        suffix = "MMB" if unit == "million barrels" else "BCF"
        note = notes.get(prefix, NOT_ASSESSED)
        for fractile, phrase in FRACTILE.items():
            cols.append(
                {
                    "name": f"{prefix}_{fractile}_{suffix}",
                    "type": "double",
                    "description": (
                        f"Technically recoverable {what} at the {phrase}, in {unit}. "
                        f"{note}"
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
                "USGS world energy region number; 5 for North America. Null on the "
                f"{stats['null_region']} assessment units whose source release omits the "
                "region fields."
            ),
        },
        {
            "name": "REGNAME",
            "type": "string",
            "description": (
                f"USGS world energy region name. Null on the {stats['null_region']} assessment "
                "units whose source release omits the region fields."
            ),
            "values": stats["values"]["REGNAME"],
        },
        code_list(
            "PROVCODE",
            "Four-digit USGS geologic province code, the stable identifier for the province: "
            f"the accompanying PROVNAME is missing on {stats['null_provname']} assessment units "
            f"and spelled two ways for {word(len(stats['provname_variants']))} codes, so group "
            "on the code.",
            stats,
            "provcode_names",
        ),
        {
            "name": "PROVNAME",
            "type": "string",
            "description": (
                "Geologic province name, for example Permian Basin, Gulf Coast Mesozoic or "
                "Northern Alaska. Upstream spelling is inconsistent, so this is not a reliable "
                f"grouping key: it is null on {stats['null_provname']} of the {stats['rows']} "
                "assessment units, "
                + series([f"province {c} appears as both {' and '.join(n)}"
                          for c, n in stats["provname_variants"].items()])
                + ". Group on PROVCODE instead."
            ),
            "values": stats["values"]["PROVNAME"],
        },
        code_list(
            "TPSCODE",
            "Six-digit USGS Total Petroleum System code; the first four digits are the province "
            f"code. {word(len(stats['tpsname_variants'])).capitalize()} codes carry two upstream "
            f"spellings of their name ({', '.join(stats['tpsname_variants'])}), so group on the "
            "code rather than TPSNAME.",
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
                f"units. Null on {stats['null_tpsname']} of the {stats['rows']} assessment units."
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
    cols += volume_columns(stats)
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
                "the row: the merged layer has no version of its own."
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
        "**Coverage is the releases in that community, not every assessed US province.** "
        "Assessments published outside it are not included. The Paradox Basin (province 5021) "
        f"is a separate collection, `{PARADOX}`.\n\n"
        f"**Volume estimates cover part of the layer.** Only {len(with_results)} of the "
        f"{report['us_releases']} releases publish a per-AU results table; the rest, published "
        "2018 to 2022, publish the boundaries and the assessment input forms only. So "
        f"{stats['rows_with_volumes']} of the {stats['rows']} assessment units carry oil, gas and "
        "NGL fractiles and the remainder carry nulls. A null is always \"not published\" or \"not "
        "assessed\", never an estimate of zero.\n\n"
        "**Assessment units overlap.** Conventional and continuous units, and different Total "
        "Petroleum Systems, are separate resources that can stack over one location, so a "
        "spatial join returns several units per location. Volumes are per-unit totals, not "
        "densities, and the GeoParquet has one row per unit, so the means sum directly across "
        "units.\n\n"
        "**Gas is reported two ways.** Most units split gas into associated (`AG_*_BCF`) and "
        f"nonassociated (`NAGAS_*_BCF`); {word(stats['rows_combined_gas'])} report only the combined "
        "`GAS_*_BCF`. No unit has both, so total gas combines them (natural gas liquids work the "
        "same way with `NGL_*`, `AGL_*` and `NAGL_*`):\n\n"
        "```sql\n"
        "-- correct: total mean undiscovered oil and gas\n"
        "SELECT SUM(OIL_MN_MMB) AS oil_mmb,\n"
        "       SUM(COALESCE(GAS_MN_BCF, COALESCE(AG_MN_BCF, 0) + COALESCE(NAGAS_MN_BCF, 0))) AS gas_bcf\n"
        f"FROM read_parquet('s3://{BUCKET}/{DATASET}.parquet');\n"
        f"-- wrong: SUM(GAS_MN_BCF) alone covers {word(stats['rows_combined_gas'])} units and is about "
        f"{stats['gas_mn_total_bcf'] / stats['gas_mn_combined_bcf']:.0f} times too low\n"
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
        f"assessment units overlap, so a cell carries {stats['hex_rows'] / stats['distinct_h8']:.1f} "
        "rows on average. Resolution 8 matches "
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
            f"{COMMUNITY}. Merged layer; accessed {ACCESS_DATE}."
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
                    f"One row per assessment unit: {stats['rows']} rows, "
                    f"{stats['distinct_assesscode']} distinct `ASSESSCODE`, so no "
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
- **Coverage is the releases in that community**, not every assessed US province. The Paradox
  Basin (province 5021) is a separate collection,
  [`{PARADOX}`]({BASE}/{PARADOX}/README.md).
- **No version number.** There is no national compilation upstream, so the edition record is the
  release manifest; each row names its release in `sciencebase_id` and `release_pubdate`.
- **{stats['rows_with_volumes']} of {stats['rows']} units carry volume estimates.** Only
  {len([r for r in report['releases'] if r['results_csv']])} releases publish a results table; the
  others publish boundaries and assessment input forms only. Null is never zero.
- **Units overlap.** Conventional and continuous units and different Total Petroleum Systems cover
  the same ground, so a spatial join returns several units per location. Only the mean is
  additive across units.
- **Gas is reported two ways.** Most units split it into `AG_*` (associated) and `NAGAS_*`
  (nonassociated); {stats['rows_combined_gas']} report only the combined `GAS_*`. No unit has
  both, so total gas is the `COALESCE` below, not `SUM(GAS_MN_BCF)`.
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

-- total mean undiscovered gas: combined GAS_ where reported, else associated + nonassociated
SELECT SUM(COALESCE(GAS_MN_BCF, COALESCE(AG_MN_BCF, 0) + COALESCE(NAGAS_MN_BCF, 0))) AS gas_bcf
FROM read_parquet('{BASE}/{DATASET}.parquet');
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


def bucket_section(report, stats):
    return f"""## USGS Undiscovered Oil and Gas Assessment Units — United States

USGS estimates of undiscovered, technically recoverable oil, gas and natural gas liquids for
the onshore and state-water United States, as Assessment Unit (AU) polygons with a probability
distribution (F95, F50, F5, mean) per unit: **{stats['rows']} assessment units**, native H3 resolution **8**.

USGS publishes the national assessment one province or formation release at a time and there is
no national compilation upstream, so this layer was merged from the **{report['us_releases']} United States releases**
in the [National and Global Oil and Gas Assessment Project ScienceBase community]({COMMUNITY}),
accessed **{ACCESS_DATE}**. It carries **no version number**: the edition record is the release
manifest, and each row names its own release in `sciencebase_id` and `release_pubdate`.
Coverage is the releases in that community, not every assessed US province: the Paradox Basin
(province 5021) is the separate `{PARADOX}` collection.

> **Three things to know before aggregating.** Assessment units **overlap** (conventional and
> continuous units and different Total Petroleum Systems cover the same ground), so a spatial
> join returns several units per location; on the hex asset, dedup by `ASSESSCODE` before any
> `SUM`. Only the **mean** is additive across units — `F95`, `F50` and
> `F5` are fractiles of one unit's distribution. And **null is never zero**: only {stats['rows_with_volumes']} of the {stats['rows']}
> units carry volume estimates, because the remaining releases publish boundaries and assessment
> input forms without a results table.

```sql
-- total mean undiscovered gas: most units split it into AG_ and NAGAS_; a few report only GAS_
SELECT SUM(COALESCE(GAS_MN_BCF, COALESCE(AG_MN_BCF, 0) + COALESCE(NAGAS_MN_BCF, 0))) AS gas_bcf
FROM read_parquet('{BASE}/{DATASET}.parquet');
```

Full documentation:
[`{DATASET}/README.md`]({BASE}/{DATASET}/README.md)
and
[`{DATASET}/stac-collection.json`]({SELF}).

**Source:** USGS assessments of undiscovered oil and gas —
<{LANDING}>
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
    with open(os.path.join(args.out_dir, "bucket-section.md"), "w") as fh:
        fh.write(bucket_section(report, stats))
    print(stac_path)
    print(readme_path)


if __name__ == "__main__":
    main()
