#!/usr/bin/env bash
# Preview (no writes) what a source.coop mirror sync would change, run locally.
# rclone --dry-run only lists metadata on both sides, so it's fast and safe and
# does NOT need the cluster. Shows files that would be copied, updated, or
# DELETED on source.coop (mirror-with-delete) before you run the real job.
#
# Usage:
#   ./dry-run-local.sh                 # all in-scope repos
#   ./dry-run-local.sh mobi wdpa       # only the named repos
#
# Requires an rclone config that defines the `nrp` and `source` remotes
# (RCLONE_CONFIG env var, or ~/.config/rclone/rclone.conf). On the cluster the
# `rclone-config` secret already has both.
set -euo pipefail
ACCOUNT="cboettig"
DEST_BUCKET="us-west-2.opendata.source.coop"
REPOS=(
  ca-dac ca-wolves ca30x30 calenviroscreen carbon census cgs cpad datacenters
  ecoregion epa-water fire gbif gfw high-seas hydrobasins icca im3 inat
  indigenous iucn land-cover landfire mappinginequality mobi ncp overturemaps
  padus population rap rivers social-vulnerability tpl trails usfws wdpa
  wetlands wlfw working-lands wyoming
)
[ $# -gt 0 ] && REPOS=("$@")
CFG_FLAG=""; [ -n "${RCLONE_CONFIG:-}" ] && CFG_FLAG="--config ${RCLONE_CONFIG}"

for repo in "${REPOS[@]}"; do
  echo "=== DRY RUN: nrp:public-${repo} -> source:${DEST_BUCKET}/${ACCOUNT}/${repo} ==="
  rclone $CFG_FLAG sync --dry-run --tpslimit 5 -v \
    "nrp:public-${repo}" "source:${DEST_BUCKET}/${ACCOUNT}/${repo}" 2>&1 \
    | grep -iE 'Skipped|would|delete|copy|error' || echo "(no changes / both sides match)"
done
