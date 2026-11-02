# Benthic habitats of the main Hawaiian Islands (NOAA NCCOS 2007): build notes

Issue: https://github.com/boettiger-lab/data-workflows/issues/843
Bucket: `s3://public-hawaii/`, dataset `benthic-habitat-2007`
Raw retrieved: 2026-11-02

## Source

Hawaiʻi Statewide GIS Program `CoastalMarine/MapServer/1` ("Benthic Habitat"): NOAA NCCOS 2007
mapping of the main eight islands, downloaded by the program from NCCOS in Feb 2018 and merged
statewide. Live service, no edition label, so the staged response is the provenance. sha256 values
were computed in the stage-raw job from the staged objects:

| object (`raw/benthic-habitat-2007/`) | bytes | sha256 |
|---|---|---|
| `benthic-habitat-2007-service-response.geojson` (untouched, outSR=4326) | 80,134,352 | `ff37f44c77853be1a1abec33264118072e33e57a560b49ce4aac131568436dee` |
| `benthic-habitat-2007.geojson` (convert input) | 79,436,283 | `c1596f73f4bd7ec0f53e5ca63e1a8fdaf797de475e0e6c2cdfb557eb696ab2b4` |
| `benthic_habitat.pdf` (metadata) | 106,471 | `c13ef06961f685bb3a6411c6d1169a289b973678de7ad8b76d57f6e9d5dc0074` |

Licence: NOAA work (US Government), and the ArcGIS item's licenseInfo says the contents are public
domain and exempt from the State of Hawaii Terms of Use restrictions. `license: public-domain`.

Fields dropped: `st_area(shape)`, `st_perimeter(shape)` (State Plane units, derived).

## Measured (duckdb-geo MCP, 2026-11-02)

- 8,762 polygons, all valid, all POLYGON; 8,762 distinct `_cng_fid`; matches the REST count.
- `acres` sums to 5,029,977; geometry area 5,022,764 acres. Zone `Land` is 4,118,898 acres and
  zone `Unknown` 581,151, so mapped seafloor is about 330,000 acres.
- `m_cover = 'Unclassified'` and `p_cover = ' '` are exactly the 2,108 `Other Delineations`
  (Land + Artificial) polygons. `polygonid` has 2,381 distinct values (not unique).
- Hex: 1,169,363 rows, 8,762 `_cng_fid`, 2 h0 partitions, no null h10/h9/h8. Distinct-h10 cell
  area per zone is within 0.2–2% of `acres` for large zones and up to 11% over for narrow ones
  (Reef Crest 1.11, Reef Hole 1.107, Shoreline Intertidal 1.092): touched-cell counting (#778).
- `verify-stac.py` reports `values-extra` for `''` on `p_cover`; the value is a single space,
  which its DISTINCT check does not see.

## Run order

```bash
kubectl apply -n geo-workflows -f benthic-habitat-2007-stage-raw.yaml
kubectl apply -n geo-workflows -f workflow-rbac.yaml -f configmap.yaml -f workflow.yaml
HEX_ROWS=1169363 HEX_FIDS=8762 python3 gen_stac.py /tmp/hi-benthic
rclone copyto /tmp/hi-benthic/stac-collection.json nrp:public-hawaii/benthic-habitat-2007/stac-collection.json
rclone copyto /tmp/hi-benthic/README.md nrp:public-hawaii/benthic-habitat-2007/README.md
# child link added to public-hawaii/stac-collection.json (read-modify-write, 2026-11-02)
```
