#!/usr/bin/env python3
"""Build the MegaMove tracked-individuals species grid as a long-format point layer.

Wide per-species 1° grid (numberindivs_total_perspecies_1deg.csv) → long format:
one POINT per (1° cell, species) with nind>0, enriched with taxonomy from
Supplementary Table S1 and a derived MegaMove taxon group. Written with OGR.
"""
import csv, re, unicodedata
from osgeo import ogr, osr

F1 = "/tmp/megamove/f1/1_Tracked Individuals"
GRID = f"{F1}/numberindivs_total_perspecies_1deg.csv"
PERTAXA = f"{F1}/numberindivs_pertaxa_1deg.csv"
S1 = "/tmp/megamove/f5/5_Supplementary Tables/Supplementary Table 1_Summary of the satellite tracking dataset.csv"
OUT = "/tmp/megamove/sources/tracked-individuals.gpkg"

def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())

# ---- S1 taxonomy (cp1252) ----
rows = list(csv.reader(open(S1, newline="", encoding="cp1252")))
h = rows[5]; ix = {n: i for i, n in enumerate(h)}
ci, oi, fi, sci, spi = ix["Class"], ix["Order"], ix["Family"], ix["Scientific name"], ix["Species"]
s1 = {}
for r in rows[6:]:
    if len(r) <= spi or not r[spi].strip() or r[spi].lower().startswith("total"):
        continue
    name = r[spi].strip()
    s1[norm(name)] = {"common": name, "scientific": r[sci].strip(),
                      "class": r[ci].strip(), "order": r[oi].strip(), "family": r[fi].strip()}

# explicit overrides: grid common-name -> S1 common-name (name variants)
OVR = {
    "Beluga whale": "Beluga", "Common thresher shark": "Common thresher",
    "Harbour seal": "Harbor seal", "Long-nosed fur seal": "Long-nosed (New Zealand) fur seal",
    "Northern Right whale": "North Atlantic right whale", "Pelagic thresher shark": "Pelagic thresher",
    "Ross gull": "Ross's gull", "Sandtiger shark": "Smalltooth sand tiger shark",
}
ovr = {norm(k): norm(v) for k, v in OVR.items()}

def lookup(grid_species):
    key = norm(grid_species.replace("_", " "))
    key = ovr.get(key, key)
    return s1.get(key)

def taxon_of(cls, order, family):
    if cls == "Reptilia": return "Turtles"
    if cls in ("Actinopterygii", "Chondrichthyes"): return "Fishes"
    if cls == "Aves": return "Penguins" if order == "Sphenisciformes" else "Birds"
    if cls == "Mammalia":
        if order == "Sirenia": return "Sirenians"
        if order == "Cetartiodactyla": return "Cetaceans"
        if order == "Carnivora": return "Polar bears" if family == "Ursidae" else "Seals"
    return "UNKNOWN"

# ---- read grid ----
gr = list(csv.reader(open(GRID)))
ghdr = gr[0]
grid_species = [c[:-5] for c in ghdr[2:]]  # strip _nind
# resolve taxonomy for all species up front + validate 1:1
meta = {}
unmatched = []
for gs in grid_species:
    m = lookup(gs)
    if not m: unmatched.append(gs); continue
    tx = taxon_of(m["class"], m["order"], m["family"])
    meta[gs] = {**m, "taxon": tx}
assert not unmatched, f"unmatched species: {unmatched}"
used_s1 = {norm(meta[gs]["common"]) for gs in grid_species}
assert len(used_s1) == 111, f"S1 names not 1:1: {len(used_s1)} distinct"
bad_tx = {gs: meta[gs] for gs in meta if meta[gs]["taxon"] == "UNKNOWN"}
assert not bad_tx, f"unmapped taxon: {bad_tx}"
print("all 111 species matched 1:1; taxon groups assigned")

# ---- validate taxon grouping vs per-taxa grid (sum of species == taxa, per cell) ----
def load_grid(path):
    rr = list(csv.reader(open(path)))
    hh = rr[0]
    return hh, rr[1:]
ph, prows = load_grid(PERTAXA)
ptax = [c[:-5] for c in ph[2:]]  # Birds, Cetaceans, ...
pidx = {t: i + 2 for i, t in enumerate(ptax)}
# build per-cell taxon sums from species grid
from collections import defaultdict
sp_taxon_sum = defaultdict(float)   # (lat,lon,taxon)->sum nind
sp_col_taxon = [meta[s]["taxon"] for s in grid_species]
for row in gr[1:]:
    lat, lon = row[0], row[1]
    for j, v in enumerate(row[2:]):
        if v in ("", "0", "0.0"): continue
        val = float(v)
        if val: sp_taxon_sum[(lat, lon, sp_col_taxon[j])] += val
# compare to pertaxa
mism = 0; checked = 0
ptax_norm = {t.replace("_", " "): t for t in ptax}  # Polar_bears -> 'Polar bears'? pertaxa uses underscores
for row in prows:
    lat, lon = row[0], row[1]
    for t in ptax:
        tg = t.replace("_", " ")
        pv = row[pidx[t]]
        pv = float(pv) if pv not in ("", ) else 0.0
        sv = sp_taxon_sum.get((lat, lon, tg), 0.0)
        if abs(pv - sv) > 1e-6:
            mism += 1
        checked += 1
print(f"taxon-grouping validation: {checked} (cell,taxon) checked, {mism} mismatches")

# ---- write long-format point GeoPackage ----
srs = osr.SpatialReference(); srs.ImportFromEPSG(4326)
drv = ogr.GetDriverByName("GPKG")
import os
if os.path.exists(OUT): drv.DeleteDataSource(OUT)
ds = drv.CreateDataSource(OUT)
lyr = ds.CreateLayer("tracked-individuals", srs, ogr.wkbPoint)
for n, t, w in [("species", ogr.OFTString, 80), ("scientific_name", ogr.OFTString, 80),
                ("class", ogr.OFTString, 32), ("order", ogr.OFTString, 32),
                ("family", ogr.OFTString, 48), ("taxon", ogr.OFTString, 16)]:
    fd = ogr.FieldDefn(n, t); fd.SetWidth(w); lyr.CreateField(fd)
lyr.CreateField(ogr.FieldDefn("nind", ogr.OFTInteger))
ldef = lyr.GetLayerDefn()
n_feat = 0
for row in gr[1:]:
    lat = float(row[0]); lon = float(row[1])
    for j, v in enumerate(row[2:]):
        if v in ("", "0", "0.0"): continue
        val = float(v)
        if not val: continue
        gs = grid_species[j]; m = meta[gs]
        f = ogr.Feature(ldef)
        f.SetField("species", gs.replace("_", " "))
        f.SetField("scientific_name", m["scientific"]); f.SetField("class", m["class"])
        f.SetField("order", m["order"]); f.SetField("family", m["family"]); f.SetField("taxon", m["taxon"])
        f.SetField("nind", int(val))
        pt = ogr.Geometry(ogr.wkbPoint); pt.AddPoint(lon, lat); f.SetGeometry(pt)
        lyr.CreateFeature(f); f = None; n_feat += 1
ds = None
print(f"wrote {n_feat} (cell,species) point features -> {OUT}")

# summary by taxon
ds = ogr.Open(OUT); lyr = ds.GetLayer()
from collections import Counter
c = Counter(); sp = set()
for f in lyr:
    c[f.GetField("taxon")] += 1; sp.add(f.GetField("species"))
print("distinct species:", len(sp))
for t, n in sorted(c.items(), key=lambda x: -x[1]):
    print(f"  {t:12s} {n} point-rows")
ds = None
