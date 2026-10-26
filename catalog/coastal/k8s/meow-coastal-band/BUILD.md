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

# Polygons + PMTiles display layer (#774)

Outputs: `s3://public-coastal/meow-coastal-band.parquet` (GeoParquet) and `s3://public-coastal/meow-coastal-band.pmtiles`.
Both are written by one job, `dissolve.yaml`, with `dissolve.py` + `tilecheck.py` from ConfigMap
`meow-coastal-band-dissolve-script`. The input is the hex above, which this job leaves unchanged. It takes about 15 min on 16 CPU / 64Gi.

## Design
- **Features.** One multipolygon per `ECO_CODE` × `side` × distance class: 1,462 features over 220 ecoregions.
  - sea classes: 0–5, 5–10, 10–20 and 20–50 km (219 features each)
  - land classes: 0–5 (217), 5–10 (191) and 10–20 km (178)
- **Bin edges.** Upper-inclusive: `(dmin, dmax]`, and the first class also takes `dist_km = 0`.
  - So `dist_max_km <= X` on the tiles selects exactly the hex cells with `dist_km <= X`.
  - Classes are disjoint, and every hex cell falls in exactly one class.
- **Geometry.** An exact cell-set → polygon conversion per group with `h3.cells_to_h3shape` (h3-py 4.5.0), not a union of hexagons.
  - Neighbouring features therefore share identical H3 edge vertices.
  - 48 polygons cross the antimeridian. They are unwrapped, split at ±180, then oriented with counter-clockwise exteriors. The split from `intersection()` returns clockwise exteriors, which made geodesic area checks read as low as 0.2 before reorienting.
- **`area_km2`.** `SUM(h3_cell_area(h8,'km^2'))` from the DuckDB h3 extension. Features do not overlap, so it can be summed.
- **GeoParquet.** Written by DuckDB (`ST_GeomFromWKB`), ZSTD, row groups of 50. `_cng_fid` = feature row id.
- **Tippecanoe** (2.79):
  ```
  -Z0 -z10 --low-detail=14 --detect-shared-borders --no-simplification-of-shared-nodes
  --no-feature-limit --no-tile-size-limit --no-tiny-polygon-reduction
  ```
  - There is no drop or coalesce step. Coalescing would merge features with different attributes.
  - `TIPPECANOE_MAX_THREADS=16`, the container limit. Using `os.cpu_count()` (the node's cores, rounded to a power of 2) aborts with "745 shards not a power of 2" on a large node. Reproduced locally: 16 and 128 work, 256 fails.

## Measured (job log, final run)
- **Cell counts.** 53,330,207 cells in, 1,462 features out. The largest group is Sunda Shelf/Java Sea, sea 20–50 km: 399,690 cells. Every polygon is valid.
- **Area reconciliation.** For all 437 ecoregion × side pairs, the summed `area_km2` matches the hex cell-area sum to within 1.4e-14 (relative).
- **Geodesic area.** Polygon area (WGS84, pyproj) divided by the H3 cell-area sum ranges from 0.9955 to 1.0086, median 0.998. Polygon edges are straight in longitude/latitude, while H3 uses an authalic sphere.
- **Tile sizes** (gzip). The PMTiles is 178 MB.

  | zoom | max | mean |
  |---|---|---|
  | z0 | 1.32 MB | — |
  | z1 | 1.17 MB | — |
  | z2 | 0.84 MB | — |
  | z4 | 0.42 MB | — |
  | z10 | < 10 KB | ~1 KB |
- **Features present per zoom.**
  - z0: 1,451 of 1,462
  - z1: 1,458 of 1,462
  - z2 to z10: all
  - The few missing at z0–z1 are made only of tiny island cells.
- **Gap check** (`tilecheck.py`): 3×3 tile blocks around Lofoten, Sulawesi and Fiji (antimeridian) at z0/2/4/6/8/10.
  - Method: union the tile's features in pixel space, then classify each hole of the union by sampling points against the source h8 set. If the band is continuous there, the hole is a gap; otherwise it is a real hole.
  - z4–z10: 0 gaps in every checked tile.
  - z2: at most 0.008 px² of sub-pixel holes per tile.
  - z0: 0.19 px² across the whole globe.
  - With tippecanoe's default tiny-polygon reduction these figures were 0.11 px² per z2 tile and 1.28 px² at z0, with tile sizes unchanged.
  - Without `--detect-shared-borders` (synthetic test), slivers appear at every low zoom and a third of the features drop at z0.
