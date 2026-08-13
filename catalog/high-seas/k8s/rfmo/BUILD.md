# rfmo/rfb rebuild (data-workflows #520)

Full rebuild of `public-high-seas/rfmo/rfb` from convert onward, 2026-08-12/13. Fixes three
defects in the prior (2026-06) build: CCAMLR (and 5 other features) missing/mis-hexed,
`_cng_fid` absent from the flat + holed in 22 hex partitions, and a STAC schema that misdescribed
all three `rfb` assets. See the #520 thread for the diagnosis.

## Source & scope (from the issue — the single source of truth)

- Source: `https://s3-west.nrp-nautilus.io/public-high-seas/raw/rfmo-rfb.zip` (unchanged).
- Extent: global, full upstream coverage, **all 105 features / 54 RFB**. No clip.
- Bucket/dataset: `public-high-seas`, `--dataset rfmo/rfb` (paths + asset keys unchanged).
- H3: native resolution **8**, parents **7,6,0** (matches what `rfb-hex` already declared).
- License: `CC-BY-SA-3.0-IGO` (FAO), unchanged.

## Pipeline (apply in order, namespace `geo-workflows`)

1. `rfmo-rfb-convert.yaml` — `--row-group-size 2000` (geometry-heavy; regenerates `_cng_fid`).
2. `rfmo-rfb-pmtiles.yaml` — tiles now carry `_cng_fid` (new flat).
3. `rfmo-rfb-split-antimeridian.yaml` — builds `rfb-hexinput.parquet` (see below), purges `chunks-staging`.
4. `rfmo-rfb-hex.yaml` — 136 completions, chunk-size 1, `--parent-resolutions 7,6,0` → `chunks-staging`.
5. `rfmo-rfb-repartition.yaml` — `chunks-staging` → `hex-staging`, 120Gi / `--memory-limit 100GiB`.
6. `rfmo-rfb-swap-staging.yaml` — purge live `hex/`, verify empty, move `hex-staging` → `hex/`.
7. Rewrite STAC `table:columns` for the 3 `rfb` assets; `verify-stac.py --bucket public-high-seas --dataset rfmo`.

The old `rfmo-rfb-add-parents.yaml` (a second full-rewrite `SELECT *` pass **without** `union_by_name`)
is **removed** — folding `7,6` into the hex pass eliminates the step that dropped `_cng_fid` from 22
partitions. Never reintroduce it.

## The antimeridian workaround (why steps 3 + the 45° split exist)

Six features have a longitude bounding box spanning > 180° and cannot be hexed at res 8 by the current
tool — its planar H3 polyfill enumerates the whole bbox span. datasets **#167** now *fails fast* on
them (that is the crisp `RuntimeError` you get, not a hang); the real capability lands with adaptive
variable-resolution polyfill (datasets **#98**), at which point this workaround can retire.

Measured (`ST_XMax-ST_XMin` on the flat):

| `_cng_fid` | OGC_FID | RFB | lon span | note |
|---|---|---|---|---|
| 13 | 12 | CCAMLR | 360.0 | circumpolar (rings Antarctica) |
| 41 | 40 | IPHC | 360.0 | crosses dateline |
| 92 | 91 | IWC | 360.0 | near-global ocean |
| 93 | 92 | ACAP | 360.0 | southern oceans |
| 102 | 101 | APFIC | 355.7 | 342-part multipolygon |
| 38 | 37 | CCSBT | 241.2 | crosses dateline |

`rfmo-rfb-split-antimeridian.yaml` clips these 6 into **45° longitude-band pieces** (planar
`ST_Intersection` with band envelopes), each a separate row **retaining the original `_cng_fid` +
attributes**, into `rfb-hexinput.parquet` (**136 rows** = 99 unchanged + 37 pieces). The
post-2026-07-12 `(feature, cell)` dedup collapses the pieces back to one feature. **45° not 90°**: a
90° band of the near-global IWC still estimates ~144M cells > the 134M per-feature cell-array limit;
45° halves that to a safe ~72M. The flat `rfb.parquet` stays **105 rows**; the split file is the hex
input only.

## Acceptance — measured on the published `hex/` (all pass)

- rows **2,708,889,616** across **122** h0 partitions (up from the prior 1.57B — the prior build was
  missing CCAMLR and mis-hexed the other 5 seam features).
- `COUNT(DISTINCT OGC_FID)` = **105**; `COUNT(DISTINCT RFB)` = **54**; `COUNT(DISTINCT _cng_fid)` = **105**.
- CCAMLR present: **64,973,149** cells (`WHERE RFB='CCAMLR'`).
- `_cng_fid` in **122/122** partitions, **0** NULL rows.
- **0** duplicate `(h8, _cng_fid)` pairs.
- Single hex filename pattern (`data_0.parquet`) — no stale `data_00.parquet` mix.
- `verify-stac.py --bucket public-high-seas --dataset rfmo`: 0 hard findings, no `values-extra` on `rfb-hex`.
