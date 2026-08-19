#!/bin/bash
# Catalog-wide pre-gate verify-stac sweep (data-workflows#509 scope amendment).
#
# Runs the FULL data-backed scripts/verify-stac.py against every collection the
# enumerator finds, in parallel, and records a compact per-collection verdict. This is
# the "run the current rule set against every collection published before the CI gate"
# pass — the gate is PR-triggered on changed catalog/** YAMLs, so pre-gate collections
# are otherwise never re-verified.
#
# Usage:
#   python3 enumerate-collections.py > /tmp/sweep/collections.tsv
#   ./run-sweep.sh /tmp/sweep            # workdir; writes collections.tsv results there
#
# Output: $WORKDIR/results/r<N>.txt, one verdict line per collection —
#   CLEAN <secs> <url> | HARD(<n>) <secs> <url>  (+ indented [HARD] lines) | TIMEOUT <secs> <url>
# Aggregate with analyze-findings.py.
set -u
WORKDIR="${1:-/tmp/pregate-sweep}"
SLICES="${SLICES:-8}"                 # parallel workers (keep MCP load sane)
PERCOLL_TIMEOUT="${PERCOLL_TIMEOUT:-300}"
VS="$(cd "$(dirname "$0")/../../.." && pwd)/scripts/verify-stac.py"
mkdir -p "$WORKDIR/results"
TSV="$WORKDIR/collections.tsv"
[ -f "$TSV" ] || { echo "missing $TSV — run enumerate-collections.py first"; exit 1; }

# leaf-data + meta (verify handles both; leaf-nodata has nothing to check)
grep -E '^leaf-data|^meta' "$TSV" | awk -F'\t' '{print $3}' > "$WORKDIR/urls.txt"
# interleave into SLICES so the big collections spread across workers
awk -v n="$SLICES" '{print > "'"$WORKDIR"'/slice-" (NR%n) ".txt"}' "$WORKDIR/urls.txt"

run_slice() {  # $1 slice file, $2 result file
  : > "$2"
  while IFS= read -r url; do
    [ -z "$url" ] && continue
    start=$(date +%s)
    raw=$(timeout "$PERCOLL_TIMEOUT" python3 "$VS" "$url" 2>&1); rc=$?
    el=$(( $(date +%s) - start ))
    if [ $rc -eq 124 ]; then
      echo "TIMEOUT	${el}s	$url" >> "$2"
    else
      n=$(echo "$raw" | grep -cE '^\[HARD\]')
      # A nonzero exit with no [HARD] line means the verifier itself failed (an MCP error,
      # an unreadable collection) — it is NOT a clean verdict, and recording it as one hides
      # an unverified collection behind a pass. Two blm collections sat in the 2026-08-17
      # results as "CLEAN ... exit=1" this way, and re-running BOTH against the current
      # checker reports real HARD findings. See data-workflows#509.
      if [ "$n" -eq 0 ] && [ $rc -ne 0 ]; then
        echo "ERROR	${el}s	$url	exit=$rc" >> "$2"
        echo "$raw" | tail -5 | sed 's/^/    /' >> "$2"
      elif [ "$n" -eq 0 ]; then echo "CLEAN	${el}s	$url	exit=$rc" >> "$2"
      else echo "HARD($n)	${el}s	$url	exit=$rc" >> "$2"
           echo "$raw" | grep -E '^\[HARD\]' | sed 's/^/    /' >> "$2"; fi
    fi
  done < "$1"
  echo "### slice done: $1" >> "$2"
}

pids=()
for i in $(seq 0 $((SLICES-1))); do
  run_slice "$WORKDIR/slice-$i.txt" "$WORKDIR/results/r$i.txt" &
  pids+=($!)
done
echo "launched $SLICES workers over $(wc -l < "$WORKDIR/urls.txt") collections → $WORKDIR/results/"
wait "${pids[@]}"
cat "$WORKDIR"/results/r*.txt > "$WORKDIR/all-results.txt"
echo "done. HARD collections: $(grep -cE '^HARD' "$WORKDIR/all-results.txt"), "\
"CLEAN: $(grep -cE '^CLEAN' "$WORKDIR/all-results.txt"), TIMEOUT: $(grep -cE '^TIMEOUT' "$WORKDIR/all-results.txt")"
