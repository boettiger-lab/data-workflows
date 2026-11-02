# Onsite Sewage Disposal Systems, five islands: build notes

Issue: https://github.com/boettiger-lab/data-workflows/issues/837
Bucket: `s3://public-hawaii/`, dataset `osds`
Raw retrieved: 2026-11-02

## Source

Hawaiʻi DOH source water protection program, served by the Hawaiʻi Statewide GIS Program as
`Infrastructure/MapServer` layers 22 (Oʻahu, 2008), 23 (Molokaʻi), 24 (Maui), 25 (Kauaʻi) and
26 (Hawaiʻi), all 2010. Live service, no edition label, so the staged responses are the
provenance. sha256 values were computed in the stage-raw job from the staged objects:

| object (`raw/osds/`) | bytes | sha256 |
|---|---|---|
| `osds-oahu-service-response.geojson` | 12,121,342 | `e9f95286005dfb64c9ed2085638abbd4425717da3c600baf7b31bee0c78b042a` |
| `osds-molokai-service-response.geojson` | 1,203,731 | `2106f55609cd7ad97989cdcbba36a0a181c658cf1f72967dde2eb7246eff884c` |
| `osds-maui-service-response.geojson` | 9,054,743 | `1530ccb012fad27c5a9f866ce5262b3e83f776dc3726c256ce731449e3bc213f` |
| `osds-kauai-service-response.geojson` | 9,761,754 | `97a755e45d3906c6d4bb1eabfe6f5384647d8c3ccaabed7c7441a643c9d4a714` |
| `osds-hawaii-service-response.geojson` | 38,784,619 | `6705ed61f8d645a2c473074c8d5b8b5db272d53c58aebda290070a8976417935` |
| `osds.geojson` (merged convert input) | 140,900,116 | `749458ff0ae7a915e489071243d72247e07292861f1e8709fe8695fa176c57da` |
| `osds_oah.pdf`, `osds_ni.pdf` (metadata) | 125,983; 147,854 | `a0a406c1…`; `665883a4…` |

Licence: the ArcGIS item of every one of the five layers carries the same licenseInfo: State of
Hawaii Terms of Use, contents public domain and exempt from its restrictions, no warranty. So
`license: public-domain`, as for `coral-reefs`.

## Merge

Two schemas: Oʻahu (2008, per-class fields) and the neighbour islands (2010, parcel totals and
treatment-plant fields). Union of fields; `layer_island`, `county`, `survey_year` added from the
layer. Maui types ten text fields as numbers, 0 on all 12,780 rows (checked via the REST API
and asserted in the job); they are nulled so each column keeps one type.

## Measured (duckdb-geo MCP, 2026-11-02)

- 94,996 points = 13,684 + 1,651 + 12,780 + 13,351 + 53,530, matching each layer's REST count;
  94,996 distinct `_cng_fid`; no empty geometry; bboxes fall on the right islands.
- Hex: 94,996 rows, 3,930 distinct h8, 2 h0 partitions, no null h8.
- Sentinels: `class`, `prmt_no`, `prmt_id` = -9999 on 81,100 of 81,312 neighbour-island rows (no
  treatment-plant record). `bldexem` = -1 on 41 rows (38 Maui, 3 Molokaʻi), undocumented upstream.
  No other numeric column has a negative value.
- `effluent` 0–90,500 (integers): upstream says million gallons/day; the values fit gallons/day.
- 147 Kauaʻi rows have `island` = ' ' and `tmk` = 0 (and `class` = 0).
- Empty text is a single space (length 1). `verify-stac.py` reports `values-extra` for `''`
  on the coded columns because its DISTINCT check does not see whitespace-only strings; the
  values are real.

## Run order

```bash
kubectl apply -n geo-workflows -f osds-stage-raw.yaml
kubectl apply -n geo-workflows -f workflow-rbac.yaml -f configmap.yaml -f workflow.yaml
python3 gen_stac.py /tmp/hi-osds
rclone copyto /tmp/hi-osds/stac-collection.json nrp:public-hawaii/osds/stac-collection.json
rclone copyto /tmp/hi-osds/README.md nrp:public-hawaii/osds/README.md
# child link added to public-hawaii/stac-collection.json (read-modify-write)
```
