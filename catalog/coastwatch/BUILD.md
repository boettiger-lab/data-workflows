# NOAA CoastWatch Aqua MODIS monthly ocean colour: build notes (#835, #836)

Scope (extent, record, resolution, reducer, naming) is in #835 and #836. This file covers how it is built.

| file | what it is |
|---|---|
| `k8s/erdMH1chlamday/erdmh1chlamday-setup-bucket.yaml` | creates `public-coastwatch` (generated; run once) |
| `k8s/coastwatch-stage.yaml` | stages every month of both products from ERDDAP and writes the COGs (hand-rolled) |
| `k8s/<dataset>/` | `cng-datasets mdim-workflow` output: hex, one pod per month, then merge (generated) |
| `gen_stac.py` | writes the three STAC collections from measured values |

## Order

```bash
kubectl apply -f k8s/erdMH1chlamday/erdmh1chlamday-setup-bucket.yaml     # once
kubectl apply -f k8s/coastwatch-stage.yaml
# when every month of a product is staged (its cog/ holds 230 or 232 files):
kubectl apply -f k8s/<dataset>/workflow-rbac.yaml -f k8s/<dataset>/configmap.yaml -f k8s/<dataset>/workflow.yaml
```

Run the two hex workflows one after the other.

## Staging

ERDDAP serves one month of the global grid (8640 x 4320 Float32) as a 149 MB netCDF3 file in about 13 seconds. The staging job asks for each month separately, using ERDDAP's own time axis as the month list. Each month is kept three ways:

- the netCDF as delivered, gzipped (58 MB), with a `.json` sidecar of request URL, access time, size and SHA-256 of the delivered file;
- a Zarr copy of the array (ZSTD, 54 MB), because GDAL cannot open a netCDF3 file over S3 and ERDDAP offers no other gridded format the hex can read in place;
- the COG, written last, so a month with a COG is finished and is skipped on retry.

The hex from the Zarr copy matched the hex from the delivered netCDF row for row (4,714 of 4,714 cells in base cell 5, 2015-08).

ERDDAP's metadata reports processing version 2018.1QL for both products. The "R2022" in the first draft of the scope was not confirmed and has been removed from the issues.

## Hex

`cng-datasets mdim-workflow --fan-out time` makes one pod per month input. One global month took about 4 minutes and wrote 8.1 million resolution 6 cells (chlorophyll, 2003-01). The pods used 0.1 CPU and at most 0.8 GiB while running, measured on the chlorophyll run at the generator's default 4 CPU and 16Gi. The Kd490 workflow was generated with `--hex-cpu 1 --hex-memory 4Gi` to match.

## Runs on 2026-11-03

| dataset | months | hex rows | hex and merge |
|---|---|---|---|
| `erdMH1chlamday` | 230, 2003-01 to 2022-03 | 1,838,591,353 | 83 minutes |
| `erdMH1kd490mday` | 232, 2003-01 to 2022-05 | 1,852,978,397 | 85 minutes |

Staging both products took 75 minutes. Every hex index succeeded on its first pass, and each table has exactly one row per cell and month, with no NaN.
