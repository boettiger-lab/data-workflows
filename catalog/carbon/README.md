# Conservation International — Irrecoverable Carbon

Workflows that convert Conservation International's carbon rasters (irrecoverable / vulnerable / manageable carbon) into globally H3-partitioned hex parquet on `public-carbon`.

## Current dataset: v2 (2025 release)

The catalog serves the **v2 (2025)** Conservation International release (Zenodo 17645053). The
processing recipes, canonical S3 layout, and validation live in **[`k8s/v2/`](k8s/v2/README.md)** —
start there. In brief:

- **Source COGs:** `public-carbon/v2/cogs/{category}_c_total_{year}.tif` — carbon **density**, Mg C ha⁻¹, ~300 m.
- **Hex (canonical):** `public-carbon/{dataset}/hex/h0=*/data_0.parquet` — **H3 resolution 9**, `carbon` = total Mg C per cell (density area-integrated). `SUM(carbon)` is a valid total.
- **Products:** irrecoverable {2018, 2022, 2023, 2024}; vulnerable & manageable {2010, 2018, 2024}.
- **Validation (#330):** hex matches an independent full-resolution COG area-integral to +0.22%; totals run ~2–3% above CI's committed-loss headline figures. See `k8s/v2/validate-cog-integral.yaml`.

The earlier **v1 (2021)** build and its bucket cruft (`irrecoverable-carbon/hex/`, the `v2/` hex
copies, `hex-h9-sum/`, `hex/us-*`, `v2/raw/`) were **retired/purged in #330**. The reducer
correction from `sum`-on-density to area-integral is #202.

Dataset-facing documentation (field descriptions, usage) is the STAC + README on S3
(`public-carbon/stac-collection.json`, `public-carbon/README.md`), not this repo.
