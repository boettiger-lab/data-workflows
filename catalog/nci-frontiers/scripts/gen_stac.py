#!/usr/bin/env python3
"""Generate the public-nci-frontiers STAC collection (CC0 Polasky et al. 2026 input layers).
One hex asset per ingested layer. Writes /tmp/nci-frontiers-stac.json."""
import json
BASE="https://s3-west.nrp-nautilus.io/public-nci-frontiers"
ROOT="https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
SRC="Polasky et al. 2026, Science 392:1069 (doi:10.1126/science.aea9058); input data Dryad doi:10.5061/dryad.qjq2bvqw5 (CC0)."

def hcols(res):
    if res==5: cols=[("h5","uint64",5,"native"),("h4","uint64",4,"parent"),("h3","uint64",3,"parent")]
    else:      cols=[("h8","uint64",8,"native"),("h7","uint64",7,"parent"),("h6","uint64",6,"parent"),("h5","uint64",5,"parent")]
    out=[{"name":n,"type":t,"description":f"H3 cell ID at resolution {r} ({k} resolution)."} for n,t,r,k in cols]
    out.append({"name":"h0","type":"int64","description":"H3 cell ID at resolution 0; hive partition key."})
    return out

def dens(col,label,nodata):
    return {"name":col,"type":"double",
      "description":f"Area-weighted MEAN {label} density in USD/ha (reducer=mean). **Intensity — aggregate across cells with AVG/MIN/MAX, never SUM.** Negative values are genuine net losses (costs>revenue). nodata {nodata} excluded. "+SRC}

def asset(key,title,res,valcol,coldesc):
    native=res; parents=[4,3,0] if res==5 else [7,6,5,0]
    return key,{"href":f"{BASE}/{key[:-4]}/hex/h0=*/data_0.parquet","type":"application/x-parquet","title":title,
      "roles":["data"],"h3:native_resolution":native,"h3:parent_resolutions":parents,
      "table:columns":[coldesc]+hcols(res)}

assets={}
# Wave 1 — economic revenue densities (res 5)
for key,title,col,lab,nd in [
  ("crop-current-hex","Current crop revenue (no palm)","crop_current_usd_ha","current crop net production value",0),
  ("crop-irrigated-hex","Potential irrigated crop revenue","crop_irrig_usd_ha","potential irrigated intensified crop net value",0),
  ("crop-rainfed-hex","Potential rainfed crop revenue","crop_rainfed_usd_ha","potential rainfed intensified crop net value",0),
  ("palm-current-hex","Current oil-palm revenue","palm_current_usd_ha","current oil-palm net production value",0),
  ("grazing-return-hex","Potential grazing revenue","grazing_usd_ha","potential livestock grazing net value at global meat prices",-9999)]:
    k,a=asset(key,title,5,col,dens(col,lab,nd)); assets[k]=a
# grazing methane (res 5)
k,a=asset("grazing-methane-hex","Potential grazing methane",5,"methane_kg_ha_yr",
  {"name":"methane_kg_ha_yr","type":"double","description":"Area-weighted MEAN potential livestock methane, kg CO2e-precursor per ha per year (reducer=mean). **Intensity — AVG not SUM.** ×0.001×20 → 20-yr CO2e stock. nodata 0 excluded. "+SRC}); assets[k]=a
# Wave 2 — forestry + FLII (res 8)
k,a=asset("forestry-return-hex","Potential forestry revenue",8,"forestry_usd_ha",dens("forestry_usd_ha","potential forestry net return",-99999)); assets[k]=a
k,a=asset("flii-hex","Forest Landscape Integrity Index",8,"flii",
  {"name":"flii","type":"double","description":"Area-weighted MEAN Forest Landscape Integrity Index, 0–10000 (÷10000 → 0–1; higher = more intact forest). reducer=mean. **Intensity — AVG not SUM.** Source: Grantham et al. 2020 (doi:10.1038/s41467-020-19493-3), provided CC0 via "+SRC}); assets[k]=a
# Wave 3 — transition costs (res 8, USD/cell totals, SUM-able)
for key,title,col,scn in [
  ("tran-cost-restoration-hex","Transition cost: restoration","tcost_restoration_usd","restoration to natural habitat"),
  ("tran-cost-sustainable-current-hex","Transition cost: sustainable current","tcost_sustainable_current_usd","sustainable current land use"),
  ("tran-cost-extensification-intensified-irrigated-hex","Transition cost: extensification+intensified irrigated","tcost_ext_intens_irrig_usd","cropland expansion + intensified irrigated"),
  ("tran-cost-extensification-intensified-rainfed-hex","Transition cost: extensification+intensified rainfed","tcost_ext_intens_rainfed_usd","cropland expansion + intensified rainfed"),
  ("tran-cost-grazing-expansion-hex","Transition cost: grazing expansion","tcost_grazing_expansion_usd","grazing expansion")]:
    k,a=asset(key,title,8,col,
      {"name":col,"type":"double","description":f"Total one-time land-use transition cost in USD per H3 cell for the **{scn}** alternative (reducer=sum of per-pixel USD). Safe to SUM across cells at the SAME resolution; do not sum across resolutions. "+SRC}); assets[k]=a

coll={"stac_version":"1.0.0",
 "stac_extensions":["https://stac-extensions.github.io/table/v1.2.0/schema.json"],
 "type":"Collection","id":"nci-frontiers",
 "title":"Sustainable Landscape Efficiency Frontiers — Input Layers (Polasky et al. 2026)",
 "description":("H3-hexed input layers for the sustainable landscape efficiency frontier analysis of Polasky et al. "
   "(2026, Science). Economic production-value layers (crop, oil palm, grazing revenue; grazing methane) are native "
   "**H3 resolution 5** (from 5-arcmin ~9 km source); forestry, Forest Landscape Integrity, and land-use transition "
   "costs are native **resolution 8** (from 300 m source); all carry an h5 parent column for a common res-5 decision "
   "unit (~8000 ha, the paper's parcel). Revenue/methane/FLII are per-ha/index DENSITIES (mean reducer — aggregate "
   "with AVG, never SUM); transition costs are per-cell USD TOTALS (sum reducer). Sourced from the CC0 Dryad deposit "
   "(doi:10.5061/dryad.qjq2bvqw5); see also iucn-richness-2025, wwf-ecoregions-2017, irrecoverable-carbon for the "
   "biodiversity and carbon objectives, and wdpa for the IUCN I–IV constraint."),
 "license":"CC0-1.0",
 "keywords":["land use","biodiversity","carbon","agriculture","ecosystem services","H3","Polasky","efficiency frontier"],
 "extent":{"spatial":{"bbox":[[-180,-90,180,90]]},"temporal":{"interval":[["2010-01-01T00:00:00Z","2022-12-31T00:00:00Z"]]}},
 "providers":[{"name":"Polasky et al. / Natural Capital Project","roles":["producer","licensor"],"url":"https://doi.org/10.5061/dryad.qjq2bvqw5"},
              {"name":"Boettiger Lab (cng-datasets H3 processing)","roles":["processor"],"url":"https://s3-west.nrp-nautilus.io/public-nci-frontiers/"}],
 "links":[
   {"rel":"self","href":f"{BASE}/stac-collection.json","type":"application/json"},
   {"rel":"root","href":ROOT,"type":"application/json"},
   {"rel":"parent","href":ROOT,"type":"application/json"},
   {"rel":"license","href":"https://creativecommons.org/publicdomain/zero/1.0/","type":"text/html"}],
 "assets":assets}
# READY_LAYERS (comma-sep dataset names) → publish only assets whose data is live (interim STAC).
import os
_ready=os.environ.get("READY_LAYERS","").strip()
if _ready:
    keep=set(_ready.split(","))
    coll["assets"]={k:v for k,v in assets.items() if k[:-4] in keep}  # asset key = "<dataset>-hex"
    coll["description"]+=f"  [Interim publish: {len(coll['assets'])} of {len(assets)} layers live; remainder land as the hex campaign completes.]"
json.dump(coll,open("/tmp/nci-frontiers-stac.json","w"),indent=2)
print("wrote /tmp/nci-frontiers-stac.json with",len(coll["assets"]),"assets")
