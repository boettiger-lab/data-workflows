# NRP catalog — license inventory & mirror verdict

Full recursive STAC walk (130 nodes). Verdict per collection:
**OK** mirror freely · **OK-NC** mirror with NC/SA label · **NO** redistribution prohibited (NRP-only) · **HOLD** confirm with upstream before mirroring · **N/A** meta/catalog node.


## public-blm
- **OK** · `public-domain` — public-blm/oil-gas-leases  · BLM National MLRS Oil & Gas Leases (ArcGIS FeatureServer, gis.blm.gov). US federal cadastral work → public domain (the ArcGIS Hub "custom" tag is generic). Mirror-eligible. Tracked: data-workflows #451.

## public-ca-dac
- **OK** · `CC-BY-4.0` — public-ca-dac  · CA DWR via CNRA open data + US Census ACS (confirm exact)

## public-ca-wolves
- **OK (license) / HELD (data semantics)** · `CC0-1.0` — public-ca-wolves  · license is fully clear (CC0); NOT mirrored to source.coop because it is a real-time updated product (`wolf_*_latest.geojson` + `snapshots/`) — a static mirror would be a stale copy presented as current. Revisit publishing only the dated `snapshots/`.

## public-ca30x30
- **OK** · `other (TNC/CDFW ds1197)` — public-ca30x30/freshwater-species-richness  · TNC California Freshwater Species Database (Aquarius) v2.0.7, distributed via CDFW BIOS ds1197. Use constraints (filelib.wildlife.ca.gov DS1197 metadata) explicitly permit redistribution provided the original source data + source citation are included; companion paper Howard et al. 2015 (PLOS ONE 10(7): e0130710) is CC-BY-4.0. Mirror with attribution (TNC data-product citation).
- **OK** · `other (free use w/ attribution)` — public-ca30x30/plant-richness  · Kling et al. (2018) Phil. Trans. R. Soc. B, [DOI 10.1098/rstb.2017.0397](https://doi.org/10.1098/rstb.2017.0397). Upstream terms: *"These data can be used freely, provided attribution is given to: Kling et al. (2018)…"* — **redistribution is permitted with attribution** (not a formal CC license, so STAC `license: other` + a `cite-as`/`sci:doi` citation, not an SPDX id). Mirror-eligible.
- **OK** · `other (free use w/ attribution)` — public-ca30x30/rarity-weighted-endemic-plant-richness  · same Kling et al. (2018) source/terms as above. Mirror-eligible.
- **N/A (partial)** — the rest of `public-ca30x30` is not yet catalogued (see `gen-source-sync.sh`); only the three collections above (freshwater-species-richness + the two plant-richness collections) are license-cleared. Do **not** add `ca30x30` to `REPOS` until the whole bucket is catalogued + cleared.

## public-calenviroscreen
- **OK** · `CA OEHHA (other)` — public-calenviroscreen  · CA public data; NOTE it is a DRAFT release

## public-carbon
- **OK-NC** · `CC-BY-NC-4.0` — public-carbon  

## public-cdfw
CDFW BIOS biogeographic data. **Verified**: the BIOS-published layers (ACE, SWAP 2015) each state CC-BY-4.0 verbatim in their ArcGIS item `licenseInfo` ("This work is licensed under Creative Commons Attribution 4.0 International License … Using the citation standards recommended for BIOS datasets satisfies the attribution requirements"), and data.ca.gov independently lists the SWAP-2015 layers as `cc-by`. Attribution via the BIOS citation standard (https://wildlife.ca.gov/Data/BIOS/Citing-BIOS).
- **OK** · `CC-BY-4.0` — public-cdfw/ace/terrestrial-biodiversity-summary  · ACE v3.0 ds2739; CC-BY-4.0 verified in item licenseInfo. Contact ACE@wildlife.ca.gov.
- **OK** · `CC-BY-4.0` — public-cdfw/swap-2015/provinces  · SWAP 2015 ds1900; CC-BY-4.0 verified (item + data.ca.gov).
- **OK** · `CC-BY-4.0` — public-cdfw/swap-2015/terrestrial-targets  · SWAP 2015 ds1966; CC-BY-4.0 verified.
- **OK** · `CC-BY-4.0` — public-cdfw/swap-2015/aquatic-targets  · SWAP 2015 ds2733; CC-BY-4.0 verified.
- **HOLD** · `CC-BY-4.0` (inferred, unconfirmed) — public-cdfw/swap-2025/* (all 10 collections: provinces, conservation-units, sgcn-ranges, marine-bioregions, noaa-esu-dps, bay-delta-conservation-unit, targets, strategies, sgcn-species, sgcn-species-units)  · The SWAP 2025 source items (ArcGIS AGOL owner `cdfwswap`, services `SWAP_target_strategy_v3_gdb` / `SWAP_SGCN_V4_gdb` / `SWAP_Reference_Layers_WFL1`) carry **empty** `licenseInfo`/credits and are **not yet in the formal BIOS / data.ca.gov catalog**, so the CC-BY-4.0 in our STAC is an inference from every peer CDFW/BIOS dataset (ACE, SWAP 2015, CNRA 30×30) + the CA open-data default — **not** an explicit CDFW statement. **Do NOT mirror to source.coop until CDFW confirms.** Confirm with the SWAP Team (SWAP@wildlife.ca.gov) or Biogeographic Data Branch (BDB@wildlife.ca.gov / (916) 322-2493). Tracked: data-workflows #381.
- **N/A (partial)** — `public-cdfw` is mixed-clearance: ACE + swap-2015 are mirror-eligible, swap-2025 is HOLD. Do **not** add `cdfw` to `REPOS` (gen-source-sync.sh) until the swap-2025 license is confirmed and the whole bucket is clear.

## public-census
- **OK** · `public-domain` — public-census/census-2024/cd  
- **OK** · `public-domain` — public-census/census-2024/county  
- **OK** · `public-domain` — public-census/census-2024/state  
- **OK** · `public-domain` — public-census/census-2024/tract  
- **OK** · `public-domain` — public-census/census-2025/sldl  
- **OK** · `public-domain` — public-census/census-2025/sldu  
- **OK** · `public-domain` — public-census  

## public-cgs
- **OK** · `public-domain` — public-cgs/sierra-nevada-atlas/map-unit-polys  
- **OK** · `public-domain` — public-cgs/sierra-nevada-atlas  
- **OK** · `public-domain` — public-cgs  

## public-cpad
- **OK** · `CC-BY-4.0` — public-cpad/cced-stac-collection  · GreenInfo CPAD/CCED via CNRA open data = CC-BY
- **OK** · `CC-BY-4.0` — public-cpad/cpad-holdings-stac-collection  · GreenInfo CPAD/CCED via CNRA open data = CC-BY
- **OK** · `CC-BY-4.0` — public-cpad/cpad-units-stac-collection  · GreenInfo CPAD/CCED via CNRA open data = CC-BY
- **OK** · `CC-BY-4.0` — public-cpad  · GreenInfo CPAD/CCED via CNRA open data = CC-BY

## public-ecoregion
- **OK** · `CC-BY-4.0` — public-ecoregion  

## public-epa-water
- **OK** · `public-domain` — public-epa-water/epa-sab-v3/cws  
- **OK** · `public-domain` — public-epa-water  

## public-fire
- **OK** · `CA public (other)` — public-fire/calfire-2024/firep  · CAL FIRE FRAP public record; attribution+disclaimer
- **OK** · `CA public (other)` — public-fire/calfire-2024/rxburn  · CAL FIRE FRAP public record; attribution+disclaimer
- **HOLD** · `proprietary` — public-fire  · unmapped/proprietary — confirm
- **OK** · `public-domain` — public-fire/usgs-fires-2021/combined  

## public-gbif
- **OK-NC** · `CC-BY-NC (mixed)` — public-gbif  · GBIF aggregate; per-record CC0/BY/BY-NC -> NC conservative

## public-gfw
- **OK-NC** · `CC-BY-NC-4.0` — public-gfw  

## public-globio
- **OK** · `CC-BY-4.0` — public-globio (all 12 collections: `globio-msa-{2015,ssp1rcp26-2050,ssp3rcp60-2050,ssp5rcp85-2050}-{overall,plants,wbvert}`)  · GLOBIO 4 terrestrial Mean Species Abundance, PBL Netherlands Environmental Assessment Agency (Schipper et al. 2020, GCB, [DOI 10.1111/gcb.14848](https://doi.org/10.1111/gcb.14848)). PBL states all GLOBIO4 spatial layers are CC-BY 4.0. Mirror freely with attribution (PBL / Schipper et al. 2020). data-workflows #463.

## public-high-seas
- **OK** · `CBD custom (other)` — public-high-seas/ebsa  · CBD EBSA: redistribute w/ attribution + note modifications
- **OK** · `CC-BY-4.0` — public-high-seas/ecs  
- **OK** · `public-domain` — public-high-seas/gebco-2025  · GEBCO grid placed in public domain
- **STALE** · `—` — public-high-seas/ghs-pop-2020  · dead STAC file
- **OK-NC** · `CC-BY-NC-SA-4.0` — public-high-seas/hydrothermal-vents  
- **OK** · `CC-BY-4.0` — public-high-seas/iho  
- **NO** · `proprietary (IUCN-MMPATF ToS)` — public-high-seas/imma  · Important Marine Mammal Areas (IUCN-MMPATF). Non-commercial User Licence Agreement; no third-party sharing, no republishing in original format, derived products carry same terms (https://www.marinemammalhabitat.org/immas/imma-spatial-layer-download/). NRP + MinIO backup only; EXCLUDED from source.coop (EXCLUDES: imma/**, imma.parquet, imma.pmtiles). WDPA/IUCN class. data-workflows #65.
- **OK** · `CC-BY-4.0` — public-high-seas/longhurst  
- **OK** · `CC0-1.0` — public-high-seas/megamove/corridors  
- **OK** · `CC0-1.0` — public-high-seas/megamove/immegas  
- **OK** · `CC0-1.0` — public-high-seas/megamove/residencies  
- **OK** · `CC0-1.0` — public-high-seas/megamove  
- **OK** · `CC0-1.0` — public-high-seas/megamove/tracked-individuals  
- **OK-NC** · `CC-BY-NC-3.0` — public-high-seas/meow  · WWF MEOW = CC-BY-NC 3.0 (verified)
- **HOLD** · `unknown source` — public-high-seas/mpa-candidates  · identify source of candidate-MPA polygons before mirroring
- **OK-NC** · `CC-BY-SA-3.0-IGO` — public-high-seas/rfmo  
- **OK** · `CC-BY-4.0` — public-high-seas/seafloor-geomorphology  
- **N/A** · `various` — public-high-seas  · meta/aggregate (children carry licenses)

## public-hydrobasins
- **NO** · `HydroSHEDS v1 custom` — public-hydrobasins  · no stand-alone redistribution (tech-doc Appendix A; v1c not CC-BY)

## public-icca
- **NO** · `UNEP-WCMC custom` — public-icca/icca-registry/icca-point  · Protected Planet terms (verified)
- **NO** · `UNEP-WCMC custom` — public-icca/icca-registry/icca-polygon  · Protected Planet terms (verified)
- **NO** · `UNEP-WCMC custom` — public-icca  · Protected Planet terms (verified)

## public-inat
- **N/A** · `various` — public-inat  · meta/aggregate (children carry licenses)

## public-indigenous
- **OK** · `CC-BY-4.0` — public-indigenous/landmark/indicative-poly-stac  
- **OK** · `CC-BY-4.0` — public-indigenous/landmark/indicative-pt-stac  
- **OK** · `CC-BY-4.0` — public-indigenous/landmark/iplc-poly-stac  
- **OK** · `CC-BY-4.0` — public-indigenous/landmark/iplc-pt-stac  
- **OK** · `CC-BY-4.0` — public-indigenous  

## public-iucn
- **NO** · `IUCN Red List ToU` — public-iucn/iucn-ranges-2025  · IUCN: no redistribution, incl. derivatives (verified)
- **NO** · `IUCN Red List ToU` — public-iucn  · IUCN: no redistribution, incl. derivatives (verified)
- **NO** · `IUCN Red List ToU` — public-iucn/taxonomy  · IUCN: no redistribution, incl. derivatives (verified)

## public-kba
- **NO** · `proprietary (KBA Partnership ToS)` — public-kba  · World Database of Key Biodiversity Areas (BirdLife/KBA Partnership). Non-commercial GIS request; ToS prohibits "all forms of reposting… redistribution or communication to the public" (https://www.keybiodiversityareas.org/termsofservice). NRP + MinIO backup only; NOT on source.coop. WDPA/IUCN class. data-workflows #432.
- **NO** · `proprietary (KBA Partnership ToS)` — public-kba/kba-2026-03/sites  · same ToS; includes the trigger-species sidecar (derivative of KBA + IUCN Red List data — also non-redistributable).

## public-land-cover
- **OK** · `CC-BY-4.0` — public-land-cover/cgls-lc100-2019  
- **OK** · `public-domain` — public-land-cover/nlcd-2024  · NLCD MRLC/USGS = US federal PD

## public-mappinginequality
- **OK-NC** · `CC-BY-NC-SA-4.0` — public-mappinginequality  

## public-mobi
- **OK-NC** · `CC-BY-NC-4.0` — public-mobi/mobi-species-richness-all  

## public-ncp
- **OK** · `CC-BY-4.0` — public-ncp  

## public-overturemaps
- **OK** · `CDLA-Permissive-2.0` — public-overturemaps/2026-02-18.0/counties  
- **OK** · `CDLA-Permissive-2.0` — public-overturemaps/2026-02-18.0/countries  
- **OK** · `CDLA-Permissive-2.0` — public-overturemaps/2026-02-18.0/regions  
- **OK** · `CDLA-Permissive-2.0` — public-overturemaps  

## public-missouri
- **HOLD** · `other` (license pending) — public-missouri/ccs-2022/* (7 Conservation Opportunity Area layers)  · Missouri Dept of Conservation CCS 2022 (MDC ArcGIS Server). MDC states no explicit data license; STAC `license: other` + link to MDC terms, pending confirmation. Do NOT mirror to source.coop until confirmed. data-workflows #384.

## public-nevada
- **HOLD** · `other` (license pending) — public-nevada/swap-2022/* (species-distributions, key-habitats)  · Nevada Dept of Wildlife SWAP 2022 (NDOW ArcGIS). NDOW states no data license on the SWAP page; STAC `license: other` + link, pending confirmation (ndowinfo@ndow.org). Do NOT mirror to source.coop until confirmed. data-workflows #383.

## public-padus
- **OK** · `public-domain` — public-padus/padus-4-1/combined  
- **OK** · `public-domain` — public-padus/padus-4-1/easement  
- **OK** · `public-domain` — public-padus/padus-4-1/fee  
- **OK** · `public-domain` — public-padus/padus-4-1/marine  
- **OK** · `public-domain` — public-padus/padus-4-1/proclamation  
- **OK** · `public-domain` — public-padus  

## public-parks
California Park Access Tool 2020 (SCORP 2020) — Parks for All Californians, GreenInfo Network for CA State Parks OGALS. Derived from CPAD 2019b (parks, published **CC-BY** by GreenInfo on data.cnra.ca.gov) + ACS 2014-18 / Census 2010 (US-federal public domain). Verified via the bundle's SCORP 2020 Download Metadata + CPAD's data.cnra.ca.gov license field. Attribute GreenInfo Network + CA State Parks OGALS. data-workflows #460.
- **OK** · `CC-BY-4.0` — public-parks/park-access-2020/tract-acres-per-thousand
- **OK** · `CC-BY-4.0` — public-parks/park-access-2020/no-park-access
- **OK** · `CC-BY-4.0` — public-parks/park-access-2020/half-mile-access
- **N/A** · `CC-BY-4.0` — public-parks  · bucket collection (children all CC-BY)

## public-population
- **OK** · `CC-BY-4.0` — public-population/ghs-pop-2020  
- **N/A** · `various` — public-population  · meta/aggregate (children carry licenses)

## public-rap
- **OK** · `public-domain` — public-rap/rap-arte  · USDA/NTSG RAP = US public domain (data.gov)
- **OK** · `public-domain` — public-rap/rap-iag  · USDA/NTSG RAP = US public domain (data.gov)
- **OK** · `public-domain` — public-rap/rap-pfg-cover  · USDA/NTSG RAP = US public domain (data.gov)
- **OK** · `public-domain` — public-rap  · USDA/NTSG RAP = US public domain (data.gov)

## public-rivers
- **HOLD** · `American Rivers (unclear)` — public-rivers/american-rivers/campaigns  · org-produced layer; no clear redistribution license
- **OK** · `CC-BY-4.0` — public-rivers/american-rivers/dam-removal  
- **HOLD** · `American Rivers (unclear)` — public-rivers/american-rivers/ira-watersheds  · org-produced layer; no clear redistribution license
- **OK** · `public-domain` — public-rivers/american-rivers/nri-2016  
- **OK** · `public-domain` — public-rivers/american-rivers/nri-2024  
- **HOLD** · `American Rivers (unclear)` — public-rivers/american-rivers/roo-cjest  · org-produced layer; no clear redistribution license
- **N/A** · `various` — public-rivers/american-rivers  · meta/aggregate (children carry licenses)
- **OK** · `public-domain` — public-rivers/american-rivers/wild-scenic-designated  
- **OK** · `public-domain` — public-rivers/american-rivers/wild-scenic-eligible  

## public-social-vulnerability
- **OK** · `public-domain` — public-social-vulnerability/2000  
- **OK** · `public-domain` — public-social-vulnerability/2010  
- **OK** · `public-domain` — public-social-vulnerability/2020  
- **OK** · `public-domain` — public-social-vulnerability/2022  
- **OK** · `public-domain` — public-social-vulnerability  

## public-tpl
- **HOLD** · `TPL (no public terms)` — public-tpl/conservation-almanac-2024-funding  · no data license found; TPL requires contact for spatial data
- **HOLD** · `TPL (no public terms)` — public-tpl/conservation-almanac-2024-sites  · no data license found; TPL requires contact for spatial data
- **HOLD** · `TPL (no public terms)` — public-tpl/landvote  · no data license found; TPL requires contact for spatial data
- **NO** · `proprietary` — public-tpl/parkserve-2025/parks  · TPL ParkServe. Hosted **with TPL permission (host, NOT redistribute)**; service areas derive from proprietary Esri StreetMap Premium + Business Analyst. NRP + MinIO backup only; **excluded from source.coop** (public-tpl not in REPOS). data-workflows #461.
- **NO** · `proprietary` — public-tpl/parkserve-2025/service-areas  · same as parkserve-2025/parks — host-only, no redistribution, no source.coop mirror.
- **NO** · `proprietary` — public-tpl/parkserve-2025/places  · ParkServe phase 2 (city boundaries + ParkScore). Host-only, no mirror. #461.
- **NO** · `proprietary` — public-tpl/parkserve-2025/urban-areas  · ParkServe phase 2 (urban-area boundaries). Host-only, no mirror.
- **NO** · `proprietary` — public-tpl/parkserve-2025/priority-areas-place  · ParkServe phase 2 (priority areas for new parks, by place). Host-only, no mirror.
- **NO** · `proprietary` — public-tpl/parkserve-2025/priority-areas-urban-area  · ParkServe phase 2 (priority areas for new parks, by urban area). Host-only, no mirror.
- **NO** · `proprietary` — public-tpl/parkserve-2025/parkscore  · ParkServe phase 2 (ParkScore / City Park Facts 2026 scores, 99 cities). Host-only, no mirror.
- **HOLD** · `TPL (no public terms)` — public-tpl  · no data license found; TPL requires contact for spatial data
- **OK (license) / RELOCATING** · `CC-BY-4.0` — public-tpl/wcb-approved-projects  · CDFW BIOS ds672 (CA Wildlife Conservation Board) — a CDFW **state-agency** product misfiled under "tpl". Moving to the planned `public-cdfw` bucket (geo-agent-ops #19; data-workflows #228); mirror as `cboettig/cdfw` afterward. `cboettig/tpl` was NOT created (rest of public-tpl is HOLD).

## public-trails
- **HOLD** · `various (U.S. federal works — see assets)` — public-trails/federal-trails-2026  · unmapped/proprietary — confirm
- **HOLD** · `various (U.S. federal works — see per-collection assets)` — public-trails  · unmapped/proprietary — confirm

## public-usfws
- **OK** · `public-domain` — public-usfws/critical-habitat/final  
- **OK** · `public-domain` — public-usfws/critical-habitat/proposed  
- **OK** · `public-domain` — public-usfws/critical-habitat  
- **OK** · `public-domain` — public-usfws  

## public-wdpa
- **NO** · `UNEP-WCMC custom` — public-wdpa  · Protected Planet: no redistribution incl. derivatives (verified)
- **NO** · `UNEP-WCMC custom` — public-wdpa/wdoecm-may-2026  · Protected Planet: no redistribution incl. derivatives (verified)
- **NO** · `UNEP-WCMC custom` — public-wdpa/wdpa  · Protected Planet: no redistribution incl. derivatives (verified)

## public-wetlands
- **OK** · `CC-BY-4.0` — public-wetlands/glwd  · GLWD v2 (Lehner 2025) = CC-BY 4.0 (verified)
- **OK** · `public-domain` — public-wetlands/nwi  · USFWS NWI = US federal PD
- **OK** · `public-domain` — public-wetlands/ramsar  · Ramsar Secretariat treats site data as public domain
- **N/A** · `various` — public-wetlands  · meta/aggregate (children carry licenses)

## public-wyoming
- **OK** · `public-domain` — public-wyoming/blm-sma  
- **OK** · `public-domain` — public-wyoming/nlcd-2024  
- **OK** · `public-domain` — public-wyoming/pad-us  
- **OK** · `WGFD open-data (other)` — public-wyoming/priority-areas-gye  · WGFD public ArcGIS Open Data; attribution+disclaimer (confirm)
- **OK** · `public-domain` — public-wyoming/rap-arte  
- **OK** · `public-domain` — public-wyoming/rap-iag  
- **OK** · `public-domain` — public-wyoming/rap-pfg-biomass  
- **OK** · `WGFD open-data (other)` — public-wyoming/sage-grouse-priority  · WGFD public ArcGIS Open Data; attribution+disclaimer (confirm)
- **OK** · `public-domain` — public-wyoming/sagebrush-design  
- **HOLD** · `proprietary` — public-wyoming  · unmapped/proprietary — confirm
- **OK** · `public-domain` — public-wyoming/ungulate-migration  
- **OK** · `WGFD open-data (other)` — public-wyoming/wgfd-elk-crucial  · WGFD public ArcGIS Open Data; attribution+disclaimer (confirm)
- **OK** · `WGFD open-data (other)` — public-wyoming/wgfd-elk-seasonal  · WGFD public ArcGIS Open Data; attribution+disclaimer (confirm)
- **OK** · `WGFD open-data (other)` — public-wyoming/wgfd-mule-deer-crucial  · WGFD public ArcGIS Open Data; attribution+disclaimer (confirm)
- **OK** · `WGFD open-data (other)` — public-wyoming/wgfd-mule-deer-seasonal  · WGFD public ArcGIS Open Data; attribution+disclaimer (confirm)
- **OK** · `WGFD open-data (other)` — public-wyoming/wgfd-pronghorn-crucial  · WGFD public ArcGIS Open Data; attribution+disclaimer (confirm)
- **OK** · `WGFD open-data (other)` — public-wyoming/wgfd-pronghorn-seasonal  · WGFD public ArcGIS Open Data; attribution+disclaimer (confirm)
- **OK** · `public-domain` — public-wyoming/wy-counties  
- **OK** · `public-domain` — public-wyoming/wyoming-places

## Additions 2026-07 (batch: usgs-nhd, usgs-wbd, facts, nci-frontiers, connectivity, hazard)

## public-usgs-nhd
- **OK** · `public-domain` — public-usgs-nhd/streams-by-order  · USGS National Hydrography Dataset; US federal work (PD).
- **OK** · `public-domain` — public-usgs-nhd/perennial-streams  · USGS NHD; US federal work (PD).

## public-usgs-wbd
- **OK** · `public-domain` — public-usgs-wbd/wbd/hu2 · hu4 · hu6 · hu8 · hu10 · hu12  · USGS Watershed Boundary Dataset (all HU levels); US federal work (PD).

## public-facts
- **OK** · `public-domain` — public-facts/common-attributes-2026-06  · USFS FACTS Common Attributes; US federal work (PD).

## public-nci-frontiers
- **OK** · `CC0-1.0` — public-nci-frontiers  · Polasky et al. (2026, Science) / Natural Capital Project; CC0 (STAC declares CC0 + CC0 link; confirm against the paper's data deposit on first mirror).

## public-connectivity
- **OK** · `CC-BY-4.0` — public-connectivity/regional-connectivity-linkages  · South Coast Missing Linkages (Beier et al. 2006) via CDFW BIOS ds419; CC-BY.
- **OK** · `CC0-1.0` — public-connectivity/climate-migration-routes  · Schloss et al. 2022; CC0.
- **OK** · `CC0-1.0` — public-connectivity/present-day-connectivity/flow  · Cameron/Schloss/Theobald/Morrison 2022; CC0.
- **OK** · `CC0-1.0` — public-connectivity/present-day-connectivity/categories  · same; CC0.
- **OK** · `CC-BY-4.0` — public-connectivity/wildlife-movement-barriers  · CDFW BIOS ds2867; CC-BY.

## public-hazard
- **OK** · `public-domain` — public-hazard/flood-hazard  · FEMA National Flood Hazard Layer; US federal work (PD).
- **OK** · `public-domain` — public-hazard/sea-level-rise  · NOAA Office for Coastal Management; US federal work (PD).
- **HOLD** · `other` — public-hazard/mid-century-habitat-climate-exposure  · Thorne et al. (2016), CDFW-commissioned (SWAP 2015). NOT a Dryad/Zenodo deposit; STAC states redistribution terms "are not explicitly published with the source and require confirmation." BIOS-general is CC-BY and this is not a CNDDB/spotted-owl carve-out, so likely includable — but source ships no explicit license, so do NOT assert one. **Excluded from the `hazard` mirror** until CDFW/Thorne terms are confirmed.  