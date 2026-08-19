# iucn-ranges-2025 hex — the #577 `_cng_fid` re-key

Collection: `s3://public-iucn/iucn-ranges-2025/`
Flat: `s3://public-iucn/iucn-ranges-2025.parquet` (135,986 rows, 114,087 IUCN range records)
Hex: `s3://public-iucn/iucn-ranges-2025/hex/h0=*/data_0.parquet` (4,077,008,576 rows, 22 GiB,
122 partitions, multi-resolution — per-row `native_res` ∈ {5, 6, 8})

## What was wrong

The hex was built 2026-06-08. On **2026-07-09** the **#372 `_cng_fid` backfill**
(`catalog/backfill/k8s/cngfid-372/catA-cngfid-convert.yaml`) re-ran
`cng-convert-to-parquet` over ten published flats — this one at 13:10, and
`high-seas/hydrothermal-vents` at 13:07 — synthesizing a fresh `_cng_fid` in each and
promoting the result. `_cng_fid` is assigned at conversion time, so the flat was renumbered
while the hex kept the old numbering.

The two numberings are not an offset but an unrelated permutation: **0 of 134,969 ids were
unchanged**. Joining hex→flat on the documented universal key returned an unrelated species
on essentially every row, across a 4-billion-row asset, with no row-count or schema symptom.
That is the same mechanism and the same afternoon as #574.

**Only the id was wrong.** The hex's own attributes were never corrupt: its `sci_name` already
agreed with the flat's on all 113,621 shared range records.

## Why a re-key rather than a rebuild

A rebuild is the correct fix and remains the eventual one, but it is blocked and expensive:
the multi-resolution build recipe is **not in this repo**, and the standard it would target
(#548, "a standard multi-resolution H3 representation") is still open. Regenerating means
reconstructing that pipeline and re-deriving 4.08 billion rows.

Re-keying in place was chosen instead because the defect is confined to one column and a
sound bridge exists. It is a remediation, not a substitute for the rebuild.

### The bridge, and why it is trustworthy

The hex carries no geometry, so parts cannot be matched back to individual flat rows by
shape. The only bridge is IUCN's natural key `(id_no, presence, origin, seasonal)`. Each of
these was measured before anything was written:

| fact | measured |
|---|---|
| natural keys whose attributes vary across their flat rows | **0** of 114,087 (`sci_name`, `latest_category_code`, `family`, `common_name_en`, `in_holdings`) |
| shared keys where the hex's own `sci_name` already agreed with the flat | **113,621 of 113,621** |
| hex `_cng_fid` values spanning more than one natural key | **0** |
| keys with more hex parts than flat rows (`M > N`) | **0** — so a within-key injective pairing always exists |

Because attributes are constant within a key, pairing a hex part with *any* flat row of the
same key yields correct attributes for every attribute column.

### The pairing rule

Within a natural key, rank hex parts by their old `_cng_fid` and flat rows by their
`_cng_fid`, then pair by rank. Deterministic, and globally injective because a flat id
belongs to exactly one key. The resulting map was verified to be a bijection
(134,969 → 134,969, no NULLs, **0 remapped ids whose species disagrees**).

### ⚠️ The residual limit — state it, do not paper over it

For the **9,890 multi-part range records (31,238 parts, 23% of the total)** the part-to-part
assignment is **arbitrary**: the re-keyed `_cng_fid` identifies the correct range record and
therefore the correct species and attributes, but not necessarily the same polygon part as
the GeoParquet row of that id. For the **103,731 single-part records the correspondence is
exact**.

So: attribute joins are correct; a join that then uses the flat's *geometry* may get a
different part of the right range. Consumers needing a specific boundary should read the
GeoParquet asset directly. Only a rebuild removes this.

## Coverage: 134,969 of 135,986 (1,017 absent)

Measured, not assumed — the shortfall decomposes exactly:

- **486** flat rows belonging to **466 range records absent entirely**
- **531** individual parts of **203 records** that are otherwise present

A res-8 polyfill was run over all 2,308 flat rows of the 669 affected records
(resolution 8 is the finest this dataset's scheme assigns, so a polygon yielding no cell
there yields none at 6 or 5 either). Result: **0 records show unexplained loss** — for every
affected record, the number of parts that actually polyfill never exceeds the number the hex
holds. There is no dropped chunk and no coverage cap.

Note the honest caveat: 1,244 of those 2,308 parts have **zero or undefined (NaN) spheroid
area**, and 114 records hold *more* parts than a res-8 polyfill yields. So the "zero cells"
population is sub-cell geometry **plus** degenerate polygons that the H3 polyfill cannot
process — not simply "too small". The STAC says so in those terms.

## Rebuilding the audit trail

The staged hex under `s3://public-iucn/iucn-ranges-2025/staging-577/hex/` was *moved* into
place by the swap, so it no longer exists. Two small tables remain there deliberately:

- `fid-map.parquet` (676 KiB) — the old→new id map. It is the **rollback inverse**: joining
  it the other way reconstructs the pre-swap numbering, which is the only thing the previous
  hex held that this one does not.
- `hex-fid-summary.parquet` (2.5 MiB) — the per-(key, fid) collapse the audit was built on.

Both are cheap to keep and expensive to regenerate (each needs a full 4.08e9-row scan). Retire
them when #577 is closed and the eventual rebuild lands. The jobs that produce everything are
in this directory and are re-runnable in order:

1. `iucn-577-hex-fid-summary.yaml` — collapses 4.08e9 rows to one row per (natural key, fid).
   Everything else queries that ~135k-row table, because full-scan queries time out the MCP
   at 300 s.
2. `iucn-577-build-fid-map.yaml` — builds and asserts the bijection.
3. `iucn-577-rekey-hex.yaml` — 122 indexed pods, one per `h0`, writing to staging.
4. `iucn-577-verify-staging.yaml` — the acceptance gate, run **before** the swap.
5. `iucn-577-swap-hex.yaml` — refuses to swap unless the partition sets match exactly.

`iucn-577-polyfill-groundtruth.yaml` measures the coverage cause. It needs >32Gi: the first
attempt was OOMKilled and succeeded on retry.

## Do not re-run the flat conversion

Anything that re-runs `cng-convert-to-parquet` over `iucn-ranges-2025.parquet` renumbers
`_cng_fid` again and re-orphans this hex — including a catalog-wide backfill, which is what
caused this. If the flat is ever re-converted, the hex must be rebuilt or re-keyed in the
same pass.
