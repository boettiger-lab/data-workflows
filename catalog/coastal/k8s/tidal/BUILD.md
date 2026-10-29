# Tidal marshes and tidal flats: build notes (#792)

Three collections in `public-coastal`: `tidal-marsh-2020` (Worthington et al. 2024, v2.6),
`tidal-flats-v1-2` (Murray et al., 7 periods 1999–2019) and `tidal-flats-v1-1` (the 5 periods
1984–1998, plus the v1.1 mapped-area mask). H3 resolution 8, parent 0.

## Order
1. `stage-raw.yaml`: Zenodo 8420753 and `gs://uq-intertidal` → `s3://public-coastal/raw/`,
   md5-checked against upstream; size, md5, sha256, URL and access time in `raw/MANIFEST.tsv`.
2. `cogs.yaml`: one WGS84 COG per period (14 indexes). Tiles are re-tiled in parallel first: the
   v1.2 and marsh tiles are row-striped, and a single COG pass through a VRT of them read ~7% of
   one period in an hour (`cog-timing-test.yaml`). 0 is kept valid; 255 = outside the tiles.
   Hand-rolled because `preprocess-cog` writes two uncompressed full-grid intermediates
   (datasets#277).
3. `generate-hex.sh` → `hex/<collection>-<period>/`, one generated workflow per COG (`sum`,
   nodata `0,255`, opportunistic per #804). `run-hex.sh` applies the generated hex Jobs one at a
   time; it skips the generated orchestrator, whose `bitnami/kubectl:latest` pull hung for 4 h.
4. Marsh h0 positions 17 and 73 straddle the antimeridian and crawl at the h0 level
   (datasets#295); both re-run at `--chunk-resolution 2` (`hex/tidal-marsh-2020-2020-h0-17`,
   `-h0-73`). h0 17's two runs agreed exactly (1,411 cells, 1,546,551.607 px), but only
   because both had the same bug (see #811 below). h0 73's units all recorded
   `wrote_data = False`; that was the bug too, not an absence of marsh (Tonga has some).
5. `consolidate.yaml`: staging → `<collection>/hex/` with `epoch`, `<eco>_km2`, `<eco>_fraction`.
   Ellipsoidal areas; DuckDB ≥ 2.0 needs `SET geometry_always_xy = true` (checked: a 1×1° box at
   the equator = 12,308.8 km²).
6. `cog-pixel-count.yaml`: exact count of value-1 pixels per tidal-flat COG.

## Measured (2026-10-27)
- **Marsh (after #811):** 52,876.2 km² vs the published 52,880 km². 288,838 cells, 68 h0 partitions,
  fraction 2.3e-11 to 1 (406 cells at 1), no nulls.
- **Hex = COG, every tidal-flat period:** hex `SUM(flat_px)` equals the COG count of 1-pixels
  within 5 pixels (≤ 3e-8); v1.1 periods exactly. So period-to-period swings are in the source
  maps, e.g. v1.2 142,054 km² (2011–2013) → 183,499 km² (2014–2016).
- **Tidal flats, km²:** v1.2 153,791 / 157,671 / 146,533 / 146,227 / 142,054 / 183,499 / 184,453;
  v1.1 70,439 / 103,214 / 113,695 / 94,149 / 99,740. Fraction ranges 3e-14 to 1, no nulls.
- **v1.1 mask:** 14,601,002 km² mapped, 21,290,205 cells.
- No published global tidal-flat total exists for v1.2 (the Scientific Data paper gives none).
- `gs://uq-intertidal/v1_2/` has no mapped-area layer (only `global_intertidal/`,
  `qa_pixel_count/`); `v1_2_v5_masked/` is undocumented and excluded.

## #811 rebuild (2026-10-28)
The marsh COG is georeferenced -170..190, as the producers' tiles are (origin x = -170.00006,
4,007,503 columns). Before datasets#298 the hex step pruned every cell west of -170, so the first
build had no cells between -180 and -170. `hex/tidal-marsh-2020-2020-am/` rebuilt the 14 h0
base cells overlapping that strip with `:latest` (3d8baf1), and `consolidate-marsh.yaml`
rewrote the 7 that hold marsh. Result: 7 new cells, 5 near Adak (51.75-51.90 N) and 2 in
Vava'u, Tonga (18.66 S), 0.3605 km² in total, which is exactly the change in the global total,
so no other partition moved. 14/14 indexes, no pod failures, no old-path log lines.

## Since this build
- datasets#277 (mosaic intermediates) and #272 (bilinear warp) are fixed in cng-datasets 0.11.3:
  use the generator's preprocess-cog for a new tiled ingest; re-tile row-striped tiles first.
- datasets#295 (antimeridian h0) is fixed by datasets PR #298, merged after 0.11.4: no
  `--chunk-resolution` re-run should be needed once a release carries it.
- datasets#299 (merge-chunks on an all-empty h0) is still open. Its h0 73 example was this
  build's frame bug, not a truly empty h0 (corrected on the issue); the synthetic MRE stands.

STAC and README live on S3 only (`public-coastal/<collection>/stac-collection.json`).
