# `roadless-land-status` — build notes and measured evidence

NFS roadless land-status stratification (Manley 2026), Zenodo record 23265719
(doi:10.5281/zenodo.23265719, published 2026-10-09, no version label). It replaces version 1.0
(Zenodo 23105982), which this prefix held from 2026-10-02 to 2026-10-15.
Issue: boettiger-lab/data-workflows#743. Bucket `public-usfs` (existing, #584).

## Source

`https://zenodo.org/records/23265719/files/roadless_land_status_shapefile.zip`, staged
2026-10-14 to `s3://public-usfs/raw/roadless_land_status_shapefile_23265719.zip`: 390,739,112
bytes, md5 `a289574b63722aef99ea0c2bf6e57fa7` (matches Zenodo), sha256
`93886dea5c329db494acc29b070c0e3982516c0e0d49affb6a385f5635a2e322`. FGDC sidecar staged as
`raw/roadless_land_status_metadata_23265719.xml` (27,673 bytes, pubdate 2026-10-08). Licence
CC-BY-4.0 (Zenodo record). Source CRS EPSG:6933 (EASE-Grid 2.0), reprojected to EPSG:4326 by
convert.

The version 1.0 source stays at `raw/roadless_land_status_shapefile.zip` (196,065,585 bytes, md5
`6a3ef3ac5e8a4bdf9e16dde5bc6d956a`) and `raw/roadless_land_status_metadata.xml`.

## Pipeline

| Setting | Value | Why |
|---|---|---|
| H3 | native `10`, parents `9,8,0` | matches `roadless-areas-2001` so strata join cell-for-cell |
| hex `--chunk-size` | `1` | one feature per pod; 702 completions × 50 parallelism |
| `--hex-memory` | 8Gi | all hex pods peaked under 2.5 GiB |
| convert memory | **32Gi, hand-edited** | 8Gi OOMKilled twice (peak ~9.2 GiB); no generator flag, boettiger-lab/datasets#275 |
| `--expect-features` | 702 | FGDC entity count |
| priority | default | opportunistic preempted multi-minute hex pods in #585 |

```bash
kubectl apply -n geo-workflows -f roadless-land-status-stage-raw.yaml
kubectl apply -n geo-workflows -f workflow-rbac.yaml -f configmap.yaml -f workflow.yaml
```

Hex took 5 h, all of it one feature: `_cng_fid` 77 (AK, Unassigned NFS, N) is 33 ac in
1,555,731 parts / 9.7M vertices. Every other pod finished in minutes.

## Measured (2026-10-15, duckdb-geo MCP)

Flat parquet: 702 rows, 702 distinct `_cng_fid` and `SRC_ID`, `PART_ID` 0 on every row, 0
invalid, 0 empty. bbox `(-150.0079, 18.0337, -65.7066, 61.5190)` matches FGDC. 46
states/territories (CT and NJ are slivers only), 112 `FOR_NAME` (111 forests plus
`Unassigned NFS`), regions `01..06,08,09,10` plus `NA`. `IRA_CAT` NULL on every row.

| STRATUM | rows | acres | v1.0 acres | H3 footprint vs ACRES | on FS-owned |
|---|---:|---:|---:|---:|---:|
| N | 248 | 135,478,432 | 173,795,718 | +0.42% | 99.5% |
| R1 | 141 | 5,849,268 | 5,865,752 | +2.69% | 99.8% |
| R1s | 25 | 13,134,206 | 13,117,915 | -0.08% | 100.0% |
| R2 | 130 | 14,891,263 | 14,987,479 | +0.74% | 99.4% |
| R3 | 158 | 23,848,420 | 23,972,530 | -0.00% | 99.8% |
| total | 702 | 193,201,589 | 231,739,395 | | 99.6% |

Roadless (R1+R1s+R2+R3) = 57,723,157 ac; unexposed (R1+R1s+R2) = 33,874,737 ac; exposed R3 =
23,848,420 ac. "On FS-owned" is the h10 join against `nfs-surface-ownership`
(`OWNERCLASS = 'USDA FOREST SERVICE'`), area-weighted. In v1.0, N was 77.7% FS-owned (~38.8M ac
of inholdings); this version drops them, which the FGDC text does not mention.

`Unassigned NFS` (`REGION = 'NA'`): 113 rows, 57,988 ac. One 55,515 ac N piece in Utah; the
rest are slivers under 65 ac, some with very many parts (fid 77 above; fid 71 AK R2 8 ac in
322,521 parts; fid 72 AK R3 64 ac in 125,190 parts).

## Build results

Artifacts: `roadless-land-status.parquet` (447.9 MB, 2026-10-14 20:12 UTC), `.pmtiles`
(123.7 MB, 20:17 UTC), 9 `hex/h0=*` partitions (2026-10-15 01:20 UTC), 52,916,466 hex rows.

| Check | Result |
|---|---|
| Feature count / `COUNT(DISTINCT _cng_fid)` flat | 702 / 702 |
| `COUNT(DISTINCT _cng_fid)` hex | 702, nothing dropped |
| Hex/flat deduped `SUM(ACRES)` per stratum | exact |
| NULL `h10` / `h8` | 0 / 0 |
| h10 cells carrying two or more strata | 123,243; noted on hex asset |
| `verify-stac.py --bucket public-usfs --dataset roadless-land-status` | PASS |
| `lint-stac-pmtiles-fields.py`, `lint-stac-categorical.py` | PASS |

## Published

- `s3://public-usfs/roadless-land-status/stac-collection.json`, via `gen_stac.py` +
  `roadless-land-status-publish-stac.yaml`
- `s3://public-usfs/stac-collection.json`: child link (unchanged by this rebuild)
- `s3://public-usfs/README.md`: table row + section, replaced in place by `gen_stac.py`
