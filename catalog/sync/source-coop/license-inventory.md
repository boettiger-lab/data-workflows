# NRP catalog — license inventory & mirror verdict

Full recursive STAC walk (130 nodes). Verdict per collection:
**OK** mirror freely · **OK-NC** mirror with NC/SA label · **NO** redistribution prohibited (NRP-only) · **HOLD** confirm with upstream before mirroring · **N/A** meta/catalog node.


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

## public-high-seas
- **OK** · `CBD custom (other)` — public-high-seas/ebsa  · CBD EBSA: redistribute w/ attribution + note modifications
- **OK** · `CC-BY-4.0` — public-high-seas/ecs  
- **OK** · `public-domain` — public-high-seas/gebco-2025  · GEBCO grid placed in public domain
- **STALE** · `—` — public-high-seas/ghs-pop-2020  · dead STAC file
- **OK-NC** · `CC-BY-NC-SA-4.0` — public-high-seas/hydrothermal-vents  
- **OK** · `CC-BY-4.0` — public-high-seas/iho  
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

## public-padus
- **OK** · `public-domain` — public-padus/padus-4-1/combined  
- **OK** · `public-domain` — public-padus/padus-4-1/easement  
- **OK** · `public-domain` — public-padus/padus-4-1/fee  
- **OK** · `public-domain` — public-padus/padus-4-1/marine  
- **OK** · `public-domain` — public-padus/padus-4-1/proclamation  
- **OK** · `public-domain` — public-padus  

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