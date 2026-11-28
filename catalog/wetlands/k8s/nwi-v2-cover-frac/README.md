# NWI hex with cover_frac (#1082)

Re-hexes the existing NWI conversion (`s3://public-wetlands/nwi-v2.parquet`, 38,065,251 features)
with `--polyfill overlap`: every resolution-10 cell a wetland touches, with `cover_frac`, the share
of the cell inside the feature. The flat GeoParquet and PMTiles are unchanged, so only the hex
steps are kept. It builds under the unlinked prefix `nwi-cover-frac/` (staged while publishes
were frozen) and is then copied over `nwi-v2/hex/`.

Generated with (then the two DEVIATION edits named in the manifests):

    cng-datasets workflow --dataset nwi-cover-frac --source-url s3://public-wetlands/nwi-v2.parquet \
      --bucket public-wetlands --h3-resolution 10 --parent-resolutions "9,8,0" --polyfill overlap \
      --chunk-size 5000 --max-completions 7614 --max-parallelism 80 --hex-memory 48Gi \
      --hex-storage 20Gi --hex-retries 3 --priority-class opportunistic --namespace geo-workflows

Stage, each after the previous completes:

    kubectl apply -n geo-workflows -f configmap.yaml -f nwi-cover-frac-hex.yaml
    kubectl apply -n geo-workflows -f nwi-cover-frac-repartition.yaml

Publish (after the all-clear and a check of the staged hex): copy `nwi-cover-frac/hex/` over
`nwi-v2/hex/`, run `catalog/wetlands/k8s/nwi-v2/nwi-v2-checksums` equivalent, update the
`wetlands-nwi` STAC (`cover_frac` column, hex asset text), then delete `nwi-cover-frac/`.
