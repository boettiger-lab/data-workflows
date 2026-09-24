#!/usr/bin/env python3
"""Write the STAC collection and README for usgs-paradox-basin-assessment-units (issue #722).

Numbers are never typed in by hand: they come from `build-report.json` (written by
k8s/paradox-preprocess.py) and `stats.json` (measured from the published parquet with
the duckdb-geo MCP). Run it, check the output, then publish with k8s/paradox-publish-stac.yaml:

  python3 catalog/usgs-paradox/make-stac.py --report /tmp/build-report.json \
      --stats /tmp/stats.json --out-dir /tmp
  scripts/verify-stac.py --no-data /tmp/stac-collection.json
"""

import argparse
import json
import os

BUCKET = "public-usgs"
DATASET = "paradox-basin-assessment-units"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
SELF = f"{BASE}/{DATASET}/stac-collection.json"
LANDING = (
    "https://www.usgs.gov/centers/central-energy-resources-science-center/science/"
    "paradox-basin-oil-and-gas-assessments"
)
RELEASE = "https://doi.org/10.5066/P9PAEXLB"
SCIENCEBASE = "https://www.sciencebase.gov/catalog/item/60c78b5ed34e86b9389aecf4"
FACT_SHEET = "https://pubs.usgs.gov/fs/2012/3031/"
LICENSE_URL = "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits"
ACCESS_DATE = "2026-09-24"

FRACTILES = [
    ("_F95", "95 percent chance of at least this volume, the low end of the assessed range"),
    ("_F50", "50 percent chance of at least this volume, the median"),
    ("_F5", "5 percent chance of at least this volume, the high end of the assessed range"),
    ("MEAN", "mean estimate"),
    ("STDEV", "standard deviation of the assessed distribution"),
]

COMMODITIES = [
    ("OIL", "undiscovered oil in oil accumulations", "million barrels"),
    ("ADGAS", "undiscovered associated (dissolved) gas in oil accumulations", "billion cubic feet"),
    ("NGL", "undiscovered natural gas liquids in oil accumulations", "million barrels"),
    ("NAGAS", "undiscovered nonassociated gas in gas accumulations", "billion cubic feet"),
    ("NAGL", "undiscovered natural gas liquids in gas accumulations", "million barrels"),
    ("OILLG", "the largest expected undiscovered conventional oil accumulation", "million barrels"),
    ("GASLG", "the largest expected undiscovered conventional gas accumulation", "billion cubic feet"),
]

ZERO_NOTE = (
    "A 0 is stored where the quantity does not apply to the unit's type (oil on a continuous gas "
    "unit, a largest accumulation on a continuous unit) and on every volume of the one unit that "
    "was not quantitatively assessed; there are no nulls. A 0 at the F95 fractile of a quantity "
    "whose mean is positive is a real low-end estimate."
)


def volume_columns():
    cols = []
    for prefix, what, unit in COMMODITIES:
        for suffix, phrase in FRACTILES:
            text = f"Technically recoverable {what}: {phrase}, in {unit}. {ZERO_NOTE}"
            if prefix in ("OILLG", "GASLG"):
                text = (
                    f"Size of {what}: {phrase}, in {unit}. Describes a single accumulation, so it "
                    f"is not a resource total and is never summed. {ZERO_NOTE}"
                )
            cols.append({"name": f"{prefix}{suffix}", "type": "double", "description": text})
    return cols


def columns(stats):
    v = stats["values"]
    return [
        {
            "name": "_cng_fid",
            "type": "int64",
            "description": (
                "Universal per-feature id, one per assessment unit and unique across the "
                "collection. Use it as the join key between the GeoParquet and the hex asset, "
                "and as the dedup key for COUNT(DISTINCT)."
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
            "name": "REG_NUM",
            "type": "string",
            "description": "USGS world energy region number. Values: 5=North America.",
            "values": v["REG_NUM"],
        },
        {
            "name": "REG_NAME",
            "type": "string",
            "description": "USGS world energy region name.",
            "values": v["REG_NAME"],
        },
        {
            "name": "PROVCODE",
            "type": "string",
            "description": "Four-digit USGS geologic province code. Values: 5021=Paradox Basin.",
            "values": v["PROVCODE"],
        },
        {
            "name": "PROV_NAME",
            "type": "string",
            "description": "USGS geologic province name.",
            "values": v["PROV_NAME"],
        },
        {
            "name": "TPSCODE",
            "type": "string",
            "description": (
                "Six-digit USGS Total Petroleum System code; the first four digits are the "
                "province code. Values: " + ", ".join(f"{c}={n}" for c, n in stats["tps"]) + "."
            ),
            "values": [c for c, _ in stats["tps"]],
        },
        {
            "name": "TPSNAME",
            "type": "string",
            "description": (
                "Total Petroleum System name. A Total Petroleum System groups the source rock, "
                "reservoirs and traps that share one hydrocarbon charge, and each is assessed as "
                "one or more assessment units."
            ),
            "values": [n for _, n in stats["tps"]],
        },
        {
            "name": "ASSESSCODE",
            "type": "string",
            "description": (
                "Eight-digit USGS assessment unit code, the identifier of the assessed area. One "
                "row per code in this collection."
            ),
        },
        {
            "name": "ASSESSNAME",
            "type": "string",
            "description": "Assessment unit name, for example Cane Creek Shale Gas.",
        },
        {
            "name": "ASSESSTYPE",
            "type": "string",
            "description": (
                "Assessment unit type. Values: Conventional=discrete accumulations held in "
                "structural or stratigraphic traps, Continuous Oil=a pervasive shale oil "
                "accumulation, Continuous Gas=a pervasive shale gas accumulation, Coalbed "
                "Gas=gas held in coal beds."
            ),
            "values": v["ASSESSTYPE"],
        },
        {
            "name": "ASSESSPROB",
            "type": "string",
            "description": (
                "Assessment status note. Values: Not quantitatively assessed=the unit was "
                "defined but no volumes were estimated, so all of its volume columns are 0. "
                "Null on the units that were assessed."
            ),
            "values": v["ASSESSPROB"],
        },
        *volume_columns(),
        {
            "name": "source_shapefile",
            "type": "string",
            "description": "Name of the single-unit shapefile in the USGS release this row came from.",
        },
    ]


def geom_columns(stats):
    return columns(stats) + [
        {
            "name": "geom",
            "type": "geometry",
            "description": "Assessment unit boundary (GeoParquet, EPSG:4326, as published by USGS).",
        }
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
            "description": "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads.",
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
    t = stats["totals"]
    m = report["merged"]
    return (
        "USGS 2011 assessment of **undiscovered, technically recoverable oil, gas and natural "
        "gas liquids** in the Paradox Basin Province (province 5021), as the "
        f"**{stats['rows']} assessment unit polygons** the estimates were made for. An "
        "assessment unit is a geologic area that USGS assesses as a whole: each polygon carries "
        "the probability distribution of the undiscovered volume inside it (F95, F50, F5, mean "
        "and standard deviation). It does not locate individual accumulations.\n\n"
        "**Footprint.** The province spans southeastern Utah, southwestern Colorado, "
        "northwestern New Mexico and northeastern Arizona, and the units are published whole, "
        "not clipped to any state. The Kaiparowits Plateau coalbed gas unit lies in southern "
        "Utah west of the basin proper.\n\n"
        f"**Totals, which match USGS Fact Sheet 2012-3031.** Mean undiscovered oil "
        f"{t['oil']:,} million barrels, gas {t['gas']:,} billion cubic feet and natural gas "
        f"liquids {t['ngl']:,} million barrels. Gas is associated plus nonassociated, and "
        "liquids are those from oil plus gas accumulations:\n\n"
        "```sql\n"
        "SELECT SUM(OILMEAN) AS oil_mmbo,\n"
        "       SUM(ADGASMEAN + NAGASMEAN) AS gas_bcf,\n"
        "       SUM(NGLMEAN + NAGLMEAN) AS ngl_mmb\n"
        f"FROM read_parquet('s3://{BUCKET}/{DATASET}.parquet');\n"
        "-- wrong: summing F95, F50, F5 or STDEV across units; only the mean is additive\n"
        "-- wrong: summing OILLG or GASLG, which describe one accumulation each\n"
        "```\n\n"
        "**Zero is not always an estimate.** The source stores 0, never null, both where a "
        "quantity does not apply to a unit's type (oil on a continuous gas unit) and for the "
        "Manning Canyon unit, which was defined but not quantitatively assessed "
        "(`ASSESSPROB = 'Not quantitatively assessed'`). A 0 at the F95 fractile of a quantity "
        "whose mean is positive is a real low-end estimate.\n\n"
        "**Assessment units overlap.** Conventional and continuous units in different "
        "reservoirs cover the same ground, so a spatial join can return several units for one "
        "location.\n\n"
        "**Edition and provenance.** This is the 2011 assessment, the current USGS assessment "
        "of the province; it supersedes the 1995 National Assessment, which is not included. "
        "Province 5021 is not part of the national `usgs-noga-assessment-units` collection. "
        f"Landing page: {LANDING}. Data release: {RELEASE}, read from ScienceBase on "
        f"**{ACCESS_DATE}**. The source shapefiles and FGDC metadata are staged under "
        f"`{report['raw_prefix']}` with per-file sizes and checksums in `build-report.json` "
        f"there. The merged GeoPackage the assets were built from is `{m['path']}` "
        f"({m['size']:,} bytes, sha256 `{m['sha256']}`)."
    )


def hex_description(stats):
    return (
        "Assessment unit boundaries as H3 cells at resolution 8, with resolution 0 as the "
        "partition key. One row is one (assessment unit, cell) pair, so every attribute of a "
        "unit, including all the volume columns, is repeated on every cell the unit covers. "
        "Units also overlap, so one cell can carry rows from several units: "
        f"{stats['hex_rows']:,} rows over {stats['distinct_h8']:,} distinct cells.\n\n"
        "```sql\n"
        "-- correct: one row per unit before summing a volume\n"
        "SELECT SUM(OILMEAN) FROM (\n"
        "  SELECT DISTINCT _cng_fid, OILMEAN\n"
        f"  FROM read_parquet('s3://{BUCKET}/{DATASET}/hex/h0=*/data_0.parquet')\n"
        ");\n"
        "-- correct: which units touch a cell\n"
        "SELECT DISTINCT ASSESSNAME, ASSESSTYPE\n"
        f"FROM read_parquet('s3://{BUCKET}/{DATASET}/hex/h0=*/data_0.parquet')\n"
        "WHERE h8 = ?;\n"
        "-- wrong: SUM over hex rows, which multiplies each unit by its cell count\n"
        "```\n\n"
        "Resolution 8 matches the source: unit boundaries are basin-scale interpretive lines "
        "drawn by the province geologist, and a finer resolution would claim more precision "
        "than the source has."
    )


def collection(report, stats):
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
        ],
        "id": "usgs-paradox-basin-assessment-units",
        "title": "USGS Paradox Basin Undiscovered Oil and Gas Assessment Units (2011)",
        "description": description(report, stats),
        "license": "public-domain",
        "sci:doi": "10.5066/P9PAEXLB",
        "sci:citation": (
            "U.S. Geological Survey, 2011, National Assessment of Oil and Gas Project - Paradox "
            "Basin (021) Assessment Units: U.S. Geological Survey data release, "
            f"{RELEASE}. Accessed {ACCESS_DATE}. Results: Whidden, K.J., 2012, Assessment of "
            "undiscovered oil and gas resources in the Paradox Basin Province, Utah, Colorado, "
            "New Mexico, and Arizona, 2011: USGS Fact Sheet 2012-3031."
        ),
        "created": stats["created"],
        "updated": stats["created"],
        "providers": [
            {"name": "U.S. Geological Survey", "roles": ["producer", "licensor"], "url": LANDING},
            {"name": "ScienceBase", "roles": ["host"], "url": SCIENCEBASE},
            {"name": "Boettiger Lab", "roles": ["processor"], "url": "https://boettiger-lab.github.io"},
        ],
        "extent": {
            "spatial": {"bbox": [stats["bbox"]]},
            "temporal": {"interval": [["2011-01-01T00:00:00Z", "2011-12-31T23:59:59Z"]]},
        },
        "keywords": [
            "oil", "natural gas", "natural gas liquids", "undiscovered resources",
            "assessment unit", "Paradox Basin", "Utah", "Colorado", "New Mexico", "Arizona", "USGS",
        ],
        "links": [
            {"rel": "self", "href": SELF, "type": "application/json"},
            {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "license", "href": LICENSE_URL, "type": "text/html", "title": "USGS copyrights and credits"},
            {"rel": "about", "href": LANDING, "type": "text/html", "title": "Paradox Basin Oil and Gas Assessments"},
            {"rel": "source", "href": SCIENCEBASE, "type": "text/html", "title": "USGS data release on ScienceBase"},
            {"rel": "cite-as", "href": RELEASE, "type": "text/html"},
            {"rel": "related", "href": FACT_SHEET, "type": "text/html", "title": "USGS Fact Sheet 2012-3031"},
            {"rel": "describedby", "href": f"{BASE}/{DATASET}/README.md", "type": "text/markdown"},
        ],
        "assets": {
            f"{DATASET}-parquet": {
                "href": f"{BASE}/{DATASET}.parquet",
                "type": "application/x-parquet",
                "title": "Assessment units with undiscovered oil, gas and NGL volumes (GeoParquet)",
                "roles": ["data"],
                "description": (
                    f"One row per assessment unit: {stats['rows']} rows, {stats['rows']} distinct "
                    "`ASSESSCODE`, so no dedup is needed before summing a mean on this asset."
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
    t = stats["totals"]
    m = report["merged"]
    return f"""# USGS Paradox Basin Undiscovered Oil and Gas Assessment Units (2011)

The USGS 2011 assessment of undiscovered, technically recoverable oil, gas and natural gas liquids
in the Paradox Basin Province (5021), as the {stats['rows']} assessment unit polygons the estimates
were made for. Each unit carries F95, F50, F5, mean and standard deviation volumes.

- Mean totals: **{t['oil']:,} million barrels of oil, {t['gas']:,} billion cubic feet of gas, {t['ngl']:,}
  million barrels of NGL**, matching [USGS Fact Sheet 2012-3031]({FACT_SHEET}).
- Footprint: southeastern Utah, southwestern Colorado, northwestern New Mexico, northeastern
  Arizona. Units are not clipped to any state.
- **Units overlap.** Conventional and continuous units cover the same ground.
- **Only the mean is additive.** F95, F50, F5 and STDEV describe one unit's distribution.
  `OILLG_*` / `GASLG_*` describe the single largest expected accumulation and are never summed.
- **0 is not always an estimate.** It marks quantities that do not apply to a unit's type, and
  every volume of Manning Canyon, which was not quantitatively assessed.
- License: **US federal public domain** ([USGS copyrights and credits]({LICENSE_URL})).

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

SELECT ASSESSNAME, ASSESSTYPE, OILMEAN, ADGASMEAN + NAGASMEAN AS gas_bcf
FROM read_parquet('{BASE}/{DATASET}.parquet')
ORDER BY gas_bcf DESC;

-- province totals (means only)
SELECT SUM(OILMEAN) AS oil_mmbo, SUM(ADGASMEAN + NAGASMEAN) AS gas_bcf,
       SUM(NGLMEAN + NAGLMEAN) AS ngl_mmb
FROM read_parquet('{BASE}/{DATASET}.parquet');
```

## MapLibre GL JS

The PMTiles `source-layer` is **`{DATASET}`**.

```js
import * as pmtiles from 'pmtiles';
maplibregl.addProtocol('pmtiles', new pmtiles.Protocol().tile);

map.addSource('paradox', {{
  type: 'vector',
  url: 'pmtiles://{BASE}/{DATASET}.pmtiles'
}});

map.addLayer({{
  id: 'paradox-assessment-units',
  type: 'fill',
  source: 'paradox',
  'source-layer': '{DATASET}',
  paint: {{
    'fill-color': ['match', ['get', 'ASSESSTYPE'],
      'Conventional', '#EF8A62', 'Coalbed Gas', '#4D4D4D', '#B2182B'],
    'fill-opacity': 0.35
  }}
}});
```

## H3 hex

Native resolution **8**, partitioned on **h0**. One row is one (assessment unit, cell) pair, so
every attribute repeats on every cell the unit covers. Dedup on `_cng_fid` before summing.

```sql
SELECT DISTINCT ASSESSNAME, ASSESSTYPE
FROM read_parquet('{BASE}/{DATASET}/hex/h0=*/data_0.parquet')
WHERE h8 = 613168513569259519;
```

## Provenance

- Landing page: {LANDING}
- Data release: {RELEASE} ([ScienceBase]({SCIENCEBASE})), accessed {ACCESS_DATE}
- Staged raw: `{report['raw_prefix']}` (checksums in `build-report.json`)
- Merged GeoPackage: `{m['path']}`, {m['size']:,} bytes, sha256 `{m['sha256']}`
- Build recipe: [`catalog/usgs-paradox/`](https://github.com/boettiger-lab/data-workflows/tree/main/catalog/usgs-paradox)
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--stats", required=True)
    ap.add_argument("--out-dir", default="/tmp")
    args = ap.parse_args()

    report = json.load(open(args.report))
    stats = json.load(open(args.stats))

    with open(os.path.join(args.out_dir, "stac-collection.json"), "w") as fh:
        json.dump(collection(report, stats), fh, indent=2)
        fh.write("\n")
    with open(os.path.join(args.out_dir, "README.md"), "w") as fh:
        fh.write(readme(report, stats))
    print(os.path.join(args.out_dir, "stac-collection.json"))


if __name__ == "__main__":
    main()
