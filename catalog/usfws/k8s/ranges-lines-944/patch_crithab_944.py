#!/usr/bin/env python3
"""Patch a LIVE critical-habitat collection after its rebuild from the bulk zip (#944), in place.

    patch_crithab_944.py {final|proposed} COLLECTION.json

The May build read FWS's ArcGIS service; #944 rebuilt both layers from the bulk download
crithab_all_layers.zip (2026-08-31). This rewrites what the rebuild changed and nothing else:
  * description: counts, source and provenance, and the text a swapped generator argument had put
    where "Final"/"Proposed" belonged ("((-179.1, ...) designations only)", #911);
  * asset titles that carried the same bounding box;
  * the column dictionary and per-asset column lists, to the rebuilt schema: the service-only
    OGC_FID, OBJECTID, GlobalID, SHAPE_Leng and SHAPE_Area are gone, objectid_1 is OBJECTID_1, the
    geometry column is `geometry`, and `geometry_bbox` is new;
  * the hex note on per-feature columns, which named SHAPE_Area and SHAPE_Leng;
  * the vipcode description: its letter is the taxonomic group (V/I/P), not a verification code,
    measured against FAMILY on the species-ranges table (P: Asteraceae, I: Unionidae, V: Cyprinidae).
Every number is measured on the rebuilt files (duckdb-geo, 2026-11-17).
"""
import json
import sys

FACTS = {
    "final": {"n": 803, "hex": 1294437, "status": "Final",
              "breakdown": "Endangered 633, Threatened 170",
              "legal": "Final designations are legally in effect under the Endangered Species Act."},
    "proposed": {"n": 70, "hex": 43991, "status": "Proposed",
                 "breakdown": "Endangered 27, Proposed Endangered 18, Threatened 17, Proposed Threatened 8",
                 "legal": "Proposed designations are in rulemaking and have no legal effect until made final."},
}
ZIP = ("https://ecos.fws.gov/docs/crithab/crithab_all/crithab_all_layers.zip (Last-Modified "
       "2026-08-31, accessed 2026-11-17), staged at s3://public-usfws/raw/crithab_all_layers.zip "
       "(265,506,180 bytes, sha256 6578fe59f54cf4249a9c5e1bde500b7066b81dbcf8693b43df5a477baa35f08d)")
DROP = {"OGC_FID", "OBJECTID", "GlobalID", "SHAPE_Leng", "SHAPE_Area"}
RENAME = {"objectid_1": "OBJECTID_1", "geom": "geometry"}
ATTRS = ["_cng_fid", "singlmulti", "comname", "sciname", "spcode", "vipcode", "entity_id", "unit",
         "subunit", "unitname", "subunitnam", "status", "leadoffice", "coopoffice", "coopofmore",
         "fedreg", "pubdate", "effectdate", "vacatedate", "accuracy", "source_id", "OBJECTID_1",
         "listing_st"]

kind, path = sys.argv[1], sys.argv[2]
f = FACTS[kind]
doc = json.load(open(path))
label = f"Critical Habitat — {f['status']} (USFWS)"

doc["description"] = (
    f"Critical habitat designated by the U.S. Fish and Wildlife Service for species listed under the "
    f"Endangered Species Act: {f['status'].lower()} designations, polygon features. {f['n']} polygons, "
    f"one per species entity, by ESA listing status: {f['breakdown']}. {f['legal']}\n\n"
    "Scope: these are the USFWS polygon designations. FWS also designates critical habitat as lines "
    "(mostly streams), which FWS does not currently publish (data-workflows#944), and critical habitat "
    "for species under NOAA Fisheries jurisdiction is published separately by NOAA. Every feature "
    "carries the accuracy note 'Please check current species specific shapefile': this aggregated "
    "layer is for screening, and the Federal Register rule governs the legal boundary of any "
    "designation.\n\n"
    f"Provenance: FWS bulk download {ZIP}. Rebuilt from that file on 2026-11-17; the earlier build "
    "(May 2026) came from the FWS ArcGIS service and held fewer designations (728 final, 49 proposed).")

for key, a in doc.get("assets", {}).items():
    t = a.get("title") or ""
    if "-179." in t or "-178." in t:
        suffix = t.split("—")[-1].strip() if "—" in t else ""
        a["title"] = f"{label} — {suffix}" if suffix else label
    if key.endswith("-hex"):
        a["description"] = (
            "H3 resolution 8 hex cells, one row per (polygon, cell) pair: "
            f"{f['hex']:,} rows. Per-feature attribute columns are repeated on every cell the polygon "
            "covers, so a raw SUM over hex rows double-counts; deduplicate by _cng_fid first, e.g. "
            "SELECT DISTINCT _cng_fid, ... . Designations of different species overlap, so count "
            "distinct h8 for area.")
        a["table:row_count"] = f["hex"]
dic = []
for c in doc.get("table:columns", []):
    if c["name"] in DROP:
        continue
    c["name"] = RENAME.get(c["name"], c["name"])
    if c["name"] == "comname":
        c["description"] = "Common name of the listed species (free text)."
    if c["name"] == "vipcode":
        c["description"] = ("Taxonomic group and population number: the first letter is V=vertebrate, "
                            "I=invertebrate, P=plant; the digits number the listed populations of one "
                            "species (01 for the first). Values: " + ", ".join(c.get("values", [])) + ".")
    if c["name"] == "OBJECTID_1":
        c["description"] = "Object ID carried over from FWS's aggregation of the species shapefiles."
    dic.append(c)
if not any(c["name"] == "geometry_bbox" for c in dic):
    dic.insert(len(dic) - 2 if dic and dic[-1]["name"] == "h0" else len(dic),
               {"name": "geometry_bbox", "type": "struct",
                "description": "Bounding box of the feature (xmin, ymin, xmax, ymax), for fast spatial filtering."})
doc["table:columns"] = dic
types = {c["name"]: c.get("type") for c in dic}
for key, a in doc.get("assets", {}).items():
    if not a.get("table:columns"):
        continue
    if key.endswith("-parquet"):
        names = ATTRS + ["geometry_bbox", "geometry"]
    elif key.endswith("-hex"):
        names = ATTRS + ["geometry_bbox", "h8", "h0"]
    else:  # PMTiles carry the attributes only
        names = ATTRS
    a["table:columns"] = [{"name": n, "type": types.get(n)} for n in names]
with open(path, "w") as fh:
    fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
print(f"{doc['id']}: patched ({f['n']} polygons, {f['hex']:,} hex rows)")
