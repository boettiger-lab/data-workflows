# Seafloor organic carbon flux (NEMO-MEDUSA) build notes

Issue: data-workflows #642. Source: Zenodo 6513616, version 1.0, accessed 2026-08-29.
Published to `s3://public-high-seas/seafloor-carbon-flux/{avg,min,max}/`.

## Order of operations

```bash
kubectl apply -n geo-workflows -f seafloor-carbon-flux-stage-raw.yaml       # download + stage + inspect grid
kubectl apply -n geo-workflows -f seafloor-carbon-flux-netcdf-to-cog.yaml   # 3 variables -> 3 WGS84 COGs
for n in avg min max; do                                                    # one at a time
  kubectl apply -n geo-workflows -f $n/configmap.yaml -f $n/workflow.yaml
  kubectl wait -n geo-workflows job/seafloor-carbon-flux-$n-workflow --for=condition=complete --timeout=5400s
done
python3 gen-stac.py && rclone copyto /tmp/scf-<k>-stac-collection.json nrp:...   # see gen-stac.py
```

## What the source actually is

`ncdump -h` declares no `_FillValue` and the file has only **2D** `nav_lon`/`nav_lat`, no 1D
coordinate variables and no CF grid mapping. Consequences, all measured by the stage-raw job rather
than assumed:

- GDAL reads each variable as an ungeoreferenced 4320x2160 array (identity geotransform). The
  geotransform is derived from `nav_lon`/`nav_lat` in the COG job and asserted: 1/12 degree spacing,
  cell centres, latitude already descending, corners at -180/+90.
- Land is the netCDF default fill `9.969209968386869e+36`, which GDAL does report as the band
  nodata. It is **not** 0. Left unfolded it would have dominated every hex mean.
- Valid ocean cells: 6,102,331 of 9,331,200 pixels (65.4%), identical across the three variables.

## Hex resolution

Native **6**, parents **5,0**. A 1/12 degree cell is about 86 km2 at the equator and 43 km2 at 60
degrees; an h6 cell is 36 km2. Auto-detection would have chosen h4 (the tool targets ~3x the pixel
width); h6 was passed explicitly. There is no `h8`, which is the sanctioned coarse-raster case.

## Measured values

Reducer `mean` for all three: the value is a rate per unit area, not an amount per pixel.

| Layer | COG min / max / mean | Hex min / max / mean | Hex cells | h0 partitions |
|---|---|---|---|---|
| `avg` | 5.33e-33 / 113.047 / 0.913 | 5.33e-33 / 110.071 / 0.935 | 10,085,050 | 117 |
| `min` | 1.26e-38 / 74.512 / 0.205 | 1.26e-38 / 72.913 / 0.268 | 10,085,050 | 117 |
| `max` | 5.85e-32 / 166.513 / 2.386 | 5.85e-32 / 163.108 / 2.225 | 10,085,050 | 117 |

Checks that passed: `flux_min <= flux_avg <= flux_max` on all 10,085,050 cells joined on `h6`; the
dateline h0 `576707042908045311` spans -179.99997 to 179.99965; the 5 h0 cells absent against the
GEBCO reference set are centred on the Amazon basin, Sudan, the central US, Kazakhstan and Mongolia;
the hex cell at 100E/40S reads 0.4156 against 0.4107 for the COG pixel at the same point.

## Known tool divergence

`cng-datasets raster-workflow` flattens a hierarchical `--dataset a/b` into `a-b` for the **S3**
output path (`k8s_name` is reused for paths in `workflows.py`), unlike `workflow` for vectors, which
keeps `a/b`. The generated `--output-parquet` was edited from
`s3://public-high-seas/seafloor-carbon-flux-avg/hex/` to
`s3://public-high-seas/seafloor-carbon-flux/avg/hex/` in each hex manifest and configmap. Reported
upstream; re-apply the edit if these manifests are regenerated.
