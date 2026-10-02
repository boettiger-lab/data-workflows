# `roadless-land-status` — build notes and measured evidence

NFS roadless land-status stratification (Manley 2026, v1.0, doi:10.5281/zenodo.23105982).
Issue: boettiger-lab/data-workflows#743. Bucket `public-usfs` (existing, #584).

## Source

`https://zenodo.org/records/23105982/files/roadless_land_status_shapefile.zip`, staged
2026-10-02 to `s3://public-usfs/raw/roadless_land_status_shapefile.zip`: 196,065,585 bytes,
md5 `6a3ef3ac5e8a4bdf9e16dde5bc6d956a` (matches Zenodo), sha256
`f8161cd8a4d0a0c996496eb1565eaf32d894392693a3ba11658730537cc5e44d`. FGDC sidecar staged as
`raw/roadless_land_status_metadata.xml` (27,675 bytes). Licence CC-BY-4.0 (Zenodo record).
Source CRS EPSG:6933 (EASE-Grid 2.0), reprojected to EPSG:4326 by convert.

## Pipeline

| Setting | Value | Why |
|---|---|---|
| H3 | native `10`, parents `9,8,0` | matches `roadless-areas-2001` so strata join cell-for-cell |
| hex `--chunk-size` | **patched 1000 → 1** in `-hex.yaml` and `configmap.yaml` | generator hardcodes 1000; 709 features would otherwise all hex in one pod (same patch as #585) |
| completions × parallelism | 709 × 50 | one feature per pod; geo-workflows has no 200-completion quota |
| `--hex-memory` | 8Gi | #585 measured <1 GiB peak on Tongass (17.7M ac); largest feature here is 8.39M ac |
| `--expect-features` | 709 | FGDC entity count |
| priority | default | opportunistic preempted multi-minute hex pods in #585 |

```bash
kubectl apply -n geo-workflows -f roadless-land-status-stage-raw.yaml
kubectl apply -n geo-workflows -f workflow-rbac.yaml -f configmap.yaml -f workflow.yaml
```

## Measured from the ingested flat parquet (2026-10-02, duckdb-geo MCP)

709 rows, 709 distinct `_cng_fid`, 591 distinct `SRC_ID` (119 rows are `PART_ID > 0` split
parts). 0 invalid, 0 empty. bbox `(-150.0079, 18.2312, -65.6997, 61.5190)` matches FGDC.
44 states/territories, 111 forests, regions `01..06,08,09,10` (string, zero-padded).

| STRATUM | rows | SRC_ID | acres |
|---|---:|---:|---:|
| N | 322 | 204 | 173,795,718 |
| R1 | 121 | 121 | 5,865,752 |
| R1s | 23 | 23 | 13,117,915 |
| R2 | 110 | 110 | 14,987,479 |
| R3 | 133 | 133 | 23,972,530 |
| total | 709 | 591 | 231,739,395 |

Roadless (R1+R1s+R2+R3) = 57,943,676 ac; unexposed (R1+R1s+R2) = 33,971,146 ac; exposed R3 =
23,972,530 ac.

### Findings

- **`IRA_CAT` is NULL on all 709 rows in the source shapefile** (field present, never set), read
  from the staged zip's DBF with OGR, so not a conversion fault. Per #743 the column is unused:
  R2/R3 were derived from the 2001 IRA `CATEGORY` but the values were not carried over. Kept as
  published and documented as unpopulated; dropping it would mean rewriting flat, hex and PMTiles.
- **One feature is split across 119 rows:** `SRC_ID` 204, the N stratum of Los Padres NF (CA),
  1,328,191 ac, `PART_ID` 1..119. All other `SRC_ID`s are single rows (591 distinct).
- **Mixed geometry types after convert** (12 `GEOMETRYCOLLECTION`, 1 near-zero `LINESTRING`):
  harmless, all 709 `_cng_fid` are present in the hex.
- **N is wider than Forest Service-owned land.** Joined at h10 against
  `nfs-surface-ownership` (`OWNERCLASS = 'USDA FOREST SERVICE'`), area-weighted:

  | STRATUM | footprint ac | on FS-owned ac | % |
  |---|---:|---:|---:|
  | N | 173,736,326 | 134,943,973 | 77.7 |
  | R1 | 6,007,577 | 5,988,556 | 99.7 |
  | R1s | 13,101,747 | 13,087,927 | 99.9 |
  | R2 | 14,994,369 | 14,882,195 | 99.3 |
  | R3 | 23,931,653 | 23,804,063 | 99.5 |
  | all | 231,771,671 | 192,706,714 | 83.1 |

  FS-owned total (192.7M) matches `nfs-surface-ownership` (193.2M), so the strata cover all NFS
  land but N also includes ~38.8M ac of inholdings. Documented in STAC with the ownership
  denominator SQL.

## Build results (2026-10-02)

Artifacts: `roadless-land-status.parquet` (224.0 MB, 17:49 UTC), `.pmtiles` (104.9 MB, 17:53 UTC),
9 `hex/h0=*` partitions (18:45 UTC), 62,873,382 hex rows.

| Check | Result |
|---|---|
| Feature count / `COUNT(DISTINCT _cng_fid)` flat | 709 / 709 |
| `COUNT(DISTINCT _cng_fid)` hex | 709, nothing dropped |
| Hex/flat deduped `SUM(ACRES)` per stratum | exact |
| H3 footprint vs `ACRES` | within 0.2% per stratum, except R1 +2.42% (sliver polygons) |
| NULL `h10` / `h8` | 0 / 0 |
| Shared boundary cells (same h10, two strata) | 99,096 rows; noted on hex asset |
| `audit-feature-dup.py --key _cng_fid` | all attributes REPEATED on hex; `ACRES` raw SUM inflates 553,135x |
| `verify-stac.py --bucket public-usfs --dataset roadless-land-status` | PASS |
| `lint-stac-pmtiles-fields.py` | PASS |

## Published

- `s3://public-usfs/roadless-land-status/stac-collection.json`, via `gen_stac.py` +
  `roadless-land-status-publish-stac.yaml`
- `s3://public-usfs/stac-collection.json`: child link added; licence `public-domain` → `various`
  (this child is CC-BY-4.0), bucket-level licence link removed
- `s3://public-usfs/README.md`: table row + section
