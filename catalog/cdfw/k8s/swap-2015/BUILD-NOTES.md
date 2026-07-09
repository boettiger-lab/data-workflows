# SWAP 2015 build notes (#379)

Three CDFW State Wildlife Action Plan 2015 companion layers → `public-cdfw/swap-2015/`.

## Result
| Layer | ds# | Features | Notes |
|---|---|---|---|
| provinces | ds1900 | 7 | one multipolygon per province (FeatureServer explodes to 14 single-part) |
| terrestrial-targets | ds1966 | 31 | Conservation Units + potential targets |
| aquatic-targets | ds2733 | 16 | HUC hydrologic units + aquatic targets |

Res 8, `parent-resolutions 0`, GeoParquet + PMTiles + hex. Validated: feature
counts and `_cng_fid` round-trip flat→hex; CA bbox; verify-stac + pmtiles-fields
lint pass (0 hard).

## Decisions that differ from the vanilla `cng-datasets workflow` output
1. **Download GeoJSON, not shapefile.** The ArcGIS Hub `format=shp` export
   truncates DBF field names to 10 chars (`Conservation_Unit`→`Conservati`,
   `Potential_Target`→`Potential_`, `SWAP_Province`→`SWAP_Provi`). `format=geojson`
   (spatialRefId 4326) preserves full names. Convert curls the GeoJSON, stages it
   to `raw/`, and converts the local file.
2. **Quote the source URL.** The generated convert command left the `&`-bearing
   Hub URL unquoted, so bash backgrounded curl and mis-parsed the rest. (Tool
   YAML-gen bug — filed upstream, worked around here.)
3. **Hex `completions: 1`.** `--chunk-size 1000` puts all ≤31 features in chunk 0,
   so the other 199 indexed pods are empty no-ops that only serve to land on and
   hang the flaky `hpc-nrp-g1` node. One completion is sufficient.

Sibling reference build: `catalog/cdfw/k8s/ace/terrestrial-biodiversity-summary/`.
