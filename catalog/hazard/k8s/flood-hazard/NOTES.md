# flood-hazard (FEMA NFHL) — build pipeline

National FEMA National Flood Hazard Layer flood-hazard zones → `public-hazard/flood-hazard`.
This dataset uses a **custom pipeline** (not the standard orchestrator DAG); apply jobs individually
in order. See data-workflows #253 for full scope/decisions.

| # | Job | Purpose |
|---|---|---|
| 1 | `flood-hazard-setup-bucket.yaml` | bucket + CORS (one-time; `public-hazard` already existed) |
| 2 | `flood-hazard-harvest.yaml` | parse FEMA portal product index → download 2,662 `nfhlv2/output/County/*.zip` → merge `S_FLD_HAZ_AR` → `cng-convert` GeoParquet |
| 3 | `flood-hazard-simplify.yaml` | read merged gpkg → `ST_SimplifyPreserveTopology` ~10 m + WKB-bridge re-encode (strips CRS-tag → MCP-queryable) → `flood-hazard.parquet` |
| 4 | `flood-hazard-clean-utf8.yaml` | pyarrow repair of invalid UTF-8 in DBF-truncated text cols (DuckDB can't read them) → promote to canonical |
| 5 | `flood-hazard-hex.yaml` | H3 res-10 (parents 9,8,0); 198 chunks × 28.5k; chunks carry `fid`+h only |
| 6 | `flood-hazard-repartition-pvc.yaml` | join attrs by `fid` + write `hex/h0=*/data_0.parquet`; DuckDB temp spills to PVC (the stock repartition OOMs on dense h0) |
| 7 | `flood-hazard-pmtiles.yaml` | GeoJSONSeq (PVC) → tippecanoe **`-z13`**, no `--extend-zooms` (it thrashes on dense national tiles), PVC temp + raised fd limit |

Why the deviations (all filed upstream on `boettiger-lab/datasets`):
- stock `convert` (parquet→parquet) OOMs on 51 GiB + tags geom CRS → `stoi` MCP crash (#106) — replaced by `simplify` (WKB bridge).
- no geometry simplification in the tool (#132) — done in `simplify`.
- stock `repartition` has no temp spill → OOM on dense h0 — replaced by `repartition-pvc`.
- `--extend-zooms-if-still-dropping` unbounded (#133); large-vector PMTiles scale (#83).
