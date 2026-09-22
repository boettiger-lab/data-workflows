# BLM Utah Federal Mineral Estate — build notes

Issue: https://github.com/boettiger-lab/data-workflows/issues/706
Bucket: `s3://public-blm/`, dataset `utah-federal-mineral-estate`
Snapshot accessed: 2026-09-22

Evidence measured during the build, so the next reader inherits measurements rather than
assumptions. Every number below was queried, not carried over from upstream documentation.

## Why layer 11 and not the ten commodity views

The service exposes 11 layers, but they are definition-query views over one feature class: every
layer returns the same 39 fields, and layer 11 is the unfiltered table. Per-commodity view counts
total 106,444 against 101,585 rows, because **3,247 parcels carry more than one commodity flag**
and 158 carry none. Ingesting the views separately would duplicate geometry and lose the overlap.

## Flag semantics, and why they are not guessed

The service *field* metadata defines no domain, but the layer's FGDC metadata document does —
`GET .../FeatureServer/11/metadata` — identically on all ten flags:

```
Enumerated Domain Value: X   -> Federal Minerals
Enumerated Domain Value: I   -> Indian Minerals
```

A commodity view selects `flag IN ('X','I')`; empty string is excluded. Staging normalises `''`
to null and strips whitespace (the columns are `char(2)`), so `flag IS NOT NULL` is exactly
upstream view membership. The stage-raw job asserts this per flag and fails the snapshot if any
count drifts.

| flag | view | `X` | `I` | `''` upstream |
|---|---|---|---|---|
| `ALL_MIN` | 91,342 | 86,271 | 5,071 | 6 |
| `Oil_Gas` | 5,838 | 4,131 | 1,707 | 1 |
| `Coal` | 4,041 | 3,982 | 59 | 0 |
| `Oil_Shale` | 2,282 | 692 | 1,590 | 0 |
| `Gilsonite` | 174 | 174 | 0 | 0 |
| `Potash_Pot` | 781 | 781 | 0 | 0 |
| `Sodium` | 707 | 707 | 0 | 0 |
| `Phosphate` | 652 | 632 | 20 | 0 |
| `Geo_Steam` | 313 | 313 | 0 | 0 |
| `Unknown_` | 314 | 314 | 0 | 16 |

## Fields dropped, and why

Verified against all 101,585 rows:

| field | reason |
|---|---|
| `CreatedByRecord`, `RetiredByRecord` | 0 rows populated; metadata defines both as "Not being used" |
| `VALIDATIONSTATUS` | constant `2` on every row, carries no information |
| `CREATE_DATE`, `MODIFY_DATE`, `CREATE_BY`, `MODIFY_BY` | metadata defines the dates as "Unknown"; stored values are a 1900 sentinel (`-2209158986000`) |
| `created_date`, `last_edited_date`, `created_user`, `last_edited_user` | one bulk-migration timestamp across the table; record management, not an edition date |

`GlobalID` is kept over `OBJECTID` as the stable identifier (unique across all 101,585 rows).

## Measured column ranges and sentinels

| column | measurement |
|---|---|
| `GIS_Acres` | min 0.00005, max 4,882.17, sum 38,938,685; null on 59 rows |
| `Section_` | 1–36 on 100,908 rows; **97 (118), 98 (83), 99 (50), 0 (3)** are out-of-grid placeholders; null on 423 |
| `County` | 32 distinct: all 29 Utah counties, plus `Tribal`, the case variant `Box Elder`, and one leaked survey id `UT260040S0040W0SN190` (1 row); null on 386 |
| `Admin` | 16 distinct; `Federal` (88,954) and `FEDERAL` (20) are the same value spelled two ways; null on 424 |
| `Serial_NR` / `Patent_NR` / `GCDBDIVID` | null on 646 / 448 / 420 rows |
| geometry | 99,801 POLYGON, 1,783 MULTIPOLYGON, **1 null**, 0 empty, 0 invalid |

Split estate: **12,183** parcels carry a commodity flag under surface administered by someone
other than the federal government or the BLM (`Admin NOT IN ('Federal','FEDERAL','BLM')`).

## Hex

Native resolution 9, parents 8 and 0. Parcels are PLSS aliquot parts, commonly ~40 acres
(0.16 km²), between res 8 (0.74 km²) and res 9 (0.105 km²). Largest parcel is 4,882 acres
(19.8 km², ~190 res-9 cells), so the hex is light: 102 completions × 1,000 features finished in
103 s with **zero pod failures**.

Result: 1,375,094 rows, 101,584 features, 1,372,026 distinct h9, 220,654 distinct h8, 2 h0
partitions, no nulls in h9/h8/h0. The one parcel with no source geometry cannot be polyfilled and
is absent from the hex — documented in the hex asset description, which is what clears the
`hex-missing-features` gate.

## A generation footgun worth remembering

`--max-completions` is a **coverage budget**, not just a pod cap (skill `hex-tuning`,
data-workflows #494). With no row count available — the source is a remote GeoJSON that `ogrinfo`
could not count — the generator assumes `total_rows = max_completions × 1000`. A first pass with
`--max-completions 50` produced a hex job covering only 50,000 of 101,585 features. The CLI does
print `Warning: feature count unknown — defaults cover at most N features`, so read that line.
Use `--max-completions >= ceil(n_features / 1000)`; 102 here.

## Provenance

Raw staged at `s3://public-blm/raw/utah-federal-mineral-estate.geojson`, 117,231,722 bytes,
sha256 `1636cf7c7bec6d9d796193cea6614e6cfedcfe377f1a8f00ec2191f795f7ec5a` (recomputed from the
object by the `raw-fingerprint` job, not transcribed).

Licence evidence is direct rather than inferred — the layer metadata states:
`Access Constraints: None, these data are considered public domain.`

The service is live and unversioned. `pubDate 20260309` and `idVersion 6.11(3.0.1)` in the
metadata are a metadata-record date and the ArcGIS metadata-standard version, **not** data
editions. The access date is the only edition marker; the publisher states content currency as
2026-03-01, which is the temporal-extent start.

## Run order

```bash
kubectl apply -n geo-workflows -f utah-federal-mineral-estate-stage-raw.yaml   # standalone, first
kubectl apply -n geo-workflows -f workflow-rbac.yaml                           # once
kubectl apply -n geo-workflows -f configmap.yaml -f workflow.yaml              # setup-bucket -> convert -> pmtiles+hex -> repartition
```

Total build time: stage-raw 2m24s, convert 4m7s, pmtiles 51s, hex 103s, repartition 22s.
