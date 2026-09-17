#!/bin/bash
# check-chunk-manifests.sh — guard against `--expect-chunks` passing on a STALE manifest.
#
# `cng-datasets merge-chunks --expect-chunks N` counts records under
# `<hex-chunks>/_manifest/`. Those objects are keyed by CHUNK INDEX, so a re-run
# overwrites them one at a time as each chunk finishes. If the prefix still holds a
# PREVIOUS run's manifests, a chunk that fails in the new run leaves the OLD manifest in
# place and the gate counts it: `--expect-chunks` passes on an incomplete build. That is
# the #409 silent-partial-build failure wearing the gate's own badge.
#
# This is not hypothetical: it is exactly the state data-workflows#609 was left in after
# an aborted hex run was re-submitted into the same prefix with a corrected --h0-subset.
#
# It also does not rely on inspecting pods. Armada reaps failed pods (and k8s deletes them
# when backoffLimitPerIndex is set), but a MISSING manifest record cannot be reaped.
#
# Run this BEFORE merging any re-run. A clean first run needs only --expect.
#
# Usage:
#   scripts/check-chunk-manifests.sh <chunks-prefix> --expect <N> [--since <RFC3339>]
#
#   <chunks-prefix>  parent of _manifest/, as rclone path or s3:///https:// URL, e.g.
#                    nrp:public-mesic/mesic-persistence-unmasked-2026-09/hex-chunks/
#   --expect <N>     the fan-out size (what you pass to --expect-chunks)
#   --since <ts>     treat manifests older than this as stale, e.g. 2026-09-17T20:23:00Z.
#                    Omit on a first run into a clean prefix.
#
# Exit 0 = every index recorded completion (and, with --since, all are fresh);
# exit 1 = missing or stale indices (listed); exit 2 = usage.

set -euo pipefail
usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

to_rclone() {
  local p="$1"; p="${p#s3://}"; p="${p#https://s3-west.nrp-nautilus.io/}"; p="${p#nrp:}"
  [ "${p: -1}" = "/" ] || p="${p}/"; echo "nrp:${p}"
}

[ $# -ge 1 ] || usage
PREFIX="$1"; shift
EXPECT=""; SINCE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --expect) EXPECT="$2"; shift 2 ;;
    --since)  SINCE="$2";  shift 2 ;;
    -h|--help) usage ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done
[ -n "$EXPECT" ] || usage

MAN="$(to_rclone "$PREFIX")_manifest/"
SINCE_EPOCH=0
[ -n "$SINCE" ] && SINCE_EPOCH=$(date -u -d "$SINCE" +%s)

FRESH=""; STALE=""
while read -r _sz d t name; do
  [ -z "${name:-}" ] && continue
  idx=$(echo "$name" | grep -o 'chunk-[0-9]*' | grep -o '[0-9]*' || true)
  [ -z "$idx" ] && continue
  ts=$(date -u -d "${d} ${t%.*}" +%s 2>/dev/null || echo 0)
  if [ "$ts" -ge "$SINCE_EPOCH" ]; then FRESH="$FRESH $idx"; else STALE="$STALE $idx"; fi
done < <(rclone lsl "$MAN" 2>/dev/null)

echo "manifest prefix : $MAN"
echo "expected chunks : $EXPECT"
[ -n "$SINCE" ] && echo "run started     : $SINCE"
echo "recorded fresh  : $(echo $FRESH | wc -w)"

MISSING=""
for i in $(seq 0 $((EXPECT-1))); do
  echo " $FRESH " | grep -q " $i " || MISSING="$MISSING $i"
done

rc=0
if [ -n "$STALE" ]; then
  echo "STALE manifests (from an earlier run, would be miscounted by --expect-chunks):$STALE" >&2
  rc=1
fi
if [ -n "$MISSING" ]; then
  echo "MISSING completion records for chunk indices:$MISSING" >&2
  rc=1
fi
[ "$rc" -eq 0 ] && echo "PASS: all $EXPECT chunk indices recorded completion in this run"
exit $rc
