Overture maps

Derived from Release 2025-07-23.0


```bash
cng-datasets workflow \
  --dataset counties \
  --source-url https://s3-west.nrp-nautilus.io/public-overturemaps/counties.parquet \
  --bucket public-overturemaps \
  --h3-resolution 10 \
  --parent-resolutions "8,9,0" \
  --hex-memory 32Gi \
  --max-completions 200
```