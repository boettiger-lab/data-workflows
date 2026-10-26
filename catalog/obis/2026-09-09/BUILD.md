# OBIS 2026-09-09 build

Native ingest of the OBIS occurrence export (#660). Source: `s3://obis-open-data/occurrence/`
(anonymous, one parquet per source dataset). Output: `s3://public-obis/`.

## Run order

```bash
NS=geo-workflows
kubectl apply -n $NS -f configmap.yaml   # re-apply after any edit to the two stage scripts

# 1. Create the bucket. Must finish before stage-raw, or rclone fails late on NoSuchBucket.
kubectl apply -n $NS -f obis-setup-bucket.yaml
kubectl wait -n $NS job/obis-setup-bucket --for=condition=complete --timeout=600s

# 2. These two run concurrently. The hex reads AWS directly, not the staged raw.
kubectl apply -n $NS -f obis-stage-raw.yaml   # raw/occurrence/, raw/licenses.tsv, raw/MANIFEST.txt
kubectl apply -n $NS -f obis-hex.yaml         # 2026-09-09/chunks/h0=*/ and 2026-09-09/shards/
kubectl wait -n $NS job/obis-2026-09-09-hex --for=condition=complete --timeout=86400s

# 3. Dedup on _id, one file per h0 -> 2026-09-09/hex/h0=<int>/data_0.parquet
kubectl apply -n $NS -f obis-consolidate.yaml
kubectl wait -n $NS job/obis-2026-09-09-consolidate --for=condition=complete --timeout=86400s

# 4. STAC + README to public-obis, obis-derived appended to the root catalog
python3 measure_obis.py && python3 build_stac.py && python3 build_readme.py
kubectl -n $NS create configmap obis-2026-09-09-publish \
  --from-file=/tmp/stac-collection.json --from-file=/tmp/README.md --from-file=append_root_child.py
kubectl apply -n $NS -f obis-publish-stac.yaml
```

Stage 1 exits nonzero if any source file fails or has an unexpected schema. Each shard writes a
marker to `2026-09-09/shards/` only on success. Stage 2 refuses to run unless the markers cover
every source file under a single `TOTAL_SHARDS`, and fails any partition where
`COUNT(*) != COUNT(DISTINCT _id)`.

`configmap.yaml` is generated from the two stage scripts:

```bash
kubectl create configmap obis-2026-09-09-scripts -n geo-workflows --dry-run=client -o yaml \
  --from-file=consolidate_h0_partitions.py --from-file=process_obis_h3.py > configmap.yaml
```

## Acceptance checks

Run through the `duckdb-geo` MCP.

```sql
SELECT COUNT(*) AS n, COUNT(DISTINCT _id) AS ids, COUNT(DISTINCT dataset_id) AS datasets
FROM read_parquet('s3://public-obis/2026-09-09/hex/h0=*/data_0.parquet');

SELECT COUNT(*) FROM glob('s3://public-obis/2026-09-09/hex/h0=*/*.parquet');  -- 122
```

Then `scripts/verify-stac.py --bucket public-obis` must exit 0.
