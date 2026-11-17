#!/bin/bash
# Weekly FracTracker sync, last step (#931): rebuild the STAC for the layers in $LAYERS (dc, mo)
# from the data just published, gate it, and upload it. Then run the full data-backed
# verify-stac against the live collections; a finding fails the job so the CronJob run shows it.
set -euo pipefail
RC="--retries 10 --low-level-retries 20 --retries-sleep 20s --s3-no-check-bucket"
B=https://raw.githubusercontent.com/boettiger-lab/data-workflows/main/scripts
mkdir -p /tmp/v
for f in stac-publish-guard.py verify-stac.py lint-stac-categorical.py lint-stac-pmtiles-fields.py; do
  curl -fsSL "$B/$f" -o "/tmp/v/$f"
done
python3 /sync/gen_stac.py build /tmp/stac --layers "$LAYERS" --merge-live

paths=""
for l in ${LAYERS//,/ }; do
  case $l in
    dc) p=fractracker/data-centers; id=fractracker-data-centers ;;
    mo) p=fractracker/moratoriums; id=fractracker-moratoriums ;;
  esac
  paths="$paths $p"
  f=/tmp/stac/$p/stac-collection.json
  python3 /tmp/v/verify-stac.py --no-data "$f"
  python3 - "$f" "$id" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
assert c["id"] == sys.argv[2] and c["license"] == "other", (c["id"], c["license"])
assert any(l["rel"] == "license" for l in c["links"]), "no license link"
assert sum("default" in a.get("roles", []) for a in c["assets"].values()) == 1, "default styles"
print("gate OK:", c["id"], len(c["assets"]), "assets")
PY
  rclone cat "nrp:public-datacenters/$p/stac-collection.json" > /tmp/v/live.json 2>/dev/null || : > /tmp/v/live.json
  python3 /tmp/v/stac-publish-guard.py "$f" /tmp/v/live.json
done
if [ -n "${DRY_RUN:-}" ]; then
  echo "DRY_RUN: nothing uploaded"; exit 0
fi
for p in $paths; do
  rclone copyto "/tmp/stac/$p/README.md" "nrp:public-datacenters/$p/README.md" $RC
  rclone copyto "/tmp/stac/$p/stac-collection.json" "nrp:public-datacenters/$p/stac-collection.json" $RC
  echo "published $p"
done
for p in $paths; do
  python3 /tmp/v/verify-stac.py --bucket public-datacenters --dataset "$p"
done
# the snapshot behind each republished layer is now the published one
for l in ${LAYERS//,/ }; do
  case $l in dc) r=nrp:public-datacenters/raw/fractracker ;; mo) r=nrp:public-datacenters/raw/fractracker/moratoriums ;; esac
  if rclone cat "$r/PENDING" > /tmp/v/pending 2>/dev/null && [ -s /tmp/v/pending ]; then
    rclone copyto /tmp/v/pending "$r/CURRENT" $RC && rclone deletefile "$r/PENDING"
    echo "CURRENT ($l): $(tr '\n' ' ' < /tmp/v/pending)"
  fi
done
echo OK
