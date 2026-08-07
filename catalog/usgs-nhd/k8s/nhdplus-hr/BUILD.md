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

## Open question (not blocking)

Which `lengthkm` is authoritative where the two products disagree. Worth measuring both against a
geodesic length on a sample before either is treated as canonical for length reporting.
