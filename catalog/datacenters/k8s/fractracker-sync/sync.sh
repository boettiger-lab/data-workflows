#!/bin/bash
# Weekly FracTracker sync orchestrator (#931), run by the fractracker-sync CronJob.
#
#   1. stage   (fractracker-sync-stage): download, vet, stage what changed; stop if nothing did.
#   2. rebuild each changed layer with its generated jobs, read verbatim from the
#      fractracker-{data-centers,moratoriums}-yamls ConfigMaps: convert, then pmtiles alongside
#      plan -> hex -> repartition, as the generated workflow.yaml runs them. Two edits: the
#      datasets image is pinned to $DATASETS_IMAGE, and convert's --expect-features is set to the
#      row count the stage step measured. Setup-bucket is skipped (the bucket exists).
#   3. publish (fractracker-sync-publish): regenerate, gate and upload the STAC, then verify it.
# Any failure stops the run: published files from the last good run stay, unless a rebuild step
# had already replaced them, in which case the next run rebuilds.
set -euo pipefail
NS=geo-workflows

wait_job() {  # wait_job <job> <timeout seconds>
  local job=$1 timeout=$2 waited=0 state
  while :; do
    state=$(kubectl get job "$job" -n $NS -o jsonpath='{.status.conditions[?(@.status=="True")].type}')
    case " $state " in
      *" Complete "*) echo "✓ $job complete"; return 0 ;;
      *" Failed "*) echo "✗ $job failed; inspect with: kubectl logs job/$job -n $NS"; exit 1 ;;
    esac
    [ "$waited" -ge "$timeout" ] && { echo "✗ $job did not finish within ${timeout}s"; exit 1; }
    sleep 30; waited=$((waited + 30))
  done
}
pin() {  # pin <yaml>: the generated jobs use :latest; an unattended run uses the tested image
  sed -e "s#image: ghcr.io/boettiger-lab/datasets:latest#image: $DATASETS_IMAGE#" \
      -e "s#__DATASETS_IMAGE__#$DATASETS_IMAGE#" \
      -e "s#imagePullPolicy: Always#imagePullPolicy: IfNotPresent#" "$1"
}
fresh() { kubectl delete job "$@" -n $NS --ignore-not-found --wait=true; }
message() { kubectl get pods -n $NS -l job-name="$1" \
  -o jsonpath='{.items[*].status.containerStatuses[0].state.terminated.message}'; }

# ---- 1. stage
fresh fractracker-sync-stage
pin /sync/stage-job.yaml | kubectl create -n $NS -f -
wait_job fractracker-sync-stage 3600
MSG=$(message fractracker-sync-stage)
echo "stage: $MSG"
get() { echo "$MSG" | tr ' ' '\n' | sed -n "s/^$1=//p" | tail -1; }
DC=$(get dc); MO=$(get mo); NDC=$(get ndc); NMO=$(get nmo)
case "$DC$MO" in 00) echo "FracTracker unchanged; nothing to do"; exit 0 ;; 01|10|11) ;; *)
  echo "stage reported no decision ('$MSG'); refusing to guess"; exit 1 ;; esac

# ---- 2. rebuild, one hex workflow at a time (AGENTS.md): wait for any other to finish
for i in $(seq 1 72); do
  busy=$(kubectl get jobs -n $NS -o jsonpath='{range .items[?(@.status.active)]}{.metadata.name}{"\n"}{end}' | grep -- '-hex$' || true)
  [ -z "$busy" ] && break
  [ "$i" = 72 ] && { echo "another hex job ran all along ($busy); giving up"; exit 1; }
  echo "waiting for $busy"; sleep 300
done

build() {  # build <dataset job prefix> <generated yamls dir> <expected features>
  local d=$1 dir=$2 n=$3 w=/tmp/$1
  mkdir -p "$w"
  for j in convert plan pmtiles hex repartition; do pin "$dir/$d-$j.yaml" > "$w/$j.yaml"; done
  sed -i -E "s/--expect-features [0-9]+/--expect-features $n/" "$w/convert.yaml"
  grep -qE -- "--expect-features $n( |$)" "$w/convert.yaml"
  fresh $d-convert $d-plan $d-pmtiles $d-hex $d-repartition
  kubectl create -n $NS -f "$w/convert.yaml"; wait_job $d-convert 3600
  kubectl create -n $NS -f "$w/pmtiles.yaml"
  kubectl create -n $NS -f "$w/plan.yaml"; wait_job $d-plan 3600
  local chunks par
  chunks=$(message $d-plan | tr ' ' '\n' | sed -n 's/^chunks=\([0-9][0-9]*\)$/\1/p' | tail -1)
  [ -n "$chunks" ] && [ "$chunks" -ge 1 ] || { echo "plan reported no chunk count"; exit 1; }
  par=$(( chunks < 50 ? chunks : 50 ))
  echo "$d: $chunks hex chunks, parallelism $par"
  kubectl patch --local -f "$w/hex.yaml" --type merge \
    -p "{\"spec\":{\"completions\":$chunks,\"parallelism\":$par}}" -o yaml | kubectl create -n $NS -f -
  wait_job $d-hex 21600
  kubectl create -n $NS -f "$w/repartition.yaml"; wait_job $d-repartition 3600
  wait_job $d-pmtiles 3600
}
LAYERS=""
[ "$DC" = 1 ] && { build fractracker-data-centers /dc "$NDC"; LAYERS=dc; }
[ "$MO" = 1 ] && { build fractracker-moratoriums /mo "$NMO"; LAYERS=${LAYERS:+$LAYERS,}mo; }

# ---- 3. publish
fresh fractracker-sync-publish
pin /sync/publish-job.yaml | sed "s#__LAYERS__#$LAYERS#" | kubectl create -n $NS -f -
wait_job fractracker-sync-publish 1800
echo "✓ sync complete: $LAYERS"
