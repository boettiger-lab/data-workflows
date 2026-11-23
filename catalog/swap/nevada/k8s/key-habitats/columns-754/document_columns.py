#!/usr/bin/env python3
"""Document the six upstream columns of nevada-swap-2022-key-habitats, in place (#754).

    document_columns.py COLLECTION.json

FID, Id, gridcode, FCode, Shape_Leng and Shape_Area are in the GeoParquet and hex data but
were declared only on the PMTiles asset, with no description. NDOW's FeatureServer
(keyhab_merge/FeatureServer/0) gives them no alias or description; the texts below come from
the data (all 17 rows read on 2026-11-20):
  FID = Id = OGC_FID = 1..17; gridcode = 1..15, one per class, on the other 15 classes, 0 on
  Perennial Rivers and Streams and Springs; FCode = 46006 on Perennial Rivers and Streams,
  0 elsewhere; Shape_Area / (Area_in_Acres x 4046.86 m2) = 0.995-1.19 and
  Shape__Area / Shape_Area = 1.55-1.75, so Shape_Area is planar m2 in a projected CRS.

Adds the columns to the parquet and hex assets, describes them in the collection
dictionary, and gives the hex asset its per-feature duplication note. Idempotent.
"""
import json
import sys

GRIDCODE = {
    0: "no class code (Perennial Rivers and Streams, Springs)",
    1: "Alpine and Tundra", 2: "Lakes and Reservoirs", 3: "Sparsely Vegetated Habitats",
    4: "Mojave Warm Desert", 5: "Mojave Mid-Elevation Mixed Desert Shrub",
    6: "Pinyon-Juniper Woodland", 7: "Upper Montane Coniferous Forest and Woodland",
    8: "Aspen Woodland", 9: "Montane Shrublands", 10: "Low Elevation Sagebrush Dominated Shrubland",
    11: "Lower Montane Woodlands and Chaparral",
    12: "High Elevation Sagebrush Dominated Shrublands", 13: "Desert Grasslands",
    14: "Riparian and Wetland", 15: "Salt Desert Shrub",
}
DICT = {
    "FID": ("int32", "Upstream feature id (1 to 17). Equal to OGC_FID on every feature."),
    "Id": ("int32", "Upstream shapefile Id field. Equal to FID on every feature; it carries no "
           "information of its own."),
    "gridcode": ("int32", "Upstream class code, the field ArcGIS writes when it converts a raster "
                 "to polygons. Use KEYHABCLAS for the class name. Values: "
                 + ", ".join(f"{k}={v}" for k, v in GRIDCODE.items()), list(GRIDCODE)),
    "FCode": ("int32", "National Hydrography Dataset feature code. Values: 46006=Stream/River, "
              "perennial (on Perennial Rivers and Streams), 0=not an NHD feature (every other "
              "class)", [0, 46006]),
    "Shape_Leng": ("double", "Feature perimeter in metres, measured in the projected coordinate "
                   "system of NDOW's original shapefile. Per-feature total."),
    "Shape_Area": ("double", "Feature area in square metres, measured in the projected coordinate "
                   "system of NDOW's original shapefile. Per-feature total. It differs from "
                   "Area_in_Acres and from Shape__Area (Web Mercator), which are measured "
                   "other ways."),
}
# column order in the parquet
ORDER = ["_cng_fid", "OGC_FID", "FID", "Id", "gridcode", "KEYHABCLAS", "FCode", "StateProvi",
         "Shape_Leng", "Shape_Area", "Shape__Area", "Shape__Length", "Area_in_Acres"]
HEX_NOTE = (
    "One row per (habitat class, H3 res-8 cell). The per-feature totals Area_in_Acres, "
    "Shape_Area, Shape__Area, Shape_Leng and Shape__Length are repeated on every cell a class "
    "covers, so never SUM them on hex; dedup by _cng_fid first (SELECT DISTINCT _cng_fid, "
    "Area_in_Acres)."
)

path = sys.argv[1]
doc = json.load(open(path))
if doc.get("id") != "nevada-swap-2022-key-habitats":
    sys.exit(f"{path}: unexpected collection {doc.get('id')!r}")
before = json.dumps(doc, sort_keys=True)


def place(cols, name, typ):
    names = [c["name"] for c in cols]
    if name in names:
        cols[names.index(name)]["type"] = typ
        return
    # insert after the nearest preceding column in parquet order that is present
    i = ORDER.index(name)
    prev = [n for n in ORDER[:i] if n in names]
    at = names.index(prev[-1]) + 1 if prev else 0
    cols.insert(at, {"name": name, "type": typ})


for key in ("key-habitats-parquet", "key-habitats-hex"):
    cols = doc["assets"][key]["table:columns"]
    for name, (typ, *_) in DICT.items():
        place(cols, name, typ)

dict_cols = {c["name"]: c for c in doc["table:columns"]}
for name, (typ, desc, *values) in DICT.items():
    c = dict_cols.get(name)
    if c is None:
        c = {"name": name}
        doc["table:columns"].append(c)
    c["type"] = typ
    c["description"] = desc
    if values:
        c["values"] = values[0]

doc["assets"]["key-habitats-hex"]["description"] = HEX_NOTE

json.dump(doc, open(path, "w"), indent=2, ensure_ascii=False)
print(f"{doc['id']}: {'changed' if json.dumps(doc, sort_keys=True) != before else 'unchanged'}")
