# source.coop mirror

Mirrors the canonical NRP `public-*` buckets to [Source Cooperative](https://source.coop)
for discoverability, the same way `catalog/sync/k8s/sync-public-*.yaml` mirrors
them to MinIO. NRP S3 stays canonical; source.coop is a downstream copy.

## Layout

source.coop data lives in a **shared, multi-tenant** AWS bucket per region. Our
repos are sub-paths of one bucket:

```
us-west-2.opendata.source.coop/cboettig/<repo>/      <- one "product" (repo) per NRP bucket
```

Repo name == NRP bucket minus the `public-` prefix (1:1), e.g.
`public-wdpa` → `cboettig/wdpa`. Two NRP buckets get a **new** repo while the
older differently-versioned repo is left untouched:

| NRP bucket | source.coop repo | legacy repo kept as-is |
|---|---|---|
| `public-padus` (PAD-US 4.1) | `cboettig/padus` | `cboettig/pad-us-3` |
| `public-rivers` | `cboettig/rivers` | `cboettig/us-rivers` |

**Excluded** (infra/internal): `public-test`, `public-output`, `public-requests`,
`public-boettiger-lab`, and `public-data` (the root STAC catalog — its hrefs point
at NRP URLs, so it would publish broken cross-links). `public-tnc` is empty.

## ⚠️ Credentials are account-wide — handle with care

The `source` rclone remote (in the k8s `rclone-config` secret) is a long-term AWS
IAM key with access to the **entire** source.coop AWS account, i.e. every tenant's
data in the shared bucket. The jobs therefore:

- hard-code the full `source:us-west-2.opendata.source.coop/cboettig/<repo>` dest, and
- include a guard that **refuses to run** unless the dest is a `cboettig/<repo>` sub-path,

so a typo can never `rclone sync` (delete-extras) against the bucket root or another
account. Always `dry-run-local.sh` a repo before its first real sync.

## Step 1 — create the repos (manual, web UI)

The programmatic create endpoint (`POST /api/v1/products/{account_id}`) is currently
**`501 Not implemented`** in production (the documented `/repositories/` API is stale).
So create each repo in the source.coop web UI first (`visibility: public`). The repo
list with titles/descriptions is generated from each bucket's STAC collection — see
the PR description / `gen-source-sync.sh` for the canonical set. A sync writes bytes
to `cboettig/<repo>/`, but the data is only discoverable once the product exists.

## Step 2 — generate / regenerate the jobs

```bash
./gen-source-sync.sh        # (re)writes ../k8s/source-sync-<repo>.yaml for all in-scope repos
```

Each job mirrors the MinIO recipe exactly — `--transfers 2 --checkers 4 --bwlimit 50M
--tpslimit 5 --retries 5`, `priorityClassName: opportunistic`, 2 cpu / 4 Gi, one
long-running pod per bucket — only the destination differs.

## Step 3 — preview, then sync (sequentially)

```bash
./dry-run-local.sh wdpa            # preview adds/updates/DELETES (no writes, no cluster)
./run-source-sync.sh wdpa          # apply one job, wait for completion
./run-source-sync.sh               # all repos, smallest -> largest (gbif ~1.2 TB last)
```

**Run sequentially** (the runner does this). 41 jobs at `--bwlimit 50M` in parallel
would be ~2 GiB/s of NRP egress — the opposite of gentle.

Monitor: `kubectl -n biodiversity get jobs | grep source-sync` /
`kubectl -n biodiversity logs job/source-sync-<repo>`.

## Notes

- **Mirror-with-delete:** `rclone sync` makes the dest an exact copy, deleting stale
  source.coop files. For the ~8 repos that predate this mirror (`carbon`, `ca30x30`,
  `cpad`, `fire`, `gbif`, `mappinginequality`, `mobi`, `social-vulnerability`) this
  replaces their older structure with NRP-canonical content — dry-run first to see what
  gets removed.
- Total in scope ≈ 2.9 TB / ~45 k objects (gbif alone ≈ 1.2 TB).
