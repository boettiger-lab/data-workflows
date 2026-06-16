# source.coop repos to create (account: cboettig)

32 new repos. Create each in the source.coop web UI with **visibility: public**.
`repository_id` = the id below. Already-existing repos (carbon, ca30x30, cpad, fire, gbif, mappinginequality, mobi, social-vulnerability) are NOT listed — they only need a data refresh.

## ca-dac

**Title:** California Disadvantaged Communities (DAC) and Economically Distressed Areas (EDA), 2023

**Description:** California Department of Water Resources (DWR) layers identifying Disadvantaged Communities (DAC, MHI < 80% of statewide) and Economically Distressed Areas (EDA, MHI < 85% of statewide plus distress factors) at multiple Census geographies, joined to ACS 2019-2023 5-year estimates on 2020 Census boundaries.

## ca-wolves

**Title:** California Gray Wolf Monitoring

**Description:** California gray wolf pack territory polygons and GPS collar location snapshots from the CDFW Wolf Program.

## calenviroscreen

**Title:** CalEnviroScreen 5.0 (Draft)

**Description:** Draft CalEnviroScreen 5.0 (released January 2026) is a cumulative environmental pollution and health vulnerability screening tool developed by California's Office of Environmental Health Hazard Assessment (OEHHA).

## census

**Title:** US Census Geographic Boundaries

**Description:** US Census geographic boundary datasets in cloud-native formats. Includes 2024 TIGER/Line boundaries (state, county, census tract, congressional district) and 2025 state legislative districts (upper and lower chambers).

## cgs

**Title:** California Geological Survey (CGS) Datasets

**Description:** Geologic, geophysical, and neotectonic data products published by the California Geological Survey (CGS), often co-produced with the U.S. Geological Survey. Each child collection corresponds to a published Geologic Data Map (GDM) series volume.

## datacenters

**Title:** Global Data Center Locations

**Description:** Point dataset of global data center locations (Cloud Regions, Local Zones, On-Ramps) with provider, region, type, metro, country, and coordinates. Sourced from Cloud Infrastructure Map. CSV + GeoJSON.

## ecoregion

**Title:** WWF Terrestrial Ecoregions of the World (2017 update)

**Description:** Global terrestrial ecoregions from the World Wildlife Fund (WWF), based on the landmark Olson et al. (2001) classification. The dataset delineates 847 ecoregions grouped into 14 biomes and 9 biogeographic realms. Each ecoregion represents a distinct community of plants and animals sharing evolutionary history.

## epa-water

**Title:** EPA Water Datasets

**Description:** U.S. Environmental Protection Agency datasets related to drinking water and water utilities, processed into cloud-native formats (GeoParquet, PMTiles, H3 hex Parquet) for the Boettiger Lab data catalog.

## gfw

**Title:** Global Fishing Watch Annual Fishing Effort v3 (2012–2024)

**Description:** Annual apparent fishing effort derived from AIS vessel tracking data, aggregated to H3 resolution-6 hexagonal cells (~36 km²) by gear type. Source: Global Fishing Watch fleet-monthly dataset v3.0 (released March 2025), covering >190,000 AIS-tracked vessels globally.

## high-seas

**Title:** High Seas & Ocean Governance Datasets

**Description:** Cloud-native geospatial datasets supporting analysis of areas beyond national jurisdiction (ABNJ) and ocean governance. Includes maritime boundaries, seafloor geomorphology, fishing effort, biodiversity, and conservation priority datasets for the global high seas.

## hydrobasins

**Title:** HydroBasins Global Watershed Boundaries v1c

**Description:** Global watershed boundary data from HydroSHEDS HydroBasins v1c, organized by hierarchical basin levels (1-12). Compiled from multiple continental datasets into unified global layers. Available in GeoParquet and PMTiles formats.

## icca

**Title:** ICCA Registry — Indigenous and Community Conserved Areas

**Description:** The ICCA Registry is a global, community-submitted inventory of Indigenous and Community Conserved Areas (ICCAs) — territories and areas conserved by Indigenous Peoples and local communities through customary governance, cultural practice, and self-determined management.

## im3

**Title:** IM3 Open-Source Data Center Atlas

**Description:** Open-source atlas of data center locations from the IM3 (Integrated Multisector Multiscale Modeling) project — a point inventory of data centers as CSV + GeoPackage.

## inat

**Title:** iNaturalist Species Ranges & Taxonomy

**Description:** Modeled species ranges (polygons and H3 hexagons) and comprehensive taxonomic data from iNaturalist.

## indigenous

**Title:** LandMark: Indigenous & Community Land Rights (v202509)

**Description:** LandMark provides the world's first global platform to map land rights of Indigenous Peoples and local communities.

## iucn

**Title:** IUCN Species Richness 2025

**Description:** Global species richness and range-weighted richness maps derived from the IUCN Red List of Threatened Species (Version 2025.1), covering five taxonomic groups (Amphibians, Birds, Mammals, Reptiles, Freshwater Fish) plus all-taxa Combined layers.

## land-cover

**Title:** Land Cover (Global & US)

**Description:** Land-cover classification products. Two child collections: Copernicus Global Land Cover 100 m v3.0.1 (CGLS-LC100, 2019) and Annual NLCD Land Cover 2024 (CONUS, 30 m).

## landfire

**Title:** LANDFIRE — Vegetation & Fire Regimes (CONUS)

**Description:** LANDFIRE products for the conterminous US: Existing Vegetation Type (EVT 2023), Biophysical Settings (BPS 2020), and Fire Regime Groups (FRG 2016). WGS84 COG + source rasters.

## ncp

**Title:** Nature's Contributions to People (NCP) - Biodiversity Indicators

**Description:** Global indicators of Nature's Contributions to People (NCP) focusing on biodiversity and natural habitat, derived from Chaplin-Kramer et al. (2019). Two layers: ncp_biod_nathab (NCP weighted by biodiversity & natural habitat) and ncp_only (NCP alone) — integer indicator scores (count of NCP a location ranks highly for).

## overturemaps

**Title:** Overture Maps Divisions

**Description:** Global administrative boundaries (country, region/state/province, county/district) from the Overture Maps Foundation Divisions theme. Versioned releases processed into GeoParquet, PMTiles, and H3 hex-partitioned parquet with an English name column (`name_en`) for all features.

## padus

**Title:** PAD-US 4.1 - Protected Areas Database of the United States

**Description:** The Protected Areas Database of the United States (PAD-US) 4.1 is a comprehensive national inventory of 656,986 protected areas managed by USGS Gap Analysis Project (GAP).

## population

**Title:** Population & Demography

**Description:** Global and regional human population and demography layers. Seeded with GHS-POP (GHSL R2023A); intended home for future WorldPop, LandScan, and age-stratified population surfaces.

## rap

**Title:** Rangeland vegetation cover (RAP / rangeland-s2)

**Description:** NTSG (University of Montana) rangeland vegetation-cover products aggregated to H3: RAP Vegetation Cover v3 (CONUS) and rangeland-s2 Sentinel-2 functional-group covers.

## rivers

**Title:** US Rivers

**Description:** Parent collection for US river conservation datasets. Currently American Rivers: eight river conservation & water-infrastructure datasets spanning identification, protection, and restoration of US rivers.

## tpl

**Title:** Trust for Public Land datasets

**Description:** TPL-sourced datasets hosted on NRP Nautilus S3. The Conservation Almanac 2024 has been split into two collections — `conservation-almanac-2024-sites` (one row per protected site, with geometry and H3 hex aggregation) and `conservation-almanac-2024-funding` (long transaction table, no geometry) — joined by `tpl_id`.

## trails

**Title:** U.S. Federal Trails Network

**Description:** Federal-agency-managed trail systems harmonized into a single per-segment dataset. v1 includes U.S. Forest Service NFST and National Park Service Public Trails; BLM is reserved for a future v2 release when a unified national source is identified.

## usfws

**Title:** U.S. Fish and Wildlife Service (USFWS) Datasets

**Description:** Geospatial datasets administered by the U.S. Fish and Wildlife Service (USFWS), starting with ESA Critical Habitat. Note: USFWS National Wetlands Inventory (NWI) is published in a separate `public-wetlands` bucket alongside Ramsar and GLWD.

## wdpa

**Title:** Protected Planet — WDPA + WD-OECM

**Description:** UNEP-WCMC Protected Planet data products hosted on NRP S3.

## wetlands

**Title:** Global Wetlands Data (Ramsar, GLWD, NWI)

**Description:** Parent collection linking three major global wetland datasets, each a separate child collection: Ramsar Sites of International Importance (designated wetland polygons), the Global Lakes and Wetlands Database v2.0 (GLWD, Lehner et al. 2025), and the USFWS National Wetlands Inventory (NWI).

## wlfw

**Title:** Working Lands for Wildlife (WLFW)

**Description:** NRCS Working Lands for Wildlife datasets. Currently migratory big-game movement corridors and habitat (GeoParquet + PMTiles + H3 hex).

## working-lands

**Title:** Working & Agricultural Lands

**Description:** Working- and agricultural-lands datasets. Currently the California Farmland Mapping & Monitoring Program (FMMP) 2020 important-farmland classification.

## wyoming

**Title:** Wyoming Wildlife & Land Cover Datasets

**Description:** Cloud-native geospatial datasets for Wyoming including wildlife habitat ranges from the Wyoming Game & Fish Department (WGFD), BLM Surface Management Areas, land cover rasters (NLCD 2024, RAP rangeland cover, sagebrush design), and administrative boundaries. All vector datasets include GeoParquet, PMTiles, and H3 hex-indexed parquet.

