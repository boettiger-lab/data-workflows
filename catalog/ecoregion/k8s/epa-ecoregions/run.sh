#!/usr/bin/env bash
# EPA Omernik ecoregions Level III (CONUS+AK) + Level IV (CONUS) — data-workflows #633.
#
# Level III merges two EPA products that ship in different projections with different
# attribute schemas, so conversion happens in the preprocess jobs (Step 1c) rather than in
# the generated workflow — the generated workflow.yaml therefore has NO convert step.
#
# Run from the repo root.  Everything targets the geo-workflows namespace.
set -euo pipefail
NS=geo-workflows
HERE=catalog/ecoregion/k8s/epa-ecoregions

# --- Step 1b/1c: stage the three source archives, then merge + reproject + convert ------
kubectl apply -n $NS -f $HERE/stage-raw.yaml
kubectl wait -n $NS --for=condition=complete --timeout=1800s job/epa-ecoregions-stage-raw

kubectl apply -n $NS -f $HERE/preprocess-l3.yaml -f $HERE/preprocess-l4.yaml
for d in l3 l4; do
  kubectl wait -n $NS --for=condition=complete --timeout=3600s job/epa-ecoregions-$d-preprocess
done

# --- Steps 2-4: PMTiles + hex + repartition, one dataset at a time ---------------------
# Sequential on purpose: a single hex job can take 50 pods, and AGENTS.md caps us at ~200
# namespace-wide as good practice on shared nodes.
kubectl apply -n $NS -f catalog/ecoregion/k8s/epa-ecoregions-l3/workflow-rbac.yaml
for d in l3 l4; do
  kubectl apply -n $NS \
    -f catalog/ecoregion/k8s/epa-ecoregions-$d/configmap.yaml \
    -f catalog/ecoregion/k8s/epa-ecoregions-$d/workflow.yaml
  kubectl wait -n $NS --for=condition=complete --timeout=7200s job/epa-ecoregions-$d-workflow
done

# --- Steps 5-6: build + publish the STAC tree (also relocates the WWF collection) ------
kubectl create configmap epa-ecoregions-stac-script -n $NS \
  --from-file=make-epa-stac.py=catalog/ecoregion/stac/make-epa-stac.py \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl delete job epa-ecoregions-publish-stac -n $NS --ignore-not-found
kubectl apply -n $NS -f $HERE/publish-stac.yaml
kubectl wait -n $NS --for=condition=complete --timeout=1800s job/epa-ecoregions-publish-stac

# --- Verification gates ----------------------------------------------------------------
for d in epa-ecoregions-l3 epa-ecoregions-l4; do
  scripts/check-hex-coverage.sh nrp:public-ecoregion/$d/hex/ \
    --expect-count "$([ "$d" = epa-ecoregions-l3 ] && echo 10 || echo 6)"
  scripts/verify-stac.py --bucket public-ecoregion --dataset $d
done
scripts/verify-stac.py --bucket public-ecoregion   # the new bucket-root parent collection

# NOTE: the bucket root becoming a parent collection also makes the ROOT catalog's child
# link for public-ecoregion stale (it still said id/title "wwf-ecoregions-2017"). That one
# entry's id + title were updated to "ecoregion"/"Ecoregions"; the href did not change.
