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

## HUC12 carries no HUC code — we derive one

The GeoPackage ships `name` (ambiguous: 28,978 WBD watersheds share only 23,626 names in this
footprint) and `fid`, and no HUC12 code at all. `mesic-huc12-2026-09-enrich` recovers it by
**max-overlap spatial join against `s3://public-usgs-wbd/wbd/hu12.parquet`** — which is what upstream
built these polygons from, so the match is near-identity. The job **gates on a 1:1 match** (every
feature matched, no duplicate codes, every overlap ≥90% of the mesic polygon's area) and refuses to
publish an ambiguous key. The column is documented in STAC as **derived by us, not shipped upstream**.

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
scripts/check-hex-coverage.sh nrp:public-mesic/<dataset>/hex/ --expect-h0 <the 5 h0 cells>
```

## Hex parameters

| dataset | native | parents | reducer | why |
|---|---|---|---|---|
| `mesic-persistence-unmasked-2026-09` | 10 | 9,8,0 | `mean` | 30 m source pixel → res 10 (`raster-hexing` anchors) |
| `mesic-persistence-masked-2026-09` | 10 | 9,8,0 | `mean` | same |
| `mesic-presence-2026-09` | 8 | 0 | `mean` | fraction needs many pixels per cell; see above |
| `mesic-huc12-2026-09` | 8 | 0 | — | matches `usgs-wbd-hu12` (native 8 / `[0]`) so they join on `h8` |

`Persistence` is a per-pixel intensive count — **never `sum`**. The hex fan-out uses
`--chunk-resolution 1` (34 res-1 chunks over the 5 h0 cells the source touches: base cells
9, 19, 20, 34, 36) so no pod carries a whole h0 at res 10.

## Never SUM these on hex

Per-feature totals are repeated on every cell a feature covers. On `mesic-huc12-2026-09` that is
`area_vb_m2`, `area_vb_ac`, **and every `pr*` proportion column** — a proportion is a per-watershed
value, so averaging across cells is valid only weighted by cell count within the watershed. Dedup on
`huc12` (or `_cng_fid`).
