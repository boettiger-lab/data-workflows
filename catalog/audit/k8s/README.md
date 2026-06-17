# Audit / repair jobs

One-off cluster jobs that audit or repair S3 layout issues across buckets.

## `fix-double-slash-keys.yaml`

Consolidates hex H3 partitions written with a **double-slash** key (`hex//h0=…`,
or `h0=<cell>//data_N.parquet`) onto the canonical single-slash path, and purges
stale intermediate prefixes. These bad keys come from a path-join that concatenated
a base ending in `/` (e.g. a trailing-slash `--output-parquet …/hex/`) with a
leading-`/` subpath; `rclone` **silently skips** `//` keys, so they are invisible to
the normal `hex/h0=*/data_0.parquet` glob and to the MinIO/source.coop mirrors.

Per `//` key (boto3, internal endpoint, server-side copy — no data egress):
- **target absent** → copy `//`→`/` then delete `//` (surfaces hidden data)
- **target present, byte-identical** → delete `//` orphan
- **target present, in `VERIFIED_FLAGS`** → delete `//` (byte-different but proven
  content-identical to its single-slash twin via whole-row `bit_xor(hash(row))`)
- **target present, differs & unverified** → FLAG, never auto-deleted

`DRYRUN=true` (default) classifies and reports without mutating. Set `DRYRUN=false`
to execute. See data-workflows #240 for the full audit + the 2026-06 run results
(carbon 792, gbif 234, overturemaps 196 keys).

## `purge-stale-chunks.yaml`

Deletes leftover intermediate `chunks/` prefixes (pre-repartition per-pod output).
The cng-datasets repartition `--cleanup` step removes these via `rclone purge`, which
**silently no-ops under S3 load** (300s timeout, non-fatal) — so large/busy datasets
leak chunks while small ones don't. Found on `gbif` (174 GiB / 20.5k objs),
`padus` (5 layers), `wetlands/ramsar` (#240).

**Only purge after verifying the canonical `hex/` is complete** (`hex` row count ≥
`chunks` per h0). boto3 list+delete, guarded to `chunks/` prefixes only, verify-empty
after. `TARGETS` = space-separated `bucket/prefix/` list; `DRYRUN=true` default.

## `../../gbif/k8s/gbif-2025-repair-hex.yaml`

Before gbif chunks could be purged, the hex≥chunks check found 3 h0 cells
(`8011`/`804b`/`8047`) where `hex/` was **truncated** — the original fill-missing
write was preempted (opportunistic priority) and the retry skipped the partial files
(`OVERWRITE_OR_IGNORE`), so `hex/` held far fewer rows than the complete `chunks/`.
This job re-consolidates those cells from `chunks/`, **deleting the partition first on
every attempt** (so a preemption can't leave a partial) and writing the corrected
no-trailing-slash path; it asserts `hex == chunks` per cell. Only then were gbif
chunks safe to purge.
