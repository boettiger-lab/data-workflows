# Hawaii coral reefs (NOAA nautical charts): build notes

Issue: https://github.com/boettiger-lab/data-workflows/issues/782
Bucket: `s3://public-hawaii/` (new), dataset `coral-reefs`
Raw retrieved: 2026-10-14

## Source

Hawaii Statewide GIS Program, `CoastalMarine/MapServer/7` ("Coral Reefs (Nautical Chart)"),
digitized from NOAA raster nautical charts of 2002. Live service with no edition label, so the
staged response is the provenance. sha256 values were recomputed from the staged objects:

| object | bytes | sha256 |
|---|---|---|
| `raw/coral-reefs-service-response.geojson` (untouched, outSR=4326) | 2,527,148 | `d42b995ce1c37dab2a06f6a7e1cbec624132b9ad728bc737db96ae02823dca9c` |
| `raw/coral-reefs.geojson` (convert input, `id` dropped) | 2,619,956 | `a1a913d745b91688fd48049e4bc629daa4036c19d88080566cb65c662ffc87ee` |
| `raw/coralreefs_nc.pdf` (upstream metadata) | 106,679 | `9b80daf856abcd00ee3d0338f35e39f1f3a59d8902612629a94140a85c074932` |

Licence: the ArcGIS item's licenseInfo says the contents are public domain and exempt from the
State of Hawaii Terms of Use restrictions, so `license: public-domain`.

## Measured (duckdb-geo MCP, 2026-10-14)

- 474 polygons (387 Polygon, 87 MultiPolygon in the source), all valid; 474 distinct `_cng_fid`.
- `acres` 0 to 3,189.9 (one row is 0), sum 33,355.25.
- bbox -159.7888, 18.9666, -155.0146, 22.2311.
- Hex: 8,028 rows at h10, all 474 polygons present, 2 h0 partitions, no null h10/h9/h8.
  Area of distinct h10 cells is 34,214 acres, 2.6% over the features' own `acres`.
- `chart2` is the empty string on 419 rows and `notes` on 457 (not NULL). `notes` has two
  spellings of "Coral Reef Extremely Shoal" (one with a double space), as in the source.
  `verify-stac.py` reports `values-extra` for `''` on both columns: its DISTINCT check does not
  see empty strings. The values are real.

## Fields dropped

| field | reason |
|---|---|
| `id` | 0 on all 474 rows (stage-raw asserts this) |
| `st_area(shape)`, `st_perimeter(shape)` | StatePlane units, derived |

## Run order

```bash
kubectl apply -n geo-workflows -f coral-reefs-setup-bucket.yaml   # new bucket: before stage-raw
kubectl apply -n geo-workflows -f coral-reefs-stage-raw.yaml
kubectl apply -n geo-workflows -f workflow-rbac.yaml -f configmap.yaml -f workflow.yaml
python3 gen_stac.py /tmp/hi-coral
rclone copyto /tmp/hi-coral/stac-collection.json nrp:public-hawaii/coral-reefs/stac-collection.json
rclone copyto /tmp/hi-coral/README.md nrp:public-hawaii/coral-reefs/README.md
rclone copyto /tmp/hi-coral/bucket-stac-collection.json nrp:public-hawaii/stac-collection.json
# root catalog: child link to public-hawaii/stac-collection.json added once (2026-10-14)
```
