# BLM National Surface Management Agency (SMA): build notes

Issue: boettiger-lab/data-workflows#561 (scope is recorded there).

## Source

- ArcGIS item `6bf2e737c59d4111be92420ee5ab0b46` (owner `blm_arcgis_hub_natl`), "BLM National SMA
  Surface Management Agency Area Polygons", File Geodatabase. Item last modified 2026-06-30; no
  edition label published.
- Download `https://www.arcgis.com/sharing/rest/content/items/6bf2e737c59d4111be92420ee5ab0b46/data`
  → `SMA_WM.gdb.zip`, accessed 2026-10-10.
- Staged: `s3://public-blm/raw/SMA_WM.gdb.zip`, 1,113,064,445 bytes,
  sha256 `aede58f2d7084a77e129e090d85b9f62f8c29d9f6a526a49fe53e1de9a6e1b31`.
- `SMA_WM.gdb` holds 14 layers, EPSG:3857. `SurfaceManagementAgency` (464,680 features) is the
  union of the 13 per-agency layers (`SurfaceMgtAgy_DOD` 877, `_BLM` 11,472, `_NPS` 13,657,
  `_USFS` 21,230, `_FWS` 27,958, `_BOR` 18, `_BIA` 600, `_OTHFED` 489, `_STATE` 72,702,
  `_LOCAL` 7,090, `_PRIUNK` 242,263, `_NTVALL` 11,304, `_NTVPIC` 55,020; sum 464,680). Only the
  combined layer is converted. (The retired `public-wyoming/blm-sma` build merged the per-agency
  layers with the combined one; its `ADMIN_ST='WY'` rows are exactly double this file's per agency.)

## Measured on the converted GeoParquet (duckdb-geo MCP, 2026-10-10)

- 464,680 rows, `_cng_fid` 1..464,680 unique, 0 null geometry, 0 invalid; 463,845 MULTIPOLYGON +
  835 POLYGON. bbox lon -179.149 to 179.775, lat 24.396 to 71.387.
- **Footprint is conterminous US + Alaska only.** BLM's item description lists Hawaii, PR, Guam,
  American Samoa and USVI; none are present (min latitude 24.4).
- **Two grains.** `ADMIN_ST='AK'`: 463,556 polygons (`_cng_fid` 1125..464680), 1.52 M km².
  Lower 48: 1,124 dissolved multipolygons (`_cng_fid` 1..1124), 8.10 M km², up to 2.43 M vertices
  and 3.05 M km² (ES `UND`) in a single row.
- `ADMIN_ST` (BLM state office): AK 463,556; ES 520; CA 304; AZ 102; MT 43; WY 43; NM 27; NV 25;
  OR 20; ID 18; CO 11; UT 11.
- `ADMIN_AGENCY_CODE` counts: UND 219,917; ST 72,702; NTVPIC 55,020; FWS 27,958; PVT 22,346;
  USFS 21,230; NPS 13,657; BLM 11,471; NTVALL 11,304; LG 7,090; BIA 600; ARMY 529; USAF 241;
  USCG 185; OTHFE 131; FAA 78; USACE 51; NAVY 30; NOAA 27; USPS 27; USBR 18; DOD 17; GSA 11;
  USMC 9; DOT 9; USDA 7; DOE 7; HHS 3; FHA 1; BOP 1; DOI 1; VA 1; BPA 1.
  The app-required codes BLM/USFS/NPS/FWS/USBR/DOD/ST/PVT are present verbatim.
- `HOLD_*` and `HOLD_ID` populated on the same 338 rows. `ADMIN_UNIT_NAME` null on 269,685,
  `ADMIN_UNIT_TYPE` null on 192,654 (76 distinct non-null values, incl. literal 'None' and
  'Not Applicable'). No leading/trailing whitespace in either.
- `SHAPE_Area` is Web Mercator m² carried from the GDB: median ratio to
  `ST_Area_Spheroid` is 4.19 in AK, ~1.5 in CA/ES (2,000-row sample).

## Code definitions

The GDB carries no field domains, and the FGDC metadata's `ADMIN_AGENCY_CODE` domain is an older
list (FS, BOR, AF …) that does not match the data. Definitions come from BLM's SMA data-standard
domains `SMA_DOM_ADMIN_AGENCY_CODE` / `SMA_DOM_ADMIN_DEPT_CODE` as served by
`https://gis.blm.gov/azarcgis/rest/services/lands/BLM_AZ_SMA/FeatureServer` (layer fields,
read 2026-10-10); every code present in the data is defined there.

## Pipeline (all manifests in this directory)

1. `surface-management-agency-stage-raw.yaml` (hand-rolled, k8s) → raw zip to NRP.
2. `surface-management-agency-convert.yaml` (k8s) → GeoParquet, row-group-size 2000,
   `--expect-features 464680`.
3. `surface-management-agency-pmtiles.yaml` (k8s).
4. `surface-management-agency-plan.yaml` (k8s) → `_hex_plan.parquet`, 1 M estimated cells per
   chunk, `--max-chunks 480`. Result: **473 chunks**, 13,450,428 estimated cells, largest chunk
   4,136,388 cells (one feature on its own; 2 features exceed the budget alone). A fixed
   chunk size would have put all 1,124 lower-48 giants into the first two chunks.
5. `armada-surface-management-agency-hex.yaml` (Armada, 480 jobs; indexes 473..479 exit cleanly)
   at H3 resolution 8, parents 0, 8Gi each.
6. `surface-management-agency-repartition.yaml` (k8s) → `hex/h0=*/data_0.parquet`.

Acceptance: hex `COUNT(DISTINCT _cng_fid)` must equal 464,680. STAC is written by `gen-stac.py`
(to /tmp, never this repo).
