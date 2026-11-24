"""Write stac-collection.json and README.md for public-coastal/global-delta-change (#796).

usage: gen_stac.py <outdir>

Units come from the authors' GlobalDeltaData.nc; definitions from their processing scripts
(get_Qriver.m, get_Qwave.m, get_Qtide.m, get_channel_slope.m, get_bathy_profile.m,
land_area_change/get_aquamonitor_data.m, export_data/webpage/create_webpage_data.m) at the pinned
commit. Ranges, nulls and coded values were measured on the prep outputs on 2026-11-24.
Each asset's `created` is the object's Last-Modified, read from the bucket listing.
"""
import json
import re
import sys
import urllib.request

OUT = sys.argv[1]
B = "https://s3-west.nrp-nautilus.io/public-coastal"
D = f"{B}/global-delta-change"
COMMIT = "99fa08a4d86755db4e0b5deea4e03bcc81f77bbf"
REPO = "https://github.com/jhnienhuis/GlobalDeltaChange"
ACCESSED = "2026-11-24"


def listing(prefix):
    """{key: LastModified} under a prefix of the bucket."""
    out, token = {}, ""
    while True:
        url = f"{B}/?list-type=2&prefix={prefix}" + (f"&continuation-token={token}" if token else "")
        x = urllib.request.urlopen(url).read().decode()
        out.update(dict(re.findall(r"<Key>([^<]+)</Key><LastModified>([^<]+)</LastModified>", x)))
        m = re.search(r"<NextContinuationToken>([^<]+)<", x)
        if not m:
            return out
        token = urllib.parse.quote(m.group(1))


import urllib.parse  # noqa: E402

L = listing("global-delta-change")
stamp = lambda s: s[:19] + "Z"


def created(prefix):
    v = [t for k, t in L.items() if k.startswith(prefix)]
    assert v, f"nothing published under {prefix}"
    return stamp(max(v))


REGIONS = ["Baltic", "Carribean", "East Africa", "East Asia", "Eastern Central America", "Eastern North America",
           "Eastern South America", "Middle-East", "Northern Mediterranean", "Oceania", "Pacific Islands", "Russia",
           "South Asia", "Southeast Asia", "West Africa", "Western Central America", "Western Europe",
           "Western North America", "Western South America"]
CODES = {1: "East Africa", 2: "South Asia", 3: "West Africa", 4: "Baltic", 5: "Eastern Central America",
         6: "Western Central America", 7: "Carribean", 8: "Russia", 9: "East Asia", 10: "Middle-East",
         12: "Eastern North America", 13: "Western North America", 14: "Northern Mediterranean",
         15: "Western Europe", 16: "Oceania", 17: "Pacific Islands", 18: "Eastern South America",
         19: "Western South America", 20: "Southeast Asia",
         21: "no name in the source; 194 deltas around the southern and eastern Mediterranean, the Black Sea and the Caspian Sea, including the Nile"}

COLS = {
    "_cng_fid": ("int64", "Unique row id assigned at conversion, one per feature."),
    "delta_id": ("int32", "Delta identifier, 1 to 10,848: the delta's position in the authors' delta list. "
                          "It is the key that links the layers and the projections table."),
    "basin_id2": ("int64", "Basin identifier the authors use to link their files. Five of its values are shared "
                           "by two deltas each, so join on delta_id instead."),
    "delta_name": ("string", "River name, where one is known (2,105 of 10,848 deltas), from FAO AQUAMAPS. A few "
                             "names carry a damaged character from the source file."),
    "basin_id_atlas": ("int64", "MAIN_BAS identifier of the river's drainage basin in HydroATLAS (BasinATLAS v1.0)."),
    "river_id_atlas": ("int64", "HYRIV_ID of the river reach matched to the delta in HydroATLAS (RiverATLAS v1.0)."),
    "region": ("string", "World region the authors assign the delta to. Empty for the 194 deltas whose region "
                         "code has no name in the source (region_code 21)."),
    "region_code": ("int32", "World region code from the source. Values: " +
                    ", ".join(f"{k}={v}" for k, v in CODES.items())),
    "mouth_lon": ("double", "Longitude of the river mouth, in decimal degrees (WGS84)."),
    "mouth_lat": ("double", "Latitude of the river mouth, in decimal degrees (WGS84)."),
    "basin_area_km2": ("double", "Area of the upstream drainage basin, in km² (50 to 5,981,000)."),
    "discharge_prist_m3s": ("double", "Mean river water discharge at the mouth without human influence (pristine), in m³/s, "
                                      "from the WBMsed global hydrological and sediment model."),
    "discharge_dist_m3s": ("double", "Mean river water discharge at the mouth under present-day conditions (disturbed: "
                                     "including dams and land use), in m³/s, from WBMsed."),
    "discharge_tide_m3s": ("double", "Tidal water discharge through the river mouth, in m³/s, estimated from the tidal "
                                     "amplitude (TOPEX/Poseidon) and the shape of the lower channel."),
    "qriver_prist_kgs": ("double", "Mean suspended sediment flux delivered by the river to the delta without human "
                                   "influence (pristine), in kg/s, from WBMsed. Nine deltas carry 1e-10, a floor value "
                                   "rather than a measured flux."),
    "qriver_dist_kgs": ("double", "Mean suspended sediment flux delivered by the river to the delta under present-day "
                                  "conditions, in kg/s, from WBMsed. It includes sediment trapped behind dams and the extra "
                                  "sediment from land use such as deforestation. Multiply by 31,557,600 for kg per year."),
    "qtide_kgs": ("double", "Sediment flux that tides can move at the mouth, in kg/s: the tidal discharge times the "
                            "river's pristine sediment concentration, bounded between 10 and 1,000 mg/L (Nienhuis et al. "
                            "2020). Compared with the river and wave fluxes it sets the delta's predicted shape."),
    "qwave_kgs": ("double", "Potential alongshore sediment flux that waves can move at the mouth, in kg/s, as defined by "
                            "Nienhuis et al. (2020). Zero for 38 fully sheltered deltas."),
    "hs_m": ("double", "Significant wave height offshore of the mouth, in metres, from WaveWatch III with a fetch "
                       "estimate where the coast is sheltered. Zero for 38 fully sheltered deltas."),
    "tp_s": ("double", "Peak wave period offshore of the mouth, in seconds, from WaveWatch III."),
    "tidal_amp_m": ("double", "Tidal amplitude at the mouth, in metres, from TOPEX/Poseidon."),
    "channel_slope": ("double", "River channel slope near the mouth (dimensionless, m per m), fitted to the SRTM elevation "
                                "profile up to 30 m. 509 deltas have a negative fitted slope and 20 are empty, where the "
                                "fit did not work."),
    "shelf_depth_m": ("double", "Depth of the seabed offshore of the mouth, in metres, negative below sea level, from ETOPO."),
    "shelf_slope": ("double", "Slope of the seabed offshore of the mouth (dimensionless, negative downward), from ETOPO. "
                              "Empty for 1,080 deltas."),
    "land_gain_km2yr": ("double", "Land gained in the delta around the mouth, in km² per year, from Landsat water and land "
                                  "change between about 1985 and 2015 (Deltares Aquamonitor)."),
    "land_loss_km2yr": ("double", "Land lost in the delta around the mouth, in km² per year, written as a negative number, "
                                  "from the same Landsat change."),
    "land_net_km2yr": ("double", "Net land area change of the delta, in km² per year (gain plus loss). The authors set it "
                                 "to 0 for the Caspian Sea deltas, and describe these estimates as noisy for single deltas."),
    "sediment_change_pct": ("double", "Change in sediment supply to the delta from pristine to present-day conditions, in "
                                      "percent: 100 × (qriver_dist_kgs − qriver_prist_kgs) / qriver_prist_kgs. Negative means "
                                      "less sediment now, mostly from dams; positive means more, mostly from land use. Empty "
                                      "where the pristine flux is the 1e-10 floor value."),
    "delta_area_km2": ("double", "Delta area, in km², from the delta outline (apex, shoreline and mouth) of Nienhuis et al. "
                                 "(2023). On the outlines it is the present area. In the projections table it is the area "
                                 "for that year and scenario; it is empty for years with only a sea-level value, and falls "
                                 "below zero for 250 deltas from 2100 onward, which means the model projects the whole "
                                 "present delta to drown, so read it as 0."),
    "scenario": ("string", "Climate scenario of the projection. Values: SSP1-2.6=low emissions, SSP2-4.5=intermediate "
                           "emissions, SSP5-8.5=very high emissions"),
    "year": ("int32", "Year of the projection (1900 to 2300)."),
    "rslr_m": ("double", "Relative sea-level change at the delta since 2000, in metres: sea-level change plus "
                         "vertical land motion such as subsidence, following Nienhuis & van de Wal (2021). Empty for "
                         "1985 and 2015, which carry only an area."),
    "geometry": ("geometry", "Feature geometry (WGS84)."),
    "bbox": ("struct", "Bounding box of the geometry (xmin, ymin, xmax, ymax), used to speed up spatial filters."),
    "h8": ("uint64", "H3 cell id at resolution 8."),
    "h6": ("uint64", "H3 cell id at resolution 6."),
    "h0": ("int64", "H3 cell id at resolution 0, used as the partition key for hive-partitioned reads."),
}
VALUES = {"region": REGIONS, "region_code": [k for k in CODES], "scenario": ["SSP1-2.6", "SSP2-4.5", "SSP5-8.5"]}

ATTRS = ["delta_id", "basin_id2", "delta_name", "basin_id_atlas", "river_id_atlas", "region", "region_code",
         "mouth_lon", "mouth_lat", "basin_area_km2", "discharge_prist_m3s", "discharge_dist_m3s", "discharge_tide_m3s",
         "qriver_prist_kgs", "qriver_dist_kgs", "qtide_kgs", "qwave_kgs", "hs_m", "tp_s", "tidal_amp_m",
         "channel_slope", "shelf_depth_m", "shelf_slope", "land_gain_km2yr", "land_loss_km2yr", "land_net_km2yr",
         "sediment_change_pct"]
LINE = ["delta_id", "basin_id2", "delta_name", "region", "basin_area_km2", "discharge_prist_m3s",
        "discharge_dist_m3s", "qriver_prist_kgs", "qriver_dist_kgs", "sediment_change_pct"]
AREA = ["delta_id", "basin_id2", "delta_area_km2", "delta_name", "region", "qriver_prist_kgs", "qriver_dist_kgs",
        "sediment_change_pct", "land_net_km2yr"]
PROJ = ["delta_id", "scenario", "year", "rslr_m", "delta_area_km2"]

LAYERS = {  # name: (attribute columns, H3 resolution, title, one-line description)
    "mouths": (ATTRS, 8, "Delta river mouths",
               "One point per delta at its river mouth (10,848 deltas), with every attribute: water and sediment "
               "discharge, wave and tide fluxes, coastal setting and land area change."),
    "rivers": (LINE, 8, "Delta river channels",
               "The lower river channel of each delta, from the mouth upstream to 30 m elevation (10,839 deltas; nine "
               "have too few profile points to draw a line)."),
    "basins": (LINE, 6, "Delta drainage basins",
               "The upstream drainage basin of each delta (10,848 polygons, from HydroATLAS), carrying the river's "
               "water and sediment discharge."),
    "delta_areas": (AREA, 8, "Delta outlines",
                    "Outlines of the 811 deltas larger than 10 km² from Nienhuis et al. (2023): a four-sided shape "
                    "joining the delta apex, the two shoreline ends and the mouth, with the delta's area."),
}

dictionary, seen = [], set()
for n in ["_cng_fid"] + ATTRS + ["delta_area_km2", "scenario", "year", "rslr_m", "geometry", "bbox", "h8", "h6", "h0"]:
    if n not in seen:
        seen.add(n)
        t, d = COLS[n]
        e = {"name": n, "type": t, "description": d}
        if n in VALUES:
            e["values"] = VALUES[n]
        dictionary.append(e)

typed = lambda names: [{"name": n, "type": COLS[n][0]} for n in names]
tile = lambda names: [{"name": n, "type": "String" if COLS[n][0] == "string" else "Number"} for n in names]

assets, links_pm = {}, []
for name, (cols, res, title, desc) in LAYERS.items():
    feat = "point" if name == "mouths" else "line" if name == "rivers" else "polygon"
    assets[f"{name}-parquet"] = {
        "href": f"{D}/{name}.parquet", "type": "application/x-parquet", "title": f"{title} — GeoParquet",
        "roles": ["data"], "created": created(f"global-delta-change/{name}.parquet"), "description": desc,
        "table:columns": typed(["_cng_fid"] + cols + ["geometry", "bbox"])}
    assets[f"{name}-pmtiles"] = {
        "href": f"{D}/{name}.pmtiles", "type": "application/vnd.pmtiles", "title": f"{title} — PMTiles",
        "roles": ["visual"], "created": created(f"global-delta-change/{name}.pmtiles"),
        "description": f"Vector tiles of the {title.lower()} for web maps; the source layer is {name}.",
        "vector:layers": [name], "table:columns": tile(["_cng_fid"] + cols)}
    if feat == "point":
        hexdesc = ("Each river mouth placed in the one H3 resolution-8 cell (about 0.7 km²) that contains it, one row "
                   "per delta with every attribute. Deltas sharing a cell are not merged; count deltas with "
                   "COUNT(DISTINCT delta_id).")
    else:
        size = "about 36 km²" if res == 6 else "about 0.7 km²"
        how = ("by buffering each line by the cell size before filling it with cells" if feat == "line"
               else "covering each polygon")
        hexdesc = (f"Each {title.lower()[:-1]} filled with H3 resolution-{res} cells ({size}) {how}, one row per "
                   f"(delta, cell). Every attribute, including the discharges and sediment fluxes, is repeated on "
                   f"every cell a feature covers, so dedup by delta_id before summing: "
                   f"SELECT DISTINCT delta_id, qriver_dist_kgs FROM ….")
        if res == 6:
            hexdesc += (" The basins are hexed at resolution 6 rather than the catalog's usual 8 because the largest "
                        "cover millions of km², so this asset has no h8 column; join through "
                        "h3_cell_to_parent(other.h8, 6) = h6.")
    assets[f"{name}-hex"] = {
        "href": f"{D}/{name}/hex/h0=*/data_0.parquet", "type": "application/x-parquet",
        "title": f"{title} — H3 hex (resolution {res})", "roles": ["data"],
        "created": created(f"global-delta-change/{name}/hex/"), "description": hexdesc,
        "h3:native_resolution": res, "h3:parent_resolutions": [0],
        "table:columns": typed(["_cng_fid"] + cols + [f"h{res}", "h0"])}
    links_pm.append({"rel": "pmtiles", "href": f"{D}/{name}.pmtiles", "type": "application/vnd.pmtiles",
                     "title": f"{title} — PMTiles", "pmtiles:layers": [name]})
    assets[f"style-{name}"] = {
        "href": f"{D}/styles/{name}-sediment_change_pct.json", "type": "application/vnd.mapbox.style+json",
        "title": f"{title} by change in sediment supply", "roles": ["style", "default"],
        "description": ("Coloured by the change in sediment supply from pristine to present-day: dark orange where "
                        "dams have cut supply by more than three quarters, through lighter shades to pale where "
                        "supply has held or grown. Grey where there is no estimate.")}

assets["projections-parquet"] = {
    "href": f"{D}/projections.parquet", "type": "application/x-parquet", "roles": ["data"],
    "title": "Relative sea-level rise and delta area projections, 811 deltas",
    "created": created("global-delta-change/projections.parquet"),
    "description": ("One row per delta, scenario and year for the 811 deltas larger than 10 km²: relative sea-level "
                    "change since 2000 (1900 to 2300) and delta area (1985 to 2300) under SSP1-2.6, SSP2-4.5 and "
                    "SSP5-8.5, from Nienhuis et al. (2023). Join to any layer on delta_id."),
    "table:columns": typed(PROJ)}

DESC = f"""Nearly 11,000 river deltas worldwide, with the sediment their rivers deliver before and after human influence, the waves and tides that shape them, and how much land they have gained or lost since 1985. Built from the global delta dataset of Nienhuis et al. (2020), with outlines and sea-level rise projections for the 811 largest deltas from Nienhuis et al. (2023).

Dams trap sediment that would otherwise build deltas, while deforestation and farming upstream add sediment. Each delta carries its river's modelled sediment flux without human influence (pristine) and today (disturbed), from the WBMsed model, and the percent change between them, sediment_change_pct. Across all deltas the flux falls from 19.1 to 17.3 billion tonnes per year; 964 deltas have lost more than half their supply, among them the Nile (−98%) and the Rhône (−65%). Land area change comes from Landsat (Deltares Aquamonitor), about 1985 to 2015; the authors note it is noisy for a single delta.

Four map layers share the key delta_id: river mouths (points, with every attribute), the lower river channels (lines), the upstream drainage basins (polygons) and outlines of the 811 deltas over 10 km². A projections table gives relative sea-level change and delta area to 2300 under three climate scenarios for those 811 deltas. Deltas whose rivers have lost most of their sediment:

```sql
SELECT delta_name, region, qriver_prist_kgs, qriver_dist_kgs, sediment_change_pct, land_net_km2yr
FROM read_parquet('{D}/mouths.parquet')
WHERE qriver_prist_kgs > 100 ORDER BY sediment_change_pct LIMIT 20
```

The Caspian Sea deltas are included, although the Caspian is a lake; the authors set their land change to 0.

Source: Nienhuis, J. H., et al. (2020), Global-scale human impact on delta morphology has led to net land area gain, Nature 577, 514–518, https://doi.org/10.1038/s41586-019-1905-9, and Nienhuis, J. H., et al. (2023), River deltas and sea-level rise, Annual Review of Earth and Planetary Sciences 51, 79–104, https://doi.org/10.1146/annurev-earth-031621-093732. Data from the GlobalDeltaChange repository ({REPO}, commit {COMMIT[:7]} of 2023-03-13, release 3.0 plus the 2023 exports), MIT licence, copyright Jaap Nienhuis, accessed {ACCESSED}. No edition label beyond the repository release. The repository's shapefiles have damaged attribute tables, so attributes were read from GlobalDeltaData.mat (8,390,920 bytes, SHA-256 4bd87e24ab724b4d5c9000df0f4af178fa9656d1f0506c08af2259283cc6b453), land_area_change/GlobalDeltaData_AreaChange.mat (3,324,609 bytes, SHA-256 03837c1d7d2772b784b480009538a5a25dc81c8673541d49b45cf796d8ff6410) and GlobalDeltaData.xlsx (1,398,938 bytes, SHA-256 78198862404c2f9bbf2465bbcb3af2c9d5875b63e56a130e96fa93b0eb72c6f0); basin outlines from GlobalDeltaBasins_shp.zip (9,272,222 bytes, SHA-256 bca53732de237409d4223f2c76b0e79a59d72d38c2e047e4928562f5d5286990) and delta outlines from GlobalDeltaAreaWeb_shp.zip (60,800 bytes, SHA-256 31d71e631897b60b41c5b19c74c6d3bb188461b6bfab349020734258aa4c8d45); projections from GlobalDelta_DeltaSLRWeb.csv (277,870 bytes, SHA-256 d570fdf6c8666f564774006e8af411849f21cc6927090e921dc20a452cb63fc1) and GlobalDelta_DeltaAreaWeb.csv (408,618 bytes, SHA-256 3700f51d084af46e719d5cb61a8b210992308bf2c7a70f372281de405f98afa5)."""

now = max(a["created"] for a in assets.values() if "created" in a)
col = {
    "stac_version": "1.1.0",
    "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json",
                        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
                        "https://stac-extensions.github.io/web-map-links/v1.3.0/schema.json",
                        "https://schemas.portolan-sdi.org/portolan/v0.3.0/schema.json"],
    "type": "Collection", "id": "global-delta-change",
    "title": "Global river deltas: sediment supply, land change and sea-level rise",
    "description": DESC, "license": "MIT",
    "keywords": ["river deltas", "sediment supply", "dams", "land loss", "sea-level rise", "subsidence",
                 "coastal geomorphology", "global"],
    "sci:doi": "10.1038/s41586-019-1905-9",
    "sci:citation": ("Nienhuis, J. H., Ashton, A. D., Edmonds, D. A., Hoitink, A. J. F., Kettner, A. J., Rowland, J. C., "
                     "& Törnqvist, T. E. (2020). Global-scale human impact on delta morphology has led to net land area "
                     f"gain. Nature, 577, 514–518. Data: GlobalDeltaChange, {REPO}, commit {COMMIT[:7]}, accessed {ACCESSED}."),
    "sci:publications": [{"doi": "10.1146/annurev-earth-031621-093732",
                          "citation": "Nienhuis, J. H., Kim, W., Milne, G. A., Quock, M., Slangen, A. B. A., & Törnqvist, T. E. (2023). River deltas and sea-level rise. Annual Review of Earth and Planetary Sciences, 51, 79–104."},
                         {"doi": "10.1029/2021GL093368",
                          "citation": "Nienhuis, J. H., & van de Wal, R. S. W. (2021). Projections of global delta land loss from sea-level rise in the 21st century. Geophysical Research Letters, 48, e2021GL093368."}],
    "providers": [{"name": "Jaap Nienhuis, Utrecht University", "roles": ["producer", "licensor"], "url": REPO},
                  {"name": "Boettiger Lab", "roles": ["processor", "host"], "url": "https://github.com/boettiger-lab"}],
    "extent": {"spatial": {"bbox": [[-180, -55.1, 180, 79.5]]},
               "temporal": {"interval": [["1900-01-01T00:00:00Z", "2300-12-31T23:59:59Z"]]}},
    "created": now, "updated": now,
    "table:columns": dictionary,
    "links": [
        {"rel": "self", "href": f"{D}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json"},
        {"rel": "parent", "href": f"{B}/stac-collection.json", "type": "application/json"},
        {"rel": "license", "href": f"{REPO}/blob/{COMMIT}/LICENSE", "type": "text/html", "title": "MIT License"},
        {"rel": "about", "href": REPO, "type": "text/html", "title": "GlobalDeltaChange on GitHub"},
        {"rel": "via", "href": REPO, "type": "text/html", "title": "GlobalDeltaChange on GitHub"},
        {"rel": "cite-as", "href": "https://doi.org/10.1038/s41586-019-1905-9", "type": "text/html"},
        {"rel": "describedby", "href": f"{D}/README.md", "type": "text/markdown", "title": "README"},
    ] + links_pm,
    "assets": assets,
}
json.dump(col, open(f"{OUT}/stac-collection.json", "w"), indent=2, ensure_ascii=False)

README = f"""# Global river deltas: sediment supply, land change and sea-level rise

{DESC}

## Files

| File | Contents |
|---|---|
""" + "".join(f"| `{D}/{n}.parquet`, `.pmtiles` | {LAYERS[n][2]} (GeoParquet; vector tiles, source layer `{n}`) |\n" for n in LAYERS) + \
    "".join(f"| `{D}/{n}/hex/h0=*/data_0.parquet` | {LAYERS[n][2]} indexed to H3 resolution {LAYERS[n][1]} |\n" for n in LAYERS) + \
    f"| `{D}/projections.parquet` | Sea-level and delta area projections for 811 deltas |\n" + f"""
## DuckDB

```sql
INSTALL httpfs; LOAD httpfs;
SELECT m.delta_name, p.scenario, p.rslr_m
FROM read_parquet('{D}/projections.parquet') p
JOIN read_parquet('{D}/mouths.parquet') m USING (delta_id)
WHERE p.year = 2100 AND m.delta_name = 'Mississippi';
```

## MapLibre GL JS

```js
map.addSource('deltas', {{ type: 'vector', url: 'pmtiles://{D}/mouths.pmtiles' }});
map.addLayer({{
  id: 'delta-mouths', type: 'circle', source: 'deltas',
  'source-layer': 'mouths',
  paint: {{ 'circle-radius': 3, 'circle-color': ['step', ['get', 'sediment_change_pct'],
    '#a63603', -75, '#e6550d', -50, '#fd8d3c', -25, '#fdae6b', -5, '#fdd0a2', 5, '#feedde'] }}
}});
```

## Columns

| Column | Description |
|---|---|
""" + "\n".join(f"| `{e['name']}` | {e['description']} |" for e in dictionary) + "\n"
open(f"{OUT}/README.md", "w").write(README)
print("wrote", len(assets), "assets,", len(dictionary), "columns")
