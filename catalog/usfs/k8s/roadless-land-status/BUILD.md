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

### Open findings

- **`IRA_CAT` is NULL on all 709 rows in the source shapefile** (field present, never set),
  although the FGDC says R2/R3 rows carry `1B`/`1B-1`/`1C`. Upstream, not conversion: confirmed
  by reading the staged zip's DBF with OGR. Ask the author; document as empty in STAC meanwhile.
- **Geometry types are mixed after convert:** 12 `GEOMETRYCOLLECTION` rows (42,357 ac total,
  largest R1 `_cng_fid` 94 at 28,400 ac) and 1 `LINESTRING` (`_cng_fid` 273, 4e-12 ac). Check
  whether the hex dropped the GeometryCollection rows: `COUNT(DISTINCT _cng_fid)` on hex must be
  709 (or 708 excluding the degenerate line).

## Remaining

1. Hex coverage + h0 partition gate once repartition completes.
2. `audit-feature-dup.py` (dedup key `_cng_fid`; `SRC_ID` groups split parts).
3. STAC dataset collection, child link on `public-usfs/stac-collection.json`, README section.
4. `verify-stac.py --bucket public-usfs --dataset roadless-land-status` exits 0.
