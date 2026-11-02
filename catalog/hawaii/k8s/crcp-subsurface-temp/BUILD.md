# crcp-subsurface-temp (#817)

NOAA NCRMP subsurface temperature recorders, Hawaiian Islands, from NCEI ERDDAP
`CRCP_Subsurface_Temp_Hawaii`, accessed 2026-11-02.

## Order

1. `crcp-subsurface-temp-stage-raw.yaml`: per-site ERDDAP pull to `s3://public-hawaii/raw/crcp-subsurface-temp/`
   (145 files, 2,597,090,082 bytes; `MANIFEST.sha256` sha256 88355806aca4a2b83f10e529f41b7af881626b41d35a037a9cd8ec9a4bba1f5b).
   A time-sliced pull runs ~1 minute per day of record; a per-site pull is ~30 s per site.
2. `crcp-subsurface-temp-build.yaml`: observations, deployments, and the sites input.
3. `workflow.yaml` (generated): PMTiles + res-8 hex of sites.
4. `gen_stac.py`: STAC + README (`STAC_OUT=/tmp/x python3 gen_stac.py`), then `verify-stac.py`.

## Measured (2026-11-02)

| | |
|---|---|
| upstream rows | 136,474,266 |
| distinct readings | 88,808,469 (47,665,797 repeats dropped) |
| deployments | 308 (one per INSTFIELDSUMMARYID) |
| sites | 145, in 109 res-8 cells; 1–5 deployments each |
| TEMP_C | 16.0–32.9 °C, no nulls, no sentinels |
| DEPTH_M | 0.3–38.6 m; varies by up to 3.5 m within a site across deployments |
| time | 2005-03-02T21:30Z – 2024-08-25T19:59:59Z |

## Upstream quirks

- About a third of upstream rows are exact repeats.
- Deployments 2306–2309 and 2311 (Hawaiʻi Island, 2016–2019) are served twice. The second copy went
  through a spreadsheet: INSTRUMENTSN in scientific notation (`5.69066E+11`), RETRIEVE_UTC and
  TIMESTAMP truncated to the minute (1,000,000 readings). Readings are deduplicated without the
  deployment fields; deployment metadata takes the full-precision values.
- REGION is spelled two ways per region (`MHI` / `Main Hawaiian Islands`, `NWHI` /
  `Northwestern Hawaiian Islands`).
- 344 readings share site, depth and time across two deployments with different temperatures
  (overlapping instruments); both kept.
- Site grain is one row per OCC_SITEID (scope changed in #817): DEPTH_M is re-measured per deployment.
