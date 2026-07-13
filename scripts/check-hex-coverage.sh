#!/bin/bash
# check-hex-coverage.sh — coverage gate for indexed raster/vector hex builds.
#
# Catches the "silent partial build" class (data-workflows #409): a 122-completion
# indexed hex Job that dies/gets-preempted mid-run can leave a *subset* of the h0
# partitions on S3, which then gets published as if complete. This gate compares the
# set of h0 partitions a hex prefix actually POPULATED against an expected set —
# either an explicit list/count, or a reference hex prefix built from the same source.
#
# ⚠️ Count POPULATED partitions, not directories (the #409/#410 lesson).
#   A `mode` (or any sparse) reducer writes a partition ONLY for h0 cells that contain
#   valid pixels. A `sum`/coverage/fractions reducer writes a "full grid": it
#   materializes a `data_0.parquet` for every h0 the grid *touches*, including h0 that
#   are entirely nodata — those come out as an empty, footer-only parquet (~214 bytes,
#   0 rows). So the raw h0=* DIRECTORY set of a full-grid layer is a SUPERSET of its
#   real data extent, and comparing directory sets across reducers gives false gaps:
#   NLCD mode (6 populated h0) looked like "6 of 11" only because the fractions
#   reference had 5 extra *empty* partition dirs. This gate therefore treats a
#   partition as present only if its parquet bytes exceed --min-bytes (default 4 KiB),
#   which cleanly separates a ~214-byte empty footer from any real partition (smallest
#   observed real partition ~9.9 MB). Both the target and the reference are filtered
#   the same way, so mode-vs-fractions compares like with like.
#
# It is a CHEAP metadata listing (rclone lsf of h0=*/*.parquet sizes) — NOT a
# big-data scan — so it is safe to run from a laptop and cannot trip HARD BOUNDARY 0.
#
# Usage:
#   scripts/check-hex-coverage.sh <hex-prefix> --reference <ref-hex-prefix>
#   scripts/check-hex-coverage.sh <hex-prefix> --expect-count <N>
#   scripts/check-hex-coverage.sh <hex-prefix> --expect-h0 <h0a,h0b,...>
#   (any form) [--min-bytes <N>]   # populated-partition size threshold, default 4096
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

# --- list the sorted set of h0 cell ids that hold a POPULATED partition ---
# A partition counts only if the total parquet bytes under h0=<cell>/ exceed MIN_BYTES,
# so empty (0-row, footer-only ~214 B) full-grid partitions are excluded.
list_h0() {
  local prefix; prefix="$(to_rclone "$1")"
  # `-R --files-only --format sp` → "<size>;<relpath>" for every file under the prefix,
  # e.g. "9892327;h0=576812596024311807/data_0.parquet". Sum bytes per h0, keep those
  # whose total >= MIN_BYTES.
  rclone lsf "$prefix" -R --files-only --format "sp" 2>/dev/null \
    | awk -F';' -v min="$MIN_BYTES" '
        {
          size=$1; path=$2
          if (match(path, /^h0=[0-9]+/)) {
            cell=substr(path, RSTART+3, RLENGTH-3)
            bytes[cell]+=size
          }
        }
        END { for (c in bytes) if (bytes[c] >= min) print c }
      ' \
    | sort -u
}

[ $# -ge 1 ] || usage
HEX="$1"; shift
REF=""; EXPECT_COUNT=""; EXPECT_H0=""; MIN_BYTES=4096
while [ $# -gt 0 ]; do
  case "$1" in
    --reference)    REF="$2"; shift 2 ;;
    --expect-count) EXPECT_COUNT="$2"; shift 2 ;;
    --expect-h0)    EXPECT_H0="$2"; shift 2 ;;
    --min-bytes)    MIN_BYTES="$2"; shift 2 ;;
    -h|--help)      usage ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done

ACTUAL="$(list_h0 "$HEX")"
ACTUAL_N=$(printf '%s\n' "$ACTUAL" | grep -c . || true)
echo "hex prefix  : $HEX"
echo "min bytes   : $MIN_BYTES (a partition smaller than this is treated as empty)"
echo "h0 populated: $ACTUAL_N"

# Build the expected set from whichever mode was requested.
EXPECTED=""
if [ -n "$REF" ]; then
  EXPECTED="$(list_h0 "$REF")"
  echo "reference   : $REF ($(printf '%s\n' "$EXPECTED" | grep -c . || true) populated h0)"
elif [ -n "$EXPECT_H0" ]; then
  EXPECTED="$(printf '%s\n' "${EXPECT_H0//,/$'\n'}" | sed '/^$/d' | sort -u)"
elif [ -n "$EXPECT_COUNT" ]; then
  if [ "$ACTUAL_N" -eq "$EXPECT_COUNT" ]; then
    echo "PASS: $ACTUAL_N == expected $EXPECT_COUNT populated h0 partitions"; exit 0
  fi
  echo "FAIL: $ACTUAL_N populated h0 partitions, expected $EXPECT_COUNT" >&2; exit 1
else
  echo "no expectation given (--reference / --expect-count / --expect-h0)" >&2; usage
fi

# Set comparison: every expected h0 must be populated.
MISSING="$(comm -23 <(printf '%s\n' "$EXPECTED") <(printf '%s\n' "$ACTUAL"))"
EXTRA="$(comm -13 <(printf '%s\n' "$EXPECTED") <(printf '%s\n' "$ACTUAL"))"
[ -n "$EXTRA" ] && { echo "note: h0 populated but not in expected set:"; printf '  %s\n' $EXTRA; }
if [ -z "$MISSING" ]; then
  echo "PASS: all $(printf '%s\n' "$EXPECTED" | grep -c .) expected h0 partitions populated"; exit 0
fi
echo "FAIL: missing $(printf '%s\n' "$MISSING" | grep -c .) expected h0 partitions:" >&2
printf '  %s\n' $MISSING >&2
exit 1
