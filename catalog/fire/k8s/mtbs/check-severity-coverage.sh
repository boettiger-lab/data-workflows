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

# ⚠️ MIN_BYTES is 1000, NOT the gate's 4096 default, and that default produced FALSE FAILURES here.
# The default documents its assumption as "a real partition is MB-GB", which holds for most of the
# catalog but not for this one: h0 576812596024311807 is a thin strip along the northern border
# (~120.4W-112.5W, 47.3N-49.1N) that in a quiet fire year holds only a few hundred burned cells.
# Measured on the completed CONUS mode layer, its smallest genuinely-populated partitions are
# 2,408 B (1997, 432 cells), 2,647 B (2013, 597 cells) and 3,977 B (1986, 1,260 cells) -- all real
# data, all under 4096. An EMPTY footer-only parquet is ~214 B, so 1000 separates the two cleanly
# with an order of magnitude of margin on each side.
MIN_BYTES=1000

# ⚠️ Some (year, h0) pairs are legitimately absent, and demanding all 6 CONUS cells in every year
# is wrong for a SPARSE reducer. `mode` writes a partition only where burned pixels exist, and in
# the small northern-border cell there are years with no MTBS fire at all -- so no partition is the
# correct output, not a hole.
#
# Each entry below is VERIFIED against the perimeters collection, which covers all 41 years and is
# a strict superset of severity: `SELECT year(Ig_Date), COUNT(*) ... WHERE h0 = <cell>` returns no
# row for these years, i.e. no fire was mapped in that cell that year. Re-derive rather than trust
# this list if the source release changes.
#
#   conus 1990 / 1993 / 1995 / 2024, h0 576812596024311807 -- zero perimeters in that cell
#
# The arithmetic checks out end to end: 39 years x 6 h0 = 234 expected, less these 4, is 230 --
# exactly the number of partitions the completed mode layer wrote, against a Job that reported
# 234/234 succeeded with no failed indexes.
KNOWN_EMPTY="conus:1990:576812596024311807 conus:1993:576812596024311807 conus:1995:576812596024311807 conus:2024:576812596024311807"

# expected_h0 <domain> <year> -- the full set for that domain minus any verified-fireless cells
expected_h0 () {
  local dom=$1 year=$2 full=$3 out=""
  local IFS=,
  for c in $full; do
    case " $KNOWN_EMPTY " in
      *" ${dom}:${year}:${c} "*) continue ;;
    esac
    out="${out:+$out,}$c"
  done
  echo "$out"
}

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
      exp=$(expected_h0 "$dom" "$y" "$h0")
      if [ -z "$exp" ]; then
        n_ok=$((n_ok + 1)); continue      # every cell verified fireless this year
      fi
      if out=$("$GATE" "$prefix" --expect-h0 "$exp" --min-bytes "$MIN_BYTES" 2>&1); then
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
