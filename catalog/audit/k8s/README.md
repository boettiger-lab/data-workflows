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
