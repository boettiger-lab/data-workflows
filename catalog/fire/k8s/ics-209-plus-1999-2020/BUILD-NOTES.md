# ICS-209-PLUS wildfire 1999-2020 — build notes

Issue [#636](https://github.com/boettiger-lab/data-workflows/issues/636). Source: St. Denis, L.A.
et al. 2023, *All-hazards dataset mined from the US National Incident Management System, 1999-2020*
(ICS-209-PLUS), figshare **v3**, CC BY 4.0,
DOI [10.6084/m9.figshare.19858927.v3](https://doi.org/10.6084/m9.figshare.19858927.v3).

These are the decisions a regeneration would silently revert. Read before re-running
`cng-datasets workflow` against this directory.

## Job order

```
ics-209-plus-stage-raw.yaml     # download + md5-verify + schema probe -> raw/
ics-209-plus-preprocess.yaml    # CSV -> typed parquet (+ point geom) and the 6 sidecars
configmap.yaml + workflow.yaml  # setup-bucket -> convert -> pmtiles + hex -> repartition
ics-209-plus-fod-linkage-probe.yaml   # diagnostic only; writes nothing
```

## Why a preprocess step exists at all

`cng-convert-to-parquet` has a CSV point path (`--lat-column`/`--lon-column`), so pointing it
straight at `ics209-plus-wf_incidents_1999to2020.csv` looks like the obvious one-step build. It
mistypes four columns.

That path calls `read_csv_auto` with DuckDB's **default 20480-row sample**. The file is ordered by
year, and `INC_IDENTIFIER`, `FATALITIES_PUBLIC`, `FATALITIES_RESPONDER` and `PEAK_EVACUATIONS` are
2013+ only — so all four are **entirely NULL in that head sample** and DuckDB falls back to
`VARCHAR`, while a full scan types them `DOUBLE`. The columns are cleanly numeric throughout: 0
non-castable values in 34,622 rows. Publishing fatality and evacuation counts as strings would make
`SUM()` a cast-first operation and misdescribe them in STAC.

So `ics-209-plus-preprocess.yaml` reads with `sample_size=-1`, attaches a WKB point `geom` built
from `POO_LONGITUDE`/`POO_LATITUDE`, and hands the convert step an already-typed parquet — which it
ingests through its documented BLOB-geometry branch (`ST_GeomFromWKB`, `_GEOM_COLUMN_NAMES`
includes `geom`) and where it synthesizes `_cng_fid`. **The published GeoParquet is still the
tool's output**, not the intermediate.

Filed upstream as boettiger-lab/datasets#188 (expose the CSV sample size, or default to
`sample_size=-1`). Drop this step once that lands. `--lat-column`/`--lon-column` are also absent
from the `workflow` subcommand, which is the other reason the CSV cannot be the `--source-url`.

## Hex fan-out: completions is hand-set to 35

The generator **could not count features** (`ogrinfo` is not on the local venv PATH) and fell back
to its conservative default: `chunk_size=1000, completions=200`, covering 200,000 features. Coverage
was never at risk here — 200,000 >= 34,622 — but it scheduled 200 pods for 35 chunks of work, so 165
were no-ops on a shared namespace.

Hand-set to **`completions: 35`, `parallelism: 35`** against the measured count:

```
features = 34,622   chunk_size = 1,000   completions = ceil(34622/1000) = 35   -> 35,000 covered
```

If the source is ever re-staged, **re-derive this from the real count**. The failure mode runs the
other way (#494): a completions x chunk_size product *below* the feature count leaves features
unhexed while repartition and STAC still look complete.

## Both copies of every manifest are hardened

`configmap.yaml` embeds its own copy of each job, and **the orchestrator applies the configmap
copy** — the standalone `*-hex.yaml` etc. are for step-by-step runs. Every change below was made in
**both** places; patching only the standalone file means the hardening does not apply to the actual
run (the #587 lesson).

- `backoffLimit: 0` -> **`backoffLimitPerIndex: 2` + `maxFailedIndexes: 3`** on hex. With
  `backoffLimit: 0` a preempted index leaves a partial h0 set on S3 while the Job reports nothing
  actionable, and a partial hex can publish as if complete (#409).
- `ttlSecondsAfterFinished: 10800` -> **86400**, so a finished job is still interrogable the next day.
- **GPU-node exclusion dropped.** GPU hosts have spare CPU/RAM for these jobs; a wider schedulable
  pool finishes the fan-out faster and reduces pile-up on a flaky node (AGENTS.md).

`--hex-memory 8Gi` is the default and is right here: hexing points is the cheapest case (each point
polyfills to exactly one res-10 cell), and the largest input the flag also sizes — convert — reads a
~30 MB parquet.

## H3: native 10, parents 9,8,0

Per the issue, matching FPA-FOD (#587) so the two ignition layers meet at the catalog's universal
`h8` join key. Points are not deduplicated within a cell.

## Data facts that the STAC must carry

Measured, not assumed:

| | |
|---|---|
| incidents | **34,622** rows, `INCIDENT_ID` distinct on every row |
| with coordinates | **34,200** — so hex `COUNT(DISTINCT _cng_fid)` is 34,200, **not** 34,622 |
| null coordinates | **422** (NULL geom, hex to nothing) |
| `POO_LONGITUDE = -POO_LATITUDE` | **439**, all 1999-2002, all placed in the Atlantic |
| other off-US coordinates | **4**, all 2015 (incl. a Mississippi fire at 88.92 N) |
| bbox over plausible records | `[-171.400, 17.9656, -65.3253, 70.1381]`, no antimeridian crossing |
| FOD join | **33,247 of 35,208** (94.4%) distinct pre-2021 FOD join ids match |

The 443 defective coordinates are **published exactly as upstream supplies them**. The true
longitudes are not recoverable from the record, so repairing them by inference would be fabrication;
they are quantified in the STAC with a filter recipe instead.

The FOD shortfall is not ours to fix: normalization recovers none of the 1,961, none appear in the
wildfire sitreps, and the all-hazards bundle accounts for only 2 — leaving 1,960 that match no
ICS-209-PLUS v3 record in either bundle. figshare lists versions 1-3 only, so v3 is current, and
FPA-FOD 7th edition (2026) evidently linked against an ICS-209-PLUS vintage that was never published
on this record. Any FOD join must be a **left** join.

## Sidecar tables

Six non-spatial parquets at the bucket root as `<dataset>-<name>.parquet`, matching
`fpa-fod-1992-2024-nwcg-units.parquet`. `INCIDENT_ID` is the join key back to the incidents layer.

| Asset | Rows | Note |
|---|---|---|
| `-sitreps` | 182,826 | 5.28 rows per incident — dedup before aggregating incident attributes |
| `-complex-assoc` | 4,764 | complex/member fire associations |
| `-by-tract` | 45,245 | carries `SPATIAL_DATA_ORIGIN` |
| `-by-county` | 40,688 | " |
| `-by-cbg` | 48,370 | " |
| `-lookup-codes` | 368 | reference bundle's official code definitions |

**No `_cng_fid` is synthesized on the sidecars, deliberately.** An independently numbered row id
would not correspond to the incidents layer's `_cng_fid` and would invite a wrong join.

All three main tables lead with an **unnamed pandas index column** (DuckDB names it `column00` /
`column000` by width). It is **dropped** from the incidents table — `INCIDENT_ID` is unique there and
convert adds `_cng_fid` — but **kept as `SOURCE_ROW`** on sitreps and complex-assoc, because neither
has a unique natural key:

- sitreps: 182,826 rows vs 181,144 distinct `(INCIDENT_ID, REPORT_FROM_DATE, REPORT_TO_DATE)`, and
  `INC209R_IDENTIFIER` is non-null on only 68,139 (2014+);
- complex-assoc: 4,764 rows vs 4,754 distinct `(CPLX_INCIDENT_ID, MEMBER_INCIDENT_ID, FIRE_NAME)`.

Dropping it would leave those tables with no row-addressable key at all. It is **not** named
`_cng_fid`: it is upstream's row order, not a cng-datasets synthetic id, and must not be joined
across tables. The preprocess job asserts no `column*` name survives in any published table.

## Not published

- The three `ics209_sitreps_deleted_*` CSVs (4,726 rows) — records withdrawn upstream. Staged in
  `raw/` only.
- The four `*_field-definitions.csv` files — they feed the STAC column descriptions
  (`gen_stac.py`), and are staged in `raw/`.
- The `ics209plus-source.zip` (427 MB) and `ics209plus-allhazards.zip` bundles — out of scope per
  the issue. All-hazards was downloaded once by the linkage probe and not retained.

## Coded domains

Enumerated **from the ingested data** (#294), with definitions from the reference bundle's
`sit209_lookup_codes_definitions.csv`:

- `CAUSE`: `H`=Human, `L`=Lightning/Natural, `O`=Other, `U`=Unknown (206 null)
- `INCTYP_ABBREVIATION`: `WF`, `WFU`, `RX`, `CX`
- `SUPPRESSION_METHOD`: `FS`=Full Suppression, `C`=Confine, `M`=Monitor, `PZP`=Point Zone
  Protection — plus **`MMS` (878 rows), which is absent from the reference bundle's
  `FIRE_SUPPRESSION_STRATEGY` domain** and is flagged as undefined upstream rather than guessed.

`SPATIAL_DATA_ORIGIN` is **not** a column on the incidents table (the issue listed it as one); it
lives on the three `by-*` aggregation tables.

Partial-coverage first years, measured rather than assumed: `SUPPRESSION_METHOD` 2007+,
`LL_CONFIDENCE` 1999+, `PEAK_EVACUATIONS` 2013+, `FATALITIES_PUBLIC`/`FATALITIES_RESPONDER` 2013+,
`POO_CITY` 2014+. Pre-coverage nulls mean "not collected", not "zero".

## PMTiles: `-lco AUTODETECT_JSON_STRINGS=NO` is load-bearing

The generated pmtiles step failed three times identically, and the failure mode is silent-shaped:
tippecanoe reported `Did not read any valid geometries`, wrote **0 features**, and the orchestrator
still reported `Complete`.

Cause: `SUP_SERIES` is a VARCHAR holding a pandas-stringified list — `"[nan, nan, 0.0]"`. Since GDAL
3.7 the GeoJSON writers auto-detect a JSON-looking *string* and re-emit it as a real JSON array,
parsing it leniently enough to accept `nan` and then normalising it to a bare `NaN` token. Bare `NaN`
is not legal JSON, so tippecanoe rejects the very first line and stops. 13,058 of the 34,622 records
carry it.

The counterintuitive part, measured three ways in one pod against the same input:

| ogr2ogr option | GDAL says | `SUP_SERIES` rendered as | bare `NaN` tokens |
|---|---|---|---|
| `-lco AUTODETECT_JSON_STRINGS=NO` | `Warning 6: ... does not support layer creation option` | `"[nan, nan, ...]"` (quoted string) | **0** |
| `-dsco AUTODETECT_JSON_STRINGS=NO` | accepted silently | `[NaN,NaN,...]` (array) | 13,083 |
| omitted | — | `[NaN,NaN,...]` (array) | 13,083 |

**`-lco` is the form that works, and GDAL's "does not support" warning about it is wrong.** `-dsco` —
the option level you would reach for, and the one GDAL accepts without complaint — has no effect.
Do not "fix" the warning by switching to `-dsco`.

A grep gate follows the conversion so this can never again publish empty tiles quietly: any bare
`NaN`/`Infinity` in the GeoJSONSeq output fails the job. Note the gate must not require a preceding
`:` — the tokens appear inside an array (`:[NaN,NaN`), which is why an initial `grep ':NaN'` came back
clean while the file was in fact broken.

Reported upstream as part of the pmtiles-step discussion; the GeoParquet and hex are unaffected
(`SUP_SERIES` is correctly a string there).

## What the STAC gate caught that hand-checking would not

`scripts/verify-stac.py` went 33 HARD → 0. Three classes, all real:

1. **`column-description-divergent` (28 findings).** The incident and sitrep field-definition files
   give *different* prose for the ~30 columns they share. mcp-data-server's #303 renderer dedups
   per-column descriptions across assets by keeping the first it sees and dropping the rest, so
   divergent text silently loses information. Fixed by folding all four definition files into ONE
   global column→prose map (incident table wins, it is the canonical layer) that every asset renders
   from; asset-specific notes live in the asset `description`.
2. **`categorical` (9 findings)** on `SUP_METHOD_INITIAL`, `SUP_METHOD_FINAL`, `GEN_FIRE_BEHAVIOR` —
   coded columns with no `values` array. Enumerated from the data and added to `_codes.json`, along
   with `FUEL_MODEL` (which the data stores as descriptive labels, *not* the 1-13 codes the reference
   bundle documents).
3. **`area-recipe-inlined`.** The hex description inlined `SUM(h3_cell_area(...))`; per #389 even the
   correct formula must not be baked into STAC, because it drifts from the h3-guide. Removed.

The data-backed `values` check earned its keep on **`SPATIAL_DATA_ORIGIN`**: the upstream
field-definitions file documents the domain as `MTBS, FIRED or MTBS_AND_FIRED`, but the data holds
**`POO`** (the single most common value, absent from the upstream doc), `FIRED`, `MTBS` and
mixed-case **`MTBS_and_FIRED`**. Transcribing the upstream documentation would have shipped a wrong
domain and failed the gate — this is the #114/#294 class exactly.

`hex-missing-features` also fired on the 422-record shortfall. That shortfall is legitimate (no
coordinate → NULL geometry → zero cells), so the fix was to state it in the hex asset description in
terms the gate recognises, not to re-hex.

## Backup / mirror

Nothing to register. The backup/mirror tier was retired from this repo in #550/#568
(`catalog/sync/` no longer exists here), and `public-fire` is a long-standing bucket in any case.
CC BY 4.0 is source.coop-eligible.

## Verified acceptance (all criteria, post-build)

```
flat rows                34,622   distinct INCIDENT_ID  34,622
flat COUNT(geom)         34,200
hex COUNT(DISTINCT fid)  34,200 = hex COUNT(*) 34,200   (one point -> exactly one cell)
h0 partitions                16   NULL h10: 0   NULL h8: 0
FPA-FOD pre-2021 join    33,247 / 35,208 = 94.4%
verify-stac.py --bucket public-fire --dataset ics-209-plus-1999-2020/wf-incidents  -> exit 0
```
