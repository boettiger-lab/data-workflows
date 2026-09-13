# RAP rebuild campaign — issues #666, #667, #607

Three independent defects across the four `public-rap` collections, all found to be build-recipe
errors rather than upstream problems. This directory holds the corrected jobs; the old manifests
under `../rap-arte/`, `../rap-iag/` and `../rap-pfg-cover/` are marked SUPERSEDED and must not be
re-run.

## Upstream facts, measured (not taken from the old STAC)

`README` at <https://rangeland.ntsg.umt.edu/data/rap/rap-vegetation-cover/v3/README>:

| fact | value |
|---|---|
| band order | 1 annual forb & grass, 2 bare ground, 3 litter, **4 perennial forb & grass**, 5 shrub, 6 tree |
| nodata | 255 |
| CRS / pixel | EPSG:4326, ~30 m |
| licence | **CC0-1.0** — <https://creativecommons.org/publicdomain/zero/1.0/> |
| edition | v3.0; 2025 data released **2026-02-24** (upstream changelog) |
| staged raw | `s3://public-rap/raw/vegetation-cover-v3-2025.tif`, 37,594,614,065 bytes |
| staged raw SHA-256 | `012e29a570865ecf6845578a50fe7e3ea0fe68621bb4b150cb00308f20ea0e84` |
| access date | 2026-06-13 (S3 last-modified of the staged copy) |
| suitability | "primarily intended for rangeland ecosystems… may not be suitable in other ecosystems, e.g., forests, agricultural lands" |

The previously published collections claimed `license: public-domain` with a link to
`https://rangelands.app/`, which states no terms at all (`/terms` and `/about` both 404). CC0-1.0
is the actual grant, and it is an SPDX id, so the collections now assert it with the CC0 deed as
the licence link.

`rangeland-s2` tile naming is `{product}-{year}-{zone}-{easting}-{northing}.tif`. Measured over the
full listing: the third field takes **exactly four values — 10, 11, 12, 13** — with 117/201/217/229
tiles each, identical in every year 2018–2025. It is the **UTM zone**, not a month (a month cannot
be 13, and zone 10's narrow easting range 350000–725000 versus 200000–725000 for the others is
exactly the Pacific zone's geometry).

## Defect 1 — `rap-pfg-cover-cog.tif` was the raw 6-band stack (#666)

39.48 GB and 6 bands, against 1.32/1.85 GB single-band siblings. TiTiler returned HTTP 500
`Source data must be 1 band` for every tile, so the layer could not render at all.

**This one is not our recipe's fault.** `rap-pfg-cover-preprocess-cog.yaml` passes `--band 4`.
The tool ignored it: with a single `--input`, `cng-datasets` never consults the band argument
(`cog.py:1101` — it is applied only on the 2+ input mosaic branch), and exits 0 with no warning.
Reproduced as boettiger-lab/datasets#214 — the identical command with the input listed twice
returns one band, value 44; with it listed once, six bands.

`rap-extract-bands.yaml` uses `gdal_translate` directly rather than the tool, so the fix does not
wait on the upstream one. It needs `-co BIGTIFF=YES`: a single band is ~6.6 GB, past the 4 GB
classic-TIFF limit, and the COG driver's default sizing guessed wrong on compressed output
(`TIFFAppendToStrip:Maximum TIFF file size exceeded`, ~70% through the first attempt).

## Defect 2 — the hex was missing two CONUS h0 cells (#666)

`CHUNK_MAP=(12 20 50 71)`, commented "CONUS-bounding h0 indices", is four of the six CONUS cells.
The two absent are `--h0-index` **14** (base cell 34, GA/FL) and **78** (base cell 21, NC/VA/ME).

**Two 0–121 numberings exist and do not coincide** — the H3 base cell number and the cng-datasets
`--h0-index`. The mapping is the `i` column of `s3://public-grids/hex/h0-valid.parquet`, which is
what the tool itself reads (`cng_datasets/raster/cog.py`: `WHERE i = {h0_index}`):

| `--h0-index` | h0 cell | base cell |
|---:|---:|---:|
| 12 | 576812596024311807 | 9 |
| 14 | 577692205326532607 | 34 |
| 20 | 577164439745200127 | 19 |
| 50 | 577199624117288959 | 20 |
| 71 | 577762574070710271 | 36 |
| 78 | 577234808489377791 | 21 |

Index 20 is base cell **19**. Do not eyeball these as one list. The full CONUS set
`12,14,20,50,71,78` is also the example string carried in `cng_datasets/k8s/workflows.py`.

Verified that the four partitions that *did* exist were complete, so only the two were missing:
per-cell longitude spans differing from `landfire-2024-cbd` were traced to (a) that longitude band
belonging to base cell 20 at those latitudes, and (b) Lake Huron / Ontario, where the COG returns
nodata on all six bands.

## Defect 3 — the hex was band 1, not band 4 (#666 → #667)

Consequence of defect 1. `--value-column pfg` names the *output* column and selects nothing, so the
hex step read band 1 from the multi-band input. Measured against the COG's own bands over two
independent 1°×1° windows:

| window | published hex | band 1 (AFG) | band 4 (PFG) |
|---|---|---|---|
| Kansas prairie (−100…−99, 38…39) | mean 7.234, max 72.6 | **7.343 / 75.0** | 26.660 / 93.0 |
| Great Basin NV (−117…−116, 40…41) | mean 20.662, max 99.65 | **20.776 / 100.0** | 13.829 / 100.0 |

Band 1 matches within 1.5% on the mean in both; band 4 is wrong by 3.7× one way and 1.5× the
other, so it is a different variable rather than a scaling offset. The Kansas window is what
separates band 1 from band 2 (7.34 vs 3.07); Nevada alone cannot (20.78 vs 20.73).

AFG and PFG share the 0–100 percent domain, so a value-range check cannot catch this — only a
cross-check against the source band can. The hex jobs here therefore refuse to run against a
multi-band input rather than defaulting to band 1.

Since the catalog wants both variables, those 384,922,346 rows are AFG data under the wrong name
and are migrated rather than discarded (`rap-afg-migrate-hex.yaml`), and PFG is built fresh.

## Defect 4 — `rap-arte` / `rap-iag` staged 117 of 764 tiles (#607)

The zone-field-as-month misreading above. Consequence: both collections covered −125.05…−120.00
(2 h0 partitions) and Wyoming — the region these layers are most used for — was absent entirely.
The published STAC did not merely omit this, it asserted *"Extent is the product's native
Pacific-west coverage"*, which is false.

Correct target, from reprojecting every 2025 tile corner (75 km tiles, EPSG:326{10,11,12,13}):

| zone | bbox |
|---:|---|
| 10 | −125.05 … −118.96, 33.40 … 49.65 |
| 11 | −121.04 … −112.96, 32.05 … 49.65 |
| 12 | −115.04 … −106.96, 30.70 … 49.65 |
| 13 | −109.04 … −100.96, 28.68 … 49.65 |
| **union** | **−125.05 … −100.96, 28.68 … 49.65** |

Zone 10 alone reproduces the published COG (−125.08, 33.40, −118.85, 49.65) to within warp edge
effects, confirming both the arithmetic and the diagnosis.

**`rangeland-s2` is a western-US product and takes 4 h0 cells** (`--h0-index` 12, 20, 50, 71),
not the 6-cell CONUS set. Base cells 21 and 34 lie east of −79° and can never hold data here, so
pinning six would leave two indices permanently empty. The existing fan-out was already correct —
only the COG beneath it was truncated.

## Two configuration traps worth knowing before re-running any of this

**`AWS_PUBLIC_ENDPOINT` must point at the internal RGW, not the public host.** `cng-datasets`
resolves source rasters through `_ensure_vsi_path(use_public_endpoint=True)`, which honours
`AWS_PUBLIC_ENDPOINT` and falls back to `AWS_S3_ENDPOINT`. The legacy manifests set it to
`s3-west.nrp-nautilus.io`, so a job running *inside* the cluster read every source tile over the
~12 MB/s public path. The first mosaic attempt spent 35 minutes opening 764 tiles without writing
a byte, at 4.8% CPU. Setting it to `rook-ceph-rgw-nautiluss3.rook` keeps those reads on the
100 Gb/s network. This is configuration, not a tool bug — the tool explicitly refuses to hardwire
the endpoint. Writes were already fine, since they go through `/vsis3` and `AWS_S3_ENDPOINT`.

**`TMPDIR` must point at the scratch PVC.** `create_mosaic_cog` builds an *uncompressed*
intermediate (`COMPRESS=NONE`) via `tempfile.mkdtemp()`. For the full western-US 10 m mosaic that
is roughly 60 GB, against a 20 Gi ephemeral limit. `TMPDIR=/tmp/cng-raster-cache` on the
`rechunk-scratch` PVC keeps it off ephemeral storage. Note that PVC is shared with other work —
never clear it wholesale.

For the record, the mosaic path does set `BIGTIFF=IF_SAFER` on both its intermediate and its COG,
so it does not hit the 4 GB ceiling that `gdal_translate -of COG` hit in `rap-extract-bands`.

## Run order

```bash
kubectl apply -n geo-workflows -f rap-extract-bands.yaml        # band 1 + band 4 COGs
kubectl apply -n geo-workflows -f rap-afg-migrate-hex.yaml      # AFG rows out of rap-pfg-cover
kubectl apply -n geo-workflows -f rap-afg-hex.yaml              # + h0-index 14, 78
kubectl apply -n geo-workflows -f rap-pfg-hex.yaml              # all 6, fresh, band 4

kubectl apply -n geo-workflows -f rap-s2-stage-all-zones.yaml   # 764 tiles x arte, iag
kubectl apply -n geo-workflows -f rap-s2-mosaic-all-zones.yaml
kubectl apply -n geo-workflows -f rap-s2-hex-all-zones.yaml
```

`rap-afg-migrate-hex` **must** precede `rap-pfg-hex`, which overwrites the same four partitions.
Each hex job guards its own precondition (single-band input; COG eastern edge past −105) and fails
loudly rather than silently rebuilding a defective layer.

`rap-raw-checksum.yaml` computes the SHA-256 of the staged raw for the STAC provenance block —
the S3 ETag is multipart and unusable for this.
