# rcn-national - build

TNC Resilient and Connected Network, nationally-consistent product, conterminous US.
Scope, provenance and pre-flight evidence: [#606](https://github.com/boettiger-lab/data-workflows/issues/606).

| | |
|---|---|
| Source | `RCN_National_2024` in `RCN.gdb`, 193419 × 133487, Int32, 30 m, NAD83 Albers, no declared nodata |
| Staged raw | `s3://public-connectivity/raw/Resilient_and_Connected_Network_National_2024.zip` (1470642324 B, sha256 `6993d6c4…4b45a`, accessed 2026-09-15) |
| Band | `rcn_class`, uint8, nodata **255** |
| H3 | native **10**, parents `9,8,7,6,5,0` - matches `land-cover/nlcd`, the same 30 m CONUS categorical raster |
| Reducer | `mode`, plus a `fractions` companion |

## Run order

The orchestrator (`workflow.yaml`) only covers setup-bucket → hex. The reclass and the
fractions companion are separate Jobs, applied around it.

```bash
kubectl apply -n geo-workflows -f workflow-rbac.yaml            # one-time
kubectl apply -n geo-workflows -f rcn-national-setup-bucket.yaml
kubectl apply -n geo-workflows -f rcn-national-reclassify.yaml  # hours; writes rcn-national-cog.tif
kubectl wait  -n geo-workflows job/rcn-national-reclassify --for=condition=complete --timeout=43200s
kubectl apply -n geo-workflows -f rcn-national-hex.yaml
kubectl apply -n geo-workflows -f rcn-national-hex-fractions.yaml
```

Validate before anything downstream reads it:

```bash
scripts/check-hex-coverage.sh nrp:public-connectivity/rcn-national/hex/ \
  --reference nrp:public-connectivity/rcn-national/hex-fractions/
```

## Why the reclass exists

The pixel value is not the class. `Value` (100000 to 404311) is a composite digit-position code:
leading digit is the methods region, the rest are the Resilience / Recognized Biodiversity /
Secured / Climate Connectivity / Marsh Migration flags. The class is the VAT field
`RCN_DESC_NEW`, whose numeric code sits in the VAT column `Vals`. Hexing the raw band with
`mode` returns composite codes, not RCN classes.

`band.GetDefaultRAT()` returns `None` - OpenFileGDB does not attach the CONUS VAT - so the LUT
is built from the pre-flight dump at `s3://public-connectivity/raw/vat/a00000020_vat_RCN_National_2024.csv`
(297 rows).

`rcn_class` coding:

| Code | Meaning |
|---|---|
| 10, 20, 30, 40, 50, 60, 70, 80, 90, 91, 92, 93 | VAT `Vals`, as-is |
| 0 | `Not in Network` (VAT class with no `Vals`) |
| 1 | `Resilient Not in Network` (VAT class with no `Vals`) |
| 255 | nodata - no VAT row, i.e. off-CONUS background |

**`0` is a real class.** The precedent this job was copied from
(`catalog/cwhr/k8s/reclassify-fveg.yaml`) warps with `-srcnodata 0 -dstnodata 0`, which here
would silently merge the background into `Not in Network`.

The reclass job checks itself: the VAT's `Count` column is the exact source histogram, so it
compares its own per-class pixel counts against it and fails on any mismatch or any
non-canonical output code.

## Why 16 completions, not 122

`--h0-subset 6,9,12,14,15,18,20,35,50,59,71,78,89,90,96,100`.

Derived from the **source grid footprint**, not from where CONUS is: the Albers extent
(−2848835, −229014 → 2953735, 3775596) densified and reprojected to WGS84 gives
lon −137.21…−53.47, lat 16.95…57.28, and those are the h0 base cells covering it. That is a
superset of the data, so nothing can be dropped; the CONUS bbox alone would give 9. The
remainder produce no output and are not worth a pod.

## Open

- **Licence blocks publication, including the COG.** TNC prohibits redistribution without
  approval (#151); `public-connectivity` is a public bucket, so writing there is redistribution.
  Resolve before running anything in the order above.
- **Acceptance criterion "dateline h0 `576707042908045311` present" does not apply.** That cell
  is Alaska's, and Alaska is out of scope (#684). Nothing in a CONUS-only product reaches the
  dateline.
