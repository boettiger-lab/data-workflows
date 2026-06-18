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
# NOT mirrored — wyoming: a Wyoming-CLIPPED collection whose datasets (NLCD, RAP,
#   etc.) now exist as full-extent buckets (public-land-cover, public-rap, ...).
#   Kept on NRP as-is (apps wired to it); migrate its constituents into their
#   full-extent buckets first, then retire the wyoming-scoped naming (see #225).
# Partially mirrored — HOLD sub-paths excluded below until terms are confirmed.
# NOT mirrored — tpl: the only license-clear collection in public-tpl was
#   wcb-approved-projects (CDFW BIOS ds672 — CA Wildlife Conservation Board), but
#   that is a CDFW state-agency product misfiled under "tpl", being relocated to
#   the planned public-cdfw bucket (geo-agent-ops #19; data-workflows #228). The
#   rest of public-tpl (Conservation Almanac, LandVote) is HOLD pending TPL terms,
#   so there is nothing license-clear left to mirror as cboettig/tpl. Revisit as
#   cboettig/cdfw once WCB moves.
# NOT mirrored — ca-wolves: license is clear (CC0-1.0), but it is a REAL-TIME
#   updated product (wolf_*_latest.geojson + snapshots/); a static source.coop
#   mirror would be a stale point-in-time copy presented as current. Hold until we
#   decide whether to publish only dated snapshots/ (not the _latest feeds). The
#   block here is data-semantics, NOT licensing.
set -euo pipefail
OUTDIR="$(cd "$(dirname "$0")/../k8s" && pwd)"
ACCOUNT="cboettig"
DEST_BUCKET="us-west-2.opendata.source.coop"

# Catalogued, license-clear repos (== NRP public-<repo>).
REPOS=(
  ca-dac calenviroscreen carbon census cgs cpad ecoregion epa-water
  fire gbif gfw high-seas inat indigenous land-cover mappinginequality mobi ncp
  overturemaps padus population rap rivers social-vulnerability trails usfws
  wetlands
)

# Per-repo sub-path excludes (HOLD: license unconfirmed for these collections).
# Space-separated rclone --exclude patterns, relative to the bucket root.
declare -A EXCLUDES=(
  [rivers]="american-rivers/campaigns/** american-rivers/ira-watersheds/** american-rivers/roo-cjest/**"
  [high-seas]="mpa-candidates/**"
)

# Per-repo rclone verb. Default "sync" (mirror-with-delete: dest becomes an exact
# copy of NRP). Override to "copy" (additive: never deletes on dest) for repos
# that hold content which exists ONLY on source.coop and must be preserved.
#   mobi: a 27k-tile XYZ pyramid (tiles/**), a whole range-size-rarity-all/ layer,
#   the original SpeciesRichness_All/RSR_All source rasters, and LICENSE.txt all
#   live only on source.coop (NRP public-mobi has just the reprocessed COG + hex).
#   A mirror-with-delete would wipe them, so mobi is copy-only.
declare -A MODE=(
  [mobi]="copy"
)

for repo in "${REPOS[@]}"; do
  src="nrp:public-${repo}"
  dest="source:${DEST_BUCKET}/${ACCOUNT}/${repo}"
  # build --exclude flags (single-quoted patterns) for this repo
  excl=""
  for pat in ${EXCLUDES[$repo]:-}; do excl="${excl} --exclude '${pat}'"; done
  verb="${MODE[$repo]:-sync}"
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
              echo "${verb^}ing: \$SRC -> \$DEST  (DRYRUN=\${DRYRUN:-false})"
              rclone ${verb} \$RCLONE_FLAGS${excl} "\$SRC" "\$DEST"
              echo "Done: ${repo}"
      volumes:
        - name: rclone-config
          secret:
            secretName: rclone-config
YAML
  echo "wrote source-sync-${repo}.yaml  [${verb}]${excl:+  (excludes:${excl})}"
done

echo "Generated ${#REPOS[@]} per-repo jobs into ${OUTDIR}"

# ---------------------------------------------------------------------------
# Scheduled weekly backup = ONE CronJob (mechanism, static) + a generated
# ConfigMap (policy/scope). Keeping the repo list / verb / excludes in a
# generated ConfigMap rather than baked into the CronJob means THIS file stays
# the single source of truth: the per-repo jobs above and the weekly cron can
# never drift. Re-run this generator after editing REPOS/MODE/EXCLUDES, then
# re-apply source-sync-cron-config.yaml (the CronJob itself rarely changes).
# ---------------------------------------------------------------------------
CFG="${OUTDIR}/source-sync-cron-config.yaml"
{
  cat <<'HEAD'
# GENERATED by catalog/sync/source-coop/gen-source-sync.sh — do not edit by hand.
# Scope consumed by the `source-sync` CronJob: one line per repo,
#   <repo> <rclone-verb> [space-separated HOLD exclude globs...]
apiVersion: v1
kind: ConfigMap
metadata:
  name: source-sync-scope
  namespace: biodiversity
  labels:
    app: source-sync
data:
  repos.txt: |
    # <repo> <verb> [exclude globs...]
HEAD
  for repo in "${REPOS[@]}"; do
    printf '    %s %s %s\n' "${repo}" "${MODE[$repo]:-sync}" "${EXCLUDES[$repo]:-}"
  done
} > "${CFG}"
echo "wrote $(basename "${CFG}")  (${#REPOS[@]} repos)"

CRON="${OUTDIR}/source-sync-cron.yaml"
cat > "${CRON}" <<'YAML'
# GENERATED by catalog/sync/source-coop/gen-source-sync.sh — do not edit by hand.
# Weekly off-NRP backup of every catalogued, license-clear public-* bucket to
# source.coop (cboettig/<repo>). One pod loops the `source-sync-scope` ConfigMap
# sequentially at 50 MB/s — the same gentle recipe as the per-repo
# source-sync-<repo>.yaml jobs. continue-on-error: one bad repo doesn't block
# the rest, but the Job still exits non-zero so the failure is visible.
#   Apply:      kubectl apply -f source-sync-cron-config.yaml -f source-sync-cron.yaml
#   Manual run: kubectl -n biodiversity create job --from=cronjob/source-sync source-sync-manual
#   Dry run:    edit env DRYRUN=true on the manual Job (lists changes, writes nothing)
apiVersion: batch/v1
kind: CronJob
metadata:
  name: source-sync
  namespace: biodiversity
  labels:
    app: source-sync
spec:
  schedule: "0 8 * * 0"          # Sundays 08:00 UTC
  timeZone: Etc/UTC
  concurrencyPolicy: Forbid       # never overlap with a still-running weekly backup
  startingDeadlineSeconds: 3600
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 1
      ttlSecondsAfterFinished: 604800
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
                requests: {cpu: "2", memory: "4Gi"}
                limits:   {cpu: "2", memory: "4Gi"}
              env:
                - name: DRYRUN
                  value: "false"
              volumeMounts:
                - name: rclone-config
                  mountPath: /root/.config/rclone
                  readOnly: true
                - name: scope
                  mountPath: /config
                  readOnly: true
              command: [bash, -c]
              args:
                - |
                  set -ufo pipefail           # NOT -e: keep going past a failed repo. -f: no
                                              # globbing, so exclude patterns (e.g. mpa-candidates/**)
                                              # stay literal and a HOLD path can't accidentally expand away.
                  ACCOUNT="cboettig"
                  DEST_BUCKET="us-west-2.opendata.source.coop"
                  RCLONE_FLAGS="--transfers 2 --checkers 4 --bwlimit 50M --tpslimit 5 --retries 5 --stats 300s -v"
                  if [ "${DRYRUN:-false}" = "true" ]; then RCLONE_FLAGS="$RCLONE_FLAGS --dry-run"; fi
                  fail=0 ; n=0
                  while read -r repo verb excludes; do
                    [ -z "${repo:-}" ] && continue
                    case "$repo" in \#*) continue ;; esac
                    # Require an explicit verb. A missing column must NOT silently
                    # default to the destructive `sync` (which would delete a
                    # copy-only repo's source.coop-only content, e.g. mobi).
                    case "${verb:-}" in
                      sync|copy) : ;;
                      *) echo "REFUSING: repo '$repo' has invalid/missing verb '${verb:-}' (want sync|copy)" >&2 ; fail=1 ; continue ;;
                    esac
                    SRC="nrp:public-${repo}"
                    DEST="source:${DEST_BUCKET}/${ACCOUNT}/${repo}"
                    # Safety: the source.coop creds have account-wide access to a
                    # SHARED bucket. Refuse unless DEST is the cboettig/<repo> path.
                    case "$DEST" in
                      "source:${DEST_BUCKET}/${ACCOUNT}/"?*) : ;;
                      *) echo "REFUSING: '$DEST' is not a cboettig/<repo> sub-path" >&2 ; fail=1 ; continue ;;
                    esac
                    args=( "$verb" $RCLONE_FLAGS )
                    for pat in ${excludes:-} ; do args+=( --exclude "$pat" ) ; done
                    args+=( "$SRC" "$DEST" )
                    n=$((n+1))
                    echo "=== [$n] rclone $verb $SRC -> $DEST  (DRYRUN=${DRYRUN:-false}) ==="
                    if rclone "${args[@]}" ; then echo "OK: $repo" ; else echo "FAILED: $repo (rc=$?)" >&2 ; fail=1 ; fi
                  done < /config/repos.txt
                  echo "=== source-sync complete: $n repos attempted, fail=$fail ==="
                  exit $fail
          volumes:
            - name: rclone-config
              secret:
                secretName: rclone-config
            - name: scope
              configMap:
                name: source-sync-scope
YAML
echo "wrote $(basename "${CRON}")"

echo "Generated ${#REPOS[@]} per-repo jobs + weekly CronJob (source-sync) into ${OUTDIR}"
