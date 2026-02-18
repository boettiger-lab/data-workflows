# Dataset Completion Status

This document tracks the completion status of datasets in the boettiger-lab/datasets repository. 

**Important Note**: Most S3 buckets are **COLLECTIONS** containing multiple sub-datasets, not single datasets.

**File Formats:**
- ✅ **PMTiles** (for visualization)
- ✅ **GeoParquet** (for analysis)
- ✅ **H3 Hexagons** (partitioned by h0)
- ✅ **Cloud-Optimized GeoTIFF (COG)** (for rasters)

**Documentation & Metadata:**
- ✅ **README.md** (Comprehensive description & source info)
- ✅ **STAC Collection** (`stac-collection.json` with correct links)
- ✅ **Column Definitions** (`table:columns` schema in STAC/README)

**H3 Encoding Types:**
- **STRING** (VARCHAR): Hexadecimal strings like `8001fffffffffff` (most datasets)
- **INTEGER** (BIGINT/UBIGINT): Numeric IDs like `577199624117288959` (CPAD, Mapping Inequality)

**Standard Workflow:** See [DATASET_DOCUMENTATION_WORKFLOW.md](DATASET_DOCUMENTATION_WORKFLOW.md).

---

## ✅ Complete Dataset Collections

### CPAD (California Protected Areas Database)
- **Status:** 🌟 Gold Standard
- **Type:** Vector Collection (3 sub-datasets)
- **Bucket:** `public-cpad`
- **Organization:** CPAD-pattern (named directories = datasets)
- **Encoding:** INTEGER (BIGINT/UBIGINT)

#### Sub-Datasets:

**1. cced-2025b** (California Conservation Easement Database)
- **Formats:**
  - ✅ PMTiles
  - ✅ GeoParquet
  - ✅ H3 Hexagons (h8, h9, h10, INTEGER encoding)
- **Documentation:** Part of collection README/STAC

**2. cpad-2025b-holdings** (CPAD Holdings)
- **Formats:**
  - ✅ PMTiles
  - ✅ GeoParquet
  - ✅ H3 Hexagons (h8, h9, h10, INTEGER encoding)
- **Documentation:** Part of collection README/STAC

**3. cpad-2025b-units** (CPAD Units)
- **Formats:**
  - ✅ PMTiles
  - ✅ GeoParquet
  - ✅ H3 Hexagons (h8, h9, h10, INTEGER encoding)
- **Documentation:** Part of collection README/STAC

**Collection Documentation:**
- ✅ README.md (Comprehensive)
- ✅ STAC Collection
- ✅ Column Definitions

---

### IUCN Species Richness
- **Status:** 🌟 Gold Standard
- **Type:** Raster Collection (14 sub-datasets)
- **Bucket:** `public-iucn`
- **Organization:** IUCN-pattern (format dirs: `hex/`, `cog/` contain sub-datasets)
- **Encoding:** STRING (VARCHAR)

#### Sub-Datasets in `hex/` (all h8, STRING):
1. ✅ amphibians_sr
2. ✅ amphibians_thr_sr
3. ✅ birds_sr
4. ✅ birds_thr_sr
5. ✅ combined_rwr (Range-Weighted Richness)
6. ✅ combined_sr (Species Richness)
7. ✅ combined_thr_rwr (Threatened RWR)
8. ✅ combined_thr_sr (Threatened SR)
9. ✅ fw_fish_sr (Freshwater Fish)
10. ✅ fw_fish_thr_sr
11. ✅ mammals_sr
12. ✅ mammals_thr_sr
13. ✅ reptiles_sr
14. ✅ reptiles_thr_sr

#### COG Layers in `cog/richness/`:
- ✅ 14 COG files (matching hex sub-datasets)

**Collection Documentation:**
- ✅ README.md (Comprehensive)
- ✅ STAC Collection
- ✅ Column Definitions

---

### Wetlands Collection
- **Status:** ✅ Complete (3 sub-datasets)
- **Type:** Mixed (Vector + Raster)
- **Bucket:** `public-wetlands`
- **Organization:** Directory-based (ramsar/, glwd/, nwi/)
- **Encoding:** STRING (VARCHAR)

#### Sub-Datasets:

**1. Ramsar** (Wetlands of International Importance)
- **Formats:**
  - ✅ PMTiles
  - ✅ GeoParquet
  - ✅ H3 Hexagons (h1-h9, STRING encoding)
- **Documentation:**
  - ✅ README.md (part of wetlands-global)
  - ✅ STAC Collection
  - ✅ Column Definitions

**2. GLWD** (Global Lakes and Wetlands Database)
- **Formats:**
  - ⚠️ Raster (33 class TIFFs, not COGs)
  - ✅ H3 Hexagons (h8, STRING encoding)
  - ✅ Category codes CSV
- **Documentation:**
  - ✅ README.md (part of wetlands-global)
  - ✅ STAC Collection
  - ❌ Column Definitions (need category codes integrated)
- **Issues:** Raw TIFFs need conversion to COGs

**3. NWI** (National Wetlands Inventory - USA)
- **Formats:**
  - ❌ PMTiles
  - ❌ GeoParquet
  - ✅ H3 Hexagons (h8, STRING encoding)
- **Documentation:**
  - ❌ README.md
  - ❌ STAC Collection
  - ❌ Column Definitions
- **Issues:** Missing parquet/pmtiles, only has hex data

**Collection Documentation:**
- ✅ README.md (wetlands-global)
- ✅ STAC Collection (wetlands-global)

---

## ✅ Complete Single Datasets

### WDPA (World Database on Protected Areas)
- **Status:** ✅ Complete
- **Type:** Vector
- **Bucket:** `public-wdpa`
- **Formats:**
  - ✅ PMTiles
  - ✅ GeoParquet
  - ✅ H3 Hexagons (h8, STRING encoding)
- **Documentation:**
  - ✅ README.md (Comprehensive)
  - ✅ STAC Collection
  - ✅ Column Definitions (Full WDPA Dictionary)

---

### Mapping Inequality (Redlining)
- **Status:** ✅ Complete
- **Type:** Vector
- **Bucket:** `public-mappinginequality`
- **Formats:**
  - ✅ PMTiles
  - ✅ GeoParquet
  - ✅ H3 Hexagons (h8, h9, h10, INTEGER encoding)
- **Documentation:**
  - ✅ README.md (Comprehensive)
  - ✅ STAC Collection
  - ✅ Column Definitions (DSL Richmond dictionary)

---

### GBIF (Occurrence Data)
- **Status:** ✅ Complete (Derived Products)
- **Type:** Vector
- **Bucket:** `public-gbif`
- **Formats:**
  - ❌ PMTiles (Not for this subset)
  - ✅ GeoParquet (Redlined Cities Subset)
  - ✅ H3 Hexagons (h0-h11, STRING encoding)
- **Documentation:**
  - ✅ README.md (Describes derived assets)
  - ✅ STAC Collection
  - ✅ Column Definitions (Mapping Inequality + Taxa)

---

### iNaturalist
- **Status:** ✅ Complete (Species Ranges)
- **Type:** Vector
- **Bucket:** `public-inat`
- **Formats:**
  - ✅ GeoParquet (27 taxonomic class files)
  - ✅ H3 Hexagons (h4, STRING encoding)
- **Documentation:**
  - ✅ README.md (Describes ranges, not observations)
  - ✅ STAC Collection
  - ✅ Column Definitions (Taxon ID, Geomodel Version)
- **Note:** Organized as flat parquet files by taxonomic class

---

### Overture Maps
- **Status:** ✅ Complete (Divisions)
- **Type:** Vector
- **Bucket:** `public-overturemaps`
- **Formats:**
  - ✅ GeoParquet (Regions & Countries)
  - ✅ PMTiles (Regions)
  - ✅ H3 Hexagons (h8, STRING encoding for regions)
- **Documentation:**
  - ✅ README.md
  - ✅ STAC Collection
  - ✅ Column Definitions
- **Note:** Countries file may not have hex representation

---

## ⚠️ Partially Complete Datasets

### Carbon (Irrecoverable/Manageable)
- **Status:** ⚠️ Partial (Inconsistent Structure)
- **Type:** Raster
- **Bucket:** `public-carbon`
- **Encoding:** STRING (VARCHAR)

**Available:**
- ✅ COG (18 files in `cogs/`)
  - irrecoverable_c (biomass, soil, total) x 2 years
  - manageable_c (biomass, soil, total) x 2 years
  - vulnerable_c (biomass, soil, total) x 2 years
- ✅ H3 Hexagons for `vulnerable-carbon` (h3-h8, STRING, partitioned)
- ✅ H3 Flat files (3 US-specific h8 parquet files)

**Documentation:**
- ✅ README.md (Detailed Methodology)
- ✅ STAC Collection
- ✅ Layer Descriptions

**Issues:**
- Missing partitioned hex for irrecoverable and manageable carbon
- Mixed organization (partitioned vs flat hex files)
- Inconsistent hex coverage across sub-datasets

---

### NCP (Nature's Contributions to People)
- **Status:** ⚠️ Partial
- **Type:** Raster
- **Bucket:** `public-ncp`
- **Formats:**
  - ✅ COG (4 files at root)
  - ✅ H3 Hexagons (h8, STRING encoding for `ncp_biod_nathab` only)
- **Documentation:**
  - ✅ README.md (Chaplin-Kramer et al. 2019)
  - ✅ STAC Collection
  - ✅ Layer Definitions
- **Issues:** Only one sub-dataset has hex representation

---

### Social Vulnerability Index (SVI)
- **Status:** ❓ Needs Investigation
- **Type:** Vector
- **Bucket:** `public-social-vulnerability`
- **Formats:**
  - ✅ PMTiles
  - ✅ GeoParquet
  - ❓ H3 Hexagons (needs investigation)
- **Documentation:**
  - ✅ README.md (Linked to CDC docs)
  - ✅ STAC Collection
  - ✅ Column Definitions (RPL_THEME variables)

---

### ECOM Farm Polygons
- **Status:** ❓ Needs Investigation
- **Type:** 
- **Bucket:** 
- **Formats:**
  - 
- **Documentation:**
  - https://berkeley.app.box.com/folder/359824940922

---

## ❌ Incomplete / No Hex Data

### HydroBasins
- **Status:** ⚠️ No Hex Data
- **Type:** Vector
- **Bucket:** `public-hydrobasins`
- **Formats:**
  - ✅ PMTiles (Zoom-based)
  - ✅ GeoParquet
  - ❌ H3 Hexagons (not found -- FIXME look harder, they exist in the bucket)
- **Documentation:**
  - ✅ README.md (Basic)
  - ✅ STAC Collection
  - ✅ Column Definitions

---

### US Census
- **Status:** ⚠️ No Hex Data
- **Type:** Vector (Index Only)
- **Bucket:** `public-census`
- **Formats:**
  - ❌ PMTiles (Not needed for index)
  - ❌ GeoParquet (Uses hive-partitioned parquet)
  - ❌ H3 Hexagons (not found)
- **Documentation:**
  - ✅ README.md (Clarifies crosswalk nature)
  - ✅ STAC Collection
  - ✅ Column Definitions (FIPS only)

---

## Major Updates Needed

- [ ] **Carbon:** 
  - Create partitioned hex for irrecoverable and manageable carbon
  - Standardize organization (all in `hex/` with sub-datasets)
  - Update to 2025 release (https://zenodo.org/records/17645053)
  
- [ ] **NWI (Wetlands):**
  - Create parquet and pmtiles files
  - Add proper documentation (README, STAC, column definitions)
  
- [ ] **GLWD (Wetlands):**
  - Convert TIFFs to COGs
  - Integrate category codes into documentation
  
- [ ] **STAC Catalogs:**
  - Update all catalogs to reflect sub-dataset structure
  - Define whether sub-datasets are individual STAC items or grouped

---

## ❌ Incomplete / Unpublished

- **CalEnviroScreen**: No published data
- **Fire**: Bucket exists but empty
- **PAD-US**: No published data

---

## Organizational Patterns

### Pattern A: CPAD-style
Named directories = datasets (best for vector data with multiple releases)
```
bucket/
├── dataset-1/
│   ├── .parquet, .pmtiles, hex/
└── dataset-2/
    ├── .parquet, .pmtiles, hex/
```

### Pattern B: IUCN-style
Format directories contain sub-datasets (best for raster data with many layers)
```
bucket/
├── cog/
│   ├── layer1.tif, layer2.tif
└── hex/
    ├── layer1/, layer2/
```

### Pattern C: Simple
Single dataset per bucket
```
bucket/
├── .parquet, .pmtiles
└── hex/
```
