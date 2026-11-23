# PacIOOS model and Ocean Tipping Points builds

Three PacIOOS-hosted products for the Main Hawaiian Islands, built into `public-hawaii`.
Scope is recorded in issues #840 (ROMS), #841 (WaveWatch III) and #851 (Ocean Tipping Points).

## ROMS reanalysis and WaveWatch III

Source: PacIOOS ERDDAP `roms_hiig_reanalysis` and `ww3_hawaii`.

1. `kubectl apply -n geo-workflows -f k8s/pacioos-daily-configmap.yaml -f k8s/pacioos-models-stage.yaml`
   stages one calendar month per index (`stage.sh`, `daily.py`): the netCDF as delivered, a daily
   zarr cube, one COG per variable and day, and a `.days.json` marker uploaded last.
   `pacioos-daily-configmap.yaml` is made from `daily.py` and `stage.sh` (header has the command).
2. Check every month landed before hexing. List files only, or the zarr folders double the count:
   `rclone lsf --files-only nrp:public-hawaii/raw/<ds>/zarr/ --include '*.days.json' | wc -l`
   (144 for ROMS, 175 for WW3).
3. `kubectl apply -n geo-workflows -f k8s/<ds>/workflow-rbac.yaml -f k8s/<ds>/configmap.yaml -f k8s/<ds>/workflow.yaml`
   runs the generated `cng-datasets mdim-workflow` hex at resolution 6.
4. `gen_stac_models.py <stats.json> <out>` writes both collections from measured stats (see its docstring).

Measured on 2026-11-04:

| | ROMS | WW3 |
|---|---|---|
| days | 4380 (2009-01-01 to 2020-12-28) | 5250 (2011-06-21 to 2025-12-31) |
| days missing upstream | 0 | 58 (no steps on ERDDAP's time axis) |
| partial days | 0 | 19 |
| hex rows | 96,395,040 (22,008 cells, every day) | 48,107,375 (9,163–9,180 cells a day) |
| duplicate cell-days | 0 | 0 |

WW3 swell and wind-wave columns are empty on cell-days where the model has no such component at
any hour (0.8% and 14% of cell-days). ERDDAP serves these as NaN, as checked for 21.45 N,
201.75 E on 2020-06-15. Total-sea direction is empty only where total height is zero all day.

## Ocean Tipping Points

Source: PacIOOS GeoServer WCS, the 43 `hi_otp_all_*` layers in `ocean-tipping-points/layers.txt`.

1. `kubectl apply -n geo-workflows -f k8s/ocean-tipping-points/otp-stage-configmap.yaml -f k8s/ocean-tipping-points/ocean-tipping-points-stage.yaml`
   runs `ocean-tipping-points/stage.py` per layer. It requests the native grid from
   DescribeCoverage (origin, offset vectors and grid limits, not the envelope, which is wider than
   the grid for some layers), checks the delivered size and geotransform, assigns EPSG:4326 (WCS
   delivers no CRS) and writes the raw GeoTIFF, a provenance `.json` and the COG.
   PacIOOS GeoServer needs `curl --ciphers DEFAULT@SECLEVEL=1`.
2. One generated `cng-datasets raster-workflow` per layer in `k8s/ocean-tipping-points/<short>/`,
   run one at a time: resolution 10 for the 16 layers on the ~100 m grid, 9 for the 27 on the
   ~500 m grid, parents 8 and 0, mean, `--h0-cells 35,46`.
3. `ocean-tipping-points/gen_stac.py` writes the parent and 43 leaf collections.

All 43 hex tables were checked on 2026-11-04: one row per cell, no NaN, and every layer's range
inside its source raster's range. The presence layers (`coastal_mod`, `invasive_algae`,
`invasive_fish`) have fractional means where a cell averages present and absent pixels.
