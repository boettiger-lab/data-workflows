#!/usr/bin/env bash
# Re-fetch the 2001 Roadless Rule rescission source documents and verify them against sources.tsv.
#
# Usage:  ./fetch-sources.sh [outdir]        # default outdir: ./fetched
#
# Everything here was captured 2026-08-20 (see README.md). Two caveats:
#
#   1. The public-inspection PDF is TRANSIENT. It rotated out on publication; that URL will 404.
#      The bytes are committed at docs/pi-2026-16965.pdf — this script cannot recover them.
#   2. The supporting documents are behind a Box SHARED LINK, not Regulations.gov. Box shared
#      links are not durable identifiers. When SHARED_NAME stops resolving, find the current
#      "online public folder" link on https://www.fs.usda.gov/managing-land/planning/roadless
#      and update SHARED_NAME plus the file ids below. The sha256 values in sources.tsv are the
#      durable part — verify against them, not against the URL.

set -uo pipefail

OUT="${1:-fetched}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_NAME="gomzq6rruwsds8rw50o3j3g429utj8f6"
BOX_FOLDER="https://usfs-public.app.box.com/s/${SHARED_NAME}"
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"

mkdir -p "$OUT"

get() { # get <dest-name> <url>
  curl -sSL --max-time 600 -A "$UA" -H "Referer: ${BOX_FOLDER}" \
       -o "${OUT}/$1" "$2" -w "  %{http_code}  %{size_download} bytes  $1\n"
}
box() { get "$1" "https://usfs-public.app.box.com/index.php?rm=box_download_shared_file&shared_name=${SHARED_NAME}&file_id=f_$2"; }

echo "== Federal Register =="
get fr-2026-16965.pdf  "https://www.govinfo.gov/content/pkg/FR-2026-08-20/pdf/2026-16965.pdf"
get fr-2026-16965.txt  "https://www.federalregister.gov/documents/full_text/text/2026/08/20/2026-16965.txt"
get fr-2026-16965.json "https://www.federalregister.gov/api/v1/documents/2026-16965.json"
# The 2001 rule as promulgated — the version legally in effect. NOT what the CFR prints.
get fr-2001-01-726.txt "https://www.federalregister.gov/documents/full_text/text/2001/01/12/01-726.txt"

echo "== DEIS (Box) =="
box deis-vol1.pdf               2415112742244
box deis-vol2-state-maps.pdf    2415122649024
box deis-vol3-agency-letters.pdf 2415113961556

echo "== Supporting analysis (Box) =="
box economic-analysis.pdf              2415121854032
box tribal-summary-impact-statement.pdf 2415119950801
box draft-ba-usfws.pdf                 2415111198979
box draft-ba-nmfs.pdf                  2415112703194
box ak-2020-feis.pdf                   2415121215789
box ak-2023-dna.pdf                    2415112995910
box data-web-viewer-instructions.pdf   2415050314901

echo "== Forest Service =="
get rescission-summary-analysis.pdf "https://www.fs.usda.gov/sites/default/files/2001-roadless-rule-rescission-summary-analysis.pdf"
# usda.gov 403s scripted fetches; the fs.usda.gov mirror of the release serves fine.
get fs-release.html "https://www.fs.usda.gov/about-agency/newsroom/releases/usda-acts-remove-roadless-rule-restrictions-exacerbate-rising"

echo "== Regulations.gov docket FS-2025-0001 (DEMO_KEY is rate-limited; swap in your own) =="
get regs-documents.json "https://api.regulations.gov/v4/documents?filter%5BdocketId%5D=FS-2025-0001&page%5Bsize%5D=50&sort=-postedDate&api_key=${REGULATIONS_GOV_API_KEY:-DEMO_KEY}"

echo
echo "== Verifying against sources.tsv =="
fail=0
while IFS=$'\t' read -r local_path committed retrieved bytes sha url; do
  [ "$local_path" = "local_path" ] && continue
  name="$(basename "$local_path")"
  if [ ! -f "${OUT}/${name}" ]; then
    if [ "$name" = "pi-2026-16965.pdf" ]; then
      echo "  SKIP  ${name} (transient public-inspection PDF; committed copy is the only one)"
    else
      echo "  MISS  ${name} (not fetched)"; fail=1
    fi
    continue
  fi
  got="$(sha256sum "${OUT}/${name}" | cut -d' ' -f1)"
  if [ "$got" = "$sha" ]; then
    echo "  OK    ${name}"
  else
    echo "  DIFF  ${name}"
    echo "          expected ${sha}"
    echo "          got      ${got}"
    fail=1
  fi
done < "${HERE}/sources.tsv"

echo
if [ "$fail" -eq 0 ]; then
  echo "All fetched documents match the 2026-08-20 capture."
else
  echo "Mismatches above. A DIFF is not automatically a problem — the agency may have reposted a"
  echo "document — but it means the capture and the live source have diverged. Diff the text and"
  echo "record what changed in README.md before relying on either."
fi
exit "$fail"
