#!/usr/bin/env python3
"""#740: bring the 10 public-wyoming collections' STAC up to the AGENTS.md asset standard.

Moves the collection-level table:columns onto each parquet asset (flat + hex, same text),
restricted to the columns the rebuilt files actually contain; adds _cng_fid / OGC_FID / H3
columns; points the hex href at the hive glob and declares h3 resolutions; states per-feature
duplication on the hex asset description. PMTiles columns are mirrored afterwards with
scripts/mirror-pmtiles-columns.py.

    fix_stac.py <outdir>          # writes <outdir>/<dataset>.json, reports undescribed columns
"""
import json, sys, urllib.request

BASE = "https://s3-west.nrp-nautilus.io/public-wyoming"
WGFD = ["_cng_fid", "OGC_FID", "OBJECTID", "RANGE", "Acres", "SQMiles"]
H10 = (10, [9, 8, 0])
# dataset -> (flat attribute columns in file order, hex (native, parents) or None, per-feature totals)
SETS = {
    "sage-grouse-priority": (["_cng_fid", "OGC_FID", "ID", "NAME", "Acres", "Shape_Leng", "Shape_Area"], H10,
                             ["Acres", "Shape_Leng", "Shape_Area"]),
    "ungulate-migration": (["_cng_fid", "OGC_FID", "herdid", "species", "id", "season", "year", "firstdate", "lastdate"],
                           None, []),
    **{d: (WGFD, H10, ["Acres", "SQMiles"]) for d in (
        "wgfd-elk-crucial", "wgfd-elk-seasonal", "wgfd-mule-deer-crucial", "wgfd-mule-deer-seasonal",
        "wgfd-pronghorn-crucial", "wgfd-pronghorn-seasonal")},
    "wy-counties": (["_cng_fid", "OGC_FID", "OBJECTID", "Shape_Length", "Shape_Area", "COUNTYNAME", "YEARCOLLEC",
                     "TAXYEAR", "TYPENAME", "RuleID"], (11, [10, 9, 8, 0]), ["Shape_Length", "Shape_Area"]),
    "wyoming-places": (["_cng_fid", "OGC_FID", "OBJECTID", "Name", "County", "Latitude", "Longitude", "County_Seat",
                        "Population_2010"], H10, []),
}
STD = {
    "_cng_fid": {"name": "_cng_fid", "type": "int64",
                 "description": "Universal per-feature row id synthesized by cng-datasets (row-unique 1…N, one per feature). "
                                "Dedup / feature-count key: COUNT(DISTINCT _cng_fid)."},
    "OGC_FID": {"name": "OGC_FID", "type": "int64",
                "description": "Feature sequence number assigned by GDAL when the source file was read. Not a source identifier."},
}
GEOM = {"name": "geom", "type": "geometry"}
RES_TEXT = {0: "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."}

def standard_values(col):
    """values as [{value, description}] objects -> the standard plain code list, with the
    definitions moved into the description as CODE=Definition pairs (AGENTS.md)."""
    v = col.get("values")
    if v and isinstance(v[0], dict):
        pairs = ", ".join(f"{x['value']}={x['description']}" if x.get("description") else str(x["value"]) for x in v)
        col["description"] = col.get("description", "").rstrip() + " Values: " + pairs
        col["values"] = [x["value"] for x in v]
    return col

def hcol(r):
    return {"name": f"h{r}", "type": "int64", "description": RES_TEXT.get(r, f"H3 cell ID at resolution {r}.")}

out = sys.argv[1]
for d, (attrs, hexres, totals) in SETS.items():
    # Always start from the pre-#740 STAC (backed up by backup.yaml) so reruns are idempotent.
    c = json.load(urllib.request.urlopen(f"{BASE}/staging/740-nofid-backup/{d}/stac-collection.json"))
    old = {x["name"]: x for x in c.pop("table:columns", [])}
    missing = [a for a in attrs if a not in old and a not in STD]
    if missing:
        print(f"{d}: NO DESCRIPTION for {missing}")
    cols = [standard_values(dict(old.get(a) or STD.get(a) or {"name": a})) for a in attrs]
    geom = dict(old.get("geom", GEOM))
    A = c["assets"]
    A[f"{d}-parquet"]["table:columns"] = cols + [geom]
    if hexres:
        native, parents = hexres
        h = A[f"{d}-hex"]
        h["href"] = f"{BASE}/{d}/hex/h0=*/data_0.parquet"
        h["h3:native_resolution"] = native
        h["h3:parent_resolutions"] = parents
        h["table:columns"] = [dict(x) for x in cols] + [hcol(native)] + [hcol(r) for r in parents]
        point = d == "wyoming-places"
        note = (f"H3 hex index of the {c['title']} features at resolution {native}, with parent cells at "
                f"resolutions {', '.join(map(str, parents))}. Partitioned by h0. ")
        if point:
            note += (f"Each point is assigned to the single resolution-{native} cell that contains it, so there is "
                     "one row per place and points that fall in the same cell are not merged. Because no place is "
                     "repeated, SUM(Population_2010) over the hex is the population total; count places with "
                     "COUNT(DISTINCT _cng_fid).")
        else:
            note += (f"One row per (feature, resolution-{native} cell) pair, so feature attributes are repeated on "
                     f"every cell the feature covers. {', '.join(totals)} are per-feature totals: deduplicate on "
                     f"_cng_fid before summing them, for example "
                     f"SELECT SUM({totals[0]}) FROM (SELECT DISTINCT _cng_fid, {totals[0]} FROM …). "
                     "Count features with COUNT(DISTINCT _cng_fid).")
        h["description"] = note
    json.dump(c, open(f"{out}/{d}.json", "w"), indent=2, ensure_ascii=False)
    print("wrote", d)
