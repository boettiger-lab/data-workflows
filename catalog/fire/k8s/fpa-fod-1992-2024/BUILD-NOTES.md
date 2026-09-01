# FPA-FOD 1992-2024 (7th edition) — build notes

Issue [#587](https://github.com/boettiger-lab/data-workflows/issues/587). Read this before
regenerating any manifest in this directory: **two values are hand-set and the generator will
revert them.**

## Source

| | |
|---|---|
| Citation | Short, Karen C. 2026. *Spatial wildfire occurrence data for the United States, 1992-2024 [FPA_FOD_20260615]*, 7th Edition. |
| DOI | `10.2737/RDS-2013-0009.7` |
| Zip | `RDS-2013-0009.7_Data_Format3_GPKG.zip`, 238,170,979 bytes |
| sha256 | `9e36ecd0d70dd5fa126be7b5ce5b02003867da04c41f3bd137f5ccdfca81b9b2` |
| Staged | `s3://public-fire/raw/FPA_FOD_20260615.gpkg` (1,082,466,304 bytes) |
| Layers | `Fires` (Point, 2,661,383 features) · `NWCG_UnitIdActive_20200123` (non-spatial, 5,971 rows) |
| Accessed | 2026-08-25 |

This issue was filed against the **6th** edition (1992-2020, ~2.3M records) and instructed that a
newer edition be used if one existed. It does. ⛔ Do not rebuild the 6th edition. The 7th also
backfills previously underrepresented states/territories (Guam among them), so pre-2021 counts
differ from the 6th edition — it is not four years appended.

## ⛔ Hand-set values that regeneration reverts

`cng-datasets workflow` could **not** count features in the source GPKG and fell back to its
conservative default. Hex coverage is `completions × chunk-size`, **not** a soft cap
(data-workflows #494), so the default silently covers only 200,000 of 2,661,383 features — a
**7.5%** build that still produces a complete-looking repartition and STAC.

| Value | Generator emits | Must be | Why |
|---|---|---|---|
| `--chunk-size` (hex) | `1000` → 200,000 covered | **`13307`** → 2,661,400 covered | `ceil(2661383 / 200)` |
| `memory` (hex) | `16Gi` | **`8Gi`** | `--hex-memory` is one flag that also sizes convert and pmtiles; only the 1.08 GB convert needs 16Gi. Hexing points is the cheapest case — one point polyfills to exactly one res-10 cell, and a chunk is 13,307 rows. |

**Both live in two places** — the standalone `fpa-fod-1992-2024-hex.yaml` *and* the copy embedded in
`configmap.yaml`, which is what the `workflow.yaml` orchestrator actually applies. Patching only the
standalone file leaves the orchestrator truncating. Verify both:

```bash
grep -o '\-\-chunk-size [0-9]*' fpa-fod-1992-2024-hex.yaml configmap.yaml   # both must say 13307
```

Use the **exact** feature count when recomputing: a chunk-size derived from a rounded 2,660,000
gives 13300, which silently leaves 1,383 fires unhexed.

## Regeneration command

```bash
cng-datasets workflow \
  --dataset fpa-fod-1992-2024 \
  --source-url s3://public-fire/raw/FPA_FOD_20260615.gpkg --layer Fires \
  --bucket public-fire --namespace geo-workflows \
  --h3-resolution 10 --parent-resolutions "9,8,0" \
  --max-completions 200 --max-parallelism 50 --hex-memory 16Gi \
  --output-dir catalog/fire/k8s/fpa-fod-1992-2024
# then re-apply the two hand-set values above, in BOTH files
```

`--h3-resolution 10 --parent-resolutions "9,8,0"` is also the generator's point default; it is
passed explicitly so the manifest states it. Carrying `h8` keeps the dataset joinable to the rest
of the catalog.

`--row-group-size` is left at the default 100000: point WKB is ~21 bytes, so the geometry column is
~60 MB in total, far below the ~2.8 GB DuckDB httpfs `stoi` cliff. The `--row-group-size 2000`
guidance targets geometry-heavy polygons.

## Apply order

`fpa-fod-stage-raw.yaml` is not part of the generated workflow — run it first, once. It also serves
as the schema probe (layer names, feature count, `FIRE_YEAR` range, and the cause/owner domains
that upstream metadata does not enumerate).

```bash
export PATH=$HOME/bin:$PATH        # kubectl's credential plugin shells out to `kubectl` by name
kubectl apply -n geo-workflows -f workflow-rbac.yaml          # once
kubectl apply -n geo-workflows -f fpa-fod-stage-raw.yaml
kubectl apply -n geo-workflows -f fpa-fod-1992-2024-setup-bucket.yaml
kubectl apply -n geo-workflows -f fpa-fod-1992-2024-convert.yaml
kubectl apply -n geo-workflows -f fpa-fod-nwcg-units.yaml
kubectl apply -n geo-workflows -f fpa-fod-1992-2024-pmtiles.yaml
# ⛔ HEX LOCK: check `kubectl -n geo-workflows get jobs | grep hex` first — the fan-out hex step is
# exclusive namespace-wide. Only then:
kubectl apply -n geo-workflows -f fpa-fod-1992-2024-hex.yaml
kubectl apply -n geo-workflows -f fpa-fod-1992-2024-repartition.yaml
```

Do **not** apply `workflow.yaml` while another hex job is running — the orchestrator launches hex
itself.

Note: `dnsPolicy: None` with public nameservers must **not** be set on these jobs. The rclone `nrp:`
remote targets the internal endpoint `rook-ceph-rgw-nautiluss3.rook`, which only cluster DNS
resolves; overriding it hangs the upload at 0 B. (The `calfire-2025-stage-raw.yaml` template sets it
because it needed public DNS for an Azure CDN.)

## Verification

```bash
scripts/verify-stac.py --bucket public-fire --dataset fpa-fod-1992-2024   # must exit 0
```

The load-bearing check is `hex-missing-features`: hex `COUNT(DISTINCT _cng_fid)` must equal flat
`COUNT(*)` = 2,661,383. That is the gate that catches a chunk-size regression.

## STAC

`gen_stac.py` writes `/tmp/stac-collection.json` (never committed — Hard Boundary 1). Column prose
and coded domains come from `_codes.json`, generated from the upstream
`Data/_variable_descriptions.csv` inside the source zip, plus the `NWCG_GENERAL_CAUSE` and
`OWNER_DESCR` domains that upstream does **not** enumerate and which were read off the ingested
data instead of written from memory (#294).

`gen_stac.py` refuses to write while `extent.spatial.bbox` is unset. The record set spans Guam
(+144.9) to Puerto Rico, so the overall bbox **crosses the antimeridian** and its west edge has a
larger longitude than its east edge. Measure it from the data; do not paste the `ogrinfo`
min/max box, which reads -178.8 → +144.9 and describes 323° of longitude instead of ~149°.

## Hex build, 2026-08-25

Ran once the namespace hex lock cleared (#593's MTBS severity chain finished; its orchestrator
Job shows `Failed`, but that was an eviction *after* all three child jobs completed).

| Step | Result |
|---|---|
| `fpa-fod-1992-2024-hex` | ✅ **200/200, 2m10s**, `Complete=True`, `failedIndexes` empty |
| `fpa-fod-1992-2024-repartition` | ✅ 1/1, 57s → 13 `h0` partitions, 113.8 MiB |
| Coverage gate | ✅ hex `COUNT(DISTINCT _cng_fid)` = **2,661,383** — exactly the flat count |
| `verify-stac.py --bucket public-fire --dataset fpa-fod-1992-2024` | ✅ **0 hard**, 8 advisory |

**The whole chain took three minutes.** It had been recorded as blocked for a day behind a lock
that a 7.5-hour-per-layer raster build was holding; this is a 2.66 M-point vector hex and is not
in that cost class. Worth checking the lock is *actually* held rather than assuming, especially
since the documented check silently returns a false clear (see below).

### Manifest hardening applied before the run

The generated hex manifest carried `backoffLimit: 0`, which AGENTS.md/#409 prohibits on an
indexed fan-out: a partial run can publish as complete, and a pod hung on a flaky node's broken
egress never recovers. Replaced with `backoffLimitPerIndex: 3` + `maxFailedIndexes: 10` in both
the standalone manifest **and** the copy inside `configmap.yaml` (the orchestrator applies the
latter). Also dropped the generator's GPU-node exclusion, kept the two known-bad-egress host
exclusions, and raised `ttlSecondsAfterFinished` 10800 → 86400 — a 3 h TTL is what made #586
unable to answer "did that job finish?" from the cluster at all.

### Two STAC code lists were wrong, and only the data-backed gate caught them

`verify-stac.py --no-data` passed; the full run failed with 2 HARD `values-incomplete` findings on
the NWCG unit lookup. Both were transcription slips in `_codes.json`, enumerated against the
ingested table to fix:

| Column | Declared | Actually in the data |
|---|---|---|
| `GeographicArea` | `CB` (labelled "Great Basin") | **`GB`** — 360 rows |
| `GACC` | `USAKCC` | **`USAKACC`** — 183 rows |

Both lists had the right *length*, so a count check would not have found them. This is the
#114/#294 class exactly: a plausible-looking code written from a document rather than read back
out of the ingest.

### Not measured

Hex pod memory. The plan was to sample `kubectl top pod` and trim from the 8Gi starting point,
but at 2m10s the pods completed before they could be sampled and `kubectl top` reports live pods
only. 8Gi is already the low end and a rerun to trim it is not worth the lane time — recording
this as unmeasured rather than implying it was checked.

### `kubectl` lock check — use the PATH prefix

`~/bin/kubectl` invoked by absolute path fails: its client-go credential plugin `exec`s `kubectl`
from `PATH`, the error goes to stderr, and the grep prints nothing — indistinguishable from "no
hex jobs running", which is the exact failure the lock exists to prevent.

```bash
PATH="$HOME/bin:$PATH" ~/bin/kubectl -n geo-workflows get jobs | grep -E 'hex'
```
