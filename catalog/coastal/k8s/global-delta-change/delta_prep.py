"""Build clean GeoParquet layers from the GlobalDeltaChange repository (#796).

usage: delta_prep.py <srcdir> <outdir>

<srcdir> holds these files from github.com/jhnienhuis/GlobalDeltaChange at a pinned commit:
  GlobalDeltaData.mat, GlobalDeltaData_AreaChange.mat, GlobalDeltaData.xlsx,
  GlobalDeltaBasins_shp.zip, GlobalDeltaAreaWeb_shp.zip, GlobalDelta_FluxesWeb.csv,
  GlobalDelta_DeltaAreaWeb.csv, GlobalDelta_DeltaSLRWeb.csv

The repository's shapefiles carry corrupted attribute tables (MATLAB wrote values wider than the
DBF fields), so attributes come from the .mat files (delta names from the .xlsx), all in the same
delta order, which is checked by BasinID2. Geometry:
  mouths       points from MouthLon/MouthLat
  rivers       lines from channel_len_lon/lat (the channel from the mouth up to 30 m elevation);
               the repository's river shapefile has 501 empty lines
  basins       polygons from GlobalDeltaBasins_shp (rows in delta order, checked against the
               mouths), made valid
  delta_areas  the 811 delta outlines of GlobalDeltaAreaWeb_shp: four-point rings (apex,
               shoreline, mouth, shoreline) left unclosed upstream, closed here
Writes <outdir>/{mouths,rivers,basins,delta_areas}.parquet and projections.parquet (no geometry).
"""
import sys

import geopandas as gpd
import h5py
import numpy as np
import pandas as pd
import shapely
from osgeo import gdal, ogr

gdal.UseExceptions()
SRC, OUT = sys.argv[1], sys.argv[2]

m = h5py.File(f"{SRC}/GlobalDeltaData.mat", "r")
a = h5py.File(f"{SRC}/GlobalDeltaData_AreaChange.mat", "r")
v = lambda f, k: f[k][:].ravel()
ids = v(m, "BasinID2").astype("int64")
N = len(ids)
assert (v(a, "BasinID2") == ids).all(), "area-change rows are not in delta order"

ds = ogr.Open(f"{SRC}/GlobalDeltaData.xlsx")
xl = [(f.GetField("BasinID2"), f.GetField("delta_name")) for f in ds.GetLayer(0)]
assert len(xl) == N and all(int(b) == i for (b, _), i in zip(xl, ids)), "xlsx rows are not in delta order"
names = [(n or "").strip() or None for _, n in xl]

regions = ["".join(chr(c) for c in m[r][:].ravel()) for r in m["Region_str"][:].ravel()]
region = v(m, "Region").astype(int)


def lon180(x):
    return np.where(x > 180, x - 360, x)


fin = lambda x: np.where(np.isfinite(x), x, np.nan)
lon, lat = lon180(v(m, "MouthLon")), v(m, "MouthLat")
attrs = pd.DataFrame({
    "delta_id": np.arange(1, N + 1, dtype="int32"),   # row in the authors' delta order; BasinID2 repeats
    "basin_id2": ids,
    "delta_name": names,
    "basin_id_atlas": v(m, "BasinID_ATLAS").astype("int64"),
    "river_id_atlas": v(m, "RiverID_ATLAS").astype("int64"),
    "region": [regions[r - 1] if 0 < r <= len(regions) else None for r in region],
    "region_code": region.astype("int32"),   # 21 (194 deltas: Mediterranean, Black and Caspian seas) has no name upstream
    "mouth_lon": lon, "mouth_lat": lat,
    "basin_area_km2": fin(v(m, "BasinArea")),
    "discharge_prist_m3s": fin(v(m, "Discharge_prist")),
    "discharge_dist_m3s": fin(v(m, "Discharge_dist")),
    "discharge_tide_m3s": fin(v(m, "Discharge_tide")),
    "qriver_prist_kgs": fin(v(m, "QRiver_prist")),
    "qriver_dist_kgs": fin(v(m, "QRiver_dist")),
    "qtide_kgs": fin(v(m, "QTide")),
    "qwave_kgs": fin(v(m, "QWave")),
    "hs_m": fin(v(m, "Hs")),
    "tp_s": fin(v(m, "Tp")),
    "tidal_amp_m": fin(v(m, "TidalAmp")),
    "channel_slope": fin(v(m, "channel_slope")),
    "shelf_depth_m": fin(v(m, "shelf_depth")),
    "shelf_slope": fin(v(m, "shelf_slope")),
    "land_gain_km2yr": fin(v(a, "dep_aqua")),
    "land_loss_km2yr": fin(v(a, "ero_aqua")),
    "land_net_km2yr": fin(v(a, "net_aqua")),
})
p, d = attrs.qriver_prist_kgs, attrs.qriver_dist_kgs
# 1e-10 kg/s is a floor value upstream (9 deltas), not a flux, so no percentage there.
attrs["sediment_change_pct"] = np.where(p > 1e-9, 100 * (d - p) / p, np.nan)

W = dict(index=False, compression="zstd", row_group_size=2000)
mouths = gpd.GeoDataFrame(attrs, geometry=shapely.points(lon, lat), crs="EPSG:4326")
mouths.to_parquet(f"{OUT}/mouths.parquet", **W)
print("mouths", len(mouths), flush=True)

# Rivers: channel profile points from the mouth upstream; NaN is padding.
clat, clon = m["channel_len_lat"][:], m["channel_len_lon"][:]   # (30, N)
assert clat.shape == (30, N), clat.shape
rows, geoms = [], []
for i in range(N):
    la, lo = clat[:, i], clon[:, i]
    ok = np.isfinite(la) & np.isfinite(lo) & ~((la == 0) & (lo == 0))
    pts = np.column_stack([lon180(lo[ok]), la[ok]])
    if len(pts) >= 2 and np.ptp(pts[:, 0]) < 180:
        rows.append(i); geoms.append(shapely.linestrings(pts))
print("BasinID2 values shared by more than one delta:", int((pd.Series(ids).value_counts() > 1).sum()), flush=True)
keep = ["delta_id", "basin_id2", "delta_name", "region", "basin_area_km2", "discharge_prist_m3s",
        "discharge_dist_m3s", "qriver_prist_kgs", "qriver_dist_kgs", "sediment_change_pct"]
rivers = gpd.GeoDataFrame(attrs.iloc[rows][keep].reset_index(drop=True), geometry=geoms, crs="EPSG:4326")
d = shapely.distance(shapely.get_point(rivers.geometry.values, 0), mouths.geometry.values[rows])
de = shapely.distance(shapely.get_point(rivers.geometry.values, -1), mouths.geometry.values[rows])
print("rivers", len(rivers), "of", N, "; start within 0.05 degree of the mouth:", round(float(np.mean(d < 0.05)), 3),
      "; end within 0.05:", round(float(np.mean(de < 0.05)), 3), "; start distance quantiles 50/90/99/max:",
      np.round(np.quantile(d, [.5, .9, .99, 1]), 3), "; length quantiles:",
      np.round(np.quantile(shapely.length(rivers.geometry.values), [.1, .5, .9]), 3), flush=True)
rivers.to_parquet(f"{OUT}/rivers.parquet", **W)


def polys(g):
    """Keep the polygonal part of a make_valid result."""
    if g is None or g.is_empty:
        return None
    if g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    parts = [p for p in getattr(g, "geoms", []) if p.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.union_all(parts) if parts else None


def read_geoms(zipname):
    ds = ogr.Open(f"/vsizip/{SRC}/{zipname}")   # keep the dataset alive while reading the layer
    lyr = ds.GetLayer(0)
    out = []
    for f in lyr:
        g = f.GetGeometryRef()
        if g is None:
            out.append((f, None)); continue
        g = g.Clone(); g.CloseRings()
        s = shapely.from_wkb(bytes(g.ExportToIsoWkb()), on_invalid="ignore")
        out.append((f, polys(shapely.make_valid(s)) if s is not None else None))
    return out


basin_geom = [g for _, g in read_geoms("GlobalDeltaBasins_shp.zip")]
assert len(basin_geom) == N, len(basin_geom)
d = shapely.distance(np.array(basin_geom, dtype=object), mouths.geometry.values)
near = float(np.nanmean(d < 0.1))
print("basins within 0.1 degree of their own mouth:", round(near, 3), flush=True)
assert near > 0.95, "basin rows are not in delta order"
ok = [i for i, g in enumerate(basin_geom) if g is not None]
basins = gpd.GeoDataFrame(attrs.iloc[ok][keep].reset_index(drop=True),
                          geometry=[basin_geom[i] for i in ok], crs="EPSG:4326")
basins.to_parquet(f"{OUT}/basins.parquet", **W)
print("basins", len(basins), "of", N, flush=True)

# Delta outlines (2023 review): BasinID2 is their only field and parses cleanly.
area = [(f.GetField("BasinID2"), g) for f, g in read_geoms("GlobalDeltaAreaWeb_shp.zip")]
flux = pd.read_csv(f"{SRC}/GlobalDelta_FluxesWeb.csv")
assert (flux.BasinID2.to_numpy() == np.array([b for b, _ in area])).all(), "outline and flux rows differ"
# The authors select these deltas with an in-order mask over the full list, so walk both in order;
# the pristine sediment flux confirms each match.
pos, j = [], 0
for b, q in zip(flux.BasinID2, flux.QRiver_prist):
    while not (ids[j] == b and np.isclose(attrs.qriver_prist_kgs.iat[j], q, rtol=1e-3, atol=1e-3)):
        j += 1
    pos.append(j); j += 1
da = attrs.iloc[pos][["delta_id", "basin_id2", "delta_name", "region", "qriver_prist_kgs", "qriver_dist_kgs",
                      "sediment_change_pct", "land_net_km2yr"]].reset_index(drop=True)
da.insert(2, "delta_area_km2", flux.delta_area.to_numpy() / 1e6)
okd = [i for i, (_, g) in enumerate(area) if g is not None]
delta_areas = gpd.GeoDataFrame(da.iloc[okd].reset_index(drop=True),
                               geometry=[area[i][1] for i in okd], crs="EPSG:4326")
delta_areas.to_parquet(f"{OUT}/delta_areas.parquet", **W)
print("delta_areas", len(delta_areas), "of", len(area), flush=True)

# Projections: one row per delta, scenario and year. The CSVs list each delta as a block of
# years, in outline order; a block starts where the year drops or the BasinID2 changes.
outline_ids = da.delta_id.to_numpy()
long = []
for fname, col in [("GlobalDelta_DeltaSLRWeb.csv", "rslr_m"), ("GlobalDelta_DeltaAreaWeb.csv", "delta_area_km2")]:
    t = pd.read_csv(f"{SRC}/{fname}")
    blk = ((t.yrs.diff().fillna(-1) <= 0) | (t.BasinID2.diff().fillna(1) != 0)).cumsum() - 1
    assert blk.max() + 1 == len(da), (fname, blk.max() + 1)
    assert (t.BasinID2.to_numpy() == da.basin_id2.to_numpy()[blk]).all(), fname
    t["delta_id"] = outline_ids[blk]
    t = t.drop(columns="BasinID2").melt(id_vars=["delta_id", "yrs"], var_name="scenario", value_name=col)
    long.append(t.rename(columns={"yrs": "year"}).set_index(["delta_id", "scenario", "year"]))
proj = long[0].join(long[1], how="outer").reset_index()
proj["scenario"] = proj.scenario.map({"SSP126": "SSP1-2.6", "SSP245": "SSP2-4.5", "SSP585": "SSP5-8.5"})
proj = proj.astype({"delta_id": "int32", "year": "int32"}).sort_values(["delta_id", "scenario", "year"])
proj.to_parquet(f"{OUT}/projections.parquet", index=False, compression="zstd")
print("projections", len(proj), "rows,", proj.delta_id.nunique(), "deltas, years", sorted(proj.year.unique()), flush=True)

yr = 3.15576e7 / 1e12
print("sediment to deltas, pristine / present (Gt/yr):", round(attrs.qriver_prist_kgs.sum() * yr, 2), round(attrs.qriver_dist_kgs.sum() * yr, 2))
print("net land change, all deltas (km2/yr):", round(attrs.land_net_km2yr.sum(), 1))
print("named deltas:", int(attrs.delta_name.notna().sum()), "; regions:", sorted(set(attrs.region.dropna())))
