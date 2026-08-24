#!/bin/bash
# check-severity-coverage.sh — the h0 coverage gate for the MTBS severity build, every
# (domain, layer, year) in one run.
#
# The severity collections are partitioned by BOTH `year` and `h0`, so the #409 silent-partial
# failure has an extra axis: a run can lose one h0 in one year out of 75 year-layers and still
# look complete at the top of the tree. `scripts/check-hex-coverage.sh` gates one prefix; this
# drives it across all 150 of them (39 CONUS + 36 AK years x 2 layers) and reports one verdict.
#
# ⚠️ Gated against an EXPLICIT expected h0 set, not against `--reference`. BUILD.md suggests
# pairing `mode` against `hex-fractions` from the same COG, which is a fine cross-check, but the
# two layers are produced by the same fan-out over the same restricted h0 list — so a mistake in
# that list, or an h0 lost in both runs, cancels out and the reference agrees with the target
# about a hole they share. The expected sets below are the MEASURED ones (see BUILD.md: taken
# from the completed perimeters hex by cell centroid), so this compares each layer against the
# build's actual ground truth instead of against its sibling.
#
# Usage:
#   catalog/fire/k8s/mtbs/check-severity-coverage.sh              # both domains, both layers
#   catalog/fire/k8s/mtbs/check-severity-coverage.sh conus        # one domain
#   catalog/fire/k8s/mtbs/check-severity-coverage.sh ak hex       # one domain, one layer
#
# Exit 0 = every expected partition populated. Exit 1 = at least one hole, listed.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$HERE/../../../../scripts/check-hex-coverage.sh"
[ -x "$GATE" ] || { echo "cannot find check-hex-coverage.sh at $GATE" >&2; exit 2; }

# CONUS is 1984-2024 less 2004 and 2017; Alaska is 1984-2023 less 1987, 1995, 2001 and 2013.
# Those six years are absent because their source mosaic is broken upstream on ScienceBase, not
# because nothing burned — a missing year here is expected and a PRESENT one would be the
# surprise. See BUILD.md.
CONUS_YEARS=$(seq 1984 2024 | grep -vxE '2004|2017')
AK_YEARS=$(seq 1984 2023 | grep -vxE '1987|1995|2001|2013')

# Measured off the completed perimeters hex, by cell centroid. CONUS 6 cells, Alaska 1.
CONUS_H0="576812596024311807,577164439745200127,577199624117288959,577234808489377791,577692205326532607,577762574070710271"
AK_H0="576707042908045311"

DOMAINS="${1:-conus ak}"
LAYERS="${2:-hex hex-fractions}"

fail=0
checked=0
missing_prefixes=()

for dom in $DOMAINS; do
  case "$dom" in
    conus) years="$CONUS_YEARS"; h0="$CONUS_H0" ;;
    ak)    years="$AK_YEARS";    h0="$AK_H0" ;;
    *) echo "unknown domain: $dom (expected conus or ak)" >&2; exit 2 ;;
  esac
  for layer in $LAYERS; do
    n_ok=0; n_bad=0
    for y in $years; do
      prefix="nrp:public-fire/mtbs-severity-1984-2024-${dom}/${layer}/year=${y}/"
      checked=$((checked + 1))
      if out=$("$GATE" "$prefix" --expect-h0 "$h0" 2>&1); then
        n_ok=$((n_ok + 1))
      else
        n_bad=$((n_bad + 1)); fail=1
        missing_prefixes+=("$prefix")
        echo "FAIL ${dom}/${layer} ${y}:"
        printf '    %s\n' "$out"
      fi
    done
    printf '%-6s %-14s %2d/%2d years complete\n' "$dom" "$layer" "$n_ok" "$((n_ok + n_bad))"
  done
done

echo
if [ "$fail" -eq 0 ]; then
  echo "PASS: all $checked year-layers have every expected h0 partition populated"
else
  echo "FAIL: ${#missing_prefixes[@]} of $checked year-layers are incomplete:"
  printf '  %s\n' "${missing_prefixes[@]}"
fi
exit "$fail"
