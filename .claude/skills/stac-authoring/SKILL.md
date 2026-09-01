---
name: stac-authoring
description: >-
  Author and verify STAC collection metadata for a published dataset: the verify-stac.py gate, the user-facing description register, table:columns placement, SPDX license rules, categorical values arrays, hex per-feature duplication notes, h3:* resolution declarations, and registering a collection in its parent sub-catalog. Use whenever writing or editing a stac-collection.json or a dataset README.
---

# STAC Authoring

Everything needed for **Step 5 (Document)** and **Step 6 (Register in the parent sub-catalog)**.

Write STAC and README to `/tmp/` and upload with `rclone` — this repo never contains STAC JSON or README files (AGENTS.md Hard Boundary 1).

### ⛔ Verify the STAC — don't hand-check the rules

Every STAC rule below is enforced by **`scripts/verify-stac.py`** (license, nav links,
asset keys, hex glob, `h3:*` resolutions, `vector:layers`, `table:columns` placement,
per-feature-dup warnings, categorical completeness + PMTiles fields via the two
sibling linters, and a **data-backed `values` == ingested `DISTINCT`** check via the
MCP that automates the #114/#294 lesson). Do not re-verify these by hand or by
spending agent context on MCP `SELECT DISTINCT` sweeps — run the gate.

```bash
# 1. PRE-PUBLISH (static, against the /tmp file you just wrote):
scripts/verify-stac.py --no-data /tmp/stac-collection.json
#    Fix every HARD finding before rclone copyto. (Data checks need the data live, so
#    they run post-publish; --no-data skips them here.)

# 2. POST-CLUSTER (full, against the live S3 STAC, once data + STAC are published):
scripts/verify-stac.py --bucket <bucket> --dataset <dataset>
#    Must exit 0 (no HARD findings). ADVISORY lines are informational.
```

**A `*-check-failed` finding is HARD, and it means UNVERIFIED — not broken data.** If a
data-backed check cannot reach the MCP (a transport failure, a query that will not
complete), the run reports HARD rather than passing quietly: a gate that did not execute
is not a green light. `MCPClient.query` already retries once, so re-running usually clears
a transient blip. Read it as "check again", not as a defect in the collection — and never
"fix" it by making the check advisory, which is exactly how an unverified collection came
to read as clean (#509).

CI runs the same verifier on the PR (`.github/workflows/verify-stac.yml`), deriving the
collection(s) from the `s3://` paths in the changed `catalog/**` YAMLs. **The gate
evaluates the produced artifact, not the proposal:** the cluster run lands after the PR
opens, so a RED check at PR-open (STAC not published yet) is correct — don't merge
before the recipe has actually produced valid output. GitHub status checks don't
auto-refresh from S3, so **after your cluster jobs finish, re-fire the check** (Actions
→ Verify STAC → *Run workflow*, or it re-runs on the next push). Merge requires it green.

**README.md MUST include:**
- A MapLibre GL JS example with the correct `source-layer` (= last segment of `--dataset`), documented prominently
- A DuckDB example with the full public parquet URL

### ✍️ Descriptions are USER-FACING COPY — agents quote them to end users

Asset, column and collection `description` fields are not internal documentation. The geo-agent
reads them and **quotes them, nearly verbatim, into answers for end users** — for ca-30x30 that is
state-agency staff and conservation partners, often non-spatial. Write them as product copy, not as
notes to the next engineer (data-workflows#512, where issue prose reached a user as
"joining at res-8 avoids the ~11 pp overstatement that a coarse `GROUP BY` would introduce").

**Say:** what the asset is, what it is for, what resolution it is at, and the one thing a consumer
must know to use it correctly. Spell things out — "resolution 8", not "res-8".

**Do NOT put in a description:**
- issue or PR numbers, repo names (`data-workflows#506`) — those belong in the issue and the commit;
- defect magnitudes or what a previous consumer got wrong ("overstates conserved share by ~11pp");
- unexplained abbreviations (`pp`), bare column/asset keys as the subject of a sentence;
- shouted imperatives (`ALREADY A MEAN`, `do NOT re-aggregate`, `NEVER SUM`) — they read as
  scolding when quoted, and prose imperatives are exactly what leaks into an answer.

**Express a real constraint as a short SQL example instead** — it is clearer than an imperative and
does not leak as prose:

```sql
-- correct: combine cells weighted by land area
SELECT SUM((w1 + w2) * land_area_km2) / SUM(land_area_km2) FROM …
-- wrong: weighting by a cell COUNT assumes equal-area cells — H3 cells are not equal-area
-- wrong: taking the largest or any single cell's value overstates the share
```

> The count-weighted version of that example (`… * nland) / SUM(nland`) was what this file
> recommended until #522, and it is latitude-biased: over California (32.5N-42N) it returned a
> 25.684% conserved share against an area-weighted 26.135%. If a rollup asset exposes only a
> child-cell *count*, ship the child-cell *area* alongside it — the correct query should be the
> short one, not the one requiring an `h3_cell_area()` call the consumer has to remember.

The mechanical rules elsewhere in this file still apply on top of this: per-column text stays
**identical across assets** (the mcp-data-server#303 fold), the hex per-feature-duplication note
still has to be present and still has to match what `verify-stac.py` looks for (phrases like
"repeated on every … cell"), and the H3 area recipe still must not be inlined (#389). Plain register,
same guarantees.

**Publishing lags by ~15 minutes.** `mcp-data-server` refreshes its STAC cache on a **~15-minute**
cycle, so right after `rclone copyto` the agent (and the app) still read the previous text — verified
during #512, where `verify-stac.py` (which fetches S3 directly) saw the new copy while
`get_stac_details` returned the old, then agreed after the refresh. So: verify prose against the S3
URL for correctness, and wait out the cycle before judging what an agent or the app will quote. **No
cache-invalidation or restart is needed** — do not go reaching into the MCP's namespace for one.

**One text per column NAME per collection.** The `#303` fold is per column *name* across every asset
in the collection, and **first-seen wins**, so a column documented differently on two assets loses
one version silently. Two traps, both hit in #512:
- Adding a new hex-like asset with its own wording for `h10`/`h9`/`h8`/`h0` meant the older asset's
  text won — and that text said "one row per (feature, h10) pair", which was true there and **false**
  for the new per-cell assets. Keep shared H3 columns grain-neutral and identical; state grain in the
  asset `description`, which is always rendered.
- Appending a hex-only clause to a column that also exists on the flat GeoParquet (e.g. "…repeated on
  every hex cell — dedup first") makes the two differ, so the clause is dropped. Put that note in the
  hex asset's `description` instead. After editing, check no column name carries two different texts
  within the collection — `verify-stac.py` reports this as `column-description-divergent`
  (ADVISORY today; it becomes HARD once the pre-gate catalog is fold-clean, #509).

**The title and description state the FOOTPRINT, not which tranche you ingested.** A set of
whole administrative or hydrologic units is **never** a state extent, and a consumer — human or
model — trusts the title over the geometry. `usgs-nhdplus-hr-flowline` was titled *"(California)"*
and said *"COVERAGE IS CALIFORNIA ONLY"*, both true about which VPUs had been ingested and both
read as claims about the footprint, which is 13 whole HU4 units with **30.3% of its stream length
in Nevada, Utah, Oregon and Arizona**. A model skipped the California mask and its headline number
was 8.5 points wrong — the same mechanism as the pinyon-juniper defect (#505). So:

- **Title the unit set** — "…(13 California hydrologic units)", not "…(California)". Same for
  counties, ecoregions, watersheds, and every later tranche of a national build.
- **State the footprint near the top of the description**: what the units are, that they are not
  clipped to the region, how much lies outside, and the mask a region-level statistic needs
  (for California, join `h8` + `h0` against the `ca30x30-ecoregion` hex). Give the mask as a short
  SQL example, per the register rules above.
- **Never write "X ONLY" for "only the X tranche is ingested so far"** — say the ingest scope and
  the footprint as two separate facts.
- The `bbox` is usually already correct; it is the prose that lies. `verify-stac.py` flags a title
  naming one US state whose bbox reaches >1° outside it with no footprint sentence
  (`title-names-state-but-bbox-exceeds-it`, ADVISORY) — the fix is the sentence, not a narrower bbox.

**stac-collection.json MUST include:**

- **License — REQUIRED on every collection.** Set the top-level STAC `license` field to the **SPDX identifier** of the upstream data license (e.g. `CC-BY-4.0`, `CC-BY-NC-4.0`, `CC-BY-SA-4.0`, `CDLA-Permissive-2.0`, `public-domain`). Use `"other"` **only** when no SPDX id applies, and `"various"` **only** for a meta-collection whose children genuinely differ — never as a lazy default. For `other`/`various` (and recommended for all), add a license link: `{"rel": "license", "href": "<canonical terms URL>", "type": "text/html"}`. **Exception — a meta-collection (one with `child` links) may use `various`/`other` WITHOUT a license link:** its real licenses live on the child collections (each carrying + verified for its own license), and redistribution gating (source.coop excludes, etc.) keys on those per-child licenses, not the parent. A single parent-level link would misrepresent genuinely mixed children. `verify-stac.py` enforces the link only on **leaf** collections (and always for `proprietary`). **Verify the real upstream terms — do not guess `proprietary`.** The license drives redistribution decisions (e.g. whether a dataset may be mirrored to source.coop); a wrong value is a compliance risk. NonCommercial / ShareAlike licenses are fine but MUST be recorded as such (`CC-BY-NC-*`, `CC-BY-SA-*`) so downstream users aren't misled. US federal works = `public-domain`.

- **Directly contributed data with no published terms — you are the one who states them.** A
  dataset handed over by a colleague with **no citation, no attribution, and no URL** has a
  *complete* provenance: there is nothing upstream to find. Do not treat it as missing metadata
  to backfill, and do not invent a terms URL to clear the gate. But `proprietary` without a
  `{"rel": "license"}` link is a HARD finding, and no upstream page exists to link — the rule
  assumes one always does, so the gate is otherwise unsatisfiable. The resolution: **publish the
  terms statement beside the data** (`s3://<bucket>/<dataset>/LICENSE.md`) and link that, exactly
  as #417 treats a stored raw + checksum as the provenance when no stable public link exists.
  The document must **grant nothing** — it records what was and was not given: contributed
  directly, no public source, no citation, no named attribution, no redistribution right, reuse
  elsewhere needs the owner's permission. Keep `license: "proprietary"`, which is the correct
  advisory signal to the mirror-scope auditor (no grant → not mirrored). `verify-stac.py` reports
  `license-terms-self-hosted` (ADVISORY) whenever a license link resolves to our own bucket, so
  the special case stays visible and is never mistaken for a verified upstream grant. Worked
  example: `high-seas/mpa-candidates` (#579).

- **Provenance — record the access date and the staged raw's fingerprint (#417).** A provenance
  *chain* (`rel: about` to the landing page, `rel: source` to where you actually read it,
  `providers` producer → host → processor) is not enough on its own: without a **date** it cannot be
  resolved to an edition, and the date is unrecoverable later. Publishers overwrite in place and
  links rot, at which point your staged copy plus its checksum *is* the provenance. On the
  collection, record:
  - `sci:citation` (add the scientific extension) carrying the **access date** — machine-readable,
    so a downstream consumer cites the STAC rather than a bucket listing;
  - `version` (version extension) **only if upstream publishes an edition label** — `fveg22_1` yes,
    a guessed "October 2025" no;
  - `created` / `updated` on the collection, and **`created` per asset**, each measured from the
    object itself — this is what keeps "which asset came from which conversion" answerable (#549,
    where a flat and hex built 33 days apart carried different `_cng_fid` numbering);
  - the staged raw's **path, size and checksum in the description** — recomputed from the object,
    never transcribed.
  ⛔ **Do NOT add a `raw` asset** whose href points under `raw/`, tempting as it is: the
  mirror-scope auditor keys the `raw/` backup exclusion on STAC asset hrefs, so a raw asset flips the
  whole bucket into the mirrored-exempt list (#545 — how `population` ended up mirroring 10 GiB of
  re-downloadable source). Description text is just as citable and carries no href.
  ⛔ **Never let a number that isn't an edition stand in for one.** A temporal extent is content
  coverage; a product-line name (`nwi-v2`) is not a release; a derived file's mtime is the
  conversion, not the pull. All three were read as edition stamps downstream and produced retracted
  claims. If the edition is not determinable, state that plainly in the description.

- **Temporal extent — RFC 3339, or the dataset vanishes from the served catalog.** Every
  `extent.temporal.interval` endpoint must be a full RFC 3339 date-time with a timezone
  (`"1920-05-15T00:00:00Z"`), or `null` for a genuinely open start/end. This is not
  cosmetic: pystac parses these **eagerly** when it loads a collection, so one malformed
  value makes the entire collection fail to load for every MCP consumer — the dataset
  simply isn't there, with nothing but a warning in the server log. Seven BLM MLRS
  mineral collections shipped this way and were invisible for weeks.
  **When composing the string from a query result, slice the date part explicitly**
  (`str(v)[:10]`): the MCP `query` tool renders a DuckDB `DATE` as
  `"1974-03-01T00:00:00.000000"`, so appending `"T00:00:00Z"` to the raw value produces a
  doubled time component. `verify-stac.py` HARD-fails a non-RFC-3339 endpoint, a missing
  interval, and a start that is after its end.

- **Navigation links — every collection needs all four:**

  ```json
  "links": [
    {"rel": "self",   "href": "https://s3-west.nrp-nautilus.io/<bucket>/<path>/stac-collection.json", "type": "application/json"},
    {"rel": "root",   "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",        "type": "application/json"},
    {"rel": "parent", "href": "<URL of the collection that links to this one as a child>",             "type": "application/json"},
    {"rel": "child",  "href": "<URL of each sub-collection>",                                          "type": "application/json"}
  ]
  ```

  Rules:
  - `self` = the collection's own S3 URL.
  - `root` = always the NRP root catalog (`public-data/stac/catalog.json`).
  - `parent` = the collection that holds this one as a `child` link. For top-level bucket collections this is the root catalog. For nested sub-collections (e.g. `public-rivers/american-rivers/dam-removal/`) this is the domain collection (`public-rivers/american-rivers/stac-collection.json`), **not** the root.
  - `child` = `"rel": "child"` (not `"item"`) for every sub-collection. `"rel": "item"` is for individual STAC Items (features), not Collections.
  - **Without `self`/`root`/`parent`, geo-agent cannot traverse the tree and the collection won't expand.**

- **Asset keys encode the dataset, not the format.** Never use generic keys (`pmtiles`, `geoparquet`, `h3-parquet`, `parquet`, `hex`) — they collide and break downstream apps. Use `{last-segment}-{format}`:

  | Asset | Pattern | Example (`--dataset census-2025/sldl`) |
  |---|---|---|
  | GeoParquet | `{name}-parquet` | `sldl-parquet` |
  | PMTiles | `{name}-pmtiles` | `sldl-pmtiles` |
  | H3 hex | `{name}-hex` | `sldl-hex` |
  | COG | `{name}-cog` | `sldl-cog` |

  Multi-layer collections: prefix with collection context (`cpad-holdings-parquet`, `cpad-units-hex`).

- **Hex asset `href` MUST use the Hive-partitioned glob — never a bare directory:**
  - ❌ `.../census-2025/sldl/hex/`
  - ✅ `.../census-2025/sldl/hex/h0=*/data_0.parquet`

- **Any vector asset with named layers** (PMTiles, GDB, GPKG, etc.) MUST include `"vector:layers": ["<name>"]`. For PMTiles the layer name = last segment of `--dataset`.

- **`table:columns` goes on each parquet asset — NOT at the collection level.** Put it inside the asset object for the GeoParquet and hex assets. Do not add a top-level `table:columns` to the collection. `verify-stac.py` HARD-fails a collection-level `table:columns`.

  **Every queryable parquet asset is fully self-describing** — it carries the full per-column schema (name, type, description, `values`), the SAME text on the flat GeoParquet and the hex. This is deliberate: the mcp-data-server renderer dedups identical per-column descriptions across assets at read time (mcp-data-server#303), so full-both costs nothing to the LLM; and a consumer targeting a single asset directly still gets the full schema. That last point is not optional — **raster-derived datasets have a hex but no GeoParquet**, so the hex must stand alone. The single authority is the **build/relocation tool** (one source schema written identically to every asset), never a hand-edit of one asset — identical text means the #303 "first-seen wins" merge never drops anything.

  Each parquet asset documents exactly the columns it contains:
  - **GeoParquet asset** (vector, when present): include the geometry column (`Shape`, `geom`, or `geometry`).
  - **Hex asset**: full per-column descriptions identical to the flat (minus the geometry column); include the H3 index columns (`h0`, `h8`, `h9`, `h10` etc.) and `_cng_fid`/`bbox`. The hex is the primary query target (and the sole one for rasters), so it is never "lean."
  - **COG assets**: no `table:columns` needed (not SQL-queryable).

- **`_cng_fid` is the universal per-feature id — REQUIRED on every vector asset, flat GeoParquet *and* hex (#369).** cng-datasets `convert_to_parquet` synthesizes it on every conversion (always, additive, row-unique), so one uniform key works for dedup / `COUNT(DISTINCT)` across all datasets instead of per-dataset id discovery (the over-count class behind #309). Source ids (`ramsarid`, `tpl_id`, `GEOID`) may accompany it for cross-collection joins but never replace it. `verify-stac.py` **HARD**-fails a vector flat GeoParquet (has a geometry column) or a vector hex that lacks `_cng_fid`; if the data genuinely lacks it, reprocess through cng-datasets. **Exempt:** raster-derived hex (a raster reduce into H3, not a feature conversion — detected as a hex/`h0=*`-partitioned asset in a collection with no vector source; covers carbon/ghs-pop *and* the richness/cwhr/gbif reductions). A **non-spatial** parquet table (no geometry, not a hex) is **ADVISORY** — it may be a feature fact table that should carry `_cng_fid` (e.g. tpl `…-funding`) or a legit lookup/crosswalk/coefficient/scores table; use judgment.

- **PMTiles assets MUST carry tile-accurate `table:columns` (data-workflows #283/#320), in LEAN form.** The geo-agent (and human app authors) can only learn which fields are stylable/filterable in MapLibre from the PMTiles asset's own schema — an empty `table:columns` forces them to byte-range the `.pmtiles` footer. **Empirically, our tippecanoe step keeps ALL attribute columns: the tile field set is just `GeoParquet attrs − geometry + _cng_fid`** (types coarsened to String/Number/Boolean). So the standard is to **mirror the canonical GeoParquet schema onto the PMTiles asset** — do NOT hand-scrape thin metadata from the footer, and do NOT duplicate the prose:
  - **Lean columns:** each PMTiles column carries **`name` + `type` + `values`** (the `values` enumeration is the styling-critical part for categoricals) — copied from the GeoParquet column of the same name. **Omit the prose `description`** — it stays CANONICAL on the GeoParquet asset (duplicating it across 3 assets just bloats agent context; the agent reads definitions there).
  - Drop the geometry column; include `_cng_fid` (present in tiles).
  - Keep `vector:layers` (the source-layer id list).
  - **Continuous (choropleth) layers only:** add the **nodata sentinel** and flag the **intended value column** for styling, as a short `description` on that one column (e.g. SVI `RPL_THEMES = -999`) — these are viz-specific and not inferable from the GeoParquet schema.
  - **Generate it** with `scripts/mirror-pmtiles-columns.py <stac-url>` — it reads the footer to *validate* the field set (and flags the rare genuine-subset case, e.g. SVI, where tippecanoe really did drop columns), mirrors the GeoParquet `name`/`type`/`values`, and writes the updated STAC to `/tmp`. Then `rclone copyto` to S3.
  - Because PMTiles mirrors the GeoParquet, **fix the GeoParquet/hex categoricals FIRST** (the #303 work), then mirror — otherwise you copy incomplete `values`.
  - Gate with `scripts/lint-stac-pmtiles-fields.py <stac-collection.json|url>` (companion to `lint-stac-categorical.py`); it requires `name` + `type` and does NOT require descriptions.

- **Hex assets MUST declare their H3 resolutions explicitly** via `h3:native_resolution` and `h3:parent_resolutions` on the asset itself. Column-name presence (`h10`, `h9`, …) is not enough — downstream tools shouldn't have to enumerate `table:columns` to find out what resolutions exist. `h3:native_resolution` is the finest resolution (one row per feature-cell at this res); `h3:parent_resolutions` is the list of rollup resolutions, which MUST include `0` (the partition key).

- **Vector (GeoParquet/PMTiles) assets MUST flag per-feature ROW duplication — and you MUST first decide whether it is *true* duplication or *real* multi-row data.** A source file often stores one logical feature as several rows sharing a feature id (a Ramsar site split into polygon parcels; a ballot measure spanning multiple counties). Two opposite causes demand opposite rules, and confusing them silently corrupts answers (data-workflows #309):
  - **REPEATED** — the per-feature value is *copied* onto every row (e.g. a measure's total funds repeated on each county row). A raw `SUM` double-counts → **dedup by the key first** (`SELECT DISTINCT key, col …` or `GROUP BY key`), and `COUNT(DISTINCT key)` is the feature count.
  - **VARIES** — genuinely distinct per-row records that share a key (e.g. one conservation site funded by several *sponsors*, each a *different amount*). Here `SUM` is **correct** and dedup would **undercount** by dropping real rows. A repeated polygon + repeated attributes is NOT proof of duplication — a sponsor split looks identical except the varying amount.

  **Two duplication axes — and `_cng_fid` only fixes one of them.** cng-datasets always assigns `_cng_fid` as a synthetic id that is *one per input row* (never derived from a source id). So:
  - **Axis 1 — feature → H3 cell** (hexing makes one polygon span many cells). Dedup key = `_cng_fid` (or `h<N>`). `COUNT(DISTINCT _cng_fid)` collapses the cell expansion. This is the standard hex guidance below.
  - **Axis 2 — upstream source rows** (the *input file* already holds several rows per logical entity). Dedup key = an **upstream domain id** (`ramsarid`, `landvote_id`, WDPA `SITE_ID`). `_cng_fid` is unique per row, so it does NOT collapse this — `COUNT(DISTINCT _cng_fid)` still counts rows/polygons, not entities.

  For most datasets each input row *is* one logical feature, so the two keys coincide and only axis 1 exists — that is why the standard guidance leans on `_cng_fid`. Axis 2 only appears in files with upstream duplication (ramsar, landvote); there the domain id is the dedup key, and **the hex asset must also carry that domain id** or it cannot be deduped to entities (e.g. landvote's hex carries only `_cng_fid`, so it can't be reduced to distinct measures — a gap). Auditing on a per-row id always reports "clean", masking axis 2.

  **The decisive test is data-backed: does the value VARY within the key?** Do NOT guess the key from a column name — a 34%-blank source id (PAD-US `Source_PAID`) or a class label that covers thousands of parcels (Landmark `name`) fakes duplication, and a per-row id (`_cng_fid`) hides it. Run the auditor with the *upstream domain id* as `--key` (it uses the duckdb-geo MCP, not local duckdb):
  ```bash
  scripts/audit-feature-dup.py <parquet-url|stac-url --asset KEY> --key <feature-id-col>
  ```
  It reports rows vs `COUNT(DISTINCT key)`, warns on blank keys, classifies each column REPEATED vs VARIES, and quantifies raw-vs-deduped `SUM` inflation. Then document the verdict in the asset's `table:columns`: name the key, mark REPEATED columns "dedup before SUM", and (if any) note VARIES columns are safe to SUM. A clean one-row-per-feature file needs no note.

- **Hex assets MUST flag per-feature duplication — at the hex ASSET-description level, NOT per-column.** One hex row = one (feature, cell) pair, so any column that represents a per-feature total — area (`GIS_Acres`, `SHAPE_Area`), length (`SHAPE_Length`), population, count, amount, funding, intensity — is repeated on every cell the feature covers. Put this warning (name the pattern + the **dedup key**, list the affected columns) in the **hex asset's `description`**, because the mcp-data-server#303 renderer keeps per-column descriptions identical across the flat and hex (single authority) and would silently drop a per-column note that differs between them — whereas the per-asset `description` line is always rendered. `verify-stac.py` accepts the note at the asset (or collection) level. (Raster hex: the asset note states reducer semantics instead — e.g. "`sum` reducer, SUM is the catalog total" or "mean density → × cell area for totals".) The two safe patterns:
  - **SUM after dedup** (the attribute is a real per-feature value): `SELECT DISTINCT <feature_key>, <attr> …` or `ROW_NUMBER() OVER (PARTITION BY <feature_key>)` before aggregating.
  - **Area/extent from the H3 footprint** (when there is no trustworthy source value): the generic recipe — `SUM(h3_cell_area(h<N>, 'km^2'))` over DISTINCT cells, exact per cell, **never** a nominal per-resolution constant — lives in `mcp-data-server/h3-guide.md`. **Do NOT inline that formula into the column description** — it is generic guidance the geo-agent already reads from the h3-guide, and a copy baked into STAC goes stale and becomes actively harmful (a nominal-constant copy undercounted the ca-30x30 California extent ~6%, mcp-data-server#294 / #389). Just flag the column as a per-feature total not to be SUMmed on hex; the agent derives area from the h3-guide.

  Columns that are safe to aggregate on hex (H3 indexes, `_cng_fid`, `bbox`) don't need a warning. If no column on the hex asset is safe to SUM, say so once in the collection description too.

  ```json
  "assets": {
    "sldl-parquet": {
      "href": "https://…/sldl.parquet",
      "type": "application/x-parquet",
      "title": "…",
      "table:columns": [
        {"name": "GEOID", "type": "string", "description": "…"},
        {"name": "ALAND", "type": "int64", "description": "Land area in m² of the source district polygon."},
        {"name": "geometry", "type": "geometry", "description": "Feature geometry (GeoParquet)"}
      ]
    },
    "sldl-hex": {
      "href": "https://…/sldl/hex/h0=*/data_0.parquet",
      "type": "application/x-parquet",
      "title": "…",
      "h3:native_resolution": 10,
      "h3:parent_resolutions": [9, 8, 0],
      "table:columns": [
        {"name": "GEOID", "type": "string", "description": "…"},
        {"name": "ALAND", "type": "int64",
         "description": "Land area in m² of the source district polygon. **Repeated on every hex row the district covers — never SUM(ALAND) on hex data; dedup first (SELECT DISTINCT GEOID, ALAND).** For area from the H3 footprint see the h3-guide."},
        {"name": "h10", "type": "uint64", "description": "H3 cell ID at resolution 10 (native resolution; one row per (feature, h10) pair)."},
        {"name": "h9",  "type": "uint64", "description": "H3 cell ID at resolution 9."},
        {"name": "h8",  "type": "uint64", "description": "H3 cell ID at resolution 8."},
        {"name": "h0",  "type": "int64",  "description": "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."}
      ]
    }
  }
  ```

  For **coded categorical** columns, the description MUST list all valid values in `CODE=Definition, …` format and include a `"values"` array. Discover actual values via DuckDB before writing:
  ```sql
  SELECT column_name, COUNT(*) AS n FROM read_parquet('s3://…') GROUP BY column_name ORDER BY n DESC
  ```
  Example:
  ```json
  {"name": "owner_type", "type": "string",
   "description": "Owner type code. Values: FED=Federal, STAT=State, LOC=Local, NGO=Non-governmental/non-profit, TRIB=Tribal/Indigenous, PVT=Private, UNK=Unknown",
   "values": ["FED", "STAT", "LOC", "NGO", "TRIB", "PVT", "UNK"]}
  ```
  Missing definitions cause LLM agents to guess values (e.g. `WHERE owner_type = 'Federal'` instead of `'FED'`) and return empty results.

- **Categorical rasters (COG assets with discrete pixel-value classes):** the COG asset's `raster:bands[0]` MUST include `classification:classes` (STAC classification extension v2.0.0). Each entry: `{ value, name, description, color_hint }` where `color_hint` is a 6-character RGB hex (no leading `#`). Add `https://stac-extensions.github.io/classification/v2.0.0/schema.json` to `stac_extensions`. Do **not** use the legacy `class_values` field from the raster extension — geo-agent reads `classification:classes` and `color_hint` to build both the discrete legend swatches and the titiler categorical colormap; without those colors the layer falls back to a continuous gradient. Use the dataset's standard published palette where one exists (NLCD MRLC colors, etc.); otherwise pick distinguishable accessible colors and note the choice in the asset description.
  - ⛔ **Fill / no-data codes NEVER appear in `classification:classes` (#628).** That list is exactly what a consumer turns into a render colormap, so every entry in it gets *painted*. A fill code equal to the band `nodata` is at least masked and costs only a junk legend row; a fill code that is **not** the declared nodata paints solid over real ground — LANDFIRE VCC shipped `-1111` grey and `32767` white across ~6% of CONUS that way, and a client app cannot work around it because the raster branch of geo-agent's catalog reader takes `classification:classes` verbatim with no config override. Left out of the list, a fill value maps to nothing and renders transparent — which is what fill should do. Document fill codes in the collection description and the hex asset description (the no-data-sentinel rule below), never as classes. `lint-stac-categorical.py` HARD-fails both forms, so `verify-stac.py` does too.
  ```json
  "stac_extensions": [
    "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
    "https://stac-extensions.github.io/classification/v2.0.0/schema.json"
  ],
  "assets": {
    "nlcd-cog": {
      "raster:bands": [{
        "name": "land_cover_class", "data_type": "uint8", "nodata": 0,
        "classification:classes": [
          {"value": 11, "name": "Open Water", "description": "…", "color_hint": "466B9F"},
          {"value": 41, "name": "Deciduous Forest", "description": "…", "color_hint": "68AB5F"}
        ]
      }]
    }
  }
  ```

- **Per-feature row duplication / NULL finest-parent cells / no-data sentinels (data-workflows #309, gated by #311).** Three aggregation traps the geo-agent accuracy sweep surfaced — document each on the relevant asset:
  - **Repeated features (polygon/point assets).** Handled by the REPEATED-vs-VARIES per-feature row-duplication rule above — run `scripts/audit-feature-dup.py` to get the verdict and document it. `verify-stac.py`'s `polygon-row-dup-candidate` **ADVISORY** is just the automatic CI tripwire that flags a `rows ≫ COUNT(DISTINCT id)` candidate; treat it as a prompt to run that auditor, not a defect on its own (the signal over-flags — the column may be a label or provenance key, not the feature id).
  - **NULL finest-parent cells.** If the hex build caps very large features at a coarser native resolution (WDPA: `h9` is NULL for the 1,297 biggest features, `h8` is complete), the hex asset description MUST name the complete column and say joins should use the coarsest shared resolution (or `h3_cell_to_parent()`), not the finest. `verify-stac.py` **HARD**-flags an undocumented NULL finest hex column.
  - **No-data sentinels.** Document sentinel/fill codes (e.g. land-cover `0`/`200`) so consumers `WHERE col NOT IN (...)` before `SUM`/`AVG` — an undocumented sentinel poisons aggregates to `NaN`.

  ⛔ **MEASURE every added column's range and sentinels — never document one from upstream docs or
  memory.** When a build introduces columns new to this catalog, run one query per new column
  (`MIN`/`MAX`, `COUNT(*) FILTER (WHERE col < 0)`, distinct count) *before* writing STAC. This is
  the #518 lesson generalised, and it recurred three times in one session while fixing #518
  (data-workflows #205/#525):
  - `-9999` on four NHDPlus VAA columns (and `-9` on a fifth) — **the same 2,745 rows** — was
    documented nowhere in the first draft; an unfiltered `AVG(slope)`/`MIN(totdasqkm)` is poisoned.
  - Worse than omission: a sentinel note copied from upstream documentation said "check for
    negative values", which would have told consumers to discard **real** below-sea-level
    elevations (10,349 rows, min −85.61 m in Death Valley). **A negative value is not automatically
    a sentinel** — filter the exact sentinel (`<> -9998`), never a sign test, unless you have
    measured that no legitimate negatives exist.
  - A `values` array copied from a sibling collection missed 13 codes actually present. Coded
    domains come from the authoritative source table (#294), and `values` from the ingest.
  Record the measured ranges in the dataset's `BUILD.md` so the next reader inherits evidence
  rather than assumption — see `catalog/usgs-nhd/k8s/nhdplus-hr/BUILD.md` for the pattern.

- **Point datasets:** `description` or `"processing:notes"` MUST state each point resolved to one H3 cell at the processing resolution, and name the resolution. Example: *"Point observations were hexed to H3 resolution 10 (each point → one ~15 000 m² cell). Multiple points within the same cell are not deduplicated."*

## Step 6: Register in the parent sub-catalog

**The STAC catalog is a TREE.** Datasets belong in their domain/bucket sub-catalog, not the root. Root `public-data/stac/catalog.json` only links top-level sub-catalogs (e.g. `public-high-seas`, `public-padus`, `public-census`).

Before linking:
1. Check for existing sub-catalog: `curl -s https://s3-west.nrp-nautilus.io/<bucket>/stac-collection.json | jq '.links[] | select(.rel=="child")'`
2. Exists → add child link there.
3. Brand-new bucket/domain → create bucket-level `stac-collection.json`, register children in it, then link that bucket-level collection from root.

```bash
curl -s https://s3-west.nrp-nautilus.io/<bucket>/stac-collection.json > /tmp/parent.json
# Edit /tmp/parent.json to append {"rel": "child", "id": "...", "href": "...", "title": "..."}
rclone copyto /tmp/parent.json nrp:<bucket>/stac-collection.json
```

Only touch the root when adding a **new** top-level sub-catalog.
