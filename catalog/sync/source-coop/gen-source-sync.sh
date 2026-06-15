#!/usr/bin/env bash
# Generate per-repo k8s Jobs that mirror NRP public-<repo> buckets to
# source.coop (us-west-2.opendata.source.coop/cboettig/<repo>).
#
# Mirrors the minio sync recipe in catalog/sync/k8s/sync-public-*.yaml exactly
# (gentle egress: --bwlimit 50M --tpslimit 5, opportunistic priority, one
# long-running pod per bucket). The ONLY differences are the destination
# remote/path and a safety guard that refuses to run unless the destination is
# the intended cboettig/<repo> sub-path (the source.coop creds have
# account-wide access to a SHARED bucket, so a bucket-root sync could delete
# other tenants' data).
#
# Repo name == NRP bucket minus the "public-" prefix (1:1). Run from anywhere;
# writes YAMLs into the sibling k8s/ directory.
set -euo pipefail
OUTDIR="$(cd "$(dirname "$0")/../k8s" && pwd)"
ACCOUNT="cboettig"
DEST_BUCKET="us-west-2.opendata.source.coop"

# In-scope repos (== NRP public-<repo>). Excludes infra buckets
# (test/output/requests/boettiger-lab/data) and the empty public-tnc.
REPOS=(
  ca-dac ca-wolves ca30x30 calenviroscreen carbon census cgs cpad datacenters
  ecoregion epa-water fire gbif gfw grids high-seas hydrobasins icca im3 inat
  indigenous iucn land-cover landfire mappinginequality mobi ncp overturemaps
  padus population rap rivers social-vulnerability tpl trails usfws wdpa
  wetlands wlfw working-lands wyoming
)

for repo in "${REPOS[@]}"; do
  src="nrp:public-${repo}"
  dest="source:${DEST_BUCKET}/${ACCOUNT}/${repo}"
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
              rclone sync \$RCLONE_FLAGS "\$SRC" "\$DEST"
              echo "Done: ${repo}"
      volumes:
        - name: rclone-config
          secret:
            secretName: rclone-config
YAML
  echo "wrote source-sync-${repo}.yaml"
done

echo "Generated ${#REPOS[@]} jobs into ${OUTDIR}"
