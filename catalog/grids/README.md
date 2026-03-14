# public-grids — H3 Reference Grid Infrastructure

This bucket contains **H3 reference grid parquet files** used internally by the
[`cng-datasets`](https://github.com/boettiger-lab/datasets) raster hex workflow.

## What's here

These are pre-computed lookup tables mapping H3 cell hierarchies (child→parent
relationships) used during raster-to-hex tiling. They are not a published
geospatial dataset — they are infrastructure consumed by the processing pipeline.

## Not a dataset

`public-grids` does **not** follow the standard dataset layout
(parquet + pmtiles + hex + STAC). It is intentionally excluded from the
main STAC catalog and audit reports.

## Future use

Additional reference grids (e.g. other resolutions, other grid systems) may be
added here as the pipeline evolves.
