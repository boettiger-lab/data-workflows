# global-mangrove-watch-v4-1-12: build notes (#443)

## Order
1. `stage-raw.yaml` and `stage-raw-vec.yaml`: Zenodo 21346457 → `s3://public-wetlands/raw/gmw-v4-1-12/`, md5-checked against Zenodo. SHA-256 per file is in `SHA256SUMS` there, recomputed by `catalog/dem/k8s/copernicus-glo90-wbm/raw-checksums.yaml`.
2. `epoch-cogs.yaml`: 9 per-year COGs from the 41-band tile stack. 0 is kept as valid; 255 marks no tile.
3. `extent-vec-convert.yaml`, then `extent-pmtiles.yaml`; `union/` and `intersect/` convert, then pmtiles.
4. `hex/<YYYY>/…-staging-<YYYY>-hex.yaml`: one year at a time (122 pods each). Output goes to `staging-<YYYY>/hex/`.
5. `hex-consolidate.yaml`: staging → `extent/hex/`. **It reads the staging prefixes.** Do not purge `staging-*` until the final hex is verified. To change the final hex later without re-hexing, rewrite `extent/hex/` from itself.
6. `national-stats.yaml`.

## Measured (2026-09-30, final build)
- **Hex:**
  - 5,732,835 rows, unique per (year, h8), 51 h0 partitions.
  - `mangrove_fraction` range: 1.8e-13 to 1 (53,452 cells exactly 1; clamped from ~1e-9 float excess).
  - `mangrove_km2` range: 1.3e-13 to 0.888. No NULLs, no sentinels.
- **Area invariant, every year:** hex `SUM(mangrove_km2)` equals the vector `ST_Area_Spheroid` sum to 0.1 km². Both are 0.0007% above GMW's uncorrected national total (xlsx / 0.9775). 2025: 150,674.8 km².
- **Vector:** per-year rows equal the upstream GPKG feature counts (10,725,367 total); union 912,641; intersect 1,596,114.
- **Cost:** ~72–89 core-hours and 0.5–1.6 h wall per year at h8. Res 10 is ~5.6 h per h0 per year on 4 CPU (extrapolated from a single-cell test), deferred to boettiger-lab/datasets#251.
