#!/usr/bin/env bash
# Generate per-repo k8s Jobs that mirror NRP public-<repo> buckets to
# source.coop (us-west-2.opendata.source.coop/cboettig/<repo>).
#
# Mirrors the minio sync recipe in catalog/sync/k8s/sync-public-*.yaml exactly
# (gentle egress: --bwlimit 50M --tpslimit 5, opportunistic priority, one
# long-running pod per bucket). The ONLY differences are the destination
# remote/path, optional per-repo sub-path --excludes (for collections we may
# not redistribute), and a safety guard that refuses to run unless the dest is
# the intended cboettig/<repo> sub-path (the source.coop creds have account-wide
# access to a SHARED bucket, so a bucket-root sync could delete other tenants').
#
# SCOPE = catalogued datasets (reachable from public-data/stac/catalog.json)
# that are also license-clear to redistribute. See license-inventory.md.
#
# NOT mirrored — license prohibits redistribution (NRP-only):
#   hydrobasins (HydroSHEDS v1c: no stand-alone redistribution; see issue #223),
#   wdpa + wd-oecm, icca  (UNEP-WCMC Protected Planet: no redistribution),
#   iucn  (IUCN Red List: no redistribution incl. derivatives).
# NOT mirrored — not a catalogued dataset / work-in-progress:
#   datacenters, im3 (raw files, no STAC), landfire (WIP, issue #203),
#   ca30x30 + wlfw + working-lands (real data but not yet in the STAC catalog;
#   catalogue them first, then add here).
# Partially mirrored — HOLD sub-paths excluded below until terms are confirmed.
set -euo pipefail
OUTDIR="$(cd "$(dirname "$0")/../k8s" && pwd)"
ACCOUNT="cboettig"
DEST_BUCKET="us-west-2.opendata.source.coop"

# Catalogued, license-clear repos (== NRP public-<repo>).
REPOS=(
  ca-dac ca-wolves calenviroscreen carbon census cgs cpad ecoregion epa-water
  fire gbif gfw high-seas inat indigenous land-cover mappinginequality mobi ncp
  overturemaps padus population rap rivers social-vulnerability tpl trails usfws
  wetlands wyoming
)

# Per-repo sub-path excludes (HOLD: license unconfirmed for these collections).
# Space-separated rclone --exclude patterns, relative to the bucket root.
declare -A EXCLUDES=(
  [tpl]="conservation-almanac-2024-sites/** conservation-almanac-2024-funding/** landvote/**"
  [rivers]="american-rivers/campaigns/** american-rivers/ira-watersheds/** american-rivers/roo-cjest/**"
  [high-seas]="mpa-candidates/**"
)

for repo in "${REPOS[@]}"; do
  src="nrp:public-${repo}"
  dest="source:${DEST_BUCKET}/${ACCOUNT}/${repo}"
  # build --exclude flags (single-quoted patterns) for this repo
  excl=""
  for pat in ${EXCLUDES[$repo]:-}; do excl="${excl} --exclude '${pat}'"; done
  cat > "${OUTDIR}/source-sync-${repo}.yaml" <<YAML
apiVersion: batch/v1
kind: Job
metadata:
  name: source-sync-${repo}
  namespace: biodiversity
spec:
  backoffLimit: 1
  ttlSecondsAfterFinished: 86400
  template:
    spec:
      priorityClassName: opportunistic
      restartPolicy: Never
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: feature.node.kubernetes.io/pci-10de.present
                    operator: NotIn
                    values: ["true"]
      containers:
        - name: sync
          image: ghcr.io/boettiger-lab/datasets:latest
          imagePullPolicy: Always
          resources:
            requests:
              cpu: "2"
              memory: "4Gi"
            limits:
              cpu: "2"
              memory: "4Gi"
          volumeMounts:
            - name: rclone-config
              mountPath: /root/.config/rclone
              readOnly: true
          command: [bash, -c]
          args:
            - |
              set -euo pipefail
              SRC="${src}"
              DEST="${dest}"
              # Safety: the source.coop remote has account-wide access to a SHARED
              # bucket. Refuse to sync unless DEST is the intended cboettig sub-path.
              case "\$DEST" in
                "source:${DEST_BUCKET}/${ACCOUNT}/"?*) : ;;
                *) echo "REFUSING: dest '\$DEST' is not a cboettig/<repo> sub-path" >&2; exit 1 ;;
              esac
              RCLONE_FLAGS="--transfers 2 --checkers 4 --bwlimit 50M --tpslimit 5 --retries 5 --stats 120s -v"
              # DRYRUN=true (env) lists changes without writing. Default: real sync.
              if [ "\${DRYRUN:-false}" = "true" ]; then RCLONE_FLAGS="\$RCLONE_FLAGS --dry-run"; fi
              echo "Syncing: \$SRC -> \$DEST  (DRYRUN=\${DRYRUN:-false})"
              rclone sync \$RCLONE_FLAGS${excl} "\$SRC" "\$DEST"
              echo "Done: ${repo}"
      volumes:
        - name: rclone-config
          secret:
            secretName: rclone-config
YAML
  echo "wrote source-sync-${repo}.yaml${excl:+  (excludes:${excl})}"
done

echo "Generated ${#REPOS[@]} jobs into ${OUTDIR}"
