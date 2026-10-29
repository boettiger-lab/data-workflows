# Lumbierres et al. 2021 habitat map and crosswalk: build notes (#427)

Two collections in `public-iucn`: `lumbierres-habitat-2021` (the 100 m IUCN level-1 habitat map,
CC BY 4.0) and `lumbierres-habitat-2021-crosswalk` (IUCN code → map class, licence `other`: the
article is CC BY-NC 4.0 and the table came from the GPL-3 aoh package). Both are linked from the
root catalog, as the bucket's other collections are.

## Order
1. `stage-raw.yaml`: Zenodo 5146073 (`habitat_CGLS.tiff`, `legend.csv`, md5-checked) and aoh
   commit c5d21c1 `data-raw/` CSVs → `s3://public-iucn/raw/lumbierres-habitat-2021/` with
   `MANIFEST.tsv`.
2. `crosswalk.yaml`: `crosswalk.parquet` and `legend.parquet`.
3. `generate.sh` (cng-datasets 0.11.4): `mode/` preprocess-cog → COG, then hex `mode`;
   `fractions/` hex `fractions` from the COG. Applied as Jobs directly (no orchestrator). The
   preprocess job runs at default priority (declared deviation); the hex fan-outs at opportunistic.

## Source facts
- The aoh crosswalk's `value` is this map's legend (20–120), not CGLS-LC100 codes (100 = Forest
  here, moss/lichen in CGLS-LC100). Found by the Wallacea session and checked against the aoh docs.
- The raster: EPSG:4326, -180..180 x -60..80, 0.000992°, Int16, nodata -32768, LZW, row-striped,
  no overviews. COG conversion took 17 min.
- Class 0 occurs (31.0 M mode cells, mostly north of 60 N) but is in neither the legend nor the
  article. Documented as undocumented, not interpreted.
- The aoh CSV lists 5.1 → 80 twice; the parquet keeps one row per (code, class): 158 rows,
  72 codes, 11 classes.
- The producers do not state the CGLS-LC100 year; the STAC temporal extent is open.

## Measured (2026-10-29)
- `mode` hex: 1,256,334,765 rows, 80 h0 partitions, no nulls. `habitat_class` is DOUBLE.
- `fractions` hex: 2,171,566,350 rows, 80 h0 partitions, `frac` in (0, 1]. On h0
  `802fffffffffffff` (15,839,619 cells) every cell's fractions sum to exactly 1 including the
  -32768 row, and the mode class equals the largest fraction in all but 3 cells (ties).
- One hex pod sat in ContainerCreating on `nautilus-it-cpu06.fullerton.edu`; the runner deleted it
  after 5 minutes and the index completed elsewhere.

STAC and README live on S3 only.
