#!/usr/bin/env bash
# Preview (no writes) what a source.coop mirror sync would change, run locally.
# rclone --dry-run only lists metadata on both sides, so it's fast and safe and
# does NOT need the cluster. Shows files that would be copied, updated, or
# DELETED on source.coop (mirror-with-delete) before you run the real job.
#
# Scope + per-repo excludes are kept in lockstep with gen-source-sync.sh.
#
# Usage:
#   ./dry-run-local.sh                 # all in-scope repos
#   ./dry-run-local.sh mobi rivers     # only the named repos
#
# Requires an rclone config defining the `nrp` and `source` remotes
# (RCLONE_CONFIG env var, or ~/.config/rclone/rclone.conf). On the cluster the
# `rclone-config` secret already has both.
set -euo pipefail
ACCOUNT="cboettig"
DEST_BUCKET="us-west-2.opendata.source.coop"
REPOS=(
  ca-dac ca-wolves calenviroscreen carbon census cgs cpad ecoregion epa-water
  fire gbif gfw high-seas inat indigenous land-cover mappinginequality mobi ncp
  overturemaps padus population rap rivers social-vulnerability tpl trails usfws
  wetlands
)
declare -A EXCLUDES=(
  [tpl]="conservation-almanac-2024-sites/** conservation-almanac-2024-funding/** landvote/**"
  [rivers]="american-rivers/campaigns/** american-rivers/ira-watersheds/** american-rivers/roo-cjest/**"
  [high-seas]="mpa-candidates/**"
)
[ $# -gt 0 ] && REPOS=("$@")
CFG_FLAG=""; [ -n "${RCLONE_CONFIG:-}" ] && CFG_FLAG="--config ${RCLONE_CONFIG}"

for repo in "${REPOS[@]}"; do
  excl=()
  for pat in ${EXCLUDES[$repo]:-}; do excl+=(--exclude "$pat"); done
  echo "=== DRY RUN: nrp:public-${repo} -> source:${DEST_BUCKET}/${ACCOUNT}/${repo} ${EXCLUDES[$repo]:+(excl: ${EXCLUDES[$repo]})} ==="
  rclone $CFG_FLAG sync --dry-run --tpslimit 5 -v "${excl[@]}" \
    "nrp:public-${repo}" "source:${DEST_BUCKET}/${ACCOUNT}/${repo}" 2>&1 \
    | grep -iE 'Skipped|would|delete|copy|error' || echo "(no changes / both sides match)"
done
