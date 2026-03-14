#!/bin/bash
# Check H3 hex encoding (STRING vs INTEGER) across all public-* S3 buckets
# STRING encoding = old/slow; UBIGINT/BIGINT = new/fast

ENDPOINT="s3-west.nrp-nautilus.io"

check_hex() {
  local bucket="$1"
  local hex_path="$2"
  local label="$3"

  # Find first h0 partition
  local first_partition
  first_partition=$(rclone lsf "nrp:${bucket}/${hex_path}" 2>/dev/null | grep "^h0=" | head -1 | tr -d '/')
  if [ -z "$first_partition" ]; then
    echo "  SKIP  ${label}: no h0 partitions found at ${bucket}/${hex_path}"
    return
  fi

  local sample="s3://${bucket}/${hex_path}${first_partition}/data_0.parquet"

  # Get column types for h* columns
  local result
  result=$(duckdb -noheader -list -c "
INSTALL httpfs; LOAD httpfs;
SET s3_endpoint='${ENDPOINT}';
SET s3_url_style='path';
SELECT column_name || ':' || column_type
FROM (DESCRIBE SELECT * FROM read_parquet('${sample}') LIMIT 1)
WHERE lower(column_name) LIKE 'h%' AND column_name != 'href';
" 2>/dev/null || echo "ERROR")

  if [ "$result" = "ERROR" ] || [ -z "$result" ]; then
    echo "  ERROR ${label}: could not read ${sample}"
    return
  fi

  # Classify: VARCHAR = string (slow), UBIGINT/BIGINT/INTEGER = integer (fast)
  local encoding="INTEGER"
  if echo "$result" | grep -qi "varchar\|string"; then
    encoding="STRING"
  fi

  echo "  ${encoding}  ${label}: ${result}"
}

echo "=== H3 Hex Encoding Audit ==="
echo "STRING = old/slow VARCHAR encoding | INTEGER = new/fast uint64 encoding"
echo ""

# --- Early/older datasets (likely STRING) ---
echo "--- Older datasets ---"
check_hex "public-iucn"            "amphibians_sr/hex/"        "iucn/amphibians_sr"
check_hex "public-wdpa"            "wdpa/hex/"                 "wdpa"
check_hex "public-mappinginequality" "mappinginequality/hex/"  "mappinginequality"
check_hex "public-gbif"            "gbif/hex/"                 "gbif"
check_hex "public-inat"            "inat/hex/"                 "inat"
check_hex "public-hydrobasins"     "L3/"                       "hydrobasins/L3"
check_hex "public-ncp"             "ncp_biod_nathab/hex/"      "ncp/biod_nathab"
check_hex "public-overturemaps"    "divisions/regions/hex/"    "overturemaps/regions"

echo ""
echo "--- Wetlands ---"
check_hex "public-wetlands"        "ramsar/hex/"               "wetlands/ramsar"
check_hex "public-wetlands"        "glwd/hex/"                 "wetlands/glwd"
check_hex "public-wetlands"        "nwi/hex/"                  "wetlands/nwi"

echo ""
echo "--- Carbon ---"
check_hex "public-carbon"          "irrecoverable-carbon-2010/hex/"  "carbon/irrecoverable-2010"
check_hex "public-carbon"          "irrecoverable-carbon-2022/hex/"  "carbon/irrecoverable-2022"

echo ""
echo "--- Newer datasets (expect INTEGER) ---"
check_hex "public-padus"           "padus-4-1/fee/hex/"        "padus/fee"
check_hex "public-padus"           "padus-4-1/easement/hex/"   "padus/easement"
check_hex "public-census"          "census-2024/tract/hex/"    "census/tract"
check_hex "public-census"          "census-2024/county/hex/"   "census/county"
check_hex "public-ecoregion"       "ecoregion/hex/"            "ecoregion"
check_hex "public-calenviroscreen" "calenviroscreen-5-0/ces5/hex/"  "calenviroscreen/ces5"
check_hex "public-cpad"            "holdings/hex/"             "cpad/holdings"
check_hex "public-social-vulnerability" "svi-2022-tract/hex/"  "social-vulnerability/svi-2022"

echo ""
echo "--- Wyoming ---"
for ds in blm-sma sage-grouse-priority wyoming-ranchlands wyoming-ownership wyoming-parcels wyoming-water-rights wyoming-rivers wyoming-roads wyoming-places; do
  check_hex "public-wyoming" "${ds}/hex/" "wyoming/${ds}"
done
check_hex "public-wyoming" "nlcd-2024/hex/"    "wyoming/nlcd-2024"
check_hex "public-wyoming" "rap-pfg-biomass/hex/" "wyoming/rap-pfg-biomass"

echo ""
echo "Done."
