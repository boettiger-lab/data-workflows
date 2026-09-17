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
scripts/check-hex-coverage.sh nrp:public-mesic/<dataset>/hex/ \
  --expect-h0 576812596024311807,577164439745200127,577199624117288959,577692205326532607,577762574070710271
```

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
