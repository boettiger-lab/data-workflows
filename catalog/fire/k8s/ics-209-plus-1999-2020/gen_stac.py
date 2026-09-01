#!/usr/bin/env python3
"""Generate stac-collection.json + README.md for ICS-209-PLUS wildfire 1999-2020 (#636).

Runs on the cluster (see ics-209-plus-publish-stac.yaml) so it can read live schemas over the
internal S3 endpoint rather than trusting a schema transcribed by hand.

Three inputs, in priority order:
  1. the LIVE parquet schemas on S3            -> column names and types
  2. the reference bundle's *_field-definitions.csv (staged in raw/) -> column prose
  3. _codes.json                                -> coded domains, enumerated FROM THE DATA (#294)

Writes to a staging prefix; the caller verifies with scripts/verify-stac.py before publishing to
the canonical paths.
"""
import csv, io, json, os, sys

import duckdb

BUCKET  = 'public-fire'
DATASET = 'ics-209-plus-1999-2020'
LAYER   = 'wf-incidents'
RAW     = f's3://{BUCKET}/raw/{DATASET}'
PUB     = 'https://s3-west.nrp-nautilus.io'
HERE    = os.path.dirname(os.path.abspath(__file__))

# ---- measured facts. Every number here came from a query against the staged source or the
# ---- published artifacts; see BUILD-NOTES.md for how each was obtained.
N_INCIDENTS      = 34622
N_WITH_GEOM      = 34200
N_NULL_GEOM      = 422
N_MIRRORED_COORD = 439      # POO_LONGITUDE = -POO_LATITUDE, 1999-2002
N_OFFUS_OTHER    = 4        # otherwise off-US, all 2015
N_SITREPS        = 182826
FOD_JOIN_IDS     = 35208
FOD_MATCHED      = 33247
BBOX             = [-171.400, 17.9656, -65.3253, 70.1381]   # plausible records only
H3_NATIVE        = 10
H3_PARENTS       = [9, 8, 0]

SIDECARS = [
    # (asset key,            s3 basename,      definitions file,                                   title)
    ('wf-sitreps-parquet',       'sitreps',       'ics209-plus_sitrep_field-definitions.csv',
     'Situation reports (sitreps), 1999-2020'),
    ('wf-complex-assoc-parquet', 'complex-assoc', 'ics209-plus-wf-complex-assoc_field-definitions.csv',
     'Complex / member fire associations, 1999-2020'),
    ('wf-by-tract-parquet',      'by-tract',      'ics209-plus-wf-spatio-temporal_field-definitions.csv',
     'Incident x census tract linkage, 1999-2020'),
    ('wf-by-county-parquet',     'by-county',     'ics209-plus-wf-spatio-temporal_field-definitions.csv',
     'Incident x county linkage, 1999-2020'),
    ('wf-by-cbg-parquet',        'by-cbg',        'ics209-plus-wf-spatio-temporal_field-definitions.csv',
     'Incident x census block group linkage, 1999-2020'),
    ('sit209-lookup-codes-parquet', 'lookup-codes', None,
     'SIT-209 official lookup code definitions'),
]

STAC_TYPE = {
    'VARCHAR': 'string', 'DOUBLE': 'double', 'FLOAT': 'float', 'BIGINT': 'int64',
    'INTEGER': 'int32', 'BOOLEAN': 'boolean', 'TIMESTAMP': 'datetime', 'DATE': 'date',
    'UBIGINT': 'uint64', 'HUGEINT': 'int128',
}


def connect():
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;")
    con.execute(f"""
        CREATE SECRET s (TYPE S3, KEY_ID '{os.environ['AWS_ACCESS_KEY_ID']}',
            SECRET '{os.environ['AWS_SECRET_ACCESS_KEY']}',
            ENDPOINT '{os.environ['AWS_S3_ENDPOINT']}', URL_STYLE 'path', USE_SSL false)
    """)
    return con


def schema(con, path):
    """(name, stac_type) for every column, read live from the published parquet."""
    out = []
    for name, dtype, *_ in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall():
        base = dtype.split('(')[0].upper()
        out.append((name, 'geometry' if base == 'GEOMETRY' else STAC_TYPE.get(base, 'string')))
    return out


DEFS_DIR = os.environ.get('DEFS_DIR', HERE)


def load_definitions(con, filename):
    """Column -> upstream prose, from a reference-bundle field-definitions CSV.

    Each file carries a one-line banner above the real header, and the header itself varies
    between files, so locate the 'Column Name' row rather than assuming a fixed skip. Files are
    read from DEFS_DIR (the job rclone-copies them out of raw/ first) rather than over httpfs,
    so this does not depend on read_text being available for s3://.
    """
    if filename is None:
        return {}
    with open(os.path.join(DEFS_DIR, filename), encoding='utf-8-sig') as fh:
        rows = list(csv.reader(fh))
    start = next((i for i, r in enumerate(rows)
                  if r and r[0].strip().lower() == 'column name'), 0) + 1
    defs = {}
    for r in rows[start:]:
        if len(r) >= 2 and r[0].strip():
            # The complex-assoc file writes 'MEMBER INC_IDENTIFIER'; the data uses an underscore.
            key = r[0].strip().replace(' ', '_')
            if r[1].strip():
                defs[key] = ' '.join(r[1].split())
    return defs


GLOBAL_DEFS = {}


def register_definitions(defs):
    """Fold a definitions file into the ONE global column -> prose map.

    First registration wins, so callers register in authority order (incident summary table
    first). A single text per column name is a hard requirement: mcp-data-server's #303 renderer
    dedups per-column descriptions across assets by keeping the first it sees and dropping the
    others, so two assets documenting the same column differently silently lose one of them.
    """
    for k, v in defs.items():
        GLOBAL_DEFS.setdefault(k, v)


def columns(cols, defs, codes, per_feature_note=None, skip=()):
    """STAC table:columns, prose from the global map, coded domains from _codes.json."""
    out = []
    for name, ctype in cols:
        if name in skip:
            continue
        col = {'name': name, 'type': ctype}
        desc = []
        text = GLOBAL_DEFS.get(name, defs.get(name))
        if name in codes:
            desc.append(codes[name]['description'])
            col['values'] = codes[name]['values']
        elif text:
            desc.append(text + ('.' if not text.endswith('.') else ''))
        if name == 'geom':
            desc = ['Point geometry: the incident point of origin '
                    '(POO_LONGITUDE, POO_LATITUDE) in EPSG:4326. NULL for the '
                    f'{N_NULL_GEOM} incidents with no reported coordinate.']
        elif name == '_cng_fid':
            desc = ['Synthetic per-row feature id assigned at conversion. Row-unique across all '
                    f'{N_INCIDENTS:,} incidents and the dedup key for the hex asset. Local to this '
                    'table — do not join it to another dataset.']
        elif name == 'SOURCE_ROW':
            desc = ['0-based row index from the upstream CSV export. Retained because this table '
                    'has no unique natural key, so it is the only way to address a single row. '
                    'Not a domain identifier and not comparable across tables.']
        elif name.startswith('h') and name[1:].isdigit():
            r = int(name[1:])
            desc = [f'H3 cell ID at resolution {r}'
                    + (f' (native resolution; one row per (incident, h{r}) pair).' if r == H3_NATIVE
                       else '. Partition key for hive-partitioned reads.' if r == 0 else '.')]
        if per_feature_note and name in per_feature_note:
            desc.append(per_feature_note[name])
        if desc:
            col['description'] = ' '.join(desc)
        out.append(col)
    return out


def main():
    con = connect()

    flat = f's3://{BUCKET}/{DATASET}/{LAYER}.parquet'
    hexa = f's3://{BUCKET}/{DATASET}/{LAYER}/hex/h0=*/data_0.parquet'
    flat_cols = schema(con, flat)
    hex_cols  = schema(con, hexa)

    codes = {k: v for k, v in json.load(open(f'{HERE}/_codes.json')).items()
             if not k.startswith('_')}

    # Authority order: the incident summary table is the canonical layer, so its prose wins for
    # any column the sitrep / complex-assoc / spatio-temporal files also describe.
    inc_defs = load_definitions(con, 'ics209-plus-wf-incident_field-definitions.csv')
    register_definitions(inc_defs)
    for _f in ('ics209-plus_sitrep_field-definitions.csv',
               'ics209-plus-wf-complex-assoc_field-definitions.csv',
               'ics209-plus-wf-spatio-temporal_field-definitions.csv'):
        register_definitions(load_definitions(con, _f))
    print(f'{len(GLOBAL_DEFS)} column definitions registered (one text per column name)')

    coverage = (
        f"**Coverage stops at 2020.** FPA-FOD's `ICS_209_PLUS_INCIDENT_JOIN_ID` runs to 2024, so "
        f"any join to FPA-FOD must be a LEFT join — an inner join silently drops the four most "
        f"recent fire years. Two shortfalls compound: (1) no incident here is later than 2020; and "
        f"(2) of the {FOD_JOIN_IDS:,} distinct pre-2021 FPA-FOD join ids, only {FOD_MATCHED:,} "
        f"({100.0 * FOD_MATCHED / FOD_JOIN_IDS:.1f}%) match a row in this release. The "
        f"{FOD_JOIN_IDS - FOD_MATCHED:,} unmatched are not a formatting artifact: case and "
        f"whitespace normalization recovers none, none appear in the sitreps table, and the "
        f"ICS-209-PLUS all-hazards bundle accounts for only 2 of them. figshare publishes versions "
        f"1-3 of this record only, so FPA-FOD's 7th edition (2026) was evidently linked against an "
        f"ICS-209-PLUS vintage that was never published here."
    )

    coords = (
        f"**{N_MIRRORED_COORD + N_OFFUS_OTHER} incidents carry defective point-of-origin "
        f"coordinates, published exactly as upstream supplies them.** {N_MIRRORED_COORD} records "
        f"(all 1999-2002) have `POO_LONGITUDE = -POO_LATITUDE` — the longitude field holds the "
        f"negated latitude, placing the fire in the Atlantic — and {N_OFFUS_OTHER} more (all 2015) "
        f"are otherwise outside the United States. The true longitudes are not recoverable from the "
        f"record, so they are mirrored faithfully rather than repaired by inference. Exclude them "
        f"before any distance-band or spatial-join analysis:\n\n"
        f"```sql\nWHERE POO_LONGITUDE <> -POO_LATITUDE\n  AND POO_LONGITUDE BETWEEN -180 AND -64\n"
        f"  AND POO_LATITUDE  BETWEEN   17 AND  72\n```"
    )

    description = "\n\n".join([
        f"ICS-209-PLUS wildfire incident summaries, {N_INCIDENTS:,} incidents reported to the US "
        f"National Incident Management System between 1999 and 2020, mined from ICS-209 situation "
        f"reports by St. Denis et al. (2023). Each record is one incident: final size, cause, "
        f"suppression strategy, projected cost, peak personnel and aerial resources, maximum fire "
        f"spread rate, structures threatened/damaged/destroyed, fatalities and injuries, plus "
        f"pre-computed links to FPA-FOD, MTBS and FIRED. `INCIDENT_ID` (`year_incident-number_name`) "
        f"is the join key and is unique on every row of this table.",

        f"This is the **response-side** companion to the ignition and burned-area layers: FPA-FOD "
        f"records where fires started and MTBS records how much burned, but neither carries how a "
        f"fire was fought. Join on `INCIDENT_ID = FPA-FOD.ICS_209_PLUS_INCIDENT_JOIN_ID`.",

        coverage,
        coords,

        f"**{N_NULL_GEOM} incidents have no reported coordinate** and therefore a NULL geometry. "
        f"They are present in the GeoParquet but absent from the PMTiles and hex assets, so hex "
        f"`COUNT(DISTINCT _cng_fid)` is {N_WITH_GEOM:,}, not {N_INCIDENTS:,}. Count incidents from "
        f"the GeoParquet, not the hex.",

        "**Point resolution.** Each incident point of origin was hexed to H3 resolution "
        f"{H3_NATIVE} — one point resolves to exactly one ~15,000 m² cell, so there is no "
        f"per-feature cell expansion and no dedup is needed for spatial aggregation. Multiple "
        f"incidents falling in the same cell are **not** deduplicated. Parent resolutions "
        f"{', '.join('h%d' % r for r in H3_PARENTS)} are carried so this layer joins FPA-FOD and "
        f"the raster layers at the catalog's universal `h8` key.",

        "**Columns introduced mid-series.** `SUPPRESSION_METHOD` begins in 2007, "
        "`PEAK_EVACUATIONS` / `FATALITIES_PUBLIC` / `FATALITIES_RESPONDER` in 2013 and `POO_CITY` "
        "in 2014; `LL_CONFIDENCE` is populated only where ICS-209-PLUS revised a coordinate. A "
        "null in those columns means **not collected**, not zero — do not read a pre-2013 null "
        "fatality count as a fire with no fatalities. Use `FATALITIES` (complete, zero values "
        "included) for the full series.",

        "**Stringified list columns.** `FOD_FIRE_LIST`, `MTBS_FIRE_LIST`, `FOD_CAUSE`, "
        "`FOD_COORD_LIST`, `SUP_SERIES` and `LRGST_FOD_COORDS` are Python list/dict literals stored "
        "as text, not arrays — one incident maps to many fires. Never SUM across them; parse them, "
        "or use the scalar companions (`FOD_FIRE_NUM`, `MTBS_FIRE_NUM`, `FOD_FINAL_ACRES`, "
        "`LRGST_FOD_ID`). `SUP_SERIES` in particular holds `nan` tokens inside its text.",

        "**Free-text placeholders.** A handful of location and description fields contain literal "
        "`\"None\"`, `\"NONE\"`, `\"na\"` or empty-string values as typed by the reporting unit "
        "(16 rows across `POO_COUNTY`, `POO_CITY`, `POO_SHORT_LOCATION_DESC`, "
        "`INCIDENT_DESCRIPTION` and `INCIDENT_NAME`). These are upstream entries, left unaltered; "
        "treat them as missing.",

        f"**Incident types.** `INCTYP_ABBREVIATION` mixes wildfire (`WF`, 33,641), wildland fire "
        f"use (`WFU`, 772), prescribed fire (`RX`, 144) and complex umbrella records (`CX`, 65). "
        f"Filter to `WF` for a wildfire-only population; `CX` records double-count member fires "
        f"whose own rows are also present.",

        f"Companion tables are published alongside as non-spatial parquet, all joining on "
        f"`INCIDENT_ID`: {N_SITREPS:,} individual situation reports (5.28 per incident on average — "
        f"dedup before aggregating incident attributes), complex/member associations, "
        f"incident x tract / county / block-group linkages, and the official SIT-209 lookup codes.",
    ])

    # Per-feature totals repeated across hex rows. Points expand to exactly one cell, so this is
    # only a caution for the sidecar joins, not the hex itself — stated on the asset regardless.
    hex_note = (
        f"One row per (incident, h{H3_NATIVE}) pair. Each incident is a POINT and resolves to "
        f"exactly ONE res-{H3_NATIVE} cell, so there is no per-feature cell duplication and every "
        f"column is safe to aggregate as-is — the usual 'dedup before SUM on hex' warning does not "
        f"apply to this asset. `COUNT(DISTINCT _cng_fid)` = `COUNT(*)` = {N_WITH_GEOM:,}, which is "
        f"{N_NULL_GEOM} fewer than the {N_INCIDENTS:,} rows in the GeoParquet: those "
        f"{N_NULL_GEOM} incidents have no reported coordinate, so their geometry is NULL, they "
        f"polyfill to zero cells and are absent from the hex. That shortfall is expected and is "
        f"not a partial build — count incidents from the GeoParquet. Rolling up to a parent resolution "
        f"(`GROUP BY h8`) is a plain COUNT/SUM. For cell area, see the h3-guide — do not assume a "
        f"nominal per-resolution constant."
    )

    assets = {
        f'{LAYER}-parquet': {
            'href': f'{PUB}/{BUCKET}/{DATASET}/{LAYER}.parquet',
            'type': 'application/x-parquet',
            'title': f'ICS-209-PLUS wildfire incidents 1999-2020 (GeoParquet, {N_INCIDENTS:,} points)',
            'description': (f'One row per incident, {N_INCIDENTS:,} rows, `INCIDENT_ID` unique on '
                            f'every row. {N_NULL_GEOM} rows have a NULL geometry.'),
            'roles': ['data'],
            'table:primary_geometry': 'geom',
            'table:columns': columns(flat_cols, inc_defs, codes),
        },
        f'{LAYER}-pmtiles': {
            'href': f'{PUB}/{BUCKET}/{DATASET}/{LAYER}.pmtiles',
            'type': 'application/vnd.pmtiles',
            'title': 'ICS-209-PLUS wildfire incidents 1999-2020 (PMTiles)',
            'description': (f'{N_WITH_GEOM:,} tiled points — the {N_NULL_GEOM} incidents with no '
                            f'coordinate are absent. MapLibre `source-layer` is `{LAYER}`.'),
            'roles': ['visual'],
            'vector:layers': [LAYER],
            # Lean form per the PMTiles standard: name + type + values, prose stays canonical on
            # the GeoParquet asset. Tippecanoe keeps every attribute minus the geometry.
            'table:columns': [
                {k: v for k, v in c.items() if k in ('name', 'type', 'values')}
                for c in columns(flat_cols, inc_defs, codes, skip=('geom',))
            ],
        },
        f'{LAYER}-hex': {
            'href': f'{PUB}/{BUCKET}/{DATASET}/{LAYER}/hex/h0=*/data_0.parquet',
            'type': 'application/x-parquet',
            'title': f'ICS-209-PLUS wildfire incidents 1999-2020 (H3 res-{H3_NATIVE} hex)',
            'description': hex_note,
            'roles': ['data'],
            'h3:native_resolution': H3_NATIVE,
            'h3:parent_resolutions': H3_PARENTS,
            'table:columns': columns(hex_cols, inc_defs, codes),
        },
    }

    for key, base, deffile, title in SIDECARS:
        path = f's3://{BUCKET}/{DATASET}-{base}.parquet'
        cols = schema(con, path)
        n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{path}')").fetchone()[0]
        defs = load_definitions(con, deffile)
        extra = ''
        if base == 'sitreps':
            extra = (' `INCIDENT_ID` is NOT unique here — one row per situation report, 5.28 per '
                     'incident on average (`INC_MGMT_NUM_SITREPS` gives the count). Dedup by '
                     '`INCIDENT_ID` before aggregating any incident-level attribute, or you will '
                     'multiply it by the report count.')
        elif base in ('by-tract', 'by-county', 'by-cbg'):
            extra = (' `INCIDENT_ID` repeats: one row per (incident, spatial unit) pair, so a large '
                     'fire spans many units. Neither column alone is a key.')
        elif base == 'complex-assoc':
            extra = (' Maps a complex umbrella record (`CPLX_INCIDENT_ID`) to its member fires '
                     '(`MEMBER_INCIDENT_ID`); neither is unique on its own.')
        elif base == 'lookup-codes':
            extra = (' Official SIT-209 code definitions from the reference bundle, keyed by '
                     '`CODE_TYPE` + `ABBREVIATION`. Note it does NOT define '
                     '`SUPPRESSION_METHOD`=`MMS`, which does occur in the data.')
        assets[key] = {
            'href': f'{PUB}/{BUCKET}/{DATASET}-{base}.parquet',
            'type': 'application/x-parquet',
            'title': f'ICS-209-PLUS {title}',
            'description': f'{n:,} rows. Joins to the incident layer on `INCIDENT_ID`.' + extra,
            'roles': ['data'],
            'table:columns': columns(cols, defs, codes),
        }

    collection = {
        'type': 'Collection',
        'stac_version': '1.0.0',
        'stac_extensions': [
            'https://stac-extensions.github.io/table/v1.2.0/schema.json',
            'https://stac-extensions.github.io/scientific/v1.0.0/schema.json',
            'https://stac-extensions.github.io/version/v1.2.0/schema.json',
        ],
        'id': f'{DATASET}-{LAYER}',
        'title': 'ICS-209-PLUS wildfire incidents and situation reports, 1999-2020',
        'description': description,
        'license': 'CC-BY-4.0',
        'keywords': ['wildfire', 'incident management', 'ICS-209', 'suppression', 'fire response',
                     'cost', 'personnel', 'evacuations', 'structures', 'United States'],
        'version': '3',
        'sci:doi': '10.6084/m9.figshare.19858927.v3',
        'sci:citation': ('St. Denis, L.A., Short, K.C., McConnell, K., Cook, M.C., Mietkiewicz, '
                         'N.P., Buckland, M., Balch, J.K. (2023). All-hazards dataset mined from '
                         'the US National Incident Management System 1999-2020. figshare. '
                         'https://doi.org/10.6084/m9.figshare.19858927.v3'),
        'sci:publications': [{
            'doi': '10.1038/s41597-023-02276-y',
            'citation': ('St. Denis, L.A. et al. (2023). All-hazards dataset mined from the US '
                         'National Incident Management System 1999-2020. Scientific Data 10, 112.'),
        }],
        'providers': [
            {'name': 'St. Denis et al. / Earth Lab, University of Colorado Boulder',
             'roles': ['producer', 'licensor'], 'url': 'https://doi.org/10.6084/m9.figshare.19858927.v3'},
            {'name': 'USDA Forest Service Fire Sciences Laboratory', 'roles': ['producer'],
             'url': 'https://research.fs.usda.gov/firelab/products/dataandtools/ics-209-plus'},
            {'name': 'Boettiger Lab, UC Berkeley', 'roles': ['processor', 'host'],
             'url': f'{PUB}/{BUCKET}/'},
        ],
        'extent': {
            'spatial': {'bbox': [BBOX]},
            'temporal': {'interval': [['1999-01-01T00:00:00Z', '2020-12-31T23:59:59Z']]},
        },
        'links': [
            {'rel': 'self', 'href': f'{PUB}/{BUCKET}/{DATASET}/{LAYER}/stac-collection.json',
             'type': 'application/json'},
            {'rel': 'root', 'href': f'{PUB}/public-data/stac/catalog.json', 'type': 'application/json'},
            {'rel': 'parent', 'href': f'{PUB}/{BUCKET}/stac-collection.json', 'type': 'application/json'},
            {'rel': 'license', 'href': 'https://creativecommons.org/licenses/by/4.0/',
             'type': 'text/html', 'title': 'CC BY 4.0'},
            {'rel': 'about', 'href': 'https://doi.org/10.6084/m9.figshare.19858927.v3',
             'type': 'text/html'},
            {'rel': 'cite-as', 'href': 'https://doi.org/10.6084/m9.figshare.19858927.v3'},
        ],
        'assets': assets,
    }

    out_json = '/tmp/stac-collection.json'
    with open(out_json, 'w') as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)
    print(f'wrote {out_json}')
    for k, a in assets.items():
        print(f'  {k}: {len(a.get("table:columns", []))} columns')

    with open('/tmp/README.md', 'w') as f:
        f.write(readme(assets))
    print('wrote /tmp/README.md')
    return collection


def readme(assets):
    flat = f'{PUB}/{BUCKET}/{DATASET}/{LAYER}.parquet'
    return f"""# ICS-209-PLUS wildfire incidents and situation reports, 1999-2020

{N_INCIDENTS:,} wildfire incident summaries reported to the US National Incident Management System,
mined from ICS-209 situation reports by St. Denis et al. (2023). This is the **response-side** fire
layer: how each fire was fought, what it cost, and what it threatened.

- **Source** figshare v3, DOI [10.6084/m9.figshare.19858927.v3](https://doi.org/10.6084/m9.figshare.19858927.v3)
- **License** CC BY 4.0
- **Extent** United States, national · **Temporal** 1999-2020
- **STAC** [`stac-collection.json`]({PUB}/{BUCKET}/{DATASET}/{LAYER}/stac-collection.json)

## Read it before you join it

| | |
|---|---|
| Incidents (GeoParquet rows) | **{N_INCIDENTS:,}** — `INCIDENT_ID` unique on every row |
| With a usable coordinate | **{N_WITH_GEOM:,}** — hex and PMTiles hold only these |
| No reported coordinate | **{N_NULL_GEOM}** (NULL geometry) |
| Defective coordinates, published as-is | **{N_MIRRORED_COORD + N_OFFUS_OTHER}** |
| FPA-FOD pre-2021 join ids matched | **{FOD_MATCHED:,} of {FOD_JOIN_IDS:,} ({100.0*FOD_MATCHED/FOD_JOIN_IDS:.1f}%)** |

**Always LEFT join to FPA-FOD.** Coverage stops at 2020 while FPA-FOD's join id runs to 2024, and
{FOD_JOIN_IDS - FOD_MATCHED:,} pre-2021 FPA-FOD join ids match no record here at all — FPA-FOD's 7th
edition was linked against an ICS-209-PLUS vintage never published on the figshare record. An inner
join silently drops both groups.

**{N_MIRRORED_COORD} incidents (1999-2002) have `POO_LONGITUDE = -POO_LATITUDE`** — an upstream field
error placing them in the Atlantic — and 4 more (2015) are otherwise off-US. Values are mirrored
faithfully; filter them out yourself for any distance work.

## DuckDB

```sql
INSTALL spatial; LOAD spatial;

-- Suppression strategy and cost by cause, wildfires only, geographically valid records only.
SELECT CAUSE, SUPPRESSION_METHOD,
       COUNT(*)                        AS incidents,
       ROUND(SUM(FINAL_ACRES))         AS acres,
       ROUND(AVG(PROJECTED_FINAL_IM_COST)) AS avg_cost_usd,
       ROUND(MAX(WF_MAX_FSR), 1)       AS max_spread_rate
FROM read_parquet('{flat}')
WHERE INCTYP_ABBREVIATION = 'WF'
  AND START_YEAR >= 2007                      -- SUPPRESSION_METHOD starts in 2007
  AND POO_LONGITUDE <> -POO_LATITUDE          -- drop the mirrored-coordinate records
  AND POO_LONGITUDE BETWEEN -180 AND -64
  AND POO_LATITUDE  BETWEEN   17 AND  72
GROUP BY 1, 2
ORDER BY acres DESC;
```

```sql
-- Join the response side to FPA-FOD ignitions. LEFT, always.
SELECT f.FIRE_YEAR, f.NWCG_GENERAL_CAUSE,
       COUNT(*)                                        AS ignitions,
       COUNT(i.INCIDENT_ID)                            AS with_ics209_record,
       ROUND(AVG(i.WF_PEAK_PERSONNEL))                 AS avg_peak_personnel
FROM read_parquet('{PUB}/{BUCKET}/fpa-fod-1992-2024.parquet') f
LEFT JOIN read_parquet('{flat}') i
       ON f.ICS_209_PLUS_INCIDENT_JOIN_ID = i.INCIDENT_ID
WHERE f.ICS_209_PLUS_INCIDENT_JOIN_ID IS NOT NULL
GROUP BY 1, 2 ORDER BY 1, ignitions DESC;
```

```sql
-- Situation reports: dedup to incident level before aggregating incident attributes.
SELECT COUNT(*) AS sitreps, COUNT(DISTINCT INCIDENT_ID) AS incidents
FROM read_parquet('{PUB}/{BUCKET}/{DATASET}-sitreps.parquet');
```

## MapLibre GL JS

The **`source-layer` is `{LAYER}`** — not the file name, not the dataset id. A wrong `source-layer`
renders a blank map with no error.

```js
map.addSource('ics209', {{
  type: 'vector',
  url: 'pmtiles://{PUB}/{BUCKET}/{DATASET}/{LAYER}.pmtiles'
}});

map.addLayer({{
  id: 'ics209-incidents',
  type: 'circle',
  source: 'ics209',
  'source-layer': '{LAYER}',          // <-- required
  filter: ['==', ['get', 'INCTYP_ABBREVIATION'], 'WF'],
  paint: {{
    'circle-radius': ['interpolate', ['linear'], ['get', 'FINAL_ACRES'], 0, 2, 100000, 14],
    'circle-color': ['match', ['get', 'CAUSE'],
      'L', '#3b82f6',   // lightning / natural
      'H', '#ef4444',   // human
      'O', '#f59e0b',   // other
                '#9ca3af'],  // unknown / null
    'circle-opacity': 0.7
  }}
}});
```

## H3

Native resolution **{H3_NATIVE}**, parents **{', '.join('h%d' % r for r in H3_PARENTS)}** — matching
FPA-FOD so both ignition layers meet at `h8`. Each point resolves to exactly one res-{H3_NATIVE}
cell, so `COUNT(DISTINCT _cng_fid)` = `COUNT(*)` and no dedup is needed. Points sharing a cell are
not deduplicated.

```sql
-- Incidents per h8 cell, joinable to any other h8 layer in the catalog.
SELECT h8, COUNT(*) AS incidents, ROUND(SUM(FINAL_ACRES)) AS acres
FROM read_parquet('{PUB}/{BUCKET}/{DATASET}/{LAYER}/hex/h0=*/data_0.parquet')
GROUP BY h8 ORDER BY acres DESC LIMIT 20;
```

## Companion tables

All non-spatial, all joining on `INCIDENT_ID`:

| File | Rows | Note |
|---|---|---|
| `{DATASET}-sitreps.parquet` | {N_SITREPS:,} | one row per situation report, 5.28 per incident — **dedup first** |
| `{DATASET}-complex-assoc.parquet` | 4,764 | complex umbrella record to member fires |
| `{DATASET}-by-tract.parquet` | 45,245 | incident x census tract |
| `{DATASET}-by-county.parquet` | 40,688 | incident x county |
| `{DATASET}-by-cbg.parquet` | 48,370 | incident x census block group |
| `{DATASET}-lookup-codes.parquet` | 368 | official SIT-209 code definitions |

## Citation

St. Denis, L.A., Short, K.C., McConnell, K., Cook, M.C., Mietkiewicz, N.P., Buckland, M., and
Balch, J.K. (2023). *All-hazards dataset mined from the US National Incident Management System
1999-2020.* figshare. https://doi.org/10.6084/m9.figshare.19858927.v3

Companion paper: *Scientific Data* **10**, 112 (2023). https://doi.org/10.1038/s41597-023-02276-y
"""


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
