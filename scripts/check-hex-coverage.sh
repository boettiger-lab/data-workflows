#!/bin/bash
# check-hex-coverage.sh — coverage gate for indexed raster/vector hex builds.
#
# Catches the "silent partial build" class (data-workflows #409): a 122-completion
# indexed hex Job that dies/gets-preempted mid-run can leave a *subset* of the h0
# partitions on S3, which then gets published as if complete. This gate compares the
# h0-partition SET a hex prefix actually wrote against an expected set — either an
# explicit list/count, or a reference hex prefix built from the same source (e.g. the
# fractional-coverage layer, which writes a full h0 grid from the same COG).
#
# It is a CHEAP metadata listing (rclone lsf of h0=* dirs) — NOT a big-data scan — so
# it is safe to run from a laptop and cannot trip HARD BOUNDARY 0.
#
# Usage:
#   scripts/check-hex-coverage.sh <hex-prefix> --reference <ref-hex-prefix>
#   scripts/check-hex-coverage.sh <hex-prefix> --expect-count <N>
#   scripts/check-hex-coverage.sh <hex-prefix> --expect-h0 <h0a,h0b,...>
#
# <hex-prefix> is the parent of the h0=* partitions, as an rclone path or an
# s3:///https:// URL, e.g.:
#   nrp:public-land-cover/nlcd-2024/hex/
#   s3://public-land-cover/nlcd-2024/hex/
#   https://s3-west.nrp-nautilus.io/public-land-cover/nlcd-2024/hex/
#
# Exit 0 = coverage complete; exit 1 = missing partitions (prints the set); exit 2 = usage/error.

set -euo pipefail

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

# --- normalize any accepted prefix form to an `nrp:bucket/path/` rclone path ---
to_rclone() {
  local p="$1"
  p="${p#s3://}"
  p="${p#https://s3-west.nrp-nautilus.io/}"
  p="${p#nrp:}"
  [ "${p: -1}" = "/" ] || p="${p}/"
  echo "nrp:${p}"
}

# --- list the sorted set of h0 cell ids under a hex prefix ---
list_h0() {
  local prefix; prefix="$(to_rclone "$1")"
  rclone lsf "$prefix" 2>/dev/null | grep '^h0=' | sed 's|^h0=||; s|/$||' | sort -u
}

[ $# -ge 1 ] || usage
HEX="$1"; shift
REF=""; EXPECT_COUNT=""; EXPECT_H0=""
while [ $# -gt 0 ]; do
  case "$1" in
    --reference)    REF="$2"; shift 2 ;;
    --expect-count) EXPECT_COUNT="$2"; shift 2 ;;
    --expect-h0)    EXPECT_H0="$2"; shift 2 ;;
    -h|--help)      usage ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done

ACTUAL="$(list_h0 "$HEX")"
ACTUAL_N=$(printf '%s\n' "$ACTUAL" | grep -c . || true)
echo "hex prefix : $HEX"
echo "h0 present : $ACTUAL_N"

# Build the expected set from whichever mode was requested.
EXPECTED=""
if [ -n "$REF" ]; then
  EXPECTED="$(list_h0 "$REF")"
  echo "reference  : $REF ($(printf '%s\n' "$EXPECTED" | grep -c . || true) h0)"
elif [ -n "$EXPECT_H0" ]; then
  EXPECTED="$(printf '%s\n' "${EXPECT_H0//,/$'\n'}" | sed '/^$/d' | sort -u)"
elif [ -n "$EXPECT_COUNT" ]; then
  if [ "$ACTUAL_N" -eq "$EXPECT_COUNT" ]; then
    echo "PASS: $ACTUAL_N == expected $EXPECT_COUNT h0 partitions"; exit 0
  fi
  echo "FAIL: $ACTUAL_N h0 partitions, expected $EXPECT_COUNT" >&2; exit 1
else
  echo "no expectation given (--reference / --expect-count / --expect-h0)" >&2; usage
fi

# Set comparison: every expected h0 must be present.
MISSING="$(comm -23 <(printf '%s\n' "$EXPECTED") <(printf '%s\n' "$ACTUAL"))"
EXTRA="$(comm -13 <(printf '%s\n' "$EXPECTED") <(printf '%s\n' "$ACTUAL"))"
[ -n "$EXTRA" ] && { echo "note: h0 present but not in expected set:"; printf '  %s\n' $EXTRA; }
if [ -z "$MISSING" ]; then
  echo "PASS: all $(printf '%s\n' "$EXPECTED" | grep -c .) expected h0 partitions present"; exit 0
fi
echo "FAIL: missing $(printf '%s\n' "$MISSING" | grep -c .) expected h0 partitions:" >&2
printf '  %s\n' $MISSING >&2
exit 1
