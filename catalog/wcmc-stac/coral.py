import json, sys
sys.path.insert(0, '.')
from common import *
V = json.load(open('values.json'))
def vals(layer, col):
    return V[layer][col]


B = "public-coral-reefs"
BASE = f"{S3}/{B}"
BUCKET_SELF = f"{BASE}/stac-collection.json"

SENTINEL = ('Unsurveyed or unreported attributes carry the literal string "Not Reported" rather '
            'than a null. Filter it out before counting or summarising a column, for example '
            "WHERE DATA_TYPE <> 'Not Reported'.")

# ---- shared source-compilation columns (identical text on every asset, per #303) ----
def coral_columns(is_point):
    LK = 'coral-points' if is_point else 'coral-polygons'
    if is_point:
        LAYER_NAME_COL = {
            "name": "LAYER_NAME", "type": "string",
            "description": ("Short name of the study that contributed this record. Values: "
                            "\"Monsalvo et al 2018\" = a compiled inventory of reef sites, "
                            "\"Gonzalez-Barrios and Alvarez-Filip 2018\" = a photographic reef "
                            "survey."),
            "values": vals(LK, "LAYER_NAME")}
    else:
        LAYER_NAME_COL = {
            "name": "LAYER_NAME", "type": "string",
            "description": ("Short name of the contributing source this feature came from. "
                            "Values: CRR = the main UNEP-WCMC coral reef compilation, which "
                            "supplies 17,486 of the 17,504 features and itself draws on 79 "
                            "separately documented sources identified by METADATA_I (the archive "
                            "does not expand the abbreviation); "
                            "\"Ortiz-Lozano et al 2018\" = a contributed study of Mexican reefs "
                            "supplying the remaining 18 features."),
            "values": vals(LK, "LAYER_NAME")}
    if is_point:
        SURVEY_MET_COL = {
            "name": "SURVEY_MET", "type": "string",
            "description": "Survey instrument or technique used by the contributing source. "
                           "Values: Photography = mapped from photographic survey, "
                           "\"Literature review; Expert interview; Data validation\" = compiled "
                           "from published sources and expert consultation rather than direct "
                           "survey.",
            "values": vals(LK, "SURVEY_MET")}
        LOC_DEF_COL = {
            "name": "LOC_DEF", "type": "string",
            "description": "Substrate the source recorded at the site. Values: Coral = coral reef, "
                           "Rocky-Coral = mixed rocky and coral substrate, Rocky = rocky reef "
                           "without coral, \"Rocky with Macrocystis pyrifera\" = rocky reef with "
                           "giant kelp, Not Reported = the source did not record a substrate.",
            "values": vals(LK, "LOC_DEF")}
    else:
        SURVEY_MET_COL = {
            "name": "SURVEY_MET", "type": "string",
            "description": "Survey instrument or technique used by the contributing source. "
                           "Values: IKONOS = mapped from IKONOS satellite imagery, "
                           "\"British Admiralty Chart\" = digitised from a nautical chart, "
                           "\"Echo sounder\" = acoustic depth sounding, "
                           "\"Assessment of LADS features based on geomorpholog*\" = interpreted "
                           "from Laser Airborne Depth Sounder returns, stored with a trailing "
                           "asterisk because upstream cut the label to fit a 50-character field, "
                           "Not Reported = the source did not record a technique.",
            "values": vals(LK, "SURVEY_MET")}
        LOC_DEF_COL = {
            "name": "LOC_DEF", "type": "string",
            "description": "Free-text note from the source on how the feature's location or "
                           "substrate was defined. This layer carries thousands of distinct "
                           "free-text values rather than a fixed code list."}
    cols = [
        dict(LAYER_NAME_COL),
        {"name": "OGC_FID", "type": "int64",
         "description": "Feature identifier carried over from the source shapefile. It is not "
                        "guaranteed unique across the collection; use _cng_fid to identify a row."},
        {"name": "METADATA_I", "type": "double",
         "description": "Identifier of the source metadata record describing the contributing "
                        "dataset, its methods and its citation. It matches SOURCE_ID in "
                        "Metadata_CoralReefs.dbf inside the source archive, which holds 81 such "
                        "records with full titles, publishers, citations and nominal mapping "
                        "scales."},
        {"name": "ORIG_NAME", "type": "string",
         "description": "Name of the reef or site as given by the original data provider."},
        {"name": "NAME", "type": "string",
         "description": "Standardised name of the reef or site."},
        {"name": "FAMILY", "type": "string",
         "description": "Taxonomic family of the mapped organism where the source recorded one. "
                        "Every feature in this collection carries \"Not Reported\"."},
        {"name": "GENUS", "type": "string",
         "description": "Taxonomic genus of the mapped organism where the source recorded one."},
        {"name": "SPECIES", "type": "string",
         "description": "Taxonomic species of the mapped organism where the source recorded one."},
        {"name": "DATA_TYPE", "type": "string",
         "description": "How the feature was observed. Values: Remotely sensed = mapped from "
                        "satellite or aerial imagery, Field survey = mapped from in-water or "
                        "vessel-based survey, Field survey, not groundtruthed = surveyed but not "
                        "independently confirmed, Remotely sensed; field survey = both methods "
                        "combined, Not Reported = the source did not record a method.",
         "values": vals(LK, "DATA_TYPE")},
        dict(SURVEY_MET_COL),
        {"name": "START_DATE", "type": "string",
         "description": "Start of the survey period for the feature, as recorded by the source. "
                        "Formats vary between sources and the value may be \"Not Reported\"."},
        {"name": "END_DATE", "type": "string",
         "description": "End of the survey period for the feature, as recorded by the source. "
                        "Formats vary between sources and the value may be \"Not Reported\"."},
        {"name": "DATE_TYPE", "type": "string",
         "description": "Precision of the survey dates. Values: DD = exact day known, YY = year "
                        "known for both start and end, Y = a single year known, -Y = only the end "
                        "year known, OO = other, ND = no date recorded.",
         "values": vals(LK, "DATE_TYPE")},
        {"name": "VERIF", "type": "string",
         "description": "Whether the feature was checked by a subject expert. Values: "
                        "Expert Verified = reviewed by an expert, Not Reported = no review "
                        "recorded.",
         "values": vals(LK, "VERIF")},
        dict(LOC_DEF_COL),
        {"name": "GIS_AREA_K", "type": "double",
         "description": "Area in square kilometres of the source record this feature belongs to, "
                        "as calculated by UNEP-WCMC. This is a property of the source record, not "
                        "of the individual polygon, so the same value appears on every feature "
                        "sharing that record."},
        {"name": "REP_AREA_K", "type": "string",
         "description": "Area in square kilometres as reported by the original data provider, or "
                        "\"Not Reported\" where none was given. Stored as text because of that "
                        "sentinel."},
    ]
    if not is_point:
        cols += [
            {"name": "Shape_Leng", "type": "double",
             "description": "Perimeter of the polygon in decimal degrees, as carried over from the "
                            "source shapefile. Degrees are not a unit of length on the ground, so "
                            "use a geodesic calculation for real distances."},
            {"name": "Shape_Area", "type": "double",
             "description": "Area of the polygon in square decimal degrees, as carried over from "
                            "the source shapefile. Square degrees vary with latitude, so use "
                            "GIS_AREA_K or a geodesic calculation for real areas."},
        ]
    return cols

AREA_WARNING = (
    "GIS_AREA_K describes the source record a feature belongs to, not the individual feature, so "
    "it repeats across every feature sharing that record. Summing it directly counts the same "
    "area many times over — across this layer a raw sum returns 899,466 km2 against a "
    "deduplicated 151,288 km2, and the deduplicated figure is the one consistent with the reef "
    "area UNEP-WCMC publishes for this dataset.\n\n"
    "```sql\n"
    "-- correct: collapse to one row per source record before summing\n"
    "SELECT SUM(a) FROM (SELECT DISTINCT NAME, METADATA_I, GIS_AREA_K AS a FROM read_parquet(...));\n"
    "-- wrong: SUM(GIS_AREA_K) over every row multiplies each record by its feature count\n"
    "```"
)

HEX_NOTE = (
    "One row per (feature, H3 cell) pair at resolution 8, so a reef spanning several cells appears "
    "on each of them. Feature counts come from COUNT(DISTINCT _cng_fid). Every attribute column "
    "here describes the whole feature and is repeated on every cell that feature covers, so "
    "de-duplicate on _cng_fid before summarising one — GIS_AREA_K additionally repeats across "
    "features, as described on the GeoParquet asset. For reef area from the hex footprint, derive "
    "it from the H3 cells themselves rather than from an attribute column."
)

def collection(name, title, desc, bbox, temporal, n_feat, is_point, assets_extra_desc):
    ds = f"unep-wcmc-coral-reefs/{name}"
    self_href = f"{BASE}/{ds}/stac-collection.json"
    cols = coral_columns(is_point)
    flat_cols = cols + [FID, GEOM]
    hex_cols = cols + [FID] + h3_columns()
    a = {}
    a[f"{name}-parquet"] = {
        "href": f"{BASE}/{ds}.parquet",
        "type": "application/x-parquet",
        "roles": ["data"],
        "title": f"{title} — GeoParquet",
        "description": ("One row per source feature, with geometry, for SQL analysis in DuckDB or "
                        "Polars. " + assets_extra_desc + " " + AREA_WARNING),
        "table:columns": flat_cols,
    }
    a[f"{name}-pmtiles"] = {
        "href": f"{BASE}/{ds}.pmtiles",
        "type": "application/vnd.pmtiles",
        "roles": ["visual"],
        "title": f"{title} — PMTiles",
        "description": f"Vector tiles for web mapping. The MapLibre source-layer is \"{name}\".",
        "vector:layers": [name],
        "table:columns": lean(cols + [FID]),
    }
    a[f"{name}-hex"] = {
        "href": f"{BASE}/{ds}/hex/h0=*/data_0.parquet",
        "type": "application/x-parquet",
        "roles": ["data"],
        "title": f"{title} — H3 hex parquet (resolution 8)",
        "description": HEX_NOTE,
        "h3:native_resolution": 8,
        "h3:parent_resolutions": [0],
        "table:columns": hex_cols,
    }
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": EXTENSIONS,
        "id": f"unep-wcmc-coral-reefs-{name}",
        "title": title,
        "description": desc,
        "license": "other",
        "version": "4.1",
        "sci:citation": (
            "UNEP-WCMC, WorldFish Centre, WRI, TNC (2010). Global distribution of warm-water coral "
            "reefs, compiled from multiple sources including the Millennium Coral Reef Mapping "
            "Project. Version 4.0. Includes contributions from IMaRS-USF and IRD (2005), IMaRS-USF "
            "(2005) and Spalding et al. (2001). Cambridge (UK): UNEP World Conservation Monitoring "
            f"Centre. Accessed {ACCESS_DATE}."),
        "providers": PROVIDERS_CORAL,
        "extent": {"spatial": {"bbox": [bbox]},
                   "temporal": {"interval": [temporal]}},
        "links": nav_links(self_href, BUCKET_SELF) + [
            LICENSE_LINK,
            {"rel": "about",
             "href": "https://data-gis.unep-wcmc.org/portal/home/item.html?id=0613604367334836863f5c0c10e452bf",
             "type": "text/html", "title": "UNEP-WCMC Global Distribution of Coral Reefs — dataset page"},
            {"rel": "cite-as", "href": "https://doi.org/10.34892/t2wk-5t34"},
        ],
        "assets": a,
    }

PROVENANCE = (
    "\n\n**Provenance.** Downloaded from the UNEP-WCMC ArcGIS portal on " + ACCESS_DATE + " via the "
    "publisher's `https://wcmc.io/WCMC_008` link. The source archive is kept at "
    "`s3://public-coral-reefs/raw/WCMC008_CoralReefs2018_v4_1.zip` (220,904,276 bytes, sha256 "
    "`09c7fe54c85b365c3968b8945034ebc649389c2832b0ab4b91dd2e50ee3a7124`). Upstream labels this "
    "release inconsistently — the bundled README says version 4.1 released March 2021 while the "
    "requested citation says version 4.0 — so the edition recorded here is the one in the "
    "distributed filename, v4.1.\n\n" + LICENCE_NOTE)

poly_desc = (
    "Global distribution of warm-water coral reefs, the most comprehensive global baseline map of "
    "shallow tropical and subtropical reefs. UNEP-WCMC compiled it with the WorldFish Centre, the "
    "World Resources Institute and The Nature Conservancy from many contributing surveys, notably "
    "the Millennium Coral Reef Mapping Project and the World Atlas of Coral Reefs.\n\n"
    "17,504 reef polygons covering every ocean basin between roughly 34S and 33N. Because it is a "
    "compilation, mapping method, survey date and precision vary from feature to feature: the "
    "DATA_TYPE, SURVEY_MET and DATE_TYPE columns record what each contributing source reported, "
    "and surveys span 1968 to 2018. Mapping scale varies by orders of magnitude between sources, "
    "including some as fine as 1:6,000 and others as coarse as 1:15,000,000, so this is a record of "
    "where reefs have been mapped rather than an even-effort global census. Deduplicated reef area "
    "totals 151,288 km2 — see the "
    "GeoParquet asset for how to compute it correctly.\n\n" + SENTINEL + PROVENANCE)

pt_desc = (
    "Point records of coral and rocky-coral reef sites that accompany the UNEP-WCMC global "
    "warm-water coral reef dataset, for sites mapped as locations rather than as polygons.\n\n"
    "**This layer is regional, not global.** Its 925 points come from two contributed studies — "
    "Monsalvo et al. (2018) and Gonzalez-Barrios and Alvarez-Filip (2018) — and fall only in the "
    "wider Caribbean, the Gulf of Mexico and the eastern tropical Pacific, between about 118W and "
    "84W. The companion polygon collection, unep-wcmc-coral-reefs-polygons, is the global layer; "
    "use it for any global or basin-scale reef extent question. Surveys here date from 2015 to "
    "2018.\n\n"
    "Both area columns are zero throughout, because a point has no mapped extent.\n\n"
    + SENTINEL + PROVENANCE)

poly = collection(
    "polygons", "Global Distribution of Coral Reefs (UNEP-WCMC WCMC-008 v4.1)", poly_desc,
    [-179.999935, -34.298230, 179.999936, 32.514818],
    ["1968-01-01T00:00:00Z", "2018-12-31T23:59:59Z"], 17504, False,
    "17,504 reef polygons; every geometry is valid and non-empty.")

pt = collection(
    "points", "Coral Reef Point Records, wider Caribbean and eastern tropical Pacific (UNEP-WCMC WCMC-008 v4.1)",
    pt_desc,
    [-118.290176, 14.708445, -83.886970, 32.442383],
    ["2015-01-01T00:00:00Z", "2018-09-01T23:59:59Z"], 925, True,
    "925 point records.")

pt["assets"]["points-hex"]["description"] = (
    "One row per (point, H3 cell) pair at resolution 8. Each point falls in exactly one cell, so "
    "there is one row per point; several points in the same cell are kept as separate rows and are "
    "not merged. Point counts come from COUNT(DISTINCT _cng_fid). Attribute columns describe the "
    "point record itself.")
pt["assets"]["points-parquet"]["description"] = (
    "One row per point record, with geometry, for SQL analysis in DuckDB or Polars. 925 point "
    "records. GIS_AREA_K and REP_AREA_K are zero for every row, because a point has no mapped "
    "extent.")

bucket = {
    "type": "Collection",
    "stac_version": "1.0.0",
    "id": "coral-reefs",
    "title": "Coral Reef Datasets",
    "description": (
        "Global and regional maps of warm-water coral reef extent.\n\n"
        "Holdings come from the UNEP-WCMC Global Distribution of Coral Reefs (WCMC-008), the "
        "standard global baseline for shallow tropical reef extent. Each collection records its "
        "own licence; the UNEP-WCMC datasets are distributed under the UNEP-WCMC General Data "
        "License (excluding WDPA), which prohibits commercial use and redistribution."),
    "license": "other",
    "extent": {"spatial": {"bbox": [[-179.999935, -34.298230, 179.999936, 32.514818]]},
               "temporal": {"interval": [["1968-01-01T00:00:00Z", "2018-12-31T23:59:59Z"]]}},
    "links": nav_links(BUCKET_SELF, ROOT) + [
        LICENSE_LINK,
        {"rel": "child", "href": f"{BASE}/unep-wcmc-coral-reefs/polygons/stac-collection.json",
         "type": "application/json", "title": poly["title"]},
        {"rel": "child", "href": f"{BASE}/unep-wcmc-coral-reefs/points/stac-collection.json",
         "type": "application/json", "title": pt["title"]},
    ],
}

out = {
    "public-coral-reefs__stac-collection.json": bucket,
    "public-coral-reefs__unep-wcmc-coral-reefs__polygons__stac-collection.json": poly,
    "public-coral-reefs__unep-wcmc-coral-reefs__points__stac-collection.json": pt,
}
for fn, obj in out.items():
    with open(fn, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    print("wrote", fn)
