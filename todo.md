# Dataset Catalog To-Do

Last audited: 2026-03-03

**Standard outputs per dataset:** GeoParquet · PMTiles · H3 Hex Parquet · STAC Collection · README
**Standard workflow:** See [AGENTS.md](AGENTS.md) and [DATASET_DOCUMENTATION_WORKFLOW.md](DATASET_DOCUMENTATION_WORKFLOW.md).

---

## Quick-Reference: S3 Bucket Audit

| Bucket | Has Data? | STAC? | In Main Catalog? | Issues |
|--------|-----------|-------|-----------------|--------|
| `public-ca30x30` | ✅ | ❌ | ❌ | No STAC at all |
| `public-calenviroscreen` | ✅ | ✅ | ✅ | Root stac OK; `ces5/` subdir has no child stac |
| `public-carbon` | ✅ | ✅ | ✅ | OK; v2 hex still in progress |
| `public-census` | ✅ | ✅ | ✅ | Child links fixed 2026-03-03; umbrella title describes 2022 but children are 2024 TIGER |
| `public-cpad` | ✅ | ✅ | ✅ | 3 datasets in one stac with no children |
| `public-data` | catalog only | —  | — | Houses top-level catalog; no dataset stac needed |
| `public-datacenters` | ✅ CSV | ❌ | ❌ | Tabular only; low priority |
| `public-ecoregion` | ✅ | ❌ | ❌ | parquet+pmtiles+gdb+hex present; needs stac |
| `public-ecoregions` | ❌ empty | ❌ | ❌ | Empty bucket — consider deleting |
| `public-fire` | ⏳ raw/ only | ❌ | ❌ | In-progress |
| `public-gbif` | ✅ | ✅ | ✅ | Single stac; no children despite multiple products |
| `public-grids` | ⏳ hex/ only | ❌ | ❌ | In-progress |
| `public-hydrobasins` | ✅ | ✅ | ✅ | Spurious pseudo-dir; hex data presence unclear |
| `public-im3` | ✅ CSV/GPKG | ❌ | ❌ | Non-cloud-native formats; low priority |
| `public-inat` | ✅ | ✅ | ✅ | Spurious pseudo-dir |
| `public-iucn` | ✅ | ✅ | ✅ | Spurious pseudo-dir |
| `public-mappinginequality` | ✅ | ✅ | ✅ | Spurious pseudo-dir |
| `public-ncp` | ✅ | ✅ | ✅ | Spurious pseudo-dir; only 1/4 layers has hex |
| `public-output` | analysis CSVs | ❌ | ❌ | Not a published dataset |
| `public-overturemaps` | ✅ | ✅ | ✅ | 3 division types; stac has no children |
| `public-padus` | ✅ | ✅ | ✅ | 5 child stac-collections all valid as of 2026-03-03 |
| `public-redlining` | ✅ | ❌ | ❌ | Appears duplicate of `public-mappinginequality`; clarify |
| `public-social-vulnerability` | ✅ | ✅ | ✅ | 4 vintages + multiple levels; single stac with no children |
| `public-test` | test only | ❌ | ❌ | Not a published dataset |
| `public-wdpa` | ✅ | ✅ | ✅ | Spurious pseudo-dir |
| `public-wetlands` | ✅ | ✅ | ✅ | Spurious pseudo-dir; NWI missing parquet+pmtiles; GLWD TIFFs not COGs |
| `public-wyoming` | ✅ | ✅ | ✅ | 10 vector + 5 raster datasets; 7 vector have hex, 1 malformed, 2 skipped; 2/5 raster complete, 1 in progress, 2 pending |

---

## Action Items

### 🔴 High Priority

#### [x] Create STAC for `public-wyoming` — DONE 2026-03-04
Umbrella + 15 child stac-collections + README uploaded to S3. In top-level catalog.

#### [ ] Hex remaining `public-wyoming` datasets

**Vector datasets** (parquet + pmtiles exist; hex missing):
- [x] `blm-sma` — ✅ hex complete 2026-03-07 (chunks 12+15 rechunked at res 8 due to complex geometry)
- [ ] `sage-grouse-priority` — ⚠️ malformed hex: h0 partition key is decimal integer `577164439745200127` instead of H3 string ID; needs reprocessing
- ❌ `wyoming-places` — **SKIP: point geometry (99 POINT rows). `cng-datasets vector` uses `h3_polygon_wkt_to_cells` which requires polygons; points produce empty chunks. Point assignment via `h3_latlng_to_cell` is possible but not currently implemented in the tool.**
- ❌ `ungulate-migration` — **SKIP: line geometry (MultiLineString/LineString) not supported by `cng-datasets vector` hex tiling** (uses `h3_polygon_wkt_to_cells` which requires polygons). Source parquet has `geom` as WKB BLOB without GeoParquet metadata. Even if geometry was readable, line tiling requires a different approach.

**Raster datasets** (COG exists; hex missing — use `cng-datasets raster-workflow`):
- [x] `rap-pfg-biomass` — ✅ complete 2026-03-08 (1 real h0 cell for Wyoming; COG: `rap-v3-2025-band4-perennial-forb-grass-wyoming-cog.tif`)
- [x] `nlcd-2024` — ✅ complete 2026-03-09 (71 h0 partitions)
- [ ] `sagebrush-design` — ⏳ 97/122 in progress 2026-03-10 (20h, struggling with preemptions + ImagePullBackOff but not stalled; 19 active pods; COG: `sagebrush-cog.tif`)
- [ ] `rap-arte` — ⏳ running 2026-03-10; targeted 1-pod job (h0 index 20 = `8027fffffffffff`, the only Wyoming h0 cell); YAML: `rap-arte-hex-wyoming.yaml`
- [ ] `rap-iag` — YAML ready `rap-iag-hex-wyoming.yaml`; submit after rap-arte finishes

**Missing entirely** (no S3 data):
- [ ] `gye-parcels` — k8s YAML and STAC exist locally; source data never uploaded

#### [ ] Create STAC for `public-ecoregion`
Complete cloud-native stack already present: `ecoregion.parquet`, `ecoregion.pmtiles`, `ecoregion/hex/`, `ecoregions.gdb/`.
Straightforward single-dataset stac to write.

#### [ ] Create STAC for `public-ca30x30`
Multiple CA 30x30 versions exist — clarify canonical version before writing stac:
- `ca-30x30.parquet` / `ca-30x30.pmtiles` (root level)
- `ca30x30_cbn_v3.parquet` / `.pmtiles`
- `ca30x30cbn_newlyprotected_v1.parquet` / `.pmtiles`
- Subdirs: `CA_Nature/`, `CBN/`, `CPAD/`, `Preprocessing/`, `hex/`, `temp_versions/`

---

### 🟡 Medium Priority

#### [ ] Clarify `public-redlining` vs `public-mappinginequality`
`public-redlining` contains `mappinginequality.parquet`, `mappinginequality.pmtiles`, `chunks/`, `hex/` — appears to be the same dataset as `public-mappinginequality`. Determine: is this an older version, duplicate processing run, or alternate canonical location? Either consolidate buckets or add stac pointing to `public-mappinginequality` as canonical.

#### [ ] Add child stac-collections to `public-census` umbrella
The umbrella `stac-collection.json` describes a 2022 H3 spatial index, but the 4 children are 2024 TIGER geometry files. Update the umbrella title/description to cover both generations and clarify the relationship.

#### [ ] Add child stac-collections to `public-cpad`
Three distinct datasets (holdings, units, cced) share a single stac. Convert to umbrella + 3 child stac-collections (pattern already used by PAD-US and Census).

#### [ ] Add child stac-collections to `public-social-vulnerability`
Has data for 4 vintages (2000, 2010, 2020, 2022) and multiple geographic levels (`svi-2022-tract`, `svi2020_us_county`, plus per-year directories). Should become umbrella + children per vintage.

#### [ ] Add child stac or fix asset paths for `public-calenviroscreen`
Root stac exists but data lives at `calenviroscreen-5-0/ces5/`. Either add a child stac-collection at `calenviroscreen-5-0/ces5/stac-collection.json` or update root asset paths.

#### [ ] Add child stac-collections to `public-overturemaps`
Has 3 division types (countries, regions, counties). Should have children for each.

#### [ ] Complete NWI (National Wetlands Inventory) in `public-wetlands`
- ❌ Missing: GeoParquet, PMTiles (only hex exists)
- ❌ Missing: README, STAC, column definitions

#### [ ] Convert GLWD TIFFs to COGs in `public-wetlands`
Raw 33-class TIFFs need conversion. Integrate category codes into documentation.

---

### 🟢 Low Priority / Cleanup

#### [ ] Delete spurious `stac-collection.json/` pseudo-directories (7 buckets)
These are harmless legacy artifacts from incorrect `rclone copy` usage. Valid stac-collection.json files are unaffected.
```bash
for bucket in public-iucn public-mappinginequality public-ncp public-wdpa public-wetlands public-hydrobasins public-census; do
  name=$(rclone lsf nrp:${bucket}/stac-collection.json/)
  rclone deletefile "nrp:${bucket}/stac-collection.json/${name}"
  echo "Deleted ${bucket}/stac-collection.json/${name}"
done
```

| Bucket | Spurious key |
|--------|-------------|
| `public-iucn` | `stac-collection.json/iucn.json` |
| `public-mappinginequality` | `stac-collection.json/mappinginequality.json` |
| `public-ncp` | `stac-collection.json/ncp.json` |
| `public-wdpa` | `stac-collection.json/wdpa.json` |
| `public-wetlands` | `stac-collection.json/wetlands.json` |
| `public-hydrobasins` | `stac-collection.json/hydrobasins.json` |
| `public-census` | `stac-collection.json/census.json` |

#### [ ] Consider deleting `public-ecoregions` (empty bucket)
No objects found. Likely created in error.

#### [ ] Create STAC for `public-im3` and `public-datacenters` (tabular data)
Low priority; neither has cloud-native geospatial formats. Decide whether tabular-only datasets warrant catalog entries.

#### [ ] Verify hex data in `public-hydrobasins`
Existing todo notes hex "may exist in the bucket" — confirm and update stac asset links.

---

## Completed / Fixed

- [x] **2026-03-03** Added STAC Browser link to `README.md`
- [x] **2026-03-03** Reorganized `public-data/stac/catalog.json`: removed 8 individual layer links (4 PAD-US + 4 Census), kept one card per dataset family
- [x] **2026-03-03** PAD-US umbrella: added 5 child links (combined, fee, easement, marine, proclamation)
- [x] **2026-03-03** PAD-US combined: created `padus-4-1/combined/stac-collection.json` (was missing from S3)
- [x] **2026-03-03** Census umbrella: added 4 child links (state, county, tract, cd)
- [x] **2026-03-03** Census child stac files: re-uploaded to correct S3 paths (were stored as pseudo-directories, returning 404); corrected `parent` links to point at census umbrella
- [x] **2026-03-03** All updated stac files re-uploaded with `Cache-Control: no-cache`
- [x] **Carbon v2:** STAC and README updated (42 assets, temporal 2010–2024, both Zenodo DOIs)

---

## Dataset Detail: Per-Bucket Status

### public-padus — PAD-US 4.1 ✅
- ✅ 5 layers: combined, fee, easement, marine, proclamation
- ✅ Each has: parquet + pmtiles + h3-parquet + stac-collection.json
- ✅ Umbrella at `public-padus/stac-collection.json` with 5 child links
- ✅ In main catalog

### public-census — US Census ✅ (with caveats)
- ✅ 2024 TIGER: state, county, tract, cd — each has parquet + pmtiles + hex + stac
- ✅ 2022 spatial index (H3 crosswalk) at root
- ⚠️ Umbrella title/description only describes 2022 data — update needed
- ✅ In main catalog

### public-cpad — CPAD 2025b ⚠️
- ✅ 3 sub-datasets: holdings, units, cced (each: parquet + pmtiles + h3 hex, INTEGER encoding)
- ⚠️ Single stac-collection covers all 3; no children
- ✅ In main catalog

### public-carbon — Irrecoverable/Manageable Carbon ⚠️
- ✅ v1 COGs (18 files) + hex for irrecoverable and vulnerable
- ⏳ v2 (2025): COG preprocessing job running; 11 hex workflows pending
- ✅ STAC and README updated for v2
- ✅ In main catalog

### public-iucn — IUCN Species Richness ✅
- ✅ 14 sub-datasets (hex h8 STRING + COG)
- ✅ Comprehensive stac + README + column definitions
- ✅ In main catalog; spurious pseudo-dir (harmless)

### public-wetlands — Global Wetlands ⚠️
- ✅ Ramsar: parquet + pmtiles + hex (h1–h9 STRING) + stac
- ⚠️ GLWD: hex only; TIFFs not COGs; no column codes
- ❌ NWI: hex only; no parquet/pmtiles/stac/README
- ✅ In main catalog; spurious pseudo-dir (harmless)

### public-wdpa — WDPA ✅
- ✅ parquet + pmtiles + hex (h8 STRING) + stac + README + column definitions
- ✅ In main catalog; spurious pseudo-dir (harmless)

### public-mappinginequality — Mapping Inequality ✅
- ✅ parquet + pmtiles + hex (h8–h10 INTEGER) + stac + README + column definitions
- ✅ In main catalog; spurious pseudo-dir (harmless)

### public-gbif — GBIF Derived ✅
- ✅ parquet + hex (h0–h11 STRING) + stac + README + column definitions
- ⚠️ No child links despite multiple derived products
- ✅ In main catalog

### public-inat — iNaturalist ✅
- ✅ parquet (27 taxonomic class files) + hex (h4 STRING) + stac + README
- ✅ In main catalog; spurious pseudo-dir (harmless)

### public-overturemaps — Overture Maps ⚠️
- ✅ parquet + pmtiles + hex (h8 STRING) for regions; countries parquet
- ⚠️ 3 division types but single stac with no children
- ✅ In main catalog

### public-social-vulnerability — CDC SVI ⚠️
- ✅ parquet + pmtiles + stac + README + column definitions
- ⚠️ 4 vintages (2000, 2010, 2020, 2022) + multiple levels; single stac
- ✅ In main catalog

### public-hydrobasins — HydroBasins ⚠️
- ✅ parquet + pmtiles + stac + README + column definitions
- ❓ Hex data status unclear
- ✅ In main catalog; spurious pseudo-dir (harmless)

### public-ncp — Nature's Contributions to People ⚠️
- ✅ 4 COG layers + stac + README
- ⚠️ Only `ncp_biod_nathab` has hex representation
- ✅ In main catalog; spurious pseudo-dir (harmless)

### public-calenviroscreen — CalEnviroScreen 5.0 ⚠️
- ✅ Root stac + README
- ⚠️ Data at `calenviroscreen-5-0/ces5/` has no child stac
- ✅ In main catalog

### public-wyoming — Wyoming Wildlife & Land ⚠️
- ✅ STAC umbrella + 15 child stac-collections, in main catalog (2026-03-04)
- ✅ 7 vector datasets: parquet + pmtiles + hex complete
- ⚠️ 4 vector datasets missing hex: blm-sma, sage-grouse-priority, ungulate-migration, wyoming-places
- ✅ nlcd-2024, rap-pfg-biomass raster hex complete
- ⏳ sagebrush-design hex 97/122 running (2026-03-10)
- ❌ rap-arte, rap-iag hex pending (YAMLs ready)
- ❌ gye-parcels: no S3 data at all

### public-ca30x30 — CA 30×30 ❌
- ❌ No stac, not in catalog
- Multiple versions; needs clarification before documenting

### public-ecoregion — Ecoregions ❌
- ❌ No stac, not in catalog
- Complete stack present: parquet + pmtiles + hex + gdb

### public-redlining ❌
- ❌ No stac, not in catalog
- Possible duplicate of `public-mappinginequality`
