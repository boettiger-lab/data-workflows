#!/bin/bash
# One calendar month of a PacIOOS ERDDAP model grid per index (#840, #841); see k8s/pacioos-models-stage.yaml.
# Env: PRODUCT ERDDAP_ID DS FIRST_MONTH [LAST_DAY] VARS SLICE BUCKET JOB_COMPLETION_INDEX
set -euo pipefail
E=https://pae-paha.pacioos.hawaii.edu/erddap/griddap
W=/tmp/w; mkdir -p $W; cd $W
ym=$(python3 -c "y,m=map(int,'$FIRST_MONTH'.split('-')); n=y*12+m-1+$JOB_COMPLETION_INDEX; print(f'{n//12}{n%12+1:02d}')")
name=$DS-$ym
if rclone lsf "nrp:$BUCKET/raw/$DS/zarr/$name.days.json" 2>/dev/null | grep -q .; then echo "$name done, skipping"; exit 0; fi

# this month's first and last model step, from ERDDAP's own time axis
curl -sS --fail --retry 5 --retry-all-errors -o times.csv "$E/$ERDDAP_ID.csv0?time"
read -r t0 t1 < <(python3 - "$ym" "${LAST_DAY:-9999-12-31}" <<'EOF'
import sys
ym, last = sys.argv[1], sys.argv[2]
ts = [t.strip() for t in open("times.csv") if t[:7].replace("-", "") == ym and t[:10] <= last]
print(ts[0], ts[-1]) if ts else sys.exit(f"no steps in {ym}")
EOF
)
q=""
for v in $VARS; do q="$q${q:+,}$v%5B($t0):1:($t1)%5D$SLICE"; done
url="$E/$ERDDAP_ID.nc?$q"
echo "$name: $t0 to $t1"
curl -sS --fail --retry 5 --retry-all-errors --max-time 3600 -o $name.nc "$url"
printf '{"source_url":"%s","accessed":"%s","bytes":%s,"sha256":"%s"}\n' \
  "$url" "$(date -u +%FT%TZ)" "$(stat -c %s $name.nc)" "$(sha256sum $name.nc | cut -d' ' -f1)" > $name.nc.gz.json

python3 -I /scripts/daily.py "$PRODUCT" $name.nc out $name
gzip -1 $name.nc
rclone copyto $name.nc.gz "nrp:$BUCKET/raw/$DS/nc/$name.nc.gz"
rclone copyto $name.nc.gz.json "nrp:$BUCKET/raw/$DS/nc/$name.nc.gz.json"
rclone copy out/cog "nrp:$BUCKET/$DS/cog/" --transfers 16
rclone delete "nrp:$BUCKET/raw/$DS/zarr/$name.zarr/" 2>/dev/null || true
rclone copy out/$name.zarr "nrp:$BUCKET/raw/$DS/zarr/$name.zarr/"
rclone copyto out/$name.days.json "nrp:$BUCKET/raw/$DS/zarr/$name.days.json"
echo "$name staged"
