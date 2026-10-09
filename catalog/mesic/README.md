# Mesic Analysis Platform (MAP) — sagebrush biome

Issue [#609](https://github.com/boettiger-lab/data-workflows/issues/609). Bucket `public-mesic`.

40-year pixel-level persistence of mesic ground (wet meadows, springs, riparian floodplains) across
the 14-state sagebrush biome, from Working Lands for Wildlife / University of Montana NTSG.
Source: <https://rangeland.ntsg.umt.edu/data/mesic/> (the `README` at that root is the authority).

**Tier 1 (this build):** two persistence rasters, a derived presence-fraction raster, and the HUC12
subwatershed table. **Tier 2 (separate build):** the 16.9 GB valley-bottom GeoPackage.

## Upstream is replaced in place — read this before re-running

There is no immutable archive and no version string in the filenames. The upstream changelog shows
four in-place replacements since 2026-01-08, and the 2026-09-02 pass **renamed both rasters and
changed their units**. The names in the original issue body (`BIOME_Unmasked_Mesic_Pixels.tif`,
`BIOME_Herbaceous_Mesic_Pixels.tif`) now 404.

`mesic-stage-raw` therefore asserts the exact `Content-Length` of each file and **fails rather than
staging a different edition under this dataset id**. If it fails that way, upstream has replaced the
files again: re-verify with `HEAD`, update issue #609, bump the `-2026-09` id suffix, and only then
re-run.

## Band units: 1–42 years, not 0–100 percent

The upstream README contradicts itself — "DATA PRODUCTS" says `1-42 (number of years productive)`,
"DATA SPECIFICATIONS" says `0-100 (percent years productive)`. The data settles it: sampled windows
max at exactly 42, and the embedded colour table ramps 1→42 then saturates. `Persistence` is a
**count of the 42 analysed years** (1984–2025 excluding 2012), `NoData = 0`. We publish it unscaled;
percent is `value / 42 * 100` downstream.

## `masked` vs `unmasked` — which to use

Both are 30 m, EPSG:4326, paletted Byte, `NoData = 0`.

| product | masking | use it for |
|---|---|---|
| `unmasked` | none — every pixel mesic in ≥1 year, any land cover. NoData only where late-season mean NDVI never reached 0.3 ("never mesic"). | **forested / IRA analysis**, irrigated land, alpine |
| `masked` | inside valley bottoms, all productive pixels kept except development and open water; in **uplands**, pixels over 10% tree cover removed. NoData = "masked land cover". | "long-term reliable mesic" mapping outside forested uplands |

Note this is **not** the retired `Herbaceous` product, which blanked every ≥10%-tree pixel
everywhere. The current `masked` keeps forested *valley-bottom* riparian and drops forested
*uplands*. NoData means different things in the two rasters — never blur them.

## The presence-fraction layer

`mean` over `Persistence` answers *"how persistently mesic is the mesic ground here?"*, **not**
*"how much mesic ground is here?"* — a cell holding one 42-year pixel and a cell holding 500 both
report 42. So `mesic-make-cogs` derives a presence raster from **unmasked**: `1` where the raster has
any value, `0` elsewhere, **carrying no NoData**. Hexed with `mean`, each cell value *is* the mesic
pixel fraction, and `fraction × h3_cell_area(h8,'km^2')` is a defensible mesic area.

It is hexed at **native 8** (not 10) deliberately: an h8 cell holds ~820 source pixels, so the
fraction is a genuinely continuous quantity, where an h10 cell holds ~17 and quantises it to 1/17.
h8 is also the catalog's universal join key. The layer is a **full grid** over the source footprint —
cells outside the sagebrush biome read `0`, which is "no mesic pixels", not "no data". Clip to the
biome footprint before computing totals.

## ⛔ Do not compute mesic area by counting COG pixels

The rasters are EPSG:4326 with a pixel size in **degrees** (0.000269494585236 deg), so a pixel is
~30 m in latitude but ~30 x cos(lat) m in longitude. Its ground area is **~900 x cos(lat) m2, not
900 m2**. Counting valid pixels and multiplying by 900 m2 overstates mesic extent by ~37% across
this footprint.

Measured on the published build:

| method | mesic area |
|---|---:|
| `mesic-presence-2026-09` hex, `SUM(mesic_fraction * h3_cell_area(h8,'km^2'))` | **987,608 km2** |
| naive COG pixel count (1,507,376,096) x 900 m2 | 1,356,638 km2 |

The ratio is 0.728. The mesic-area-weighted mean latitude of the footprint is 42.814 deg and
cos(42.814) = 0.7336, so the gap is entirely the cos(lat) term and nothing else (agreement within
0.7%).

**The hex figure is the correct one**, because H3 cells carry true spherical area while a
geographic-CRS pixel does not. This is the substantive reason the presence layer exists: it is the
only route to a defensible acreage from this source. State it in the hex asset description so a
consumer does not "check" our number against a pixel count and conclude we are wrong.

## HUC12 ships 1,179 exact duplicate rows — dedup before anything else

Grouping the GeoPackage on geometry **and every attribute** collapses 20,032 rows to **18,853
distinct watersheds**:

| rows sharing one identical record | watersheds | rows |
|---:|---:|---:|
| 1 | 17,700 | 17,700 |
| 2 | 1,129 | 2,258 |
| 3 | 22 | 66 |
| 4 | 2 | 8 |

No group differs in `name`, `mgmt_code`, `area_vb_m2`, `prHuc_vb` or `prV_For` — they are copies,
differing only in `fid`. They are **not** multipart pieces: for a code carrying two rows the summed
polygon area is **1.998×** the WBD watershed area, so each row is a whole watershed.

Leaving them in makes an unguarded `SUM(area_vb_m2)` over-count by about 6%, and makes a 1:1 `huc12`
key impossible. **The 20,032 figure in issue #609 is a correct count of upstream rows and was never
a count of watersheds** — do not treat it as a deliverable target. Scope corrected 2026-09-21
([comment](https://github.com/boettiger-lab/data-workflows/issues/609#issuecomment-5769248942)).

`enrich` dedups on the full record, not on geometry alone: if upstream ever ships rows sharing a
geometry but differing in an attribute, both survive and the 1:1 gate fails loudly rather than
silently discarding real data.

## HUC12 carries no HUC code — we derive one

The GeoPackage ships `name` (ambiguous: 28,978 WBD watersheds share only 23,626 names in this
footprint) and `fid`, and no HUC12 code at all. `mesic-huc12-2026-09-enrich` recovers it by spatial
join against `s3://public-usgs-wbd/wbd/hu12.parquet` — which is what upstream built these polygons
from, so the match is near-identity: **19,808 of 20,032 rows overlap their matched watershed by
≥99.9%**.

Assignment runs in **two phases, overlap first and name only as a rescue**.

**Phase 1 — greedy on overlap, majority floor 0.5.** Candidates where no watershed contains half
the mesic polygon are discarded; the rest are assigned strongest-claim-first, and a weaker claimant
falls through to its next free code. This is what stops a near-duplicate from displacing the real
owner.

**Phase 2 — exact name rescue.** Only a watershed phase 1 could *not* place is reconsidered, only
onto a code still free, and only on an exact and unambiguous name match. This recovers
`Carter Creek-South Fork Shoshone River`, whose MAP polygon puts 0.749 of its area in the adjacent
Buffalo Bill watershed and only 0.251 in the WBD watershed carrying its own name — it clears no
majority floor anywhere, but the name is decisive and `100800130303` is free.

⛔ **Name must not be a phase-1 ranking key — this was tried and is wrong.** Ranking by exact `name`
match ahead of overlap lets a *sliver* overlap outrank a near-perfect one. It stole codes from the
only genuine claimant in two places: `Lone Tree Creek-Redwater River` (0.9999 into `100600020808`)
and `Lower Eighteenmile Creek` (0.9999 into `140401030309`) were both left unassigned while a record
whose name happened to match took their code on a fraction of a percent of overlap. Name is
evidence, but only about a record overlap could not place at all.

The job **gates on uniqueness**: a duplicate code fails the run and leaves the pre-enrich parquet in
place. A **low overlap is reported but does not fail** — the MAP export and the WBD edition differ
slightly along some watershed boundaries, which changes the overlap without making the code
ambiguous. Unassigned watersheds are expected in small numbers and fail the run above 5.

**Three watersheds carry a NULL `huc12`**, and each is a MAP polygon that does not correspond to any
one WBD watershed:

| `_cng_fid` | `name` | best candidate |
|---:|---|---|
| 6241 | `Upper Battle Creek` | spans four watersheds, 0.39 / 0.31 / 0.27 / 0.03 |
| 6323 | `Middle Battle Creek` | spans many, best 0.37 |
| 8654 | `100500060000` | straddles two, 0.51 / 0.47, and its "name" is a HUC code |

None has a name match to rescue it. Their geometry and attributes are published unchanged; only the
derived code is empty.

The column is documented in STAC as **derived by us, not shipped upstream**.

### ⛔ Re-running `enrich` — the snapshot must stay create-only

`enrich` publishes over its own input: it reads `mesic-huc12-2026-09.parquet` and writes the
enriched table back to that same key, keeping a pre-enrich copy under
`staging/mesic-huc12-2026-09.preenrich.parquet`. An **unconditional** `rclone copyto` of published →
staging is re-entrant-unsafe, and this bit once: re-running enrich after a *successful* run copied
the already-enriched parquet over the pristine snapshot, destroying the only pre-enrich copy and
forcing a convert re-run.

The job now snapshots **only when the published parquet still lacks a `huc12` column**, i.e. when it
is still the convert output. The `FATAL: source already has a huc12 column` guard is the second line
of defence and is what stopped the run before anything worse happened — but it fires *after* the
copy, so it cannot protect the snapshot on its own.

To rebuild from scratch, re-run `convert` first (it reads `raw/`, which is immutable and checksummed)
and then `enrich`.

## Step 6: register in the root catalog

`public-mesic` is a **new top-level bucket**, so its bucket-level collection needs one `child` link
in `s3://public-data/stac/catalog.json` — the one case AGENTS.md sanctions touching the root.

```bash
kubectl apply -n geo-workflows -f catalog/mesic/k8s/mesic-register-root-catalog.yaml
```

The read-modify-write happens **inside the job**, not on a workstation, so the read sits as close to
the write as possible: that file is shared by every dataset in the catalog, and a copy edited hours
earlier would silently drop whatever another build added in between. The job is idempotent, and it
refuses to write if any pre-existing link or non-link field changed.

## Build order

`public-mesic` does not exist until setup-bucket runs, and `rclone --s3-no-check-bucket` will
download for many minutes before failing with `NoSuchBucket`. Run setup-bucket **first**.

```bash
N="-n geo-workflows"
K=catalog/mesic/k8s

kubectl apply $N -f $K/mesic-persistence-unmasked-2026-09/workflow-rbac.yaml      # one-time
kubectl apply $N -f $K/mesic-persistence-unmasked-2026-09/mesic-persistence-unmasked-2026-09-setup-bucket.yaml
kubectl wait  $N --for=condition=complete job/mesic-persistence-unmasked-2026-09-setup-bucket --timeout=600s

kubectl apply $N -f $K/mesic-stage-raw.yaml      # 3 files, ~1.7 GB, + checksums + pre-flight
kubectl wait  $N --for=condition=complete job/mesic-stage-raw --timeout=7200s

kubectl apply $N -f $K/mesic-make-cogs.yaml      # 3 COGs incl. the presence derivation
kubectl wait  $N --for=condition=complete job/mesic-make-cogs --timeout=7200s

# One hex workflow at a time (AGENTS.md pod-count practice).
for d in mesic-persistence-unmasked-2026-09 mesic-persistence-masked-2026-09 mesic-presence-2026-09; do
  kubectl apply $N -f $K/$d/$d-hex.yaml
  kubectl wait  $N --for=condition=complete job/$d-hex --timeout=14400s
  kubectl apply $N -f $K/$d/$d-merge.yaml
  kubectl wait  $N --for=condition=complete job/$d-merge --timeout=7200s
done

# HUC12: convert -> enrich (derive huc12) -> pmtiles + hex -> repartition.
# The enrich step sits between convert and hex, so run the steps individually
# rather than applying workflow.yaml.
kubectl apply $N -f $K/mesic-huc12-2026-09/mesic-huc12-2026-09-convert.yaml
kubectl wait  $N --for=condition=complete job/mesic-huc12-2026-09-convert --timeout=7200s
kubectl apply $N -f $K/mesic-huc12-2026-09/mesic-huc12-2026-09-enrich.yaml
kubectl wait  $N --for=condition=complete job/mesic-huc12-2026-09-enrich --timeout=7200s
kubectl apply $N -f $K/mesic-huc12-2026-09/mesic-huc12-2026-09-pmtiles.yaml \
                -f $K/mesic-huc12-2026-09/mesic-huc12-2026-09-hex.yaml
kubectl wait  $N --for=condition=complete job/mesic-huc12-2026-09-hex --timeout=14400s
kubectl apply $N -f $K/mesic-huc12-2026-09/mesic-huc12-2026-09-repartition.yaml
```

After each hex job, check the `succeeded` vs `failed` gap (skill `pod-preemption`) and run the h0
coverage gate before treating a build as done:

```bash
kubectl $N get job <name>-hex -o jsonpath='succeeded={.status.succeeded} failed={.status.failed} failedIndexes={.status.failedIndexes}{"\n"}'
scripts/check-hex-coverage.sh nrp:public-mesic/<dataset>/hex/ \
  --expect-h0 576812596024311807,577164439745200127,577199624117288959,577692205326532607,577762574070710271
```

## ⛔ Re-running a hex into a prefix that already holds an earlier run

`merge-chunks --expect-chunks N` counts records under `hex-chunks/_manifest/`. Those objects are
keyed by **chunk index**, so a re-run overwrites them one by one as each chunk finishes. If the
prefix still holds a previous run's manifests, a chunk that fails in the new run leaves the **old**
manifest in place and the gate counts it: `--expect-chunks` passes on an incomplete build. That is
the #409 silent-partial-build failure wearing the gate's own badge.

This bit `mesic-persistence-unmasked-2026-09`, whose prefix carried 34 manifests from the aborted
`--h0-subset "9,19,20,34,36"` run. So **before merging a re-run, check that every manifest is newer
than the run started**, not just that there are N of them:

```bash
scripts/check-chunk-manifests.sh nrp:public-mesic/<dataset>/hex-chunks/ \
  --expect 35 --since 2026-09-17T20:23:00Z      # the corrected run's start
```

It exits non-zero on a stale or missing index and names them. It deliberately reads the
manifests rather than the pods: Armada reaps failed pods (and k8s deletes them when
`backoffLimitPerIndex` is set), but a missing completion record cannot be reaped.

Data parts are safer but not self-evidently so: they are named `part-<res1-cell>.parquet`, so a
re-run with the same chunk plan overwrites them in place, and a stale part can only survive if its
cell is absent from the new plan. Here the old plan's populated cells were all base-cell-19
children, all present in the corrected plan, so the three surviving parts were rewritten rather
than orphaned. **Purge the prefix instead if the chunk plan changed**, since a plan change is
exactly the case where a stale part outlives its cell.

## Hex parameters

| dataset | native | parents | reducer | why |
|---|---|---|---|---|
| `mesic-persistence-unmasked-2026-09` | 10 | 9,8,0 | `mean` | 30 m source pixel → res 10 (`raster-hexing` anchors) |
| `mesic-persistence-masked-2026-09` | 10 | 9,8,0 | `mean` | same |
| `mesic-presence-2026-09` | 8 | 0 | `mean` | fraction needs many pixels per cell; see above |
| `mesic-huc12-2026-09` | 8 | 0 | — | matches `usgs-wbd-hu12` (native 8 / `[0]`) so they join on `h8` |

`Persistence` is a per-pixel intensive count — **never `sum`**. The hex fan-out uses
`--chunk-resolution 1` (35 res-1 chunks over the 5 h0 cells the source touches: base cells
9, 19, 20, 34, 36 — none is a pentagon, so 5 x 7 = 35) so no pod carries a whole h0 at res 10.

## ⛔ `--h0-subset` takes GRID INDICES, not H3 base cell numbers

This silently built half the dataset once, and nothing in the build failed. **The values passed to
`--h0-subset` are the `i` column of `s3://public-grids/hex/h0-valid.parquet` — a positional index
into that 122-row grid — not the H3 base cell number.** The two are not the same, and the tool
cannot tell you which you meant: every value 0-121 is legal in both readings.

For this footprint the translation is:

| h0 base cell | grid index `i` | h0 cell id |
|---:|---:|---|
| 9  | **12** | 576812596024311807 |
| 34 | **14** | 577692205326532607 |
| 19 | **20** | 577164439745200127 |
| 20 | **50** | 577199624117288959 |
| 36 | **71** | 577762574070710271 |

So the correct argument is **`--h0-subset "12,14,20,50,71"`**.

The first build passed the base cell numbers `"9,19,20,34,36"`. Those resolved to grid rows whose
h0 cells are base cells **40, 63, 19, 90, 116** — four of which the raster does not touch at all.
Only base cell 19 was processed, and only because `20` appears in both lists by coincidence. The
job reported **34/34 succeeded with no failures**: 28 of the 34 chunks logged `No overlap between
source raster and chunk, skipping` and exited 0. The entire Great Basin / Snake River Plain /
Columbia Plateau half of the biome — Idaho, Nevada, Utah, Oregon, Washington, all in base cell 20 —
was silently absent.

Two things make this worth a permanent note. The tool's own docstring says "descendants of these h0
**base cells**", which is what misled the first build; and a clean `succeeded` count proves nothing
here, because a chunk that overlaps nothing is a success. **Verify the translation before
submitting**, and always run the h0 coverage gate after:

```sql
-- what to pass, given the base cells the source touches
SELECT i FROM read_parquet('s3://public-grids/hex/h0-valid.parquet')
WHERE h3_get_base_cell_number(h0::UBIGINT) IN (9,19,20,34,36) ORDER BY i;
```

## Never SUM these on hex

Per-feature totals are repeated on every cell a feature covers. On `mesic-huc12-2026-09` that is
`area_vb_m2`, `area_vb_ac`, **and every `pr*` proportion column** — a proportion is a per-watershed
value, so averaging across cells is valid only weighted by cell count within the watershed. Dedup on
`huc12` (or `_cng_fid`).
