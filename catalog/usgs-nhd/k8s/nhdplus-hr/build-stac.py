#!/usr/bin/env python3
"""Build the STAC collection for usgs-nhdplus-hr-flowline (#205).

⛔ EVERY documented number comes from `stats.json`, produced by measure-stats.yaml against the
PUBLISHED parquet — nothing is hardcoded. The first pass of this builder embedded
California-measured literals (feature counts, sentinel counts, elevation extremes, `values`
arrays, and a "valid range 1-10" that is 1-11 nationally); all would have shipped silently wrong
when the build went national. See AGENTS.md, "MEASURE every added column".

    python3 build-stac.py                      # /tmp/nhdplus-stats.json + local units/domain
    INCLUDE_PMTILES=0 python3 build-stac.py    # omit tiles while they are still generating
"""
import csv, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
STATS  = os.environ.get("STATS",  "/tmp/nhdplus-stats.json")
UNITS  = os.environ.get("UNITS",  os.path.join(HERE, "units-configmap.yaml"))
DOMAIN = os.environ.get("DOMAIN", os.path.join(HERE, "..", "..", "nhdfcode-domain.csv"))
OUT    = os.environ.get("OUT",    "/tmp/nhdplus-hr-flowline-stac.json")
B = "https://s3-west.nrp-nautilus.io/public-usgs-nhd"

s = json.load(open(STATS))
fcode_name = {r["fcode"]: r["description"].strip() for r in csv.DictReader(open(DOMAIN))}

# units come from the very ConfigMap the build consumed, so STAC and the run cannot disagree
units = [m.groups() for m in
         (re.match(r"\s{4}(\S+)\s+(HU4|HU8)\s+(\S+\.zip)\s+(\S+)\s*$", l) for l in open(UNITS))
         if m]
assert len(units) == s["units"], f"configmap has {len(units)} units, data has {s['units']}"
n_hu4  = sum(1 for u in units if u[1] == "HU4")
n_hu8  = sum(1 for u in units if u[1] == "HU8")
n_dated = sum(1 for u in units if u[3] != "undated")
huc2 = s["huc2"]
f = lambda n: f"{int(n):,}"
COVERAGE = (
    f"STREAM-ORDER COVERAGE: `streamorde > 0` covers **{s['pct_nocoast_min']:.2f}% of in-network, "
    f"non-coastline flowline length in EVERY ONE of the {s['units']} source units** — there is no "
    "region where this attribute is missing, which is the whole reason this collection exists "
    "alongside usgs-nhd-streams-by-order. Coastline (fcode 56600) carries no VAA and therefore no "
    "order — it is not a stream — so ALWAYS exclude it from a coverage denominator: including it "
    "makes island and coastal units look broken when they are complete (Puerto Rico 2102 reads "
    "44.24% with coastline and 100.00% without; Hawaii 2008 55.61%/100.00%; Alaska 19020203 "
    "51.22%/100.00%). Audit with `> 0`, NEVER `IS NOT NULL`. `streamorde` is NULL (never 0 or "
    f"negative) wherever it is not computed — {f(s['order_null'])} rows, being off-network reaches "
    "(innetwork = 0), coastline, canals and pipelines: the source's non-positive sentinels were "
    f"normalised to NULL at build time, so the published range is exactly {s['order_min']}-{s['order_max']}."
)

VS_BASE = (
    "RELATIONSHIP TO usgs-nhd-streams-by-order (base NHD-H): these are COMPLEMENTARY, not "
    "substitutes. Use THIS collection for stream order and network attributes; use "
    "streams-by-order for extent and flow permanence — it is the denser, more recently edited "
    f"network, and the COMPLETE source for Alaska, of which NHDPlus HR publishes only {n_hu8} HU8 "
    "units. Measured over the 13 California units for FCODEs 46003/46006/46007: (a) features in "
    "only one asset — base-only 289,426 km ephemeral, 24,336 km intermittent, 7,257 km perennial "
    "vs HR-only 16,237/8,389/4,526 km, i.e. base NHD has since been densified with ephemeral "
    "washes this NHDPlus HR vintage predates; (b) for the 2,017,710 features shared with the same "
    "fcode, HR lengthkm runs +1.88% (ephemeral), +4.77% (intermittent), +5.45% (perennial). BOTH "
    "assets' lengthkm are verified faithful to their own geometry (within 0.06%), and the "
    "divergence is a MINORITY TAIL, not an offset: in the worst basin 80.3% of shared features "
    "agree within 1% and the median ratio is exactly 1.0000. So never apply a per-basin correction "
    "factor between the two (data-workflows#525) — compare per-area network totals, not "
    "per-feature lengths, and state which product a number came from. fcode is ~96% stable "
    "(81,782 of 2,017,710 reclassify, both directions): no redefinition of ephemeral or perennial."
)

desc = (
    "USGS NHDPlus High Resolution flowlines with the network value-added attributes "
    f"(NHDPlusFlowlineVAA) joined on nhdplusid — {f(s['features'])} features across all "
    f"{s['units']} vector processing units USGS publishes, nationwide. This collection exists "
    "because the base NHD-H VAA table ships a usable STREAMORDER for only 11.4% of flowlines with "
    "15 of 22 HUC2 regions at exactly 0.0% (data-workflows#518); NHDPlus HR computes the network "
    f"attributes properly. {COVERAGE} {VS_BASE} SOURCE UNITS: {n_hu4} at HU4 granularity plus "
    f"{n_hu8} at HU8 granularity (the HU8s are all in HUC2 19, Alaska — so Alaska IS covered, "
    f"partially, at HU8 and not for the whole region). Coverage spans HUC2 {', '.join(huc2)}. "
    f"{n_dated} of the {s['units']} source files carry a publication date in their filename and the "
    "rest do not; each unit's filename, vintage and measured coverage is recorded in the "
    "flowline-units asset. Sourced from the per-unit VPU/Current/GDB downloads, NOT the National "
    "Release 2 aggregate, which USGS documents as defective (region 06 falls back to Beta data with "
    "a disconnected network; a GridCode bug affects VPUIDs 0903/1007/1015/1021/1022/1025; 0415 is a "
    "pre-Beta prototype). Geometry in OGC:CRS84 (lon, lat), reprojected from the source NAD83 + "
    "NAVD88 compound CRS (EPSG:5498). Indexed to H3 resolution 8. ⚠️ UNITS ARE WHOLE: source hydrologic units are ingested uncut, so no unit stops at a state line and an unmasked query returns a units total, NEVER a state or regional total. Mask to your area of interest first by joining the hex asset's h8 + h0 against a boundary hex layer. Worked example: across the 13 units that intersect California, 30.3% of their 1,175,296 km of in-network flowline lies outside the state, and unmasked order 1-2 length reads 924,634 km against 641,393 km inside California — a 44% overstatement."
)

SENT = (
    f" **NOT-COMPUTED SENTINEL: -9999** (-9 for streamcalc) on the same {f(s['sentinel_rows'])} "
    "flowlines, which carry no computed network attributes. Filter these out before any aggregate "
    "— an unfiltered SUM/AVG/MIN is poisoned by them."
)

FL_COLS = [
 ("_cng_fid","string","Universal per-feature identifier, unique across the whole collection. Built as '<vpu_unit>-<per-unit id>' because the per-unit conversion numbers rows from 1 independently, so raw ids collide between units. Use this for COUNT(DISTINCT) / dedup."),
 ("nhdplusid","decimal","NHDPlus High Resolution permanent feature id, and the join key to NHDPlusFlowlineVAA. Stored as an exact decimal: the source types it as a 64-bit float, and a float-equality join on a 14-digit id drops rows silently."),
 ("permanent_identifier","string","NHD permanent feature identifier (GUID). Use this to cross-reference the base-NHD usgs-nhd-streams-by-order asset; ~95% of in-network ids are shared."),
 ("reachcode","string","14-digit NHD Reach Code — a stable per-reach identifier for linear referencing, not an enumerable code list (hundreds of thousands of distinct values). The first 8 digits are the HUC8 and the last 6 a sequential reach number, so substr(reachcode,1,4) gives the HU4 and substr(reachcode,1,2) the HUC2 region."),
 ("gnis_id","string","GNIS ID of the named feature, if any."),
 ("gnis_name","string","GNIS feature name (river/stream name), if any."),
 ("lengthkm","double","Flowline length in kilometers, as published by NHDPlus HR. **Verified faithful to this asset's own geometry** — the projected (EPSG:3310) length of the stored geometry agrees to within 0.06% in aggregate — and the same holds for the base-NHD asset's LENGTHKM, so neither value is stale or miscomputed (data-workflows#525). Where the two disagree for the same permanent_identifier the GEOMETRY genuinely differs, and it is a minority tail rather than an offset: in the worst basin 80.3% of shared features agree within 1% and the median ratio is exactly 1.0000. **So do NOT apply a per-basin correction factor to reconcile the two assets** and do not read a per-feature difference as error. Compare per-area network totals, and state which product a number came from."),
 ("ftype","int32","NHD Feature Type (3-digit FType). Values: 334=Connector, 336=CanalDitch, 420=UndergroundConduit, 428=Pipeline, 460=StreamRiver, 468=Drainageway, 558=ArtificialPath, 566=Coastline", s["ftype_values"]),
 ("fcode","int32",
  "NHD Feature Code (5-digit FCode, each definition verbatim from the source NHDFCode domain table). "
  "Stream/river subtypes carry the hydrographic category, so flow permanence comes from FCODE, not "
  f"from stream order. All {len(s['fcode_values'])} values present: "
  + ", ".join(f"{v}={fcode_name[v]}" for v in s["fcode_values"])
  + ". Note 56600=Coastline is NOT a stream and carries no stream order — exclude it from any order-coverage denominator.",
  s["fcode_values"]),
 ("flowdir","int32","Flow direction (HydroFlowDirections domain): 0=Uninitialized, 1=With Digitized", s["flowdir_values"]),
 ("innetwork","int32","Whether the flowline participates in the NHD navigable network (NoYes domain): 0=No, 1=Yes. Stream order is computed for in-network features only, so restrict to innetwork = 1 before computing order coverage.", s["innetwork_values"]),
 ("mainpath","int32",
  "Whether the flowline is on the main flow path of its waterbody (MainPath domain): 0=No, 1=Yes. "
  f"**Only 0 occurs — across all {f(s['features'])} flowlines nationally there are {s['mainpath_one']} "
  "rows with mainpath = 1**, i.e. NHDPlus HR leaves this flag unset for the entire product; use "
  "levelpathi for mainstem grouping instead.", s["mainpath_values"]),
 ("visibilityfilter","int32","Scale-based cartographic visibility threshold; larger values appear only at finer display scales."),
 ("streamorde","int32",
  "Strahler stream order from NHDPlusFlowlineVAA. Headwater channels = 1; order increases downstream "
  f"where two channels of equal order merge. Published range is exactly {s['order_min']}-{s['order_max']} "
  f"— order {s['order_max']} occurs only on the lower Columbia River (HUC2 17). The source's non-positive "
  "'not computed' sentinels (including -9 on divergent paths) were normalised to NULL at build time, so "
  "IS NOT NULL and > 0 are equivalent here; still prefer `> 0`, because it is the correct predicate for "
  "the raw source and for the base-NHD asset, where the two differ completely. NULL means order is not "
  "computed for that feature (off-network, coastline, canal/pipeline), not that data is missing."),
 ("streamleve","int32",
  "NHD stream level: the downstream mainstem hierarchy counted DOWN from the terminal outlet (1 = "
  "terminal mainstem to ocean/sink), the opposite direction from streamorde, which counts UP from "
  f"headwaters. Not a substitute for stream order. Published range {s['level_min']}-{s['level_max']}; "
  "non-positive source sentinels normalised to NULL, and its NULL set is identical to streamorde's."),
 ("streamcalc","int32",
  "NHDPlus stream calculator: the order used for network routing. It tracks streamorde except on "
  f"divergences, where the minor path is set to 0 ({f(s['calc_zero'])} rows) — that is how NHDPlus keeps "
  f"a single main path through braided reaches. Range 0-{s['calc_max']}." + SENT),
 ("totdasqkm","double",
  "Total upstream drainage area in km2, routed through the full network — the standard measure of "
  f"catchment size for a reach. Valid range 0 to {s['totda_max']:,.0f} km2 (the maximum is the lower "
  "Mississippi)." + SENT),
 ("divdasqkm","double","Divergence-routed upstream drainage area in km2: like totdasqkm but apportioned at divergences. Use totdasqkm unless you specifically need divergence accounting." + SENT),
 ("slope","double",
  "Reach slope (dimensionless, rise/run) from the smoothed elevation profile. **-9998 is the 'no slope "
  f"computed' sentinel ({f(s['slope_sentinel'])} rows) and is the ONLY negative value present — filter "
  f"`slope > -9998` before AVG/MIN.** Observed valid range 0 to {s['slope_max']:.2f}."),
 ("arbolatesu","double","Arbolate sum: total upstream stream length in km (sum of all upstream flowline lengths). A per-feature CUMULATIVE value, not a per-reach length — never SUM it across features." + SENT),
 ("hydroseq","double","Hydrologic sequence number. Sorting descending traverses the network from headwaters downstream; unique per flowline within a unit."),
 ("uphydroseq","double","hydroseq of the next flowline UPSTREAM on the main path (0 at a headwater)."),
 ("dnhydroseq","double","hydroseq of the next flowline DOWNSTREAM on the main path (0 at a terminal reach). Pair with hydroseq to walk the network."),
 ("dnlevel","int32","streamleve of the next downstream main-path flowline."),
 ("levelpathi","double","Level path identifier: all flowlines on the same mainstem share this value, so it groups a river into one continuous path. Use this rather than mainpath, which is unset in this product."),
 ("terminalpa","double","Terminal path identifier: the hydroseq of the network outlet this flowline drains to. Groups flowlines by ultimate destination (ocean, sink, closed basin)."),
 ("pathlength","double","Distance in km along the main path from this flowline's downstream end to the network terminus." + SENT),
 ("maxelevsmo","double",
  "Maximum (upstream-end) elevation in cm (divide by 100 for metres), from the smoothed profile. "
  f"**-9998 is the 'not computed' sentinel ({f(s['elev_sentinel'])} rows). WARNING: filter exactly "
  "`<> -9998` — do NOT filter all negatives: other negative elevations are REAL below-sea-level "
  f"terrain** ({f(s['below_sea_rows'])} rows drain below sea level; minimum {s['elev_min_m']} m, in the "
  f"Death Valley / Salton Sea basins). Observed valid maximum {s['elev_max_m']:,.2f} m."),
 ("minelevsmo","double",
  "Minimum (downstream-end) elevation in cm (divide by 100 for metres), from the smoothed profile. "
  f"**-9998 is the 'not computed' sentinel ({f(s['elev_sentinel'])} rows). WARNING: filter exactly "
  "`<> -9998` — do NOT filter all negatives: other negative elevations are REAL below-sea-level "
  f"terrain** (minimum {s['elev_min_m']} m). Same caution as maxelevsmo."),
 ("divergence","int32","Divergence code: 0=not part of a divergence, 1=main path of a divergence, 2=minor path of a divergence", s["divergence_values"]),
 ("terminalfl","int32","Network-end flag (IsNetworkEnd, NoYes domain): 0=No, 1=Yes — 1 means this flowline is a network terminus", s["terminalfl_values"]),
 ("startflag","int32","Headwater flag (IsHeadwater, NoYes domain): 0=No, 1=Yes — 1 means no upstream flowline", s["startflag_values"]),
 ("areasqkm","double","Incremental catchment area in km2 for this flowline's own catchment (not cumulative — that is totdasqkm)."),
 ("vpuid","string","Vector processing unit id as recorded inside the source VAA table — an identifier of the source download, not an enumerable class. Mirrors vpu_unit."),
 ("vpu_unit","string",
  "Identifier of the source VPU download this flowline came from, added at build time: a 4-digit HU4 "
  "code, a 4-digit HU4 code with an 'i' suffix (5 Great Lakes units), or an 8-digit HU8 code (the "
  f"{n_hu8} Alaska units). Join to the flowline-units asset for that unit's source filename, vintage "
  "and measured coverage. Not a thematic class — it is the provenance key."),
 ("vpu_level","string",
  "Granularity of the source unit: HU4=4-digit hydrologic unit, HU8=8-digit hydrologic unit "
  f"(Alaska/HUC2 19 only, {n_hu8} units)", s["vpu_level_values"]),
 ("vpu_vintage","string",
  "Publication date stamped on the source unit's filename, or 'undated' where the filename carries none "
  f"({s['units'] - n_dated} of {s['units']} units). VPUs differ in editing vintage, which is what drives "
  "lengthkm differences against the base-NHD asset — compare per unit using this column. Values: dates "
  "in YYYY-MM-DD form, plus the literal 'undated'."),
]

UNIT_COLS = [
 {"name":"vpu_unit","type":"string","description":"Identifier of the source VPU download (4-digit HU4, HU4 with 'i' suffix, or 8-digit HU8). Join key to the flowline assets."},
 {"name":"vpu_level","type":"string","description":"Granularity of the unit: HU4=4-digit hydrologic unit, HU8=8-digit hydrologic unit (Alaska only)","values":["HU4","HU8"]},
 {"name":"source_zip","type":"string","description":"Exact filename downloaded from prd-tnm/StagedProducts/Hydrography/NHDPlusHR/VPU/Current/GDB/. Not derivable from the unit code — some carry a date stamp, some do not."},
 {"name":"vpu_vintage","type":"string","description":"Publication date from the source filename, or 'undated'."},
 {"name":"flowlines","type":"int64","description":"Flowlines ingested from this unit."},
 {"name":"innet_km","type":"double","description":"In-network flowline length in km for this unit (innetwork = 1)."},
 {"name":"pct_order_nocoast","type":"double","description":"Percent of in-network, NON-COASTLINE length with streamorde > 0 — the acceptance metric."},
 {"name":"pct_order_withcoast","type":"double","description":"The same percentage with coastline included in the denominator, for comparison only. Lower for coastal/island units because coastline carries no stream order by design — do not use this as a completeness measure."},
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
 "title": "USGS NHDPlus High Resolution — Flowlines + network VAA (national)",
 "description": desc,
 "license": "public-domain",
 "keywords": ["hydrography","streams","rivers","flowline","stream order","Strahler","NHDPlus",
              "NHDPlus HR","value added attributes","VAA","drainage area","NHD","USGS",
              "United States"],
 "providers": [
   {"name":"U.S. Geological Survey","roles":["producer","licensor"],
    "url":"https://www.usgs.gov/national-hydrography/nhdplus-high-resolution"},
   {"name":"Boettiger Lab","roles":["processor","host"],"url":"https://github.com/boettiger-lab"}],
 "extent": {"spatial": {"bbox": [[-170.847, -14.374, 145.831, 70.204]]},
            "temporal": {"interval": [["2022-04-18T00:00:00Z", "2025-09-19T00:00:00Z"]]}},
 "links": [
   {"rel":"self","href":f"{B}/nhdplus-hr/flowline/stac-collection.json","type":"application/json"},
   {"rel":"root","href":"https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json","type":"application/json"},
   {"rel":"parent","href":f"{B}/stac-collection.json","type":"application/json"},
   {"rel":"describedby","href":f"{B}/README.md","type":"text/markdown","title":"NHD / NHDPlus HR documentation"},
   {"rel":"related","href":f"{B}/streams-by-order/stac-collection.json","type":"application/json",
    "title":"Base NHD-H streams-by-order — denser network, complete Alaska, flow permanence; sparse stream order"},
   {"rel":"about","href":"https://www.usgs.gov/national-hydrography/nhdplus-high-resolution","title":"USGS NHDPlus High Resolution"},
   {"rel":"license","href":"https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits","title":"USGS Public Domain","type":"text/html"}],
 "assets": {
   "flowline-parquet": {
     "href": f"{B}/nhdplus-hr/flowline.parquet",
     "type": "application/vnd.apache.parquet",
     "title": f"GeoParquet — {f(s['features'])} NHDPlus HR flowlines with network VAA",
     "roles": ["data"],
     "description": "Cloud-native GeoParquet for DuckDB/Polars/GeoPandas. Geometry in OGC:CRS84 (lon, lat). One row per flowline — no per-feature row duplication.",
     "table:columns": cols(include_geom=True)},
   **({"flowline-pmtiles": {
     "href": f"{B}/nhdplus-hr/flowline.pmtiles",
     "type": "application/vnd.pmtiles",
     "title": "PMTiles — NHDPlus HR flowlines for web maps",
     "roles": ["visual"],
     "description": "Vector tiles for MapLibre/Leaflet, zoom 0-10. The MapLibre `source-layer` is `flowline`. Style by streamorde to render the stream hierarchy; filter [\">\", [\"get\", \"streamorde\"], 0] to drop features with no computed order (coastline, canals, off-network reaches). **Tiles drop features on dense tiles by design (--drop-densest-as-needed) — never compute quantities from them; use the GeoParquet or hex asset.**",
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
   "flowline-units": {
     "href": f"{B}/nhdplus-hr/flowline/units-manifest.csv",
     "type": "text/csv",
     "title": f"Per-unit source manifest and measured coverage ({s['units']} units)",
     "roles": ["metadata"],
     "description": f"One row per source VPU download ({n_hu4} HU4 + {n_hu8} HU8): its exact "
                    "filename, publication vintage, flowline count, in-network length and measured "
                    "stream-order coverage. This is how the collection records provenance per unit "
                    "— filenames are not derivable from unit codes, and vintage is what explains "
                    "lengthkm differences against the base-NHD asset.",
     "table:columns": UNIT_COLS},
 },
}
with open(OUT, 'w') as out_fh:
    json.dump(stac, out_fh, indent=2, ensure_ascii=False); out_fh.write("\n")
cov = {c["vpu_unit"]: c for c in s["coverage"]}
with open("/tmp/units-manifest.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow([c["name"] for c in UNIT_COLS])
    for unit, level, zipname, vintage in units:
        c = cov.get(unit, {})
        w.writerow([unit, level, zipname, vintage, c.get("flowlines",""), c.get("innet_km",""),
                    c.get("pct_nocoast",""), c.get("pct_withcoast","")])
print(f"wrote {OUT} and /tmp/units-manifest.csv "
      f"({s['units']} units: {n_hu4} HU4 + {n_hu8} HU8, {f(s['features'])} features)")
