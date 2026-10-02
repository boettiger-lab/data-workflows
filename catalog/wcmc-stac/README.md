# STAC authoring for the UNEP-WCMC coral & seagrass collections (#444)

STAC JSON and dataset READMEs are **not** kept in this repo (AGENTS.md Hard Boundary 1) — they
are canonical on NRP S3. What lives here is the tooling that produced them, so the six published
documents can be regenerated and re-verified from scratch.

| file | what it does |
|---|---|
| `common.py` | shared building blocks: nav links, licence link and text, H3 columns, `_cng_fid`, the PMTiles lean-column projection |
| `coral.py` | emits the two `public-coral-reefs` collections + the bucket collection |
| `seagrass.py` + `fill_seagrass.py` | emits the two `public-seagrass` collections + the bucket collection |
| `values.json` | **measured** distinct values per layer per column, plus each parquet's full schema |
| `extract-distinct-values.yaml` | the job that produced `values.json` |
| `read-metadata-lookup.yaml` | reads `Metadata_CoralReefs.dbf` (81 source records) out of the raw zip via GDAL range reads |
| `mk-upload-job.sh` | builds a ConfigMap + Job that uploads the generated files to NRP |

## Why `values.json` exists, and why nothing is hand-typed

Every `values` array is read out of the published parquet for **that specific layer**. This is the
#294 discipline, and it caught three real errors during this build that hand-writing had
introduced:

1. **Seagrass genus/family values were taken from the point layer and reused for polygons.** The
   polygon layer has 22 families and 31 genera against the point layer's 6 and 14, and includes
   freshwater taxa (*Myriophyllum*, *Najas*, *Vallisneria*, *Trapa*) the point layer never
   mentions.
2. **A truncated coral value was "reconstructed" and got it wrong.** `SURVEY_MET` really ends with
   a literal asterisk — `Assessment of LADS features based on geomorpholog*` — which is upstream's
   own marker for a label cut to fit a 50-character field. The plausible-looking guess
   ("…geomorphology") was simply not what is in the data.
3. **Casing differs between the two layers of the same product.** Coral polygons carry
   `Expert Verified` and `Field survey`; coral points carry `Expert verified` and `Field Survey`.
   Seagrass points carry both `Not Reported` and `Not reported` in one column.

`verify-stac.py --bucket … --dataset …` catches all of these, but only once the data is live. The
generator reading from `values.json` is what stops them being reintroduced.

## Regenerate

```bash
kubectl apply -n geo-workflows -f extract-distinct-values.yaml
kubectl -n geo-workflows logs job/wcmc-distinct-values | sed -n '/###JSON###/,$p' | tail -1 > values.json

python3 coral.py && python3 fill_seagrass.py            # writes bucket__path__file.json
scripts/verify-stac.py --no-data <each generated file>  # must be clean before upload

bash mk-upload-job.sh wcmc-stac-upload . upload.yaml
kubectl apply -f upload.yaml

# then the data-backed gate, which must exit 0:
scripts/verify-stac.py --bucket public-coral-reefs --dataset unep-wcmc-coral-reefs/polygons
scripts/verify-stac.py --bucket public-coral-reefs --dataset unep-wcmc-coral-reefs/points
scripts/verify-stac.py --bucket public-seagrass    --dataset unep-wcmc-seagrass/polygons
scripts/verify-stac.py --bucket public-seagrass    --dataset unep-wcmc-seagrass/points
```

The upload job dereferences ConfigMap symlinks (`cp -L`) before calling rclone — rclone will not
follow them, and fails with "not a directory" if handed one directly.
