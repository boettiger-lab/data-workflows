# source.coop mirror — campaign plan

Mirrors the canonical NRP `public-*` datasets to [Source Cooperative](https://source.coop)
for discoverability, the way `catalog/sync/k8s/sync-public-*.yaml` mirrors them to MinIO.
**NRP S3 stays canonical; source.coop is a downstream public copy.**

## Scope policy (what we mirror)

A bucket/collection is mirrored only if **both** hold:

1. **Catalogued** — reachable from the STAC root catalog (`public-data/stac/catalog.json`).
   Raw/uncatalogued buckets are not datasets and are not published.
2. **License-clear** — the upstream license permits redistribution by a third party.
   NC / share-alike are fine (we label them); no-redistribution licenses are not.

Per-collection license verdicts live in [`license-inventory.md`](license-inventory.md)
(OK · OK-NC · NO · HOLD). That file + the `REPOS`/`EXCLUDES` arrays in
[`gen-source-sync.sh`](gen-source-sync.sh) are the **single source of truth** for scope.

### Currently mirrored: 30 buckets
Repo name = NRP bucket minus `public-` (1:1). Two get a **new** repo while the older
differently-versioned legacy repo is left untouched:

| NRP bucket | source.coop repo | legacy repo kept as-is |
|---|---|---|
| `public-padus` (PAD-US 4.1) | `cboettig/padus` | `cboettig/pad-us-3` |
| `public-rivers` | `cboettig/rivers` | `cboettig/us-rivers` |

Three buckets are mirrored **partially** — HOLD sub-collections (license unconfirmed)
are excluded via per-repo `--exclude` until terms are confirmed:

| repo | excluded sub-paths | reason |
|---|---|---|
| `tpl` | `conservation-almanac-2024-{sites,funding}`, `landvote` | TPL spatial-data terms unconfirmed (only `wcb-approved-projects`, CC-BY, is mirrored) |
| `rivers` | `american-rivers/{campaigns,ira-watersheds,roo-cjest}` | American Rivers org layers, no clear license |
| `high-seas` | `mpa-candidates` | candidate-MPA source/license unidentified |

### NOT mirrored

- **License prohibits redistribution → NRP-only:** `hydrobasins` (HydroSHEDS v1c: "no
  stand-alone redistribution"; re-import v2 on release — issue #223), `wdpa` (+ WD-OECM),
  `icca` (UNEP-WCMC Protected Planet), `iucn` (IUCN Red List — incl. derived richness/ranges).
- **Not a catalogued dataset / WIP:** `datacenters`, `im3` (raw files, no STAC); `landfire`
  (WIP, issue #203); `ca30x30`, `wlfw`, `working-lands` (real data but not yet in the STAC
  catalog — catalogue them first, then add here).
- **Infra/internal:** `public-{test,output,requests,boettiger-lab,data,grids}`; `public-tnc` empty.

### Non-commercial datasets (mirrored, must be labeled NC)
`carbon`, `gfw`, `mobi`, `mappinginequality`, high-seas `hydrothermal-vents` (CC-BY-NC),
`rfmo` (CC-BY-SA), `meow` (CC-BY-NC), and the GBIF aggregate. Plus pre-existing source.coop
repos `fishbase` (CC-BY-NC) and `carbon`. The source.coop product page / STAC for these MUST
state the NC/SA license — we are a non-commercial project and downstream users must know.

## Adding a repo later (the maintainable loop)

1. Confirm it's catalogued and license-clear (add a row to `license-inventory.md`).
2. Add the bucket to `REPOS` in `gen-source-sync.sh` (and `EXCLUDES`/`new-repos.md` if needed).
3. `./gen-source-sync.sh` → emits `../k8s/source-sync-<repo>.yaml`.
4. Create the `cboettig/<repo>` product in the source.coop web UI (it's not automatable — see below).
5. `./dry-run-local.sh <repo>` then `./run-source-sync.sh <repo>`.

## ⚠️ Credentials are account-wide

The `source` rclone remote (k8s `rclone-config` secret) is a long-term AWS key with access to
the **entire** source.coop account (every tenant in the shared bucket). Every job hard-codes the
`source:us-west-2.opendata.source.coop/cboettig/<repo>` dest and **refuses to run** against any
other path, so a typo can't `rclone sync` (delete-extras) the bucket root or another account.
Always `dry-run-local.sh` before the first real sync.

## Phase 1 — data mirror

**Create repos (manual, web UI):** the create API (`POST /api/v1/products/{account_id}`) is
**`501 Not implemented`** in production (the documented `/repositories/` API is stale), so create
each repo in the web UI first (`visibility: public`). The 23 still-to-create repos (id / title /
description, with NC + partial-mirror notes) are in [`new-repos.md`](new-repos.md); 7 already
exist (`carbon, cpad, fire, gbif, mappinginequality, mobi, social-vulnerability`) and only refresh.

**Generate jobs:** `./gen-source-sync.sh` (30 jobs; minio recipe exactly — `--transfers 2
--checkers 4 --bwlimit 50M --tpslimit 5 --retries 5`, opportunistic, 2 cpu / 4 Gi, one pod/bucket).

**Preview then sync (sequentially):**
```bash
./dry-run-local.sh rivers          # preview adds/updates/DELETES + excludes (no writes, no cluster)
./run-source-sync.sh rivers        # apply one job, wait for completion
./run-source-sync.sh               # all repos, smallest -> largest (gbif ~1.2 TB last)
```
Run **sequentially** (the runner does this): 30 jobs at `--bwlimit 50M` in parallel ≈ 1.5 GiB/s
of NRP egress — the opposite of gentle. Monitor: `kubectl -n biodiversity get jobs | grep source-sync`.

**Mirror-with-delete:** `rclone sync` makes the dest an exact copy, deleting stale source.coop
files. For the pre-existing repos this replaces older structure with NRP-canonical content —
**dry-run first.** This is the riskiest step: several pre-existing repos were populated from an
*older* layout of their NRP bucket that has since been restructured/re-versioned, so a blind
`sync` deletes the old-vintage files. That is usually intended (the data lives on NRP under new
paths), but it **breaks any citable `cboettig/<repo>/…` URL** to the old paths, so confirm before
running. The 2026-06 refresh dry-ran all 7 and split them:

- **Safe (0–2 benign deletions):** `social-vulnerability`, `mappinginequality`, `cpad` — synced.
- **`carbon` (~445 GiB), `fire` (~6 GiB):** full `sync`; old `cogs/*_2010|2018.tif` / 2022 CALFIRE
  vintages and build cruft removed, replaced by current NRP layout (decision: match NRP).
- **`gbif` (~1.2 TB):** dry-run separately before refreshing (the long pole).

**`copy` vs `sync` (per-repo `MODE` in `gen-source-sync.sh`):** a repo holding content that exists
**only on source.coop** (not a stale version of any NRP file) must NOT be mirror-with-deleted. Set
`MODE[repo]="copy"` so the job uses `rclone copy` (additive, never deletes). Currently:

| repo | mode | why |
|---|---|---|
| `mobi` | `copy` | A 27k-tile `tiles/**` XYZ pyramid, a whole `range-size-rarity-all/` layer, the original `SpeciesRichness_All`/`RSR_All` source rasters, and `LICENSE.txt` live only on source.coop (NRP public-mobi has just the reprocessed COG + hex). A `sync` would wipe them. |
| *(all others)* | `sync` | mirror-with-delete (default) |

## Phase 2 — STAC on source.coop (after the data mirror)

The mirrored `stac-collection.json` files still carry **NRP** hrefs. A second pass should rewrite
each mirrored collection so `self`/`root`/`parent`/`child` + asset hrefs point to the source.coop
copies (`https://data.source.coop/cboettig/<repo>/…`), drop the excluded HOLD sub-collections, and
stamp the correct (NC/SA) license. This makes source.coop a self-consistent catalog rather than a
set of NRP-pointing records. Not built yet — tracked as phase 2; keep it a separate, idempotent
job so re-running the data mirror doesn't require re-running the STAC rewrite.

## Existing-content audit (2026-06-16)

Audited all pre-existing `cboettig/*` (+ `berkeley-dse`, `espm-288`) repos: **none contain
non-redistributable data** (no WDPA/IUCN/ICCA/HydroBASINS). Several are **NC** (`fishbase`,
`carbon`, `mobi`, `mappinginequality`, `gbif`) — keep, but ensure NC labels. Several hold **older
versions** than NRP (`pad-us-3`, old `ca30x30`/`cpad`/`fire`) — stale, not a license issue.

Total in current scope ≈ 2.5 TB / ~44 k objects (gbif alone ≈ 1.2 TB).

## Private backup (MinIO) for datasets NOT on source.coop

Anything we can't publish to source.coop still needs an off-NRP backup — that's MinIO
(`catalog/sync/k8s/sync-public-*.yaml`). Status:

- **License-prohibited (source.coop impossible — MinIO is the ONLY off-NRP copy):**
  `wdpa`, `icca`, `iucn`, `hydrobasins` — ✅ all have MinIO sync jobs. **Keep these.**
- **Already MinIO-backed (uncatalogued/clipped, no source.coop):** `wyoming`,
  `datacenters`, `im3`, `ca30x30` (wyoming/ca30x30 restructuring tracked in #225).
- **NOT backed up yet — and shouldn't be until fixed upstream (don't back up a mess):**
  - `landfire` — **partial import**; complete it first (#203), then catalogue + back up.
  - `wlfw` — **migrate into `public-working-lands`** first (#226), don't back up standalone.
  - `working-lands` — back up after the wlfw consolidation + proper STAC (#226).
- **Redundant-backup candidates (space optimization, not urgent):** large *public*
  datasets ALSO mirrored to source.coop (`gbif` ≈1.2 TB, `carbon`, `wetlands`, `rap`, …)
  now have an off-NRP copy on source.coop, so their MinIO copy is redundant and could be
  dropped to save private-system space. Not needed yet ("so far we are fine") — revisit
  if MinIO fills up.
