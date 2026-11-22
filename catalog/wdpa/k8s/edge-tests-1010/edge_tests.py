#!/usr/bin/env python3
"""People inside WDPA polygons from the GHS-POP 2020 raster at its native 3 arc-second pixels (#1010).

The hex answer (h9 x cover_frac) and the benchmark's raster answer (pixel centres) differ by 6%.
This measures, on the native pixels, per 10-degree tile:

  exact    : exactextract coverage-weighted sum over the union of all WDPA parcels
  centre   : sum over pixels whose centre lies in the union (the benchmark's method)
  buffers  : exact sums with the union grown or shrunk by 90 m and 270 m (boundary accuracy)
  bands    : exact sums and areas in distance bands inside and outside the union's edge
             (0-90, 90-270, 270-1000 m), i.e. density against distance from the boundary

Overlapping parcels are dissolved, so no person is counted twice. Buffers are taken in an
azimuthal equidistant projection centred on the tile; polygons are read with a 0.2 degree margin
so buffering never sees the tile edge, and every result is clipped back to the tile.

  python3 edge_tests.py prep  WDPA_PARQUET OUT_DIR       # split parcels into tile=K/ parquet
  python3 edge_tests.py run   TILE_DIR RASTER OUT_DIR    # tiles 4*IDX .. 4*IDX+3 (IDX = JOB_COMPLETION_INDEX)
Tiles: col = floor((lon+180)/10) in 0..35, row = floor((lat+90)/10) in 0..17, tile = row*36+col.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

MARGIN = 0.2
DISTS = (90, 270, 1000)  # bands; +-90 and +-270 double as the boundary-shift sensitivity


def prep(src: str, out: str) -> None:
    import duckdb
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute(f"SET temp_directory='{out}/.tmp'")
    typ = con.execute(f"SELECT typeof(SHAPE) FROM read_parquet('{src}') LIMIT 1").fetchone()[0]
    geom = "SHAPE::GEOMETRY" if typ.startswith("GEOMETRY") else "ST_GeomFromWKB(SHAPE)"
    con.execute(f"CREATE TABLE p AS SELECT _cng_fid, {geom} AS g FROM read_parquet('{src}')")
    con.execute("""
      CREATE TABLE e AS SELECT _cng_fid, ST_XMin(g) x0, ST_XMax(g) x1, ST_YMin(g) y0, ST_YMax(g) y1 FROM p""")
    con.execute(f"""
      CREATE TABLE t AS
      SELECT e._cng_fid, r.row * 36 + c.col AS tile
      FROM e,
           range(greatest(0, floor((e.x0 - {MARGIN} + 180) / 10))::INT,
                 least(35, floor((e.x1 + {MARGIN} + 180) / 10))::INT + 1) c(col),
           range(greatest(0, floor((e.y0 - {MARGIN} + 90) / 10))::INT,
                 least(17, floor((e.y1 + {MARGIN} + 90) / 10))::INT + 1) r(row)""")
    n = con.execute("SELECT count(*), count(DISTINCT tile), count(DISTINCT _cng_fid) FROM t").fetchone()
    print(f"{n[0]} (parcel, tile) pairs over {n[1]} tiles from {n[2]} parcels", flush=True)
    con.execute(f"""
      COPY (SELECT t.tile, p._cng_fid, ST_AsWKB(p.g) AS wkb FROM t JOIN p USING (_cng_fid))
      TO '{out}/tiles' (FORMAT parquet, PARTITION_BY (tile), COMPRESSION zstd)""")


def tile_box(tile: int):
    row, col = divmod(tile, 36)
    return col * 10 - 180, row * 10 - 90, col * 10 - 170, row * 10 - 80


def run(tiles_dir: str, raster: str, out_dir: str) -> None:
    """One pod = one row of subtiles (ROW) of one tile. TILE_LIST (prep's tiles.txt) maps
    JOB_COMPLETION_INDEX i to tile TILE_LIST[i // ROWS] and row i % ROWS; TILES (comma list)
    overrides for a test and runs every row of those tiles."""
    idx = int(os.environ.get("JOB_COMPLETION_INDEX", "0"))
    rows = int(round(10 / SUB))
    if os.environ.get("TILES"):
        units = [(int(t), r) for t in os.environ["TILES"].split(",") if t for r in range(rows)]
    else:
        tiles = [int(t) for t in Path(os.environ["TILE_LIST"]).read_text().split()]
        if idx // rows >= len(tiles):
            print(f"index {idx}: past the end of the tile list", flush=True)
            return
        units = [(tiles[idx // rows], idx % rows)]
    for tile, row in units:
        f = Path(tiles_dir) / f"tile={tile}"
        if not f.exists():
            print(f"tile {tile}: no parcels", flush=True)
            continue
        t0 = time.time()
        res = one_tile(tile, sorted(f.glob("*.parquet")), raster, row)
        res["seconds"] = round(time.time() - t0, 1)
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / f"tile-{tile}-row-{row}.json").write_text(json.dumps(res))
        print(json.dumps(res), flush=True)


SUB = float(os.environ.get("SUB_DEG", "2"))  # subtile size; bounds geometry and raster work per step


def one_tile(tile: int, files, raster: str, row: int) -> dict:
    """Sum every variant over one row of SUB x SUB degree subtiles (west to east) of the tile."""
    import numpy as np
    import pyarrow.parquet as pq
    import resource
    import shapely

    x0, y0, x1, y1 = tile_box(tile)
    wkb = [w for fp in files for w in pq.read_table(fp, columns=["wkb"]).column("wkb").to_pylist()]
    g = shapely.from_wkb(wkb)  # validated per subtile in one_sub, not all at once (memory)
    del wkb
    tree = shapely.STRtree(g)
    print(f"  tile {tile}: {len(g)} parcels loaded, maxrss "
          f"{resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6:.1f} GB", flush=True)
    out = {"tile": tile, "row": row, "bbox": [x0, y0, x1, y1], "parts": int(len(g)), "people": {},
           "area_km2": {}, "negative_pixels_zeroed": 0, "tile_total": 0.0, "subtiles": 0}
    n = int(round(10 / SUB))
    for i in range(n):
        for j in (row,):
            sx0, sy0 = x0 + i * SUB, y0 + j * SUB
            if sy0 >= 89.09 or sy0 + SUB <= -89.09:
                continue
            t = time.time()
            r = one_sub(g, tree, (sx0, sy0, sx0 + SUB, sy0 + SUB), raster)
            if r is None:
                continue
            out["subtiles"] += 1
            for k in ("people", "area_km2"):
                for v, x in r[k].items():
                    out[k][v] = out[k].get(v, 0.0) + x
            out["negative_pixels_zeroed"] += r["neg"]
            out["tile_total"] += r["total"]
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
            print(f"  tile {tile} sub ({sx0},{sy0}) parts {r['parts']} {time.time() - t:.0f}s "
                  f"maxrss {rss:.1f} GB", flush=True)
    return out


def one_sub(g, tree, bbox, raster: str):
    import geopandas as gpd
    import numpy as np
    import rasterio
    import shapely
    from exactextract import exact_extract
    from pyproj import Transformer
    from rasterio.features import rasterize
    from rasterio.io import MemoryFile
    from rasterio.windows import Window

    x0, y0, x1, y1 = bbox
    box = shapely.box(x0, y0, x1, y1)
    big = shapely.box(x0 - MARGIN, max(-90, y0 - MARGIN), x1 + MARGIN, min(90, y1 + MARGIN))
    idx = tree.query(big, predicate="intersects")
    if len(idx) == 0:
        return None
    part = shapely.get_parts(shapely.make_valid(g[idx]))
    part = part[np.isin(shapely.get_type_id(part), [3, 6])]
    part = shapely.intersection(part, big)
    part = shapely.get_parts(part[~shapely.is_empty(part)])
    part = part[np.isin(shapely.get_type_id(part), [3, 6])]
    if len(part) == 0:
        return None
    U = shapely.union_all(part)

    lon0, lat0 = (x0 + x1) / 2, (y0 + y1) / 2
    aeqd = f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m"
    fwd = Transformer.from_crs("EPSG:4326", aeqd, always_xy=True)
    inv = Transformer.from_crs(aeqd, "EPSG:4326", always_xy=True)
    to_m = lambda geom: shapely.transform(geom, lambda c: np.column_stack(fwd.transform(c[:, 0], c[:, 1])))
    to_ll = lambda geom: shapely.transform(geom, lambda c: np.column_stack(inv.transform(c[:, 0], c[:, 1])))

    from shapely.errors import GEOSException

    def safe(op, a, b):
        """GEOS set operation; on a topology error (projection can leave near-invalid
        rings), retry on validated inputs snapped to a 1 cm grid."""
        try:
            return op(a, b)
        except GEOSException:
            return op(shapely.make_valid(a), shapely.make_valid(b), grid_size=0.01)

    Um = shapely.make_valid(to_m(U))
    buf = {0: Um}
    for d in DISTS:
        buf[d] = shapely.buffer(Um, d, quad_segs=4)
        buf[-d] = shapely.buffer(Um, -d, quad_segs=4)
    variants_m = {
        "exact": buf[0],
        "grow90": buf[90], "grow270": buf[270], "shrink90": buf[-90], "shrink270": buf[-270],
        "in_0_90": safe(shapely.difference, buf[0], buf[-90]),
        "in_90_270": safe(shapely.difference, buf[-90], buf[-270]),
        "in_270_1000": safe(shapely.difference, buf[-270], buf[-1000]),
        "out_0_90": safe(shapely.difference, buf[90], buf[0]),
        "out_90_270": safe(shapely.difference, buf[270], buf[90]),
        "out_270_1000": safe(shapely.difference, buf[1000], buf[270]),
    }
    del buf
    def polys(geom):
        """Polygonal parts only, without slivers. Clipping can leave lines, points, and
        zero-width slivers where an edge lies on the box edge (the AEQD round trip moves it by
        a hair), and exactextract miscounts degenerate slivers."""
        parts = shapely.get_parts(shapely.get_parts(geom))
        parts = parts[np.isin(shapely.get_type_id(parts), [3])]
        parts = parts[shapely.area(parts) > 1e-10]  # ~1 m2 in degrees
        return shapely.multipolygons(parts) if len(parts) else shapely.Polygon()
    # back to lon/lat first, then clip to the exact subtile box, so seams between subtiles are exact
    variants = {k: polys(shapely.intersection(shapely.make_valid(to_ll(v)), box))
                for k, v in variants_m.items()}
    del variants_m
    area = {k: shapely.area(to_m(v)) / 1e6 for k, v in variants.items()}  # km2, AEQD

    pad = 0.002  # a few pixels, so pixels straddling the subtile edge are whole in the window
    with rasterio.open(raster) as src:
        T = src.transform  # explicit floor/ceil so the window always covers the padded bounds
        c0 = math.floor((x0 - pad - T.c) / T.a)
        c1 = math.ceil((x1 + pad - T.c) / T.a)
        r0 = math.floor((min(y1 + pad, 89.09) - T.f) / T.e)
        r1 = math.ceil((max(y0 - pad, -89.09) - T.f) / T.e)
        w = Window(c0, r0, c1 - c0, r1 - r0)
        a = src.read(1, window=w, boundless=True, fill_value=0)
        tr = src.window_transform(w)
        prof = src.profile
    neg = int((a < 0).sum())
    a[a < 0] = 0
    prof.update(driver="GTiff", height=a.shape[0], width=a.shape[1], transform=tr, nodata=None,
                tiled=False, compress=None, blockxsize=None, blockysize=None)
    names = [k for k in variants if not variants[k].is_empty]
    people = {k: 0.0 for k in variants}
    with MemoryFile() as mf:
        with mf.open(**{k: v for k, v in prof.items() if v is not None}) as dst:
            dst.write(a, 1)
        with mf.open() as ds:
            if names:
                gdf = gpd.GeoDataFrame({"v": names}, geometry=[variants[k] for k in names], crs="EPSG:4326")
                stats = exact_extract(ds, gdf, ["sum"], include_cols=["v"], output="pandas")
                for _, r in stats.iterrows():
                    people[r.v] = float(r["sum"])
    # pixel-centre method on the published union (GDAL rasterize default = centre-in-polygon)
    if not variants["exact"].is_empty:
        mask = rasterize([(variants["exact"], 1)], out_shape=a.shape, transform=tr, fill=0,
                         all_touched=False, dtype="uint8")
        people["centre"] = float(a[mask == 1].sum())
    else:
        people["centre"] = 0.0
    # tile_total: only pixels whose centre is inside the subtile, so subtiles do not double count
    rows, cols = np.indices(a.shape)
    xs = tr.c + (cols + 0.5) * tr.a
    ys = tr.f + (rows + 0.5) * tr.e
    inside = (xs >= x0) & (xs < x1) & (ys >= y0) & (ys < y1)
    return {"people": people, "area_km2": area, "neg": neg, "total": float(a[inside].sum()),
            "parts": int(len(part))}


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "prep":
        prep(sys.argv[2], sys.argv[3])
    elif mode == "run":
        run(*sys.argv[2:5])
