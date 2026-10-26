import json, sys
sys.path.insert(0, '.')
from common import *
from seagrass import (B, BASE, BUCKET_SELF, ITEM_PAGE, SENTINEL_NOTE,
                      DATASETID, EVENTDATE, VERIF, build, PROVENANCE)

V = json.load(open('values.json'))
def vals(layer, col):
    return V[layer][col]
HABITAT_VALUES = vals('seagrass-polygons', 'habitat')
HABITAT_IDS = vals('seagrass-polygons', 'habitatID')


COMPOUND = (" Some records name more than one taxon, joined by a pipe, for example "
            "\"Valisneria | najas\". Upstream spelling is inconsistent — Haloragaceae also "
            "appears as Haloragidaceae, and Vallisneria is spelled Valisneria — so match on a "
            "prefix rather than on equality when grouping.")

def taxon(layer):
    poly = layer == "seagrass-polygons"
    fam = {"name": "FAMILY", "type": "string",
           "description": ("Taxonomic family of the aquatic plant recorded at this feature, or "
                           "Not Reported where the source identified none." +
                           (COMPOUND if poly else "")),
           "values": vals(layer, "FAMILY")}
    gen = {"name": "GENUS", "type": "string",
           "description": ("Taxonomic genus of the aquatic plant recorded at this feature, or "
                           "Not Reported where the source identified none." +
                           (COMPOUND if poly else "")),
           "values": vals(layer, "GENUS")}
    sci = {"name": "scientific", "type": "string",
           "description": "Scientific name of the aquatic plant recorded at this feature, as "
                          "given by the contributing source."}
    return [fam, gen, sci]

OGC_FID = {"name": "OGC_FID", "type": "int64",
           "description": "Feature identifier carried over from the source shapefile. It is not "
                          "guaranteed unique across the collection; use _cng_fid to identify a row."}

HABITAT = {
    "name": "habitat", "type": "string",
    "description": ("Habitat type recorded for the feature. Most features are simply \"Seagrass\"; "
                    "European records carry finer EUNIS-style descriptions such as \"Posidonia "
                    "beds\". Upstream stores this in a 50-character field, so the longest labels "
                    "are cut off mid-word and a few differ only in spacing or a trailing plural "
                    "(\"Z. marina\" against \"Z.marina\", \"sediment\" against \"sediments\"). "
                    "Match on a prefix rather than on equality when grouping these."),
    "values": HABITAT_VALUES}
HABITATID = {
    "name": "habitatID", "type": "string",
    "description": (
        "Habitat classification code for the feature, where a European scheme applies: an EUNIS "
        "code, or a JNCC marine habitat code. Most of the world carries no classification. The "
        "definitions below are the habitat labels these codes actually carry in this dataset. "
        "Values: "
        "EUNIS:A5.535=Posidonia beds, "
        "EUNIS:A5.533=Zostera beds in full salinity infralittoral sediments, "
        "EUNIS:A5.53131=Association with Cymodocea nodosa on well sorted fine sand, "
        "EUNIS:A5.5331=Zostera marina beds on lower shore or infralittoral sand, "
        "EUNIS:A5.53=Sublittoral seagrass beds, "
        "EUNIS:A5.5343=Ruppia maritima in reduced salinity infralittoral sediments, "
        "EUNIS:A2.61=Seagrass beds on littoral sediments, "
        "EUNIS:A5.534=Ruppia and Zannichellia communities, "
        "EUNIS:A5.531=Cymodocea beds, "
        "EUNIS:A5.5333=recorded only as Seagrass in this dataset, "
        "JNCC:SS.SMp.SSgr=recorded only as Seagrass in this dataset, "
        "Not reported=no habitat classification was applied by the contributing source."),
    "values": HABITAT_IDS}
BIO_CLASS = {"name": "BIO_CLASS", "type": "string",
             "description": "Biological or community description of the bed as given by the "
                            "contributing source. Free text, with hundreds of distinct values."}
FIELDNOTES = {"name": "fieldNotes", "type": "string",
              "description": "Free-text notes recorded by the contributing source about the "
                             "survey or the feature."}
VERNACULAR = {"name": "vernacular", "type": "string",
              "description": "Common name of the seagrass recorded at this feature, where the "
                             "contributing source gave one, or \"Not reported\" where it did not.",
              "values": vals('seagrass-polygons', 'vernacular')}
NAMEACCORD = {"name": "nameAccord", "type": "string",
              "description": "Taxonomic authority the scientific name follows, as cited by the "
                             "contributing source."}
VERIF_POLY = {"name": "verif", "type": "string",
              "description": "Verification note recorded by the contributing source, describing "
                             "who checked the record or how it was confirmed. Free text."}
AREA = {"name": "AREA_SQKM", "type": "double",
        "description": "Area of this polygon in square kilometres, as calculated by UNEP-WCMC. "
                       "The value is specific to the individual polygon, so summing it across "
                       "rows of the GeoParquet gives a genuine total area."}
SHAPE_LENG = {"name": "Shape_Leng", "type": "double",
              "description": "Perimeter of the polygon in decimal degrees, carried over from the "
                             "source shapefile. Degrees are not a unit of length on the ground, "
                             "so use a geodesic calculation for real distances."}
SHAPE_AREA = {"name": "Shape_Area", "type": "double",
              "description": "Area of the polygon in square decimal degrees, carried over from the "
                             "source shapefile. Square degrees vary with latitude, so use "
                             "AREA_SQKM for real areas."}
REP_AREA_PT = {"name": "REP_AREA_K", "type": "double",
               "description": "Area in square kilometres reported by the original provider. Zero "
                              "for every row of this layer, because a point has no mapped extent."}

poly_cols = [OGC_FID, DATASETID, BIO_CLASS, FIELDNOTES, HABITAT, AREA, VERNACULAR] + \
            taxon('seagrass-polygons') + \
            [HABITATID, NAMEACCORD, EVENTDATE, VERIF_POLY, SHAPE_LENG, SHAPE_AREA]
pt_cols = [OGC_FID, DATASETID] + taxon('seagrass-points') + [VERIF, REP_AREA_PT, EVENTDATE]

poly_desc = (
    "Global distribution of seagrasses: the polygon component of the UNEP-WCMC global seagrass "
    "dataset, and the standard global baseline for mapped seagrass extent.\n\n"
    "293,147 polygons compiled by UNEP-WCMC with Frederick T. Short from 146 contributing surveys, "
    "spanning every ocean basin from about 44S to 70N. Because it is a compilation, mapping effort "
    "varies enormously between regions: individual polygons range from a fraction of a hectare to "
    "32,539 km2, and survey dates recorded in the data run from 1897 to 2018. Mapped polygon area "
    "totals 667,004 km2. Treat it as a record of where seagrass has been mapped, not as an "
    "even-effort global census.\n\n"
    "The layer is not restricted to marine seagrass: alongside Zostera, Posidonia and "
    "Halophila it includes freshwater and brackish aquatic plants such as Myriophyllum, "
    "Najas, Vallisneria and Trapa. Filter on FAMILY or GENUS if you need marine seagrass "
    "only.\n\nEvery geometry is valid and non-empty.\n\n" + SENTINEL_NOTE + PROVENANCE)

pt_desc = (
    "Point records of seagrass occurrence: the point component of the UNEP-WCMC global seagrass "
    "dataset, for sites recorded as locations rather than as mapped beds.\n\n"
    "17,668 points from 444 contributing datasets, spanning about 47S to 70N, with survey dates "
    "recorded in the data running from 1847 to 2014. Six seagrass families are represented, "
    "Zosteraceae most often. Use this layer together with the companion polygon collection, "
    "unep-wcmc-seagrass-polygons, which carries the mapped extent; a point records presence at a "
    "location and says nothing about the size of the bed.\n\n"
    "REP_AREA_K is zero for every row, because a point has no mapped extent.\n\n"
    + SENTINEL_NOTE + PROVENANCE)

poly_hex = (
    "One row per (polygon, H3 cell) pair at resolution 8, so a seagrass bed spanning several cells "
    "appears on each of them. Feature counts come from COUNT(DISTINCT _cng_fid). Every attribute "
    "column here describes the whole polygon and is repeated on each cell it covers, so AREA_SQKM "
    "in particular must be de-duplicated before summing:\n\n"
    "```sql\n"
    "-- correct: one row per polygon before summing its area\n"
    "SELECT SUM(a) FROM (SELECT DISTINCT _cng_fid, AREA_SQKM AS a FROM read_parquet(...));\n"
    "-- wrong: SUM(AREA_SQKM) on hex multiplies each polygon by the number of cells it covers\n"
    "```\n\n"
    "For seagrass area from the hex footprint itself, derive it from the H3 cells rather than from "
    "an attribute column.")

pt_hex = (
    "One row per (point, H3 cell) pair at resolution 8. Each point falls in exactly one cell, so "
    "there is one row per point; several points in the same cell are kept as separate rows and are "
    "not merged. Point counts come from COUNT(DISTINCT _cng_fid). Attribute columns describe the "
    "point record itself.")

poly = build("polygons", "Global Distribution of Seagrasses (UNEP-WCMC WCMC-014 v7.1)", poly_desc,
             [-175.427879, -43.550934, 178.616848, 70.494279],
             ["1897-01-01T00:00:00Z", "2018-12-31T23:59:59Z"], poly_cols, None, poly_hex,
             "One row per mapped seagrass polygon, with geometry, for SQL analysis in DuckDB or "
             "Polars. 293,147 polygons. AREA_SQKM is specific to each polygon, so summing it here "
             "gives a genuine total area — 667,004 km2 across the layer.")

pt = build("points", "Seagrass Point Records (UNEP-WCMC WCMC-013 v7.1)", pt_desc,
           [-176.640264, -46.916683, 178.533346, 69.999984],
           ["1847-01-01T00:00:00Z", "2014-12-31T23:59:59Z"], pt_cols, None, pt_hex,
           "One row per seagrass point record, with geometry, for SQL analysis in DuckDB or "
           "Polars. 17,668 point records.")

bucket = {
    "type": "Collection", "stac_version": "1.0.0",
    "id": "seagrass", "title": "Seagrass Datasets",
    "description": (
        "Global maps of seagrass occurrence and mapped extent.\n\n"
        "Holdings come from the UNEP-WCMC Global Distribution of Seagrasses (WCMC-013 points and "
        "WCMC-014 polygons), the standard global baseline for seagrass extent. Each collection "
        "records its own licence; the UNEP-WCMC datasets are distributed under the UNEP-WCMC "
        "General Data License (excluding WDPA), which prohibits commercial use and redistribution."),
    "license": "other",
    "extent": {"spatial": {"bbox": [[-176.640264, -46.916683, 178.616848, 70.494279]]},
               "temporal": {"interval": [["1847-01-01T00:00:00Z", "2018-12-31T23:59:59Z"]]}},
    "links": nav_links(BUCKET_SELF, ROOT) + [
        LICENSE_LINK,
        {"rel": "child", "href": f"{BASE}/unep-wcmc-seagrass/polygons/stac-collection.json",
         "type": "application/json", "title": poly["title"]},
        {"rel": "child", "href": f"{BASE}/unep-wcmc-seagrass/points/stac-collection.json",
         "type": "application/json", "title": pt["title"]},
    ],
}

for fn, obj in {
    "public-seagrass__stac-collection.json": bucket,
    "public-seagrass__unep-wcmc-seagrass__polygons__stac-collection.json": poly,
    "public-seagrass__unep-wcmc-seagrass__points__stac-collection.json": pt,
}.items():
    json.dump(obj, open(fn, "w"), indent=2, ensure_ascii=False)
    print("wrote", fn)
