#!/usr/bin/env bash
# HAND-ROLLED: one-off server-side move of the first daily hex layout
# (hex/h0=*/part-tYYYYMMDD-0.parquet) to hex/date=YYYY-MM-DD/h0=*/..., the layout
# update-daily.sh now writes (data-workflows#802). Run with no CRW writer active.
set -euo pipefail
BUCKET=${BUCKET:-public-coral-reef-watch}
PREFIX=crw-5km-daily
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

for p in sst ssta hs dhw baa baa-max-7d; do
  src="nrp:$BUCKET/$PREFIX/$p/hex/"
  rclone lsf -R --files-only --exclude "date=*/**" "$src" > "$WORK/$p.txt"
  # One list per day, of paths relative to hex/: h0=*/part-tYYYYMMDD-*.parquet and _manifest/chunk-YYYYMMDD.parquet
  python3 - "$WORK/$p.txt" "$WORK/$p" <<'EOF'
import os, re, sys
from collections import defaultdict
days = defaultdict(list)
for line in open(sys.argv[1]):
    line = line.strip()
    m = re.fullmatch(r"(?:h0=\d+/part-t|_manifest/chunk-)(\d{8})(?:-\d+)?\.parquet", line)
    if m:
        days[m.group(1)].append(line)
    elif line:
        print("unmatched:", line, file=sys.stderr)
os.makedirs(sys.argv[2], exist_ok=True)
for ymd, files in days.items():
    open(os.path.join(sys.argv[2], f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"), "w").write("\n".join(files) + "\n")
print(f"{len(days)} days")
EOF
  echo "$p: $(wc -l < "$WORK/$p.txt") files"
  ls "$WORK/$p" | xargs -P 8 -I{} rclone move --files-from-raw "$WORK/$p/{}" --no-traverse \
    --transfers 16 "$src" "${src}date={}/"
  left=$(rclone lsf -R --files-only --exclude "date=*/**" "$src" | wc -l)
  echo "$p: $left files left outside date= partitions"
done
