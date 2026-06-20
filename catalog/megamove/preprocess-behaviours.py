#!/usr/bin/env python3
"""Preprocess MegaMove 2_Detected_behaviours shapefiles into per-behaviour
single-file GeoPackages for cng-datasets conversion.

- merges the dissolved *_total* polygon as a Taxon='All taxa' feature
- attaches the paper's global area (km2) and time-spent fraction per taxon
- written with OGR (NOT geopandas) so downstream DuckDB conversion is clean
"""
import csv, os
from osgeo import ogr, osr

BASE = "/tmp/megamove/db/2_Detected behaviours"
OUT = "/tmp/megamove/sources"
os.makedirs(OUT, exist_ok=True)

def num(s):
    s = (s or "").strip().replace(",", "")
    return float(s) if s else None

def load_block(path):
    """Return {taxon: row_dict} for the 'Globally' block only (stop at 'In EEZ')."""
    rows = {}
    with open(path, newline="") as f:
        r = csv.reader(f)
        header = next(r)
        in_glob = False
        for row in r:
            if not row or not row[0].strip():
                continue
            key = row[0].strip()
            if key == "Globally":
                in_glob = True; continue
            if key == "In EEZ":
                break
            if in_glob:
                rows[key] = dict(zip(header, row))
    return rows

area = load_block(f"{BASE}/Area_Behaviours.csv")
time = load_block(f"{BASE}/Time_Behaviours.csv")

def taxon_key(t):
    return "All species" if t == "All taxa" else t

def stats(behaviour, taxon):
    """Return (area_km2, time_frac) for a (behaviour, taxon)."""
    k = taxon_key(taxon)
    a, t = area.get(k, {}), time.get(k, {})
    if behaviour == "corridors":
        return num(a.get("Area Corridor (km2)")), num(t.get("Corridor"))
    if behaviour == "residencies":
        return num(a.get("Area Residence (km2)")), num(t.get("Residence"))
    if behaviour == "immegas":
        tot, none = num(a.get("Area Total (km2)")), num(a.get("Area None (km2)"))
        immega_area = (tot - none) if (tot is not None and none is not None) else None
        tnone = num(t.get("None"))
        immega_time = (1.0 - tnone) if tnone is not None else None  # time in ANY behaviour
        return immega_area, immega_time
    return None, None

BEHAVIOURS = {
    "corridors":   (f"{BASE}/corridors_bytaxa/corridors.shp",     f"{BASE}/corridors_total/corridors.shp"),
    "residencies": (f"{BASE}/residencies_bytaxa/residencies.shp", f"{BASE}/residencies_total/residencies.shp"),
    "immegas":     (f"{BASE}/immegas/immegas_bytaxa/immegas.shp", f"{BASE}/immegas/immegas.shp"),
}

srs = osr.SpatialReference(); srs.ImportFromEPSG(4326)
gpkg_drv = ogr.GetDriverByName("GPKG")
shp_drv = ogr.GetDriverByName("ESRI Shapefile")

for beh, (bytaxa_p, total_p) in BEHAVIOURS.items():
    out_path = f"{OUT}/{beh}.gpkg"
    if os.path.exists(out_path):
        gpkg_drv.DeleteDataSource(out_path)
    ds = gpkg_drv.CreateDataSource(out_path)
    lyr = ds.CreateLayer(beh, srs, ogr.wkbMultiPolygon)
    fd = ogr.FieldDefn("Taxon", ogr.OFTString); fd.SetWidth(80); lyr.CreateField(fd)
    # All three carry per-taxon global stats. immegas = corridor∪residence union, so its
    # area = Area Total − Area None and time = 1 − time(None); see stats() (verified against
    # res-4 hex cell counts to within ~5%).
    with_stats = True
    if with_stats:
        lyr.CreateField(ogr.FieldDefn("area_km2", ogr.OFTReal))
        lyr.CreateField(ogr.FieldDefn("time_frac", ogr.OFTReal))
    ldef = lyr.GetLayerDefn()

    def add(geom, taxon):
        feat = ogr.Feature(ldef)
        feat.SetField("Taxon", taxon)
        if with_stats:
            a, t = stats(beh, taxon)
            if a is not None: feat.SetField("area_km2", a)
            if t is not None: feat.SetField("time_frac", t)
        g = ogr.ForceToMultiPolygon(geom.Clone())
        feat.SetGeometry(g)
        lyr.CreateFeature(feat)
        feat = None

    # per-taxon features
    src = shp_drv.Open(bytaxa_p, 0); slyr = src.GetLayer()
    n_taxa = 0
    for f in slyr:
        add(f.GetGeometryRef(), f.GetField("Taxon")); n_taxa += 1
    src = None
    # dissolved total -> 'All taxa'
    src = shp_drv.Open(total_p, 0); slyr = src.GetLayer()
    n_tot = 0
    for f in slyr:
        add(f.GetGeometryRef(), "All taxa"); n_tot += 1
    src = None
    ds = None
    print(f"{beh}: {n_taxa} taxa + {n_tot} 'All taxa' -> {out_path}")

print("\n=== verify ===")
for beh in BEHAVIOURS:
    ds = ogr.Open(f"{OUT}/{beh}.gpkg"); lyr = ds.GetLayer()
    flds = [lyr.GetLayerDefn().GetFieldDefn(i).GetName() for i in range(lyr.GetLayerDefn().GetFieldCount())]
    print(f"-- {beh}: {lyr.GetFeatureCount()} features  fields={flds}")
    for f in lyr:
        extra = "" if "area_km2" not in flds else f"  area_km2={f.GetField('area_km2')!s:>14}  time_frac={f.GetField('time_frac')}"
        print(f"   {f.GetField('Taxon'):12s}{extra}")
    ds = None
