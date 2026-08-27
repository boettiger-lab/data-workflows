#!/bin/bash
# check-coverage.sh — h0 coverage gate across every INHABIT v4 hex layer (data-workflows #610).
#
# Wraps scripts/check-hex-coverage.sh, which gates ONE hex prefix. There are up to 108 layers here
# (12 species x 9 products), so running it by hand is where a silently-partial build (#409) gets
# missed. Cheap: rclone metadata listings only, no data scan.
#
# ⚠️ WHY NOT `--expect-h0` WITH ALL SIX CONUS CELLS FOR EVERY LAYER.
# The continuous products use the `mean` reducer, which writes a partition only where valid source
# pixels exist. A species legitimately has NO partition in an h0 it does not reach: buffelgrass is a
# southwest species, and its MESS-masked product retains only 34% of CONUS, so an absent h0=78
# (Northeast) partition is correct data, not a failed pod. Demanding all six would cry wolf on every
# range-limited species and train the reader to ignore it.
#
# So each species is gated against ITS OWN class raster instead. The `integrated-binary-*` products
# carry a class (0 = unsuitable, or -1 = extrapolation) across all of CONUS, so their h0 set is the
# maximal extent for that species and grid — the natural reference for that species' continuous
# products. The class raster itself is gated against the six CONUS h0 cells.
#
# ⛔ THIS IS THE SECOND OF TWO DEFENSES, NOT THE ONLY ONE. It cannot tell "this h0 has no data for
# this species" from "this h0's pod died", so it does not replace checking the Job:
#
#   kubectl -n geo-workflows get job inhabit-v4-hex -o \
#     jsonpath='{.status.succeeded}/{.spec.completions} failed={.status.failedIndexes}'
#
# A build is complete only if the Job reports Complete with EMPTY failedIndexes AND this gate is
# clean. Run the Job check first; this one explains what landed.
#
# Usage:  catalog/invasives/scripts/check-coverage.sh [--phase 1|2|all]
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
GATE="${REPO_ROOT}/scripts/check-hex-coverage.sh"
BASE="nrp:public-invasives/inhabit-v4-2024"

# The six h0 indices CONUS occupies. NOT the RAP precedent's four — that list is missing 14
# (Southeast) and 78 (Northeast); see BUILD.md.
CONUS_H0="576812596024311807,577692205326532607,577164439745200127,577199624117288959,577762574070710271,577234808489377791"

SPECIES=(bromus_tectorum bromus_rubens bromus_japonicus bromus_arvensis
         taeniatherum_caput_medusae ventenata_dubia aegilops_cylindrica
         agropyron_cristatum salsola_tragus tamarix_chinensis_ramosissima
         elaeagnus_angustifolia cenchrus_ciliaris)

PHASE=all
[ "${1:-}" = "--phase" ] && PHASE="${2:-all}"
case "$PHASE" in
  1)   CONT=(occurrence-masked abundance-masked high-abundance-masked); CLASSES=(integrated-binary-fifth) ;;
  2)   CONT=(occurrence abundance high-abundance); CLASSES=(integrated-binary-first integrated-binary-tenth) ;;
  all) CONT=(occurrence abundance high-abundance occurrence-masked abundance-masked high-abundance-masked)
       CLASSES=(integrated-binary-first integrated-binary-fifth integrated-binary-tenth) ;;
  *)   echo "unknown --phase '$PHASE' (want 1, 2 or all)" >&2; exit 2 ;;
esac

fails=0; checked=0
for sp in "${SPECIES[@]}"; do
  # The reference for this species: prefer fifth, else whichever class product this phase builds.
  ref=""
  for c in integrated-binary-fifth "${CLASSES[@]}"; do
    if [ -n "$(rclone lsf "${BASE}/${sp}/${c}/hex/" 2>/dev/null)" ]; then ref="$c"; break; fi
  done

  for c in "${CLASSES[@]}"; do
    checked=$((checked+1))
    if ! "$GATE" "${BASE}/${sp}/${c}/hex/" --expect-h0 "$CONUS_H0" >/tmp/cov.$$ 2>&1; then
      fails=$((fails+1)); echo "FAIL  ${sp}/${c}  (vs the six CONUS h0)"; sed 's/^/        /' /tmp/cov.$$
    else
      echo "ok    ${sp}/${c}"
    fi
  done

  if [ -z "$ref" ]; then
    echo "SKIP  ${sp}: no class-raster hex yet, cannot reference the continuous products"
    continue
  fi
  for p in "${CONT[@]}"; do
    checked=$((checked+1))
    if ! "$GATE" "${BASE}/${sp}/${p}/hex/" --reference "${BASE}/${sp}/${ref}/hex/" >/tmp/cov.$$ 2>&1; then
      # A gap here may be legitimate range limitation, so name that rather than asserting a defect.
      fails=$((fails+1))
      echo "GAP   ${sp}/${p}  (vs ${ref}) — check against that species' MESS retention before"
      echo "        concluding a pod failed; a masked product can legitimately miss an h0."
      sed 's/^/        /' /tmp/cov.$$
    else
      echo "ok    ${sp}/${p}"
    fi
  done
done
rm -f /tmp/cov.$$

echo
echo "checked ${checked} layers, ${fails} needing attention"
[ "$fails" -eq 0 ] || exit 1
