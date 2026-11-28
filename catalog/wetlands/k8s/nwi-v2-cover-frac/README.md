# NWI hex with cover_frac (#1082)

Re-hexes the existing NWI conversion (`s3://public-wetlands/nwi-v2.parquet`, 38,065,251 features)
with `--polyfill overlap`: every resolution-10 cell a wetland touches, with `cover_frac`, the share
of the cell inside the feature. The flat GeoParquet and PMTiles are not rebuilt, so only the hex
steps of the generated workflow are kept here. The output replaces `nwi-v2/hex/` in place.

Generated with:

    cng-datasets workflow --dataset nwi-v2 --source-url s3://public-wetlands/nwi-v2.parquet \
      --bucket public-wetlands --h3-resolution 10 --parent-resolutions "9,8,0" --polyfill overlap \
      --chunk-size 5000 --max-completions 7614 --max-parallelism 80 --hex-memory 48Gi \
      --hex-storage 20Gi --hex-retries 3 --priority-class opportunistic --namespace geo-workflows

Apply in order, each after the previous completes:

    kubectl apply -n geo-workflows -f configmap.yaml -f nwi-v2-hex.yaml
    kubectl apply -n geo-workflows -f nwi-v2-repartition.yaml
    kubectl apply -n geo-workflows -f nwi-v2-checksums.yaml

Then update the `wetlands-nwi` STAC: `cover_frac` column, hex asset text, and the
presence-only wording replaced.
