# USGS NHD streams — build notes (issue #235)

New bucket `public-usgs-nhd`. Two datasets from the **same** source file
(`NHD_H_National_GDB.zip`, USGS National High-Resolution seamless GDB, ~30 GB zipped):

- **`streams-by-order`** — all 30,221,659 `NHDFlowline` features, with Strahler stream order
  (`STREAMORDER`) + `STREAMLEVEL` joined from the bundled non-spatial table `NHDFlowlineVAA`
  on `PERMANENT_IDENTIFIER`. **Stream order is NOT a native NHDFlowline attribute** — it lives in
  the VAA table, so a join step is required (this is why the build is custom, not a plain
  `cng-datasets workflow`). ⚠️ **`STREAMORDER` is sparse in the source VAA table and its coverage
  is GEOGRAPHIC, not topological — see "Stream-order coverage" below (#518).**
- **`perennial-streams`** — the 6,799,617 flowlines with `FCODE = 46006`
  (Stream/River: Hydrographic Category = Perennial), confirmed against the `NHDFCode` domain.

Geometry reprojected NAD83 (EPSG:4269) → **OGC:CRS84**; hexed to **H3 resolution 8**
(lines buffered by the H3 cell circumradius before polyfill).

## ⚠️ Stream-order coverage — sparse in the SOURCE, and geographic (#518)

**The import is faithful — do not re-run it to "fix" the NULLs.** `convert.yaml` extracts
`NHDFlowlineVAA` with no filter and `derive.yaml` LEFT JOINs it on `PERMANENT_IDENTIFIER`; both
are exact. The archived intermediate proves the hole is upstream, in USGS's own VAA table:

| `s3://public-usgs-nhd/raw/vaa.parquet` | |
|---|---|
| rows | 30,772,890 — all `PERMANENT_IDENTIFIER` distinct, a superset of the 30,221,659 flowlines |
| `STREAMORDER` non-null | 5,153,385 (16.7%) |
| `STREAMORDER > 0` — **actually usable** | 3,500,768 (**11.4%**) |
| `STREAMLEVEL` non-null | 12,247,542 (39.8%) |

Published: 4,589,297 non-null / 3,355,035 usable of 30,221,659 flowlines (11.1%); the difference
from the VAA counts is the 564,088 VAA ids with no matching `NHDFlowline` row. No rows lost, no
fan-out — the join is exact.

**The earlier note in this file and in STAC ("NHD computes order only for networked reaches") was
FALSE.** `INNETWORK = 1` is **29,184,336** of 30,221,659 flowlines (96.6%) — the network is
essentially the whole dataset, and ~25.8 M networked flowlines have no usable order. The real
pattern is per-subbasin refresh history:

- **15 of the 22 HUC2 regions are at exactly 0.0% usable coverage.** Best is HUC2 17 at 66.1%;
  then 02 (28.2), 11 (18.2), 18 (12.4), 01 (11.1), 16 (4.0), 04 (3.3). **No region is complete.**
- Coverage varies *inside* a single HUC4 — California's 1801 Klamath is 73.4%, the adjacent
  1802 Sacramento 0.7%.
- `STREAMORDER` and `STREAMLEVEL` coverage are **uncorrelated** by region (HUC2 17 = 66.1% order /
  6.4% level; HUC2 14 = 0.0% / 83.6%) — USGS populated one attribute *or* the other per subbasin.
  A truncated extract or bad join key would null both columns on the same rows.
- The two are not interchangeable: on rows carrying both with order > 0 they are equal on only
  4.3%, correlation **−0.116** (means 3.51 vs 5.64; maxima 191 vs 25).

⛔ **Consequence for consumers: `STREAMORDER` cannot select a stream class over any area larger
than a verified subbasin.** The predicate looks like an attribute filter and acts as a geographic
one — in California it selects 94,505 km of 1,083,964 km of in-network flowline (8.7%), and
**92,393 km of that (97.8%) is HUC4 1801 alone**. That is how `ca-30x30` reported Klamath-basin
stream numbers as statewide (ca-30x30#111). Where order *is* computed it is not selective by
feature type (in 1801 it covers 87.3% of perennial, 86.1% of intermittent, 65.6% of ephemeral
length), so the populated subset is *not* "the real streams".

**`STREAMORDER = 0` is a source sentinel, not an order** — 1,652,617 VAA rows / 1,234,262
published rows. Valid Strahler range is **1–10** (a few thousand records carry out-of-range
values up to 191). **Always filter `STREAMORDER > 0`; `IS NOT NULL` admits the sentinel** and
certifies regions that have nothing usable — HUC2 12 looks 96.7% covered by `IS NOT NULL` and is
0.0% usable; HUC2 13 goes 17.5% → 0.0%. It is documented rather than normalised to NULL in the
published files because normalising would mean re-running a correct 30 M-feature build; **fold
the normalisation into the #205 rebuild** (below) and keep `> 0` as the documented filter until
then.

**The real fix is #205, not a re-run** — the values are not in this source. Network VAAs are
computed nationally in **NHDPlus High Resolution** (`NHDPlusFlowlineVAA`), tracked as
data-workflows#205. When it lands, **audit coverage by HUC2 with `> 0`, never `IS NOT NULL`.**

Convention this build missed: when a dataset is *named* for a joined attribute, record that
attribute's **non-null and in-valid-range counts plus its distribution across a partition key** —
not just the join's row count. Run one `COUNT(col) FILTER (WHERE col > 0)` + per-HUC2 breakdown
before writing STAC.

## Actual build sequence (run manually, in order)

1. **`stage-raw.yaml`** — download the 30 GB zip to the `rechunk-scratch` PVC (exceeds the 50Gi
   ephemeral cap), archive the zip to `s3://public-usgs-nhd/raw/`, unzip the GDB onto the PVC.
2. **`convert.yaml`** — `cng-convert-to-parquet` `NHDFlowline` → `nhdflowline.parquet` (OGC:CRS84;
   auto-flattens the 3D-measured geometry); `ogr2ogr` `NHDFlowlineVAA` → `vaa.parquet`. Both
   archived to `raw/`.
3. **`derive.yaml`** — DuckDB over the internal S3 endpoint:
   - `streams-by-order.parquet` = `nhdflowline` LEFT JOIN `vaa` on `PERMANENT_IDENTIFIER`
     (VAA keys are unique → no fan-out).
   - `perennial-streams.parquet` = `nhdflowline` WHERE `FCODE = 46006`.
4. Bucket made public + CORS — **run `setup-bucket.yaml`** (`cng-datasets storage
   setup-bucket --bucket public-usgs-nhd --remote nrp --verify`). ⚠️ Do NOT substitute a
   hand-rolled "public-read" policy: a bare `s3:GetObject`-only grant omits `s3:ListBucket`,
   so anonymous object GET works but `h0=*` **globs 403** (they need a bucket LIST). The tool
   emits the correct two-statement policy (`s3:GetBucketLocation`+`s3:ListBucket` on the
   bucket **and** `s3:GetObject` on `/*`), matching every sibling `public-*` bucket. This was
   the #411 bug — the original build applied a GetObject-only policy by hand. Verify anonymously:
   `curl -so/dev/null -w '%{http_code}' 'https://s3-west.nrp-nautilus.io/public-usgs-nhd?list-type=2&max-keys=1'`
   must be `200`.
5. Per dataset: **`<ds>-hex.yaml`** (200 completions; chunk-size = ceil(features/200):
   151200 for streams-by-order, 34000 for perennial) → **`<ds>-repartition.yaml`**, and
   **`<ds>-pmtiles.yaml`**.

The generated `<ds>-convert.yaml` and `workflow.yaml` (orchestrator) are the standard
`cng-datasets workflow` scaffolding; they are **superseded** by the custom `convert.yaml` +
`derive.yaml` above (kept for reference only — do not run the orchestrator, it would skip the
VAA join). **`setup-bucket.yaml` is NOT superseded — it must still be run** (step 4); it is the
one piece of the standard scaffolding this custom build still needs, and skipping it (or hand-
rolling its policy) is exactly what caused #411.

## Notes / gotchas hit during the build

- **`<ds>-hex-rechunk.yaml`** — on both hex runs, 3 indexed pods got stuck `Terminating` on a
  preempted/lost node (output never written). The rechunk jobs reprocess just those chunk-ids
  (CHUNK_MAP) into `chunks/` before repartition. Force-delete the stuck job, run the rechunk.
- **`streams-by-order-pmtiles.yaml` uses the `rechunk-scratch` PVC** for its working dir + TMPDIR:
  the 30M-feature GeoJSONL intermediate + tippecanoe temp tiles exceed the 50Gi ephemeral cap
  (first attempt was evicted). Perennial PMTiles fit in ephemeral but the streams one does not.
