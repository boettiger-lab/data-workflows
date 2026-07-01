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

# ESA CCI land cover (current land-use mask for the economic overlay) — categorical, res 8
_ESA={10:"Cropland rainfed",11:"Cropland rainfed herbaceous",12:"Cropland rainfed tree/shrub",20:"Cropland irrigated",30:"Mosaic cropland>50%/natural",40:"Mosaic natural>50%/cropland",50:"Tree broadleaved evergreen",60:"Tree broadleaved deciduous",61:"Tree broadleaved deciduous closed",62:"Tree broadleaved deciduous open",70:"Tree needleleaved evergreen",71:"Tree needleleaved evergreen closed",72:"Tree needleleaved evergreen open",80:"Tree needleleaved deciduous",81:"Tree needleleaved deciduous closed",82:"Tree needleleaved deciduous open",90:"Tree mixed",100:"Mosaic tree-shrub>50%/herbaceous",110:"Mosaic herbaceous>50%/tree-shrub",120:"Shrubland",121:"Shrubland evergreen",122:"Shrubland deciduous",130:"Grassland",140:"Lichens/mosses",150:"Sparse vegetation",151:"Sparse tree",152:"Sparse shrub",153:"Sparse herbaceous",160:"Tree flooded fresh/brackish",170:"Tree flooded saline",180:"Shrub/herbaceous flooded",190:"Urban",200:"Bare areas",201:"Bare consolidated",202:"Bare unconsolidated",210:"Water",220:"Permanent snow/ice"}
_esa_codes=[10,11,12,20,30,40,50,60,61,62,70,71,72,80,81,82,90,100,110,120,121,122,130,140,150,151,152,153,160,170,180,190,200,201,202,210,220]
k,a=asset("esa-lc-2025-hex","ESA CCI Land Cover 2025 (current land-use mask)",8,"esa_lc",
  {"name":"esa_lc","type":"int64",
   "description":("ESA CCI land-cover class, dominant (mode) per cell. **Current land-use mask for the economic overlay:** "
     "cropland 10–40 → crop value; grass/shrub/sparse 110–153,180 → grazing; forest 50–100,160,170 → forestry; "
     "190 urban / 200–202 bare / 210 water / 220 ice → no production. Codes: "+", ".join(f"{c}={_ESA[c]}" for c in _esa_codes)+". "+SRC),
   "values":_esa_codes}); assets[k]=a

# Wave 4 — allowed-alternative constraint masks (binary 0/1) + carbon zones (res 8, mode reducer)
# Masks gate which land-use alternatives are admissible per parcel in the Polasky et al. frontier.
for key,title,col,nd,m0,m1 in [
  ("mask-irrigation-hex","Mask: irrigated cropland suitability","irrigation_suit",7,
     "not suitable for irrigated cropland","suitable for irrigated cropland"),
  ("mask-rainfed-hex","Mask: rainfed cropland suitability","rainfed_suit",7,
     "not suitable for rainfed cropland","suitable for rainfed cropland"),
  ("mask-sustainable-irrig-hex","Mask: sustainable irrigation potential","sustain_irrig",7,
     "no sustainable irrigation potential","has sustainable irrigation potential"),
  ("mask-expansion-suit-hex","Mask: agricultural expansion suitability","expansion_suit",7,
     "not suitable for natural-to-agriculture expansion","suitable for natural-to-agriculture expansion"),
  ("mask-slope-expansion-hex","Mask: slope allows agricultural expansion","slope_exp_ok",255,
     "excluded by slope (too steep for expansion)","slope permits agricultural expansion"),
  ("mask-slope-intensif-hex","Mask: slope allows agricultural intensification","slope_int_ok",255,
     "excluded by slope (too steep for intensification)","slope permits agricultural intensification")]:
    k,a=asset(key,title,8,col,
      {"name":col,"type":"int64",
       "description":(f"Binary scenario-construction constraint mask, dominant value per H3 cell (reducer=mode). "
         f"Values: 0={m0}, 1={m1}. nodata {nd} (no data / not applicable) excluded before aggregation. "
         "Restricts which land-use alternatives are admissible per parcel in the Polasky et al. frontier. "+SRC),
       "values":[0,1]}); assets[k]=a
# carbon zones (new_ecoregions.tif) — ecoregion-based zone ID; the Spawn et al. carbon_table join key (res 8, mode)
k,a=asset("carbon-zones-hex","Carbon zones (new_ecoregions)",8,"carbon_zone",
  {"name":"carbon_zone","type":"int64",
   "description":("Integer carbon-zone ID, dominant zone per H3 cell (reducer=mode; 830 distinct zones, range 1–846). "
     "A high-cardinality identifier that joins to the Spawn et al. carbon_table lookup (per-zone x land-use "
     "above/below-ground carbon density), used to derive graded per-land-use carbon for each frontier alternative — "
     "not an enumerable thematic vocabulary, so no `values` array is listed. nodata 0 (no zone / ocean) excluded "
     "before aggregation. "+SRC)}); assets[k]=a

# Reference lookup table (non-hex, non-geometry) — atomic, joinable in any context.
# carbon_table reshaped long: one row per (carbon_zone, land-use class), value = carbon density.
assets["carbon-by-zone-lulc-parquet"]={
  "href":f"{BASE}/lookups/carbon-by-zone-lulc.parquet","type":"application/x-parquet",
  "title":"Carbon density by carbon-zone × land-use class (Spawn/Polasky lookup)","roles":["data"],
  "table:columns":[
    {"name":"carbon_zone","type":"int64",
     "description":"Carbon-zone ID (1–846; 830 zones). Joins to the carbon-zones-hex `carbon_zone` column (verified 1:1 key match). "+SRC},
    {"name":"lulc_code","type":"int64",
     "description":("Land-use / land-cover class code — ESA CCI classes plus Polasky et al. custom "
       "intensification / oil-palm / plantation / grazing / forestry codes. Identifier that joins to the "
       "ESA/PREDICTS land-use classes; full code→name definitions ship in the deposit `predicts` crosswalk "
       "(published with the biodiversity layers). "+SRC)},
    {"name":"carbon_mg_ha","type":"double",
     "description":("Carbon density in metric tons of carbon per hectare (t C ha⁻¹ = Mg C ha⁻¹) for this "
       "land-use class within this carbon zone (Spawn et al. via Polasky et al.). **Density, not a total — do NOT "
       "SUM densities.** For a carbon stock multiply by ground area (paper: ×100 ha/km² × pixel_area_km²; on hex: "
       "× the H3 cell area). Zero where there is no land use. "+SRC)}]}

# COG assets (visualization) for any economic layer that has a published <dataset>-cog.tif (COG_LAYERS env)
import os as _os
_COGMETA={
 'crop-current':('crop_current_usd_ha','float32',0,'Current crop revenue (visualization COG)'),
 'crop-irrigated':('crop_irrig_usd_ha','float32',0,'Potential irrigated crop revenue (visualization COG)'),
 'crop-rainfed':('crop_rainfed_usd_ha','float32',0,'Potential rainfed crop revenue (visualization COG)'),
 'palm-current':('palm_current_usd_ha','float32',0,'Current oil-palm revenue (visualization COG)'),
 'grazing-return':('grazing_usd_ha','float64',-9999,'Potential grazing revenue (visualization COG)'),
 'forestry-return':('forestry_usd_ha','float32',-99999,'Potential forestry revenue (visualization COG)')}
for _ds in [x for x in _os.environ.get("COG_LAYERS","").split(",") if x]:
    _col,_dt,_nd,_title=_COGMETA[_ds]
    assets[f"{_ds}-cog"]={"href":f"{BASE}/{_ds}/{_ds}-cog.tif",
      "type":"image/tiff; application=geotiff; profile=cloud-optimized","title":_title,"roles":["data","visual"],
      "raster:bands":[{"name":_col,"data_type":_dt,"nodata":_nd,"unit":"USD/ha","description":"Net production value density (USD/ha); negative = net loss. "+SRC}]}

coll={"stac_version":"1.0.0",
 "stac_extensions":["https://stac-extensions.github.io/table/v1.2.0/schema.json",
   "https://stac-extensions.github.io/raster/v1.1.0/schema.json"],
 "type":"Collection","id":"nci-frontiers",
 "title":"Sustainable Landscape Efficiency Frontiers — Input Layers (Polasky et al. 2026)",
 "description":("H3-hexed input layers for the sustainable landscape efficiency frontier analysis of Polasky et al. "
   "(2026, Science). Economic production-value layers (crop, oil palm, grazing revenue; grazing methane) are native "
   "**H3 resolution 5** (from 5-arcmin ~9 km source); forestry, Forest Landscape Integrity, and land-use transition "
   "costs are native **resolution 8** (from 300 m source); all carry an h5 parent column for a common res-5 decision "
   "unit (~8000 ha, the paper's parcel). Revenue/methane/FLII are per-ha/index DENSITIES (mean reducer — aggregate "
   "with AVG, never SUM); transition costs are per-cell USD TOTALS (sum reducer). Sourced from the CC0 Dryad deposit "
   "(doi:10.5061/dryad.qjq2bvqw5); see also iucn-richness-2025, wwf-ecoregions-2017, irrecoverable-carbon for the "
   "biodiversity and carbon objectives, and wdpa for the IUCN I–IV constraint. Also included are the "
   "scenario-construction constraint masks (binary suitability/slope eligibility, mode reducer, res 8) that "
   "restrict admissible land-use alternatives per parcel, and the carbon-zone ID raster (mode reducer, res 8) "
   "that keys the Spawn et al. carbon_table for graded per-land-use carbon."),
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
