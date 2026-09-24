# BLM Special Tar Sand Areas: build notes

Issue: https://github.com/boettiger-lab/data-workflows/issues/723
Bucket: `s3://public-blm/`, dataset `special-tar-sand-areas`
Raw retrieved: 2026-09-24

## Source

BLM publishes no live STSA layer (BLM Utah REST and the GBP hub checked 2026-09-24). The only
distribution is layer `strata_unit_area_tarsand` (FGDC originator BLM, pubdate 2007) in the 2012
Oil Shale and Tar Sands PEIS geospatial package. Its site, ostseis.anl.gov, is offline, so the job
pulls the Internet Archive capture of 2013-02-16 and refuses any bytes but:

`s3://public-blm/raw/2012_OSTS_PEIS_Geospatial_Data.zip`: 2,048,223 bytes, sha256
`be1be303e5377c373299d3ca38dfe5e9dded13a7ecfa90f2dfb5abf6fd2dfb7a` (recomputed from the staged object).

## Measured

- 37 polygon parts, 11 STSAs (`ID` 1-11), all valid, all MULTIPOLYGON after conversion.
- `area_ac` 411.4 to 273,926.8 per part; sums to 1,026,285 acres.
- Hex: 5,160 rows at h8, every part present (37 distinct `_cng_fid`), 2 h0 partitions, no null h8.

## Fields dropped

| field | reason |
|---|---|
| `exp_elev` | constant 500 on all 37 rows, undocumented in the FGDC metadata |
| `PDF_FILE` | names PEIS map PDFs not in the package |
| `Shape_Leng`, `Shape_Area` | Albers units, derived |

## Run order

```bash
kubectl apply -n geo-workflows -f special-tar-sand-areas-stage-raw.yaml
kubectl apply -n geo-workflows -f workflow-rbac.yaml -f configmap.yaml -f workflow.yaml
# STAC + README are written to /tmp, loaded into the special-tar-sand-areas-stac ConfigMap, then:
kubectl apply -n geo-workflows -f special-tar-sand-areas-publish-stac.yaml
```

Hex runs as one completion: the default 1000-feature chunk covers all 37 parts, and the largest
(P.R. Spring, ~1,100 km²) is ~1,500 h8 cells.
