# WOA23 build record (data-workflows #643)

Bucket `public-high-seas`, prefix `woa23/`. 8 variables x 3 depths = 24 layers, each a COG plus H3
hex at native resolution 3, parents `[0]`, reducer `mean`.

Run 2026-08-29 in namespace `geo-workflows`:

| Job | Completions | Duration |
|---|---|---|
| `woa23-stage-raw` | 8 | 98s |
| `woa23-netcdf-to-cog` | 8 (3 COGs each) | 18s |
| `woa23-hex` | 24 | 10m |

## Why one indexed job per stage instead of per-layer `raster-workflow`

`cng-datasets raster` processes all 122 h0 regions when `--h0-index` is omitted. At native resolution 3
a layer is only ~30k cells over a 180x360 source grid, so the standard 122-completions-per-layer
fan-out would be ~2,900 pods of scheduling overhead for seconds of real work. Same tool, same
command, same output layout, 24 pods instead.

One index landed on a slow node (24 workers rather than 48) and was at h0 23 of 122 after 8 minutes
against ~2 minutes elsewhere. A graceful pod deletion, with no force flags, let the Job reschedule the
index on a healthy node, where it finished normally. Forced pod removal is never the fix here; the
control plane reaps the pod on its own.

`rclone hashsum sha256` needs `--download`: Ceph RGW does not serve sha256 server-side.

## Depth to GDAL band, verified per file

The build resolves each depth by reading each band's `NETCDF_DIM_depth` metadata rather than trusting
an index, because an off-by-one would publish 5 m data labelled as the surface and no structural check
downstream would catch it. Identical across all 8 variables:

```
0 m -> band 1     200 m -> band 25     1000 m -> band 47
```

Other gates in `scripts/woa23_netcdf_to_cog.py`, all 24 passing: north-up geotransform exactly
`(-180, 1, 0, 90, 0, -1)`; an orientation probe asserting inland Asia (100E, 40N) is nodata while the
open Indian Ocean (100E, 40S) is valid, which no symmetric check can see; and a per-variable physical
plausibility bound, which doubles as the fill-leak detector for WOA's `9.96921e+36`.

## Measured ranges

Hex values, all 24 layers. `min`/`max` are inside the corresponding COG range for every layer, as an
area-weighted mean must be. `p2`/`p98` are the app rescale bounds.

| Layer | cells | h0 parts | min | max | mean | p2 | p98 |
|---|---|---|---|---|---|---|---|
| temperature-0m | 30211 | 117 | -1.847 | 30.559 | 18.293 | -1.456 | 29.393 |
| temperature-200m | 28756 | 116 | -2.031 | 22.855 | 11.815 | -0.479 | 21.398 |
| temperature-1000m | 27552 | 114 | -2.012 | 21.754 | 4.286 | -0.042 | 8.831 |
| salinity-0m | 30211 | 117 | 5.0 | 40.137 | 34.487 | 29.746 | 37.074 |
| salinity-200m | 28756 | 116 | 12.359 | 40.531 | 34.971 | 33.729 | 36.754 |
| salinity-1000m | 27552 | 114 | 22.262 | 40.794 | 34.61 | 34.287 | 35.422 |
| oxygen-0m | 30211 | 117 | 181.12 | 433.034 | 245.536 | 194.215 | 362.68 |
| oxygen-200m | 28756 | 116 | 0.634 | 381.166 | 180.921 | 10.77 | 300.534 |
| oxygen-1000m | 27552 | 114 | 0.31 | 318.274 | 138.558 | 15.091 | 292.443 |
| oxygen-saturation-0m | 30211 | 117 | 78.019 | 121.539 | 100.587 | 90.94 | 104.163 |
| oxygen-saturation-200m | 28756 | 116 | 0.256 | 103.592 | 66.278 | 3.094 | 95.104 |
| oxygen-saturation-1000m | 27552 | 114 | 0.326 | 91.793 | 43.405 | 4.41 | 85.772 |
| aou-0m | 30211 | 117 | -8.0 | 78.539 | 0.484 | -6.199 | 33.413 |
| aou-200m | 28756 | 116 | -2.825 | 329.945 | 90.512 | 13.597 | 251.936 |
| aou-1000m | 27552 | 114 | 26.403 | 313.312 | 178.116 | 49.144 | 306.757 |
| silicate-0m | 30211 | 117 | 0.265 | 94.088 | 7.437 | 0.725 | 57.728 |
| silicate-200m | 28756 | 116 | 0.444 | 116.529 | 18.391 | 0.932 | 87.195 |
| silicate-1000m | 27552 | 114 | 4.74 | 262.928 | 66.575 | 8.547 | 143.53 |
| phosphate-0m | 30211 | 117 | 0.015 | 2.452 | 0.515 | 0.039 | 1.816 |
| phosphate-200m | 28756 | 116 | 0.04 | 5.177 | 1.213 | 0.162 | 2.527 |
| phosphate-1000m | 27552 | 114 | 0.145 | 8.261 | 2.367 | 0.932 | 3.229 |
| nitrate-0m | 30211 | 117 | 0.0 | 33.459 | 5.055 | 0.038 | 25.964 |
| nitrate-200m | 28756 | 116 | 0.0 | 42.225 | 15.891 | 1.674 | 33.155 |
| nitrate-1000m | 27552 | 114 | 0.0 | 46.506 | 33.339 | 13.297 | 44.094 |

No sentinel values survive: 0 NULL and 0 NaN on every layer. Every layer has `COUNT(*)` equal to
`COUNT(DISTINCT h3)`, so there is no per-cell duplication. Dateline h0 `576707042908045311` is present
on all 24, spanning -179.85 to 179.77.

Hex `mean` differs from the COG pixel mean by design: H3 cells are near equal-area, so the hex mean is
an area-weighted global mean, while a pixel mean over-weights the small high-latitude 1-degree cells.
Surface temperature is the clearest case, hex 18.293 against COG 14.018.

Physical cross-checks that the plumbing cannot fake: surface oxygen saturation means 100.587 percent,
AOU rises from 0.484 at the surface to 178.116 at 1000 m, and nitrate, phosphate and silicate all rise
monotonically with depth.

## Provenance

Staged to `s3://public-high-seas/raw/woa23/`, access date 2026-08-29. Sizes match upstream
`Content-Length` exactly; sha256 recomputed from the staged S3 objects. Checksums are recorded in each
layer's STAC collection description; the full table is in the issue.
