---
name: job-troubleshooting
description: >-
  Diagnose failing or stuck Kubernetes jobs and DuckDB parquet errors: OOMKilled, evictions, ContainerStatusUnknown, flaky-node hangs, ephemeral-storage limits and PVC scratch, pod quota errors, 404s on convert, blank PMTiles in MapLibre, and the DuckDB httpfs stoi crash on oversized parquet column chunks. Use when a job fails or hangs, or when a published parquet will not read.
---

# Job Troubleshooting

Diagnose before resubmitting — a failing job re-run unchanged fails the same way.

## ⛔ Serialization standard: DuckDB httpfs `stoi` crash on oversized column chunks

The MCP can abort with **`SQL Error: stoi`** when reading GeoParquet over S3/httpfs. The root cause is a **DuckDB httpfs bug on large Parquet column chunks** — not the CRS tag, writer, or geometry content. Fully diagnosed in datasets [#106](https://github.com/boettiger-lab/datasets/issues/106).

### What triggers it

A single Parquet column chunk in the **~2.8–2.88 GB compressed / ~3.73–3.84 GB uncompressed** range causes the httpfs reader to abort with `stoi`. No spatial function needed — `SELECT COUNT(geom)` (which decodes the column) is sufficient to crash; `SELECT COUNT(*)` (footer only, no decode) is fine. **Local file reads always work** — this is exclusively an httpfs path bug.

```sql
SELECT COUNT(*)  FROM read_parquet('https://…/repro-100000.parquet');   -- ✅ OK
SELECT COUNT(geom) FROM read_parquet('https://…/repro-100000.parquet'); -- ❌ stoi
```

The crash appears "plan-dependent" because queries that skip decoding the geometry column (e.g. filtered reads that never touch the oversized chunk) avoid it. Every individual row is valid; the data is not corrupt.

### What does NOT matter

| Hypothesis | Verdict |
|---|---|
| `creator: geopandas` | ❌ cng-convert-written file crashes identically |
| `OGC:CRS84` vs `EPSG:4326` CRS tag | ❌ re-tagging as `EPSG:4326` still crashes |
| Plain DuckDB `COPY` re-write | ❌ still crashes |
| A single pathological geometry | ❌ local read of same file returns all rows |

### Prevention (the real fix)

**Keep row groups small enough that no single geometry column chunk exceeds ~1 GB compressed.** For large-feature geometry (complex multipolygons, national-scale data), the default `--row-group-size 100000` can pack a single chunk well past the 2.8 GB cliff. Use `--row-group-size 2000` as a safe default for geometry-heavy datasets, or estimate `avg(octet_length(ST_AsWKB(geom)))` on a sample and size accordingly. Tracked in cng-datasets [#106](https://github.com/boettiger-lab/datasets/issues/106).

### Mitigation if a published file already crashes

Use `s3://` (internal endpoint, not `https://`) inside cluster jobs — the httpfs path is the public endpoint only. For MCP queries (which always go over https), re-publish the file with smaller row groups via a cluster DuckDB job:

```sql
COPY (SELECT * FROM read_parquet('s3://bucket/file.parquet'))
TO 's3://bucket/file-rg2000.parquet'
(FORMAT PARQUET, ROW_GROUP_SIZE 2000, COMPRESSION ZSTD);
```

### geopandas-written files

Still avoid publishing geopandas-written GeoParquet — use the cng-datasets DuckDB-native path. But the failure mode is different (geoarrow extension type, any DuckDB version; upstream [duckdb/duckdb#21691](https://github.com/duckdb/duckdb/issues/21691)) and orthogonal to the httpfs chunk-size crash above.

## Troubleshooting

**404 on convert → verify source URLs** with `curl -I` and directory listings (most common failure — always verify BEFORE generating YAMLs).

**"Cannot mix .zip files with multiple source URLs"** → preprocess job: download in parallel, unzip, pass shapefiles to `cng-convert-to-parquet`.

**Check convert logs:** `kubectl logs job/<name>-convert`

**Repeated preemptions on shared nodes → pin to Berkeley node** `stratus1.nrp-espm.berkeley.edu` (currently carries `nautilus.io/issue` taint):
```yaml
spec:
  template:
    spec:
      nodeSelector:
        kubernetes.io/hostname: stratus1.nrp-espm.berkeley.edu
      tolerations:
      - {key: "nautilus.io/issue", operator: Exists, effect: NoSchedule}
```

⛔ **This pin is a *reactive last resort* for observed, recurring preemption — NEVER a default.** By default let the k8s scheduler place pods. Many nodes across the cluster can service big requests (256/512 GB, multi-cpu) — the Berkeley node is only one of them. **Pinning a large-memory job to one node serializes it:** a 256Gi/8cpu pod fills the node, so `parallelism: N` becomes 1-at-a-time while the rest sit `Pending: Insufficient cpu` (this turned a CONUS res-10 hex from hours into 30-50h — #307). The cluster headroom is there to *request when a job genuinely needs it*; reach for `backoffLimitPerIndex` retries to absorb the occasional preemption before you ever reach for a node pin.

✅ **You do NOT need to exclude GPU nodes for CPU-only jobs.** The generated `nodeAffinity` excludes GPU nodes (`feature.node.kubernetes.io/pci-10de.present NotIn true`), but GPU nodes usually have plenty of **spare CPU/RAM** that our hex/convert/COG jobs can use. Dropping the GPU exclusion **widens the schedulable pool**, which finishes fan-out jobs faster and — importantly — reduces the chance of pods piling onto a flaky node. Keep the exclusion only if a job genuinely needs to avoid GPU-host contention.

⚠️ **Flaky-node hangs — and ⛔ NEVER `--force`-delete pods.** Some shared nodes (observed: `hpc-nrp-g1.nmsu.edu`, `service-02.nrp.mghpcc.org`) have broken egress/S3 connectivity: pods schedule but **hang on `rclone` localize / external download** ("Localizing input →" with no progress; "Could not resolve host") or sit `Pending` with the container never starting. A `backoffLimit: 0` job never recovers (pod Running/Pending, not Failed) and blocks the whole run.

- ⛔ **Never `kubectl delete pod --grace-period=0 --force`.** It drops the API object while the container may still be running on an unreachable node → split-brain / duplicate S3 writes. (Standing rule from the user.)
- ✅ **Let the control plane reap it — the safe equivalent.** A graceful `kubectl delete pod` (no `--force`) plus the node-lifecycle controller's eviction marks pods on an unreachable node `Failed` after the eviction timeout (~5 min); with `podReplacementPolicy: Failed` (the default once `backoffLimitPerIndex` is set) the Job then recreates that index on a healthy node. Net cost of *not* forcing is ~5 min, **not** a block — verified: a 4-index hang on `service-02` self-healed to 122/122 with zero force-deletes.
- **Defenses, in order (prevention beats cure):** (1) exclude known-bad hosts via a `kubernetes.io/hostname NotIn [hpc-nrp-g1.nmsu.edu, service-02.nrp.mghpcc.org, …]` nodeAffinity term so pods never land there; (2) `activeDeadlineSeconds` on the **pod template** (turns a running-hang into a Failure the Job can retry); (3) `backoffLimitPerIndex` + `maxFailedIndexes` (retry the index elsewhere). Note `activeDeadlineSeconds` only helps a *Running* hang — a `Pending` pod (container never started) is cleared only by control-plane eviction, so (1) is the real fix.

**Pod keeps getting evicted (`ContainerStatusUnknown`) → diagnose BEFORE resubmitting.** Never resubmit a failing job without `kubectl describe pod <pod>` — same resources will fail the same way.
```bash
kubectl -n geo-workflows describe pod <pod-name> | grep -A5 "Reason:\|Message:\|Events:"
```

| Message | Cause | Fix |
|---|---|---|
| `ephemeral local storage usage exceeds the total limit` | DuckDB sort spill | Raise memory AND ephemeral-storage |
| `OOMKilled` | Insufficient RAM | Raise memory |
| `ContainerStatusUnknown` on shared nodes | Preemption | Pin to Berkeley node |

**DuckDB sort jobs need both big RAM and big ephemeral-storage.** `ORDER BY` over large data spills to disk; low RAM spills more. For 1–15 GB compressed partitions: 120Gi RAM, 50Gi ephemeral-storage. Namespace max for ephemeral-storage is **50Gi** — always request the max for sort-heavy jobs.

**When scratch exceeds 50Gi, mount a PVC — do NOT fight the ephemeral cap.** Ephemeral-storage is hard-capped at 50Gi namespace-wide, so any job whose local scratch exceeds that — a raw download bigger than ~45 GB (e.g. the 35 GB RAP CONUS COG), a multi-tile `preprocess-cog` mosaic, a `raster --local-cache-dir` localization of a large COG — must use a **PersistentVolumeClaim**, not a bigger ephemeral request (which the quota will reject). A shared scratch PVC already exists: **`rechunk-scratch`** (2Ti, `RWX` rook-cephfs) — list with `kubectl -n geo-workflows get pvc`.
- Mount it and redirect the tool's scratch onto it; keep ephemeral small (~10Gi):
  ```yaml
  volumeMounts:
  - {name: scratch, mountPath: /scratch, subPath: <job-name>}   # subPath → per-job isolation on the shared PVC
  volumes:
  - {name: scratch, persistentVolumeClaim: {claimName: rechunk-scratch}}
  env:
  - {name: TMPDIR, value: /scratch}        # Python tempfile.mkdtemp (mosaic temp) honors TMPDIR
  # and pass: cng-datasets raster --local-cache-dir /scratch ...   (input localization; CLI default is /tmp/cng-raster-cache)
  ```
- **`RWX` + concurrency caveat:** `rechunk-scratch` is ReadWriteMany, but `--local-cache-dir` localizes to a fixed basename, so **N concurrent pods sharing one mountPath collide on the same file**. Use a per-pod `subPath` (or per-pod cache subdir) for fan-out jobs. The 122-pod raster **hex** step localizes a multi-GB COG per pod and is best left on **per-pod ephemeral** (the mosaic COG fits in 50Gi); reserve the PVC for the **single-pod** `preprocess-cog`/download/stage steps where the file genuinely exceeds 50Gi.

**Hex OOM** → regenerate with `--hex-memory 64Gi` and/or more `--max-completions`, delete failed job, reapply.

**503 SlowDown (S3 throttle)** → transient, retry.

**PMTiles renders blank in MapLibre → wrong `source-layer`.** It's the last path segment of `--dataset`, NOT the GDB/source layer name. For `--dataset padus-4-1/fee`, it's `fee` (not `PADUS4_1Fee`).

**Workflow stuck:** `kubectl logs job/<name>-workflow` and `kubectl get jobs | grep <name>`.

**`exceeded quota: reached-quota`** → pod limit hit. Delete running hex jobs and resubmit sequentially (see Namespace Pod Quota):
```bash
kubectl get jobs | grep -E 'dataset-a|dataset-b' | awk '{print $1}' | xargs kubectl delete job
```
