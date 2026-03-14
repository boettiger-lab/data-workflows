#!/bin/bash
# For each hex dataset: check h0 directory name format AND whether h0 is stored
# inside the parquet file and as what type.
#
# Output columns: DATASET | DIR_FORMAT | H0_IN_FILE | H0_TYPE

ENDPOINT="s3-west.nrp-nautilus.io"

check() {
  local label="$1"
  local bucket="$2"
  local hex_prefix="$3"   # e.g. "nlcd-2024/hex/"

  # Find first partition directory
  local first_dir
  first_dir=$(rclone ls "nrp:${bucket}/${hex_prefix}" 2>/dev/null | head -1 | awk '{print $2}' | cut -d/ -f1)
  if [ -z "$first_dir" ]; then
    printf "%-45s  %-30s  %-12s  %s\n" "$label" "NO DATA" "-" "-"
    return
  fi

  # Classify directory name format
  local dir_val="${first_dir#h0=}"
  local dir_format
  if echo "$dir_val" | grep -qE '^[0-9]{15,}$'; then
    dir_format="INT  ($first_dir)"
  else
    dir_format="STR  ($first_dir)"
  fi

  # Describe the actual parquet file
  local sample="s3://${bucket}/${hex_prefix}${first_dir}/data_0.parquet"
  local desc
  desc=$(duckdb :memory: -noheader -list -c "
INSTALL httpfs; LOAD httpfs;
SET s3_endpoint='${ENDPOINT}';
SET s3_url_style='path';
SELECT column_name || ':' || column_type
FROM (DESCRIBE SELECT * FROM read_parquet('${sample}') LIMIT 1)
WHERE column_name = 'h0';" 2>/dev/null)

  local h0_in_file h0_type
  if [ -z "$desc" ]; then
    h0_in_file="NO"
    h0_type="-"
  else
    h0_in_file="YES"
    h0_type="${desc#h0:}"
  fi

  printf "%-45s  %-36s  %-12s  %s\n" "$label" "$dir_format" "$h0_in_file" "$h0_type"
}

printf "%-45s  %-36s  %-12s  %s\n" "DATASET" "DIR_FORMAT" "H0_IN_FILE" "H0_TYPE"
printf '%s\n' "$(printf '%.0s-' {1..110})"

echo "--- Wyoming vectors ---"
check "wyoming/blm-sma"                  public-wyoming  "blm-sma/hex/"
check "wyoming/sage-grouse-priority"     public-wyoming  "sage-grouse-priority/hex/"
check "wyoming/wgfd-elk-crucial"         public-wyoming  "wgfd-elk-crucial/hex/"
check "wyoming/wgfd-elk-seasonal"        public-wyoming  "wgfd-elk-seasonal/hex/"
check "wyoming/wgfd-mule-deer-crucial"   public-wyoming  "wgfd-mule-deer-crucial/hex/"
check "wyoming/wgfd-mule-deer-seasonal"  public-wyoming  "wgfd-mule-deer-seasonal/hex/"
check "wyoming/wgfd-pronghorn-crucial"   public-wyoming  "wgfd-pronghorn-crucial/hex/"
check "wyoming/wgfd-pronghorn-seasonal"  public-wyoming  "wgfd-pronghorn-seasonal/hex/"
check "wyoming/wy-counties"              public-wyoming  "wy-counties/hex/"

echo "--- Wyoming rasters (STRING — reencode pending) ---"
check "wyoming/nlcd-2024"                public-wyoming  "nlcd-2024/hex/"
check "wyoming/rap-pfg-biomass"          public-wyoming  "rap-pfg-biomass/hex/"

echo "--- PAD-US ---"
check "padus/fee"                        public-padus    "padus-4-1/fee/hex/"
check "padus/easement"                   public-padus    "padus-4-1/easement/hex/"
check "padus/proclamation"               public-padus    "padus-4-1/proclamation/hex/"
check "padus/marine"                     public-padus    "padus-4-1/marine/hex/"
check "padus/combined"                   public-padus    "padus-4-1/combined/hex/"

echo "--- Census ---"
check "census/tract"                     public-census   "census-2024/tract/hex/"
check "census/county"                    public-census   "census-2024/county/hex/"
check "census/state"                     public-census   "census-2024/state/hex/"
check "census/cd"                        public-census   "census-2024/cd/hex/"

echo "--- Other newer datasets ---"
check "calenviroscreen/ces5"             public-calenviroscreen "calenviroscreen-5-0/ces5/hex/"
check "social-vulnerability/svi-2022"    public-social-vulnerability "svi-2022-tract/hex/"
check "cpad/holdings"                    public-cpad     "cpad-2025b-holdings/hex/"
check "cpad/units"                       public-cpad     "cpad-2025b-units/hex/"
check "ecoregion"                        public-ecoregion "ecoregion/hex/"
check "mappinginequality"                public-mappinginequality "hex/"

echo "--- STRING-encoded datasets ---"
check "wdpa"                             public-wdpa     "hex/"
check "iucn/amphibians_sr"              public-iucn     "hex/amphibians_sr/"
check "gbif"                             public-gbif     "hex/"
check "inat"                             public-inat     "hexagon/"
check "ncp/biod_nathab"                 public-ncp      "hex/ncp_biod_nathab/"
check "overturemaps/regions"             public-overturemaps "regions/"
check "carbon/irrecoverable-v1"          public-carbon   "irrecoverable-carbon/hex/"
check "carbon/vulnerable-v1"             public-carbon   "vulnerable-carbon/hex/"
check "hydrobasins/L3"                   public-hydrobasins "L3/"
check "wetlands/ramsar"                  public-wetlands "ramsar/hex/"
check "wetlands/glwd"                    public-wetlands "glwd/hex/"
check "wetlands/nwi"                     public-wetlands "nwi/hex/"
