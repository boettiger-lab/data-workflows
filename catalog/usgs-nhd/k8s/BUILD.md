# USGS NHD streams — build notes (issue #235)

New bucket `public-usgs-nhd`. Two datasets from the **same** source file
(`NHD_H_National_GDB.zip`, USGS National High-Resolution seamless GDB, ~30 GB zipped):

- **`streams-by-order`** — all 30,221,659 `NHDFlowline` features, with Strahler stream order
  (`STREAMORDER`) + `STREAMLEVEL` joined from the bundled non-spatial table `NHDFlowlineVAA`
  on `PERMANENT_IDENTIFIER`. **Stream order is NOT a native NHDFlowline attribute** — it lives in
  the VAA table, so a join step is required (this is why the build is custom, not a plain
  `cng-datasets workflow`). NHD only populates order for the connected network (~4.6M of 30.2M
  flowlines); the rest are NULL.
- **`perennial-streams`** — the 6,799,617 flowlines with `FCODE = 46006`
  (Stream/River: Hydrographic Category = Perennial), confirmed against the `NHDFCode` domain.

Geometry reprojected NAD83 (EPSG:4269) → **OGC:CRS84**; hexed to **H3 resolution 8**
(lines buffered by the H3 cell circumradius before polyfill).

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
