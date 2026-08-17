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
