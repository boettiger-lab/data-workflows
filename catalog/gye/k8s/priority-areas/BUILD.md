# public-gye/priority-areas — build notes (#769)

Greater Yellowstone Ecosystem priority areas (Absaroka Front, Upper Green, Upper Wind River),
moved out of `public-wyoming/priority-areas-gye` into the new `public-gye` bucket (#225, #578)
and rebuilt through the stock `cng-datasets workflow` so flat, PMTiles and hex share one
`_cng_fid` numbering.

## Source

`s3://public-wyoming/raw/PriorityAreas_GYE.gpkg` — the original input (no convert recipe for it
was ever committed; the old `catalog/wyoming/k8s/priority-areas-gye/` only re-hexed the derived
parquet). Copied byte-for-byte to `s3://public-gye/raw/PriorityAreas_GYE.gpkg`.

| | |
|---|---|
| layer | `PriorityAreas_GYE`, Polygon, EPSG:3857, 3 features |
| attributes | `Name` (String 64) |
| size | 98,304 bytes |
| sha256 | `496e143c4bb8df1f16b90b20f6ca738b137c3821b2e483d282d9b5a9c1bb08ca` (recomputed from the object) |
| md5 | `9b679e9a37f9edd9c78f43ee1a3a87e9` |
| staged | 2026-03-12 (object date; upstream pull date unknown, no edition label) |

## Generation

```bash
cng-datasets workflow --dataset priority-areas \
  --source-url s3://public-gye/raw/PriorityAreas_GYE.gpkg --bucket public-gye \
  --namespace geo-workflows --h3-resolution 11 --parent-resolutions "10,9,8,0" \
  --chunk-size 1000 --max-completions 1 --max-parallelism 1 --intermediate-chunk-size 1 \
  --hex-memory 64Gi --expect-features 3 --output-dir catalog/gye/k8s/priority-areas
```

Native 11 / parents 10,9,8,0 are the live build's resolutions (#136). One hex pod for all three
features (`--chunk-size 1000` turns off cells-per-chunk planning); `--intermediate-chunk-size 1`
unnests one area at a time — Upper Green alone is ~10.9 M resolution-11 cells.

Run order: `priority-areas-setup-bucket.yaml` alone first (new bucket), stage raw, then
`configmap.yaml` + `workflow.yaml`.

STAC: `python catalog/gye/scripts/gen_stac.py` (with `BUILT_*` set from the objects' dates),
plus a hand-written `LICENSE.md` terms statement; published to
`public-gye/priority-areas/{stac-collection.json,LICENSE.md}` and `public-gye/stac-collection.json`,
child link appended to `public-data/stac/catalog.json`.

## Measured

Built 2026-10-10 (workflow 4 min end to end). Objects: `priority-areas.parquet` 1,700 B,
`priority-areas.pmtiles` 291,028 B, hex 2 h0 partitions (267 MB + 26 MB).

| check | result |
|---|---|
| flat rows / distinct `_cng_fid` | 3 / 3 (`_cng_fid` 1-3 = GeoPackage `fid` 1-3) |
| geometry vs old `public-wyoming/priority-areas-gye.parquet` | `ST_Equals` true for all 3, vertex counts 15/11/15 |
| flat columns | `_cng_fid`, `fid`, `Name`, `geometry` (no `bbox` column is written) |
| hex columns | `_cng_fid`, `fid`, `Name`, `h11`, `h10`, `h9`, `h8`, `h0`; no NULL parents |
| hex distinct h11 | Absaroka Front 5,959,890; Upper Green 10,903,703; Upper Wind River 6,391,149 — identical to the old build |
| hex distinct h10 | 852,789; 1,559,602; 914,925 — identical to the old build |
| hex distinct h8 | 17,683; 32,220; 19,056 |
| hex `COUNT(DISTINCT _cng_fid)` | 3 |
| shared h11 cells between areas | 0 |
| PMTiles footer | layer `priority-areas`, fields `Name` (String), `_cng_fid` (Number), `fid` (Number) |
| `verify-stac.py --bucket public-gye --dataset priority-areas` | exit 0 (1 ADVISORY: `license-terms-self-hosted`) |

Licence: none located. The old collection's licence link was Wyoming Game & Fish's data page,
copied from the WGFD siblings — not this producer's terms — so it was dropped; the collection now
links a self-hosted terms statement that grants nothing (see #769, pending Carl's confirmation).
