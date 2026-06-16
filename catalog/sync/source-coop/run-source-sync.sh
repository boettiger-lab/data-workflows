#!/usr/bin/env bash
# Run the source.coop mirror jobs SEQUENTIALLY (one bucket at a time) to keep
# NRP egress gentle — 41 jobs at --bwlimit 50M in parallel would be ~2 GiB/s.
# Ordered smallest -> largest so the long pole (gbif, ~1.2 TB) runs last/alone.
#
# Usage:
#   ./run-source-sync.sh                # real sync, all repos, in order
#   ./run-source-sync.sh mobi wdpa      # only the named repos
#
# To preview without writing, dry-run locally first: ./dry-run-local.sh [repos...]
# (the job YAML also honors a DRYRUN=true env var if you prefer editing it).
#
# Prereq: the target source.coop product (repo) must already exist (created in
# the web UI) — its prefix is cboettig/<repo>/. The API create endpoint is
# currently 501/disabled.
set -euo pipefail
K8S="$(cd "$(dirname "$0")/../k8s" && pwd)"
NS=biodiversity

ORDER=(
  im3 datacenters ca-wolves wlfw mobi mappinginequality icca cgs ncp
  usfws calenviroscreen trails tpl working-lands cpad ca-dac gfw epa-water
  ecoregion rivers fire landfire land-cover indigenous social-vulnerability
  inat wyoming wdpa hydrobasins population census high-seas padus overturemaps
  iucn rap wetlands ca30x30 carbon gbif
)

REPOS=("$@"); [ ${#REPOS[@]} -eq 0 ] && REPOS=("${ORDER[@]}")

for repo in "${REPOS[@]}"; do
  job="source-sync-${repo}"
  yaml="${K8S}/${job}.yaml"
  [ -f "$yaml" ] || { echo "SKIP: no $yaml" >&2; continue; }
  echo "=== ${job} ==="
  kubectl -n "$NS" delete job "$job" --ignore-not-found
  kubectl -n "$NS" apply -f "$yaml"
  kubectl -n "$NS" wait --for=condition=complete --timeout=86400s "job/${job}" \
    || { echo "FAILED/timeout: ${job} — inspect: kubectl -n $NS logs job/${job}" >&2; exit 1; }
  echo "--- completed ${job} ---"
done
echo "All requested source.coop syncs complete."
