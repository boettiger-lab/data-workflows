# ETH global canopy height 2020: build notes (#440)

One collection, `public-land-cover/canopy-height-2020`: the producers' 3° COG tiles for height and
its standard deviation, published unchanged, one VRT per layer, and an H3 hex per layer (native 9,
parents 8 and 0, `mean`). Carl chose tiles + VRT over a single ~1 TB mosaic, Peru first, 16 download
streams (#440).

## Order
1. `stage-tiles.yaml` (+ `tiles-configmap.yaml`, applied server-side because it is large):
   16 pods, one stream each, `tiles-peru` (76 files) then `tiles-rest` (5,226). Resumable: a tile
   already on S3 is skipped. Per-shard manifests in `raw/canopy-height-2020/manifest/`.
   `manifest-backfill.yaml` adds the one row lost to a preemption (N36W102 height).
2. `build-vrt.yaml`: VRTs with paths relative to the VRT (open over https and /vsis3).
3. `generate-peru.sh` → `peru/`: interim Peru hex (base cells 51, 69, 71, 89) for Wallacea.
4. `generate.sh` → `global/`, run by `run-global.sh` (idempotent): 5,882 res-2 units per layer,
   k8s at 190 pods (not the auto-picked Armada, which drops per-index retries), then merge.

## Measured
- Staging: 2,651 + 2,651 tiles, 375.7 + 317.2 GB, 2026-10-29 19:25–22:43 UTC (~4 h at 16 streams,
  ~1.5 MB/s per stream). ETH publishes no checksums; each tile was checked by GDAL on download.
- Tiles: Byte, 1/12000°, 36,000² per 3° tile, nodata 255 (built-up, snow, ice, permanent water per
  the paper), overviews present. Global VRT 4,320,000 × 1,728,000, 180 W–180 E, 60 S–84 N.
- Hex: height and SD each 1,225,487,233 cells in 96 h0 partitions, identical cell sets, no nulls.
  Height 0–159.2 m, mean 8.2; 114 cells ≥ 60 m, the top one on Greenland's north coast where the
  source pixel reads 191 m (upstream artefact). SD 0–254 (whole metres, saturates at 254), mean 4.0.
- Runtime: height hex 00:05–22:40 UTC Oct 30, SD 23:14 Oct 30–16:43 Oct 31. Median ~14 min per
  unit: the 360° VRT puts every unit through the antimeridian wrap, 2.7× slower than a regional VRT
  on the same chunk (213 s vs 573 s, `diag-vrt-timing*.yaml`; datasets#313). 39 pods stuck in
  ContainerCreating on bad nodes were deleted by the runner.

STAC and README live on S3 only.
