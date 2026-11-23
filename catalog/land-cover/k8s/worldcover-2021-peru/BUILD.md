# ESA WorldCover 2021 (v200), Peru, H3 res 10: build notes (#984)

Collection `public-land-cover/worldcover-2021/peru`: a COG clipped to Peru's land boundary and two
H3 hex tables at native 10 (parents 9, 8, 0), reducers `mode` (`hex/`) and `fractions`
(`hex-fractions/`). Supersede with a global res 10 build if one is made (#439).

## Order
1. `worldcover-2021-peru-stage-raw.yaml`: the 26 WorldCover tiles that intersect Peru, unchanged, to
   `raw/worldcover-2021/map/`, with `raw/worldcover-2021/manifest.tsv` (bytes, sha256, AWS ETag, time).
2. `worldcover-2021-peru-cog.yaml`: VRT window, inverse-rasterize the Overture 2026-02-18.0 Peru land
   polygon to nodata, COG with NEAREST overviews. Gates grid alignment, class codes, and 20,000
   sampled pixels against the source.
3. `mode/` then `fractions/`: generated `raster-workflow` (`--h0-cells 51,69,71,89
   --chunk-resolution 2`, 196 units). `fractions/` renames jobs and output paths (datasets#343).
4. `worldcover-2021-peru-publish-stac.yaml`: STAC, README and parent child link, from a ConfigMap.

## Measured
- Tiles: Byte, 1/12000°, 36,000² per 3° tile, nodata 0, EPSG:4326 on one grid. 26 tiles,
  806,493,731 bytes, downloaded 2026-11-18 18:53–18:56 UTC.
- COG: 152,118 × 219,731 px, origin (-81.3284167, -0.03925), 585,593,794 bytes, sha256
  `6500504414b7de1744bbc83524ba69c9a8502f7e350e706bf00c2842becf2289`. Valid pixels 15,351,274,013
  (~1.30M km², Peru is ~1.285M km²). Class pixels: 10: 9,126,875,322; 30: 3,362,102,836;
  60: 1,820,252,816; 20: 567,315,891; 80: 204,068,547; 40: 192,434,694; 50: 44,933,897;
  70: 16,761,826; 90: 15,763,020; 95: 515,405; 100: 249,759.
- A `gdalwarp -cutline` over the same window wrote ~6 MB/min and passed 10 GiB RSS; the
  translate + `gdal_rasterize -i` path took under 5 min.
- Hex (parquet footers): mode 75,391,934 rows, `lc_class` 10–100, no nulls; fractions 103,454,883
  rows, `lc_class` 0–100 (0 = share outside Peru / no data), `frac` up to 1. Four h0 partitions
  each. Mode units peaked ~5.8 GiB of 16 GiB; one pod hung on image pull and was deleted.

STAC and README live on S3 only.
