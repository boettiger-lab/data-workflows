# NHDPlus High Resolution — flowlines + network VAA (issue #205)

The **stream-order source** for this catalog. Base NHD-H (`streams-by-order`, see
`../BUILD.md`) ships a usable `STREAMORDER` on only 11.4% of flowlines nationally with 15 of 22
HUC2 regions at exactly 0.0% (#518); NHDPlus HR computes the network attributes properly.
**California first** (13 HU4 units, 2,410,919 flowlines) to unblock ca-30x30#111; the pipeline is
national-capable and fans out by extending `units-configmap.yaml`.

**This is ADDITIVE. `streams-by-order` is not replaced** — it is the denser, more recently edited
network and the only source for Alaska (NHDPlus HR has no HUC2 19). Use base NHD for extent and
flow permanence, NHDPlus HR for order/drainage/routing.

## Result

| | value |
|---|---|
| flowlines | 2,410,919 (13 CA HU4 units) |
| `streamorde > 0` coverage | **100.00% of in-network, non-coastline length in every unit** (0.0 km gap) |
| published order range | exactly **1–10** (non-positive source sentinels normalised to NULL) |
| hex | res 8, parent 0 → 3,677,498 rows, 2,410,919 distinct `_cng_fid`, 665,381 h8 cells |

## Run order

```bash
kubectl apply -n geo-workflows -f units-configmap.yaml -f stage-raw.yaml   # 13 zips → raw/nhdplus-hr/
kubectl apply -n geo-workflows -f convert.yaml                            # 13 indexed pods → staging/units/
kubectl apply -n geo-workflows -f consolidate.yaml                        # gate + flowline.parquet
kubectl apply -n geo-workflows -f hex.yaml -f pmtiles.yaml                # parallel
kubectl apply -n geo-workflows -f repartition.yaml                        # after hex
python3 build-stac.py && scripts/verify-stac.py --no-data /tmp/nhdplus-hr-flowline-stac.json
rclone copyto /tmp/nhdplus-hr-flowline-stac.json nrp:public-usgs-nhd/nhdplus-hr/flowline/stac-collection.json
```

## Traps this build exists to document

1. **Source tree.** Use `StagedProducts/Hydrography/NHDPlusHR/VPU/Current/GDB/` — **not** `Beta/`
   (superseded) and **not** `National/GDB/` Release 2, which USGS documents as defective in an
   unlinked notes PDF: region 06 falls back to Beta data with a disconnected Tennessee/Ohio
   network and wrong `PathLength`; a GridCode bug merged sink-derived catchments in VPUIDs
   0903/1007/1015/1021/1022/1025; 0415 is a pre-Beta prototype. The corrected VPUs exist only as
   individual downloads.
2. **Filenames are not derivable from the HU4 code.** 43 of 266 units carry a `YYYYMMDD` stamp and
   33 are Great Lakes `…i` units. Enumerate the bucket listing; `units-configmap.yaml` is the
   pinned list, and the stamp doubles as the vintage recorded per unit in STAC.
3. **⛔ Column-name casing varies by VPU vintage** — lowercase in 1503/1605/1606, mixed case in
   1801–1810. A case-sensitive `ogr2ogr -select "NHDPlusID,StreamOrde"` returns **nothing** on the
   lowercase units, which would publish NULL order for those basins and look like a source problem
   — i.e. recreate #518. `convert.yaml` therefore never uses `-select`, does all column work in
   DuckDB (case-insensitive identifiers), emits lowercase aliases, and **asserts every required
   column resolves per unit**. Do not infer casing from the filename form.
4. **Join key is `nhdplusid`, not `permanent_identifier`** (the VAA table has no such column), and
   it is typed `Real`/float64 — **cast to `DECIMAL(18,0)` before joining** or a float-equality
   comparison on 14-digit ids drops rows silently. The job verifies the row count is unchanged.
5. **The network-end flag is `terminalfl`** (`IsNetworkEnd`), *not* `terminalflag` as in
   NHDPlusV2. The per-unit column assertion caught this on the first run.
6. **EPSG:5498 axis-swap guard.** These GDBs are tagged EPSG:5498 (NAD83 + NAVD88, a geographic
   *compound* CRS) — the family that `cng-convert-to-parquet` used to misclassify as projected and
   flip to (lat, lon) under an `OGC:CRS84` tag (datasets#128, fixed by #129 `always_xy`). The fix
   holds, but `convert.yaml` asserts the output bbox lies in a lon/lat envelope every run rather
   than trusting it. Widen `LON_*`/`LAT_*` env for the national fan-out.
7. **`read_parquet()` surfaces a GeoParquet column as `GEOMETRY('OGC:CRS84')`** — parameterised,
   so match the type *prefix*, and note a bare name/type equality check will miss it.
8. **`_cng_fid` is only unique per unit.** Each per-unit conversion numbers rows from 1, so the
   raw ids collide across VPUs (staging had 474,166 distinct ids across 2,410,919 rows — exactly
   one unit's count). `consolidate.yaml` namespaces it as `<hu4>-<id>` and asserts global
   uniqueness; without that, `COUNT(DISTINCT _cng_fid)` would undercount by ~5×.
9. **⛔ Coastline must be excluded from the coverage denominator.** `fcode = 56600` is not a stream
   and NHDPlus HR gives it no VAA, so leaving it in penalises coastal basins for a non-defect:
   HU4 1805 reads **94.29%** with coastline and **100.00%** without, and its entire 5.71% "gap" is
   888 coastline features / 1,262 km. The gate measures in-network **non-coastline** length and
   reports both figures. Getting this wrong would have failed a perfect build.
10. **Hex chunk sizing.** 200 completions × `--chunk-size 12100` = 2,420,000 ≥ the feature count.
    The generated default of 1000/chunk silently caps a build at 200k features (#494); always size
    from the actual count and verify `COUNT(DISTINCT _cng_fid)` on the hex equals the flat count.

## Base-NHD comparison (acceptance criterion 4 — split, never net-only)

Over these 13 units, for stream/river FCODEs 46003/46006/46007:

| effect | measurement |
|---|---|
| features only in **base NHD** | ephemeral **289,426 km**, intermittent 24,336 km, perennial 7,257 km |
| features only in **NHDPlus HR** | 16,237 / 8,389 / 4,526 km |
| `lengthkm` change, **shared** features same `fcode` (2,017,710) | ephemeral **+1.88%**, intermittent **+4.77%**, perennial **+5.45%** |
| `fcode` reclassification | 81,782 of 2,017,710 = **4.05%**, in both directions |

So base NHD's larger ephemeral total is features NHDPlus HR does not have (NHD has since been
densified with ephemeral washes), **not** a reclassification — there is no redefinition of
ephemeral or perennial. And the length divergence is a **per-VPU editing-vintage** effect, not a
different length algorithm: it ranges from 0.0% to +5.5% by basin here (and reaches +10–13% in
1803 alone), agreeing to the millimetre where the underlying NHD has not been re-edited. **Do not
apply a blanket "lengths are not comparable" note** — compare per unit via `vpu_vintage`.

## Verified value ranges (measured, not assumed)

| column | finding |
|---|---|
| `streamorde` | 1–10, zero non-positive values (sentinels normalised at build) |
| `slope` | `-9998` is the "not computed" sentinel (11,056 rows) and the **only** negative value — filter `> -9998` |
| `maxelevsmo` / `minelevsmo` | `-9998` sentinel (10,543 rows), but **other negatives are real**: 10,349 rows drain below sea level, min **−85.61 m** (Death Valley / Salton Sea). Filter `<> -9998`, **never** all negatives. Valid max 4,193.73 m (high Sierra). |
| `mainpath` | `0` for all 2,410,919 rows — NHDPlus HR leaves it unset here; use `levelpathi` for mainstem grouping |
| `fcode` | 33 distinct codes, each defined verbatim from the source `NHDFCode` domain table |
| `streamleve` | 1–16; NULL set identical to `streamorde`'s (83,483 rows with no VAA row) |
| `streamcalc` | 1–10 plus a legitimate `0` on 109,118 divergence-minor-path rows |
| `totdasqkm` / `divdasqkm` / `arbolatesu` / `pathlength` / `streamcalc` | **`-9999` (`-9` for streamcalc) on the SAME 2,745 flowlines** — a coherent "network attributes not computed" set. Filter before any aggregate. `totdasqkm` valid range 0–546,328 km². |

**Every row here was measured on the published parquet, and doing so caught two published errors
of the same kind.** An initial draft said elevation consumers should "check for negative values
before averaging" — copied from NHDPlus documentation rather than measured — which would have told
them to discard California's genuinely below-sea-level terrain. A second pass then found the
`-9999` set on the five drainage/routing columns, which the first draft did not document at all.
**When a build adds columns nobody in this catalog has used before, measure every one of their
ranges and sentinels before writing STAC** — that is the #518 lesson applied to the fix for #518.

## `lengthkm` across the two products — RESOLVED (#525, closed)

**Neither value is stale or miscomputed, and there is no "authoritative" side to pick.** Each
product's stored `lengthkm` matches the projected (EPSG:3310) length of *its own* geometry to
within 0.06% in aggregate (NHDPlus HR: +0.057% / −0.017% / +0.014% in 1606 / 1803 / 1809; base
NHD-H: −0.026% in 1803; mean per-feature |diff| ~0.4%, i.e. projection noise).

**And it is a minority tail, not a per-basin offset** — which is the part that changes the
guidance. For the 74,610 shared features in HU4 1803, the *worst* basin at aggregate +10–13%:

| | count | share |
|---|---|---|
| agree within 1% | **59,931** | **80.3%** |
| base shorter by >1% | 9,676 | 13.0% |
| base longer by >1% | 5,003 | 6.7% |
| median `base_len / hr_len` | **1.0000** | — |

So:
- ⛔ **Never apply a per-basin correction factor** to reconcile the two — it would corrupt the 80%
  of features that already agree exactly in order to fix the 20% that genuinely changed.
- ⛔ Don't treat a per-feature cross-product length difference as an error; check whether that
  feature is in the re-edited tail.
- ✅ Compare **per-area network totals**, state which product each number came from, and remember
  aggregate totals differ mainly because the products hold **different features** (base NHD has
  289,426 km of ephemeral channel this vintage lacks), not because they measure the same ones
  differently.

Base-shorter outnumbering base-longer ~2:1 points at reach **subdivision** in the newer NHD
(which holds ~2× the features in this basin), but that mechanism is *inferred* — the faithfulness
and tail measurements above are what was actually verified.
