# meow-coastal-band — build notes (#730)

Output: `s3://public-coastal/meow-coastal-band/hex/h0=*/data_0.parquet` (97 partitions). One job:
`band.yaml`, with the script from ConfigMap `meow-coastal-band-script` = `band.py`. It needs the
Copernicus Water Body Mask hex (`catalog/dem/k8s/copernicus-glo90-wbm/`) first.

## Measured column ranges (2026-09-29, final build)

| column | land (15,029,222 cells) | sea (38,300,985 cells) |
|---|---|---|
| `dist_km` | 0 – 20.000 | 0 – 50.000 |
| `k` | 0 – 33 | 0 – 88 |
| `land_frac` | 0.5 – 1 | 0 – <0.5 |
| `depth_m` | NULL (all) | −1,140.0 – 9,032.6; **566,923 negative** (GEBCO ~450 m grid puts the cell partly on land) |
| `elevation_m` | −154.0 – 5,119.4; 79,000 below 0 (real low-lying land); no −9999 sentinel | NULL (all) |

- `label_source`: `polygon` 53,126,708 (incl. 108,756 `on_boundary`), `nearest` 203,499.
- 220 ecoregions present. Absent: 9 Southern Ocean ecoregions (south of ECU's 60.8°S limit), plus Clipperton, Revillagigedos, São Pedro e São Paulo.
- The MEOW hex has exactly one ecoregion per h8 (270,730,948 cells, 0 duplicates), so `on_boundary` is neighbour-based.

## Distance accuracy
- Ring inheritance alone was up to 3.2 km over and clipped ~300k cells at the band edge (first run).
- The final run adds a 5 km expansion margin plus 30 neighbour-relaxation passes (the last still improved 16,161 cells).
- Result: 1,000 / 1,000 random cells equal a brute-force nearest-coast search.
- Per-ring distance varies with location (0.92 km at 50°N, ~0.5 km/ring in the worst direction), and k reaches 100 within 50 km. So the extent is cut on `dist_km`, never on `k`.
