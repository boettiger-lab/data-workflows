# USGS Paradox Basin Assessment Units (2011): build notes

Issue: [#722](https://github.com/boettiger-lab/data-workflows/issues/722).
Bucket `public-usgs`, dataset `paradox-basin-assessment-units`, namespace `geo-workflows`.

## Source

USGS data release [10.5066/P9PAEXLB](https://doi.org/10.5066/P9PAEXLB), ScienceBase item
`60c78b5ed34e86b9389aecf4`: ten single-polygon shapefiles (`au210301` … `au210581`), one per
assessment unit, plus FGDC metadata `au21g.xml`. Pinned in `../manifest.json` (URLs and byte sizes),
accessed 2026-09-24. EPSG:4326 at source, so no reprojection. The per-unit volumes are in the
shapefile attributes; no results table needs joining.

This release is in the ScienceBase *Legacy Data Collection*, not the NOGA community that #700
merged, which is why province 5021 is absent from `noga-assessment-units`.

## Pipeline

```bash
# 1. stage raw + merge (10 shapefiles -> one GeoPackage with source_shapefile)
kubectl -n geo-workflows create configmap paradox-preprocess \
  --from-file=paradox-preprocess.py=catalog/usgs-paradox/k8s/paradox-preprocess.py \
  --from-file=manifest.json=catalog/usgs-paradox/manifest.json \
  -o yaml --dry-run=client | kubectl apply -n geo-workflows -f -
kubectl apply -n geo-workflows -f catalog/usgs-paradox/k8s/paradox-preprocess.yaml

# 2. convert / pmtiles / hex / repartition
kubectl apply -n geo-workflows -f catalog/usgs-paradox/k8s/paradox-basin-assessment-units/configmap.yaml \
                               -f catalog/usgs-paradox/k8s/paradox-basin-assessment-units/workflow.yaml

# 3. STAC + README (see the header of paradox-publish-stac.yaml)
python3 catalog/usgs-paradox/make-stac.py --report build-report.json --stats stats.json --out-dir /tmp
```

- The merge passes `-lco GEOMETRY_NAME=geom`. Without it, `ogr2ogr -sql` names the GeoPackage
  geometry column `_ogr_geometry_`, and `cng-convert-to-parquet` fails with
  `Column "geom" in EXCLUDE list not found`.
- `cng-datasets` floors the hex chunk size at 1000 features, so all 10 units fall in chunk 0. The
  hex job and its block in `configmap.yaml` are edited to `completions: 1`, `parallelism: 1`.
  Regenerating with `cng-datasets workflow` resets this.

## Measured, from the published parquet

| | |
|---|---|
| Rows / distinct `ASSESSCODE` / distinct `_cng_fid` | 10 / 10 / 10 |
| Invalid geometries | 0 |
| `SUM(OILMEAN)` | 560.11 MMBO (fact sheet: 560) |
| `SUM(ADGASMEAN + NAGASMEAN)` | 12,698.9 BCFG (fact sheet: 12,701) |
| `SUM(NGLMEAN + NAGLMEAN)` | 490.6 MMBNGL (fact sheet: 490) |
| Hex rows / distinct `h8` / max rows per cell | 423,675 / 179,108 / 6 |
| Null values in any volume column | none |

## Traps

- **0, never null.** The source stores 0 for quantities that do not apply to the unit's type (oil
  on a continuous gas unit, `OILLG_*`/`GASLG_*` on continuous units) and for every volume of
  Manning Canyon (`ASSESSPROB = 'Not quantitatively assessed'`). But a 0 at F95 where the mean is
  positive (e.g. `ADGAS_F95` on the conventional units) is a real low-end estimate. So a zero
  cannot be read as "not assessed" without looking at the unit type and the mean.
- **Only the mean is additive.** F95/F50/F5/STDEV are per-unit distribution statistics;
  `OILLG_*`/`GASLG_*` describe one accumulation and are never summed.
- **Units overlap**, up to 6 per resolution 8 cell.
