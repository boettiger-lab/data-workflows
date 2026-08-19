# Pre-gate `verify-stac` sweep (data-workflows#509)

The Verify-STAC CI gate is **PR-triggered on changed `catalog/**` YAMLs** — deliberately,
so recipes are gated at creation. The corollary: any collection **published before a
check existed** is never retro-verified unless someone touches its recipe. This harness
runs the *current, full, data-backed* `scripts/verify-stac.py` against **every** collection
in the catalog so the pre-gate cohort is evaluated by today's rules — the systematic audit
required by #509's scope amendment.

## Run it

```bash
cd catalog/audit/pregate-verify-sweep
python3 enumerate-collections.py > /tmp/sweep/collections.tsv   # walk the STAC tree
./run-sweep.sh /tmp/sweep                                       # 8 parallel workers
python3 analyze-findings.py /tmp/sweep/all-results.txt          # per-category + per-collection
```

`run-sweep.sh` interleaves collections across `SLICES` workers (default 8) to spread the
big `COUNT(DISTINCT)` datasets, and caps each collection at `PERCOLL_TIMEOUT` (default
300 s). It posts SQL to the public duckdb-geo MCP, so it is not bound by laptop resources
— but keep `SLICES` modest (≤8) to stay friendly on the shared MCP.

## Snapshot — 2026-08-19 (266 collections, current checker)

`250 CLEAN · 16 HARD · 0 TIMEOUT · 0 ERROR`. Full run in `RESULTS-2026-08-19.txt`.

This is the first pass in which **every** collection has been evaluated by the current
rule set: the 8 collections that timed out on 08-17 all completed here (900 s per-collection
cap), and `check_hex_fid_matches_flat` (#549) landed *after* the 08-17 run, so the 161
collections clean then had never seen it. It immediately found one real
`hex-fid-mismatch` (`high-seas/hydrothermal-vents`, 720 of 720 ids disagree).

The 16 remaining HARD collections:

| what | colls | disposition |
|---|--:|---|
| **Wyoming vector family** (`wgfd-*`, `wyoming-places`, `wy-counties`, `sage-grouse-priority`, `pad-us`, `ungulate-migration`) | 11 | **Not a metadata fix.** Pre-#369 builds with no `_cng_fid`, so writing `table:columns` would trip the #369 gate — they need reprocessing, their recipes are no longer in this repo, and the work overlaps #225. Needs a scoping decision first. |
| `wyoming/blm-sma` | 1 | Genuinely broken build (277 of 865,059); spun out to **#561**. |
| `blm/acquisitions` | 1 | `hex-missing-features` (96,777 of 97,529) — surfaced only once the harness stopped scoring a failed verify as CLEAN. Needs the polyfill ground-truth triage. |
| `high-seas/hydrothermal-vents` | 1 | `hex-fid-mismatch` — the #549 class: the hex carries its own `_cng_fid` numbering. Needs a re-hex, or a hex rebuilt from the flat's ids. |
| `ca-dac` | 1 | **Stale row** — the sweep read this collection before the STAC fix landed mid-run; it verifies PASS now. |
| `high-seas/mpa-candidates` | 1 | `license-link-missing`, deferred in #560 pending canonical terms from the data owner. |

`blm/oil-gas-leases` is not in the list above only because it was fixed-in-name-only by the
old harness bug: it is genuinely HARD too (`declared-column-absent` on the hex `bbox`, plus
`hex-missing-features` 457,933 of 466,415), confirmed by an individual re-run. Both former
`CLEAN … exit=1` rows were real defects.

## Snapshot — 2026-08-17 (266 collections, checker at commit that fixed the truncation bug)

`161 CLEAN · 97 HARD · 8 TIMEOUT`. Full run in `RESULTS-2026-08-17.txt`.

> **Before triaging this list, note the checker fix that produced it.** The first pass
> reported **1,474 `declared-column-absent` findings across 50 collections** — all false.
> `check_declared_schema_matches_data` row-parsed the MCP's 50-row markdown preview as if
> complete, so every asset with >50 columns had its columns-past-50 read as absent (SVI
> county: 162 cols → 112 false). Fixed by computing the set-difference in SQL (+ a global
> guard that refuses a truncated preview). `declared-column-absent` fell to **59 real
> findings across 28 collections**. Re-run after any checker change.

### HARD findings by category (collections affected)

| category | colls | disposition |
|---|--:|---|
| `hex-missing-features` (#535) | 50 | **Triage each**: legit sub-cell shortfall (features smaller than one cell polyfill to zero) → document in the asset description; a real dropped chunk / silent coverage cap → re-hex. Distinguish by the *magnitude* and *size* of the missing features (a 1-of-84,120 SVI drop is sub-cell; PAD-US fee 64,576-of-296,456 = 22% is suspicious and needs the area check). |
| `declared-column-absent` (#534) | 28 | Real stale STAC — the `table:columns` declares a column the parquet lacks. Metadata fix (drop/rename). Clusters: BLM MLRS (8), swap/missouri ccs (7), overturemaps, iucn/taxonomy (9 list-columns). |
| `table-columns-collection-level` | 14 | `table:columns` sits at collection level, not on the asset. Metadata fix. Mostly the **Wyoming** + **cpad** families. |
| `parquet-no-table-columns` | 14 | Parquet asset carries no `table:columns` at all. Same Wyoming/cpad families. |
| `hex-href-not-glob` | 14 | Hex `href` is a bare dir, not `hex/h0=*/data_0.parquet`. **Wyoming** family. Metadata fix. |
| `hex-no-native-res` / `hex-no-parent-res` | 14 | Hex asset omits `h3:native_resolution` / `h3:parent_resolutions`. **Wyoming** family. Metadata fix. |
| `hex-duplicate-feature-cell-rows` (#509) | 10 | Row-dup remnants NOT in the original dedup sweep (rivers/american-rivers *nri/roo-cjest/wild-scenic*, overturemaps/counties, tpl/landvote, ecoregion, swap ranges). Cheap `SELECT DISTINCT *` — the known, provably-lossless pattern. |
| `license-*`, `nav-parent-missing`, `temporal-extent-missing`, `categorical` | 1–2 each | Singletons on `data` (root), tpl/high-seas, cgs/sierra-nevada. Metadata fixes. |

### Two mechanical clusters dominate the metadata findings

- **Wyoming family (13 collections)** — `wgfd-*`, `rap-*`, `wy-counties`, `sagebrush-design`,
  `nlcd-2024`, `sage-grouse-priority`: built with an older STAC template missing the hex
  glob, `h3:*` resolutions, and per-asset `table:columns`. Batch-fixable.
- **cpad family (3)** — `cpad-holdings`, `cpad-units`, `cced`: `table:columns` at collection
  level + a parquet asset with none.

### 8 TIMEOUTs (exceeded 300 s — big `COUNT(DISTINCT)` / many assets)

`iucn/iucn-ranges-2025`, `carbon` (meta), `facts/common-attributes-2026-06`, `nci-frontiers`,
`census-2025/sldu`, `land-cover/cgls-lc100-2019`, `land-cover/nlcd` (meta), `wui`. Re-run
individually with a larger `PERCOLL_TIMEOUT`, or verify per-child for the meta collections.

## Remediation classes (do NOT auto-fix — most are per-collection judgment or cluster jobs)

1. **Metadata-only** (Wyoming, cpad, declared-column-absent, singletons) — edit the S3 STAC
   JSON, `rclone copyto`, re-verify. Batch by family.
2. **Row-dup** (`hex-duplicate-feature-cell-rows`) — the `SELECT DISTINCT *` rewrite; template
   `catalog/audit/k8s/hex-dedup-sweep.yaml`. Provably lossless (byte-identical dup rows).
3. **Missing-features** (`hex-missing-features`) — per-collection: doc-note vs re-hex. A re-hex
   is a cluster job; a shortfall that is genuinely sub-cell only needs a description sentence
   the `_COVERAGE_NOTE` matcher accepts. **File real drops against #535 / a per-dataset rebuild
   issue**, not the dedup batch (they can't be rewritten from what's on S3).
