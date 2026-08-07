#!/usr/bin/env python3
"""Build the STAC collection for usgs-nhdplus-hr-flowline (#205, California first)."""
import json, os

UNITS = [("1503","NHDPLUS_H_1503_HU4_20220901_GDB.zip","2022-09-01",125982,104386,99.86),
         ("1605","NHDPLUS_H_1605_HU4_20220418_GDB.zip","2022-04-18",71880,50618,100.00),
         ("1606","NHDPLUS_H_1606_HU4_20220418_GDB.zip","2022-04-18",269992,224178,100.00),
         ("1801","NHDPLUS_H_1801_HU4_GDB.zip","undated",341762,126408,99.41),
         ("1802","NHDPLUS_H_1802_HU4_GDB.zip","undated",474166,159510,100.00),
         ("1803","NHDPLUS_H_1803_HU4_GDB.zip","undated",105430,47746,100.00),
         ("1804","NHDPLUS_H_1804_HU4_GDB.zip","undated",385039,109876,100.00),
         ("1805","NHDPLUS_H_1805_HU4_GDB.zip","undated",47293,22094,94.29),
         ("1806","NHDPLUS_H_1806_HU4_GDB.zip","undated",166606,76043,98.80),
         ("1807","NHDPLUS_H_1807_HU4_GDB.zip","undated",225480,79437,98.75),
         ("1808","NHDPLUS_H_1808_HU4_GDB.zip","undated",22496,13855,100.00),
         ("1809","NHDPLUS_H_1809_HU4_GDB.zip","undated",133619,111214,100.00),
         ("1810","NHDPLUS_H_1810_HU4_GDB.zip","undated",41174,49931,100.00)]
B = "https://s3-west.nrp-nautilus.io/public-usgs-nhd"

FCODE_VALUES = ['33400', '33600', '33601', '33603', '42000', '42003', '42800', '42801', '42802', '42803', '42804', '42805', '42806', '42807', '42808', '42809', '42810', '42811', '42812', '42813', '42814', '42816', '42820', '42821', '42822', '42823', '46000', '46003', '46006', '46007', '46800', '55800', '56600']
HU4_NAMES = {"1503":"Lower Colorado","1605":"Central Nevada Desert Basins",
             "1606":"Great Salt Lake / Escalante Desert basins","1801":"Klamath",
             "1802":"Sacramento","1803":"Tulare-Buena Vista Lakes","1804":"San Joaquin",
             "1805":"Central California Coastal","1806":"Central California Coastal (south)",
             "1807":"Southern California Coastal","1808":"North Lahontan",
             "1809":"Northern Mojave-Mono Lake","1810":"Southern Mojave-Salton Sea"}


manifest = "; ".join(f"{h}={z} (vintage {v}, {n:,} flowlines, {km:,.0f} in-network km, "
                     f"{pw:.2f}% order incl. coastline / 100.00% excl.)"
                     for h, z, v, n, km, pw in UNITS)

COVERAGE = (
    "STREAM-ORDER COVERAGE: streamorde > 0 covers 100.00% of in-network, non-coastline flowline "
    "length in EVERY one of the 13 HU4 units (0.0 km unattributed). Coastline (fcode 56600) "
    "carries no VAA and therefore no order — it is not a stream — which is the whole of the "
    "apparent shortfall where the coastline-inclusive figure is below 100% (HU4 1805 reads 94.29% "
    "with coastline and 100.00% without; its 5.71% 'gap' is 888 coastline features / 1,262 km). "
    "Audit this column with > 0, NEVER IS NOT NULL. streamorde is NULL (never 0 or negative) "
    "wherever it is not computed: the source's non-positive sentinels were normalised to NULL at "
    "build time, so the published range is exactly 1-10. Off-network flowlines (innetwork = 0) "
    "and canals/pipelines/coastline have no order by design."
)

VS_BASE = (
    "RELATIONSHIP TO usgs-nhd-streams-by-order (base NHD-H): these are COMPLEMENTARY, not "
    "substitutes. Use THIS collection for stream order and network attributes; use "
    "streams-by-order for extent and flow permanence (it is the denser, more recently edited "
    "network, and it is the ONLY source for Alaska — NHDPlus HR has no HUC2 19). Measured over "
    "these 13 California units, for stream/river FCODEs 46003/46006/46007: (a) features present "
    "in only one asset — base-only 289,426 km ephemeral, 24,336 km intermittent, 7,257 km "
    "perennial vs HR-only 16,237 / 8,389 / 4,526 km, i.e. base NHD has since been densified with "
    "ephemeral washes this NHDPlus HR vintage predates; (b) for the 2,017,710 features shared by "
    "both with the same fcode, HR lengthkm runs +1.88% (ephemeral), +4.77% (intermittent), "
    "+5.45% (perennial). Length divergence is a PER-VPU editing-vintage difference, not a "
    "different length algorithm — where the underlying NHD has not been re-edited the values "
    "agree to the millimetre, so compare per unit using vpu_vintage rather than assuming a "
    "blanket offset. fcode is ~96% stable (81,782 of 2,017,710 shared features reclassify, in "
    "both directions): there is no redefinition of ephemeral or perennial."
)

desc = (
    "USGS NHDPlus High Resolution flowlines with the network value-added attributes "
    "(NHDPlusFlowlineVAA) joined on nhdplusid — 2,410,919 features across the 13 California HU4 "
    "vector processing units (VPUs). This collection exists because the base NHD-H VAA table "
    "ships a usable STREAMORDER for only 11.4% of flowlines nationally, with 15 of 22 HUC2 "
    "regions at exactly 0.0% (data-workflows#518); NHDPlus HR computes the network attributes "
    f"properly. {COVERAGE} {VS_BASE} COVERAGE IS CALIFORNIA ONLY at present: this is the "
    "first tranche of the national build (data-workflows#205), which fans out to the remaining "
    "VPUs. NHDPlus HR covers 21 HUC2 regions (01-18, 20, 21, 22) and does NOT include Alaska "
    "(HUC2 19). Sourced from VPU/Current/GDB per-HU4 downloads, NOT the National Release 2 "
    "aggregate, which USGS documents as defective (region 06 falls back to Beta data with a "
    "disconnected network; a GridCode bug affects VPUIDs 0903/1007/1015/1021/1022/1025; 0415 is "
    f"a pre-Beta prototype). Per-unit source manifest: {manifest}. Geometry in OGC:CRS84 "
    "(lon, lat), reprojected from the source NAD83 + NAVD88 compound CRS (EPSG:5498). Indexed to "
    "H3 resolution 8."
)

FL_COLS = [
 ("_cng_fid","string","Universal per-feature identifier, unique across the whole collection. Built as '<hu4>-<per-unit id>' because the per-unit conversion numbers rows from 1 independently, so the raw ids collide between VPUs. Use this for COUNT(DISTINCT) / dedup."),
 ("nhdplusid","decimal","NHDPlus High Resolution permanent feature id, and the join key to NHDPlusFlowlineVAA. Stored as an exact decimal: the source types it as a 64-bit float, and a float-equality join on a 14-digit id drops rows silently."),
 ("permanent_identifier","string","NHD permanent feature identifier (GUID). Use this to cross-reference the base-NHD usgs-nhd-streams-by-order asset; ~95% of in-network ids are shared."),
 ("reachcode","string","14-digit NHD Reach Code — a stable per-reach identifier for linear referencing, not an enumerable code list (hundreds of thousands of distinct values). The first 8 digits are the HUC8 and the last 6 a sequential reach number, so substr(reachcode,1,4) gives the HU4 and substr(reachcode,1,2) the HUC2 region."),
 ("gnis_id","string","GNIS ID of the named feature, if any."),
 ("gnis_name","string","GNIS feature name (river/stream name), if any."),
 ("lengthkm","double","Flowline length in kilometers, as computed by NHDPlus HR. NOT directly comparable with the base-NHD asset's LENGTHKM for the same feature: the difference is a per-VPU editing-vintage effect (+1.9% to +5.5% over shared California features, 0.0% in VPUs not re-edited since this build). Compare per unit using vpu_vintage."),
 ("ftype","int32","NHD Feature Type (3-digit FType). Values present: 460=StreamRiver, 558=ArtificialPath, 336=CanalDitch, 566=Coastline, 428=Pipeline, 334=Connector, 420=UndergroundConduit, 468=Drainageway.", ["460","558","336","566","428","334","420","468"]),
 ("fcode","int32",'NHD Feature Code (5-digit FCode, verbatim from the source NHDFCode domain table). Stream/river subtypes carry the hydrographic category, so flow permanence comes from FCODE, not from stream order. All 33 values present in this dataset: 33400=Connector, 33600=Canal/Ditch, 33601=Canal/Ditch: Canal/Ditch Type = Aqueduct, 33603=Canal Ditch: Canal Ditch Type = Stormwater, 42000=Underground Conduit, 42003=Underground Conduit: Positional Accuracy = Approximate, 42800=Pipeline, 42801=Pipeline: Pipeline Type = Aqueduct; Relationship to Surface = At or Near, 42802=Pipeline: Pipeline Type = Aqueduct; Relationship to Surface = Elevated, 42803=Pipeline: Pipeline Type = Aqueduct; Relationship to Surface = Underground, 42804=Pipeline: Pipeline Type = Aqueduct; Relationship to Surface = Underwater, 42805=Pipeline: Pipeline Type = General Case; Relationship to Surface = At or Near, 42806=Pipeline: Pipeline Type = General Case; Relationship to Surface = Elevated, 42807=Pipeline: Pipeline Type = General Case; Relationship to Surface = Underground, 42808=Pipeline: Pipeline Type = General Case; Relationship to Surface = Underwater, 42809=Pipeline: Pipeline Type = Penstock; Relationship to Surface = At or Near, 42810=Pipeline: Pipeline Type = Penstock; Relationship to Surface = Elevated, 42811=Pipeline: Pipeline Type = Penstock; Relationship to Surface = Underground, 42812=Pipeline: Pipeline Type = Penstock; Relationship to Surface = Underwater, 42813=Pipeline: Pipeline Type = Siphon, 42814=Pipeline: Pipeline Type = General Case, 42816=Pipeline: Pipeline Type = Aqueduct, 42820=Pipeline: Pipeline Type = Stormwater, 42821=Pipeline: Pipeline Type = Stormwater; Relationship to Surface = At or Near, 42822=Pipeline: Pipeline Type = Stormwater; Relationship to Surface = Elevated, 42823=Pipeline: Pipeline Type = Stormwater; Relationship to Surface = Underground, 46000=Stream/River, 46003=Stream/River: Hydrographic Category = Intermittent, 46006=Stream/River: Hydrographic Category = Perennial, 46007=Stream/River: Hydrographic Category = Ephemeral, 46800=Drainageway, 55800=Artificial Path, 56600=Coastline. Note 56600=Coastline is NOT a stream and carries no stream order — exclude it from any order-coverage denominator.', FCODE_VALUES),
 ("flowdir","int32","Flow direction (HydroFlowDirections domain): 0=Uninitialized, 1=With Digitized.", ["0","1"]),
 ("innetwork","int32","Whether the flowline participates in the NHD navigable network (NoYes domain): 0=No, 1=Yes. Stream order is computed for in-network features only, so restrict to innetwork = 1 before computing order coverage.", ["0","1"]),
 ("mainpath","int32","Whether the flowline is on the main flow path of its waterbody (MainPath domain): 0=No, 1=Yes. Only 0 occurs across these 13 California VPUs — NHDPlus HR leaves this flag unset here; use mainstem grouping via levelpathi instead.", ["0"]),
 ("visibilityfilter","int32","Scale-based cartographic visibility threshold; larger values appear only at finer display scales."),
 ("streamorde","int32","Strahler stream order from NHDPlusFlowlineVAA. Headwater channels = 1; order increases downstream where two channels of equal order merge. Published range is exactly 1-10 — the source's non-positive 'not computed' sentinels (including -9 on divergent paths) were normalised to NULL at build time, so IS NOT NULL and > 0 are equivalent here. Still prefer > 0: it is the correct predicate for the source and for the base-NHD asset, where the two differ completely. NULL means order is not computed for that feature (off-network, coastline, canal/pipeline), not that it is missing data — see the collection description for measured coverage."),
 ("streamleve","int32","NHD stream level: the downstream mainstem hierarchy counted DOWN from the terminal outlet (1 = terminal mainstem to ocean/sink), the opposite direction from streamorde, which counts UP from headwaters. Not a substitute for stream order. Non-positive sentinels normalised to NULL."),
 ("streamcalc","int32","NHDPlus stream calculator: the order used for network routing. Differs from streamorde on divergent paths (0 on the minor path of a divergence), which is how NHDPlus keeps a single main path through braided reaches."),
 ("totdasqkm","double","Total upstream drainage area in km², routed through the full network. The standard measure of catchment size for a reach."),
 ("divdasqkm","double","Divergence-routed upstream drainage area in km²: like totdasqkm but apportioned at divergences. Use totdasqkm unless you specifically need divergence accounting."),
 ("slope","double","Reach slope (dimensionless, rise/run) from the smoothed elevation profile. -9998 in the source denotes 'no slope computed' — check for negative values before averaging."),
 ("arbolatesu","double","Arbolate sum: total upstream stream length in km (sum of all upstream flowline lengths). A per-feature cumulative value, not a per-reach length."),
 ("hydroseq","double","Hydrologic sequence number. Sorting descending traverses the network from headwaters downstream; unique per flowline within a VPU."),
 ("uphydroseq","double","hydroseq of the next flowline UPSTREAM on the main path (0 at a headwater)."),
 ("dnhydroseq","double","hydroseq of the next flowline DOWNSTREAM on the main path (0 at a terminal reach). Pair with hydroseq to walk the network."),
 ("dnlevel","int32","streamleve of the next downstream main-path flowline."),
 ("levelpathi","double","Level path identifier: all flowlines on the same mainstem share this value, so it groups a river into one continuous path."),
 ("terminalpa","double","Terminal path identifier: the hydroseq of the network outlet this flowline drains to. Groups flowlines by ultimate destination (ocean, sink, closed basin)."),
 ("pathlength","double","Distance in km along the main path from this flowline's downstream end to the network terminus."),
 ("maxelevsmo","double","Maximum (upstream-end) elevation in cm, from the smoothed profile. -9998 denotes not computed."),
 ("minelevsmo","double","Minimum (downstream-end) elevation in cm, from the smoothed profile. -9998 denotes not computed."),
 ("divergence","int32","Divergence code: 0=not part of a divergence, 1=main path of a divergence, 2=minor path of a divergence.", ["0","1","2"]),
 ("terminalfl","int32","Network-end flag (IsNetworkEnd, NoYes domain): 1 = this flowline is a network terminus.", ["0","1"]),
 ("startflag","int32","Headwater flag (IsHeadwater, NoYes domain): 1 = this flowline is a headwater (no upstream flowline).", ["0","1"]),
 ("areasqkm","double","Incremental catchment area in km² for this flowline's own catchment (not cumulative — that is totdasqkm)."),
 ("vpuid","string","Vector processing unit id as recorded in the source VAA table; mirrors hu4 for these units. Values: " + ", ".join(f"{h}={HU4_NAMES[h]}" for h, *_ in UNITS), [u[0] for u in UNITS]),
 ("hu4","string","4-digit hydrologic unit code (HU4) of the source VPU download, added at build time; also the key to the per-unit source manifest in the collection description. Values: " + ", ".join(f"{h}={HU4_NAMES[h]}" for h, *_ in UNITS), [u[0] for u in UNITS]),
 ("vpu_vintage","string","Publication date stamped on the source VPU filename, added at build time. VPUs differ in editing vintage, which is what drives lengthkm differences against the base-NHD asset — compare per unit using this column. Values: 2022-04-18=VPUs 1605 and 1606, 2022-09-01=VPU 1503, undated=the ten HU4 1801-1810 files, whose names carry no date stamp (vintage not published in the filename)", sorted({u[2] for u in UNITS})),
]

def cols(include_geom, hexed=False):
    out = []
    for c in FL_COLS:
        name, typ, d = c[0], c[1], c[2]
        vals = c[3] if len(c) > 3 else None
        col = {"name": name, "type": typ, "description": d}
        if vals:
            col["values"] = vals
        out.append(col)
    if hexed:
        out += [{"name":"h8","type":"uint64","description":"H3 cell ID at resolution 8 (native; one row per (flowline, h8) pair). Lines were hexed by buffering each segment by the H3 res-8 cell circumradius before polyfill. Safe to COUNT / COUNT(DISTINCT)."},
                {"name":"h0","type":"int64","description":"H3 cell ID at resolution 0 — hive partition key. Safe to aggregate."}]
    if include_geom:
        out.append({"name":"geom","type":"geometry","description":"Feature geometry — MultiLineString in OGC:CRS84 (lon, lat). Reprojected from the source NAD83 + NAVD88 compound CRS (EPSG:5498); Z/M coordinates dropped (2D)."})
    return out

def lean(cs):
    out = []
    for c in cs:
        if c["name"] == "geom":
            continue
        lc = {"name": c["name"], "type": c["type"]}
        if "values" in c:
            lc["values"] = c["values"]
        out.append(lc)
    return out

HEX_NOTE = (
 "NHDPlus HR flowlines indexed to H3 resolution 8 (~0.74 km²/cell), hive-partitioned by h0. "
 "One row = one (flowline, h8) pair. Line features were hexed to H3 res 8 by buffering each "
 "segment by the H3 cell circumradius before polyfill. PER-FEATURE VALUES ARE REPEATED ON EVERY "
 "CELL A FLOWLINE COVERS — never SUM lengthkm, arbolatesu, totdasqkm, divdasqkm, areasqkm or "
 "pathlength on hex data; dedup first (SELECT DISTINCT _cng_fid, lengthkm ...). streamorde, "
 "streamleve, streamcalc, slope and the elevation/hydroseq columns are per-feature attributes "
 "constant along a flowline and likewise repeated across its cells: aggregate them with "
 "MAX/MIN/AVG over DISTINCT features, not over hex rows. Only the H3 index columns (h8, h0) and "
 "_cng_fid counts are safe to aggregate directly. " + COVERAGE
)

stac = {
 "stac_version": "1.0.0",
 "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json"],
 "type": "Collection",
 "id": "usgs-nhdplus-hr-flowline",
 "title": "USGS NHDPlus High Resolution — Flowlines + network VAA (California)",
 "description": desc,
 "license": "public-domain",
 "keywords": ["hydrography","streams","rivers","flowline","stream order","Strahler","NHDPlus",
              "NHDPlus HR","value added attributes","VAA","drainage area","NHD","USGS",
              "California","United States"],
 "providers": [
   {"name":"U.S. Geological Survey","roles":["producer","licensor"],
    "url":"https://www.usgs.gov/national-hydrography/nhdplus-high-resolution"},
   {"name":"Boettiger Lab","roles":["processor","host"],"url":"https://github.com/boettiger-lab"}],
 "extent": {"spatial": {"bbox": [[-124.57, 31.50, -112.55, 43.35]]},
            "temporal": {"interval": [["2022-04-18T00:00:00Z", "2025-09-19T00:00:00Z"]]}},
 "links": [
   {"rel":"self","href":f"{B}/nhdplus-hr/flowline/stac-collection.json","type":"application/json"},
   {"rel":"root","href":"https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json","type":"application/json"},
   {"rel":"parent","href":f"{B}/stac-collection.json","type":"application/json"},
   {"rel":"describedby","href":f"{B}/README.md","type":"text/markdown","title":"NHD / NHDPlus HR documentation"},
   {"rel":"related","href":f"{B}/streams-by-order/stac-collection.json","type":"application/json",
    "title":"Base NHD-H streams-by-order — denser network, Alaska coverage, flow permanence; sparse stream order"},
   {"rel":"about","href":"https://www.usgs.gov/national-hydrography/nhdplus-high-resolution","title":"USGS NHDPlus High Resolution"},
   {"rel":"license","href":"https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits","title":"USGS Public Domain","type":"text/html"}],
 "assets": {
   "flowline-parquet": {
     "href": f"{B}/nhdplus-hr/flowline.parquet",
     "type": "application/vnd.apache.parquet",
     "title": "GeoParquet — 2,410,919 California NHDPlus HR flowlines with network VAA",
     "roles": ["data"],
     "description": "Cloud-native GeoParquet for DuckDB/Polars/GeoPandas. Geometry in OGC:CRS84 (lon, lat). One row per flowline — no per-feature row duplication.",
     "table:columns": cols(include_geom=True)},
   **({"flowline-pmtiles": {
     "href": f"{B}/nhdplus-hr/flowline.pmtiles",
     "type": "application/vnd.pmtiles",
     "title": "PMTiles — California NHDPlus HR flowlines for web maps",
     "roles": ["visual"],
     "description": "Vector tiles for MapLibre/Leaflet, zoom 0-12. The MapLibre `source-layer` is `flowline`. Style by streamorde to render the stream hierarchy; filter [\">\", [\"get\", \"streamorde\"], 0] to drop features with no computed order (coastline, canals, off-network reaches).",
     "vector:layers": ["flowline"],
     "table:columns": lean(cols(include_geom=True))}} if os.environ.get("INCLUDE_PMTILES", "1") != "0" else {}),
   "flowline-hex": {
     "href": f"{B}/nhdplus-hr/flowline/hex/h0=*/data_0.parquet",
     "type": "application/vnd.apache.parquet",
     "title": "H3 hex-indexed parquet (resolution 8)",
     "roles": ["data"],
     "description": HEX_NOTE,
     "table:storage_options": {"partitioning": "h0"},
     "h3:native_resolution": 8,
     "h3:parent_resolutions": [0],
     "table:columns": cols(include_geom=False, hexed=True)},
 },
}
with open('/tmp/nhdplus-hr-flowline-stac.json','w') as f:
    json.dump(stac, f, indent=2, ensure_ascii=False); f.write("\n")
print("wrote /tmp/nhdplus-hr-flowline-stac.json")
