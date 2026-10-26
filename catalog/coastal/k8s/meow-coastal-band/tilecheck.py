"""Gap check for one vector tile (data-workflows #774).

Decodes tile z/x/y of a PMTiles with tippecanoe-decode, projects every feature into tile pixel
space (256 px per tile), unions them, and reports the holes of the union. Each hole is classified
by sampling points inside it against the source H3 cells: if most fall in band cells, the source is
continuous there and the hole is a GAP opened by tiling; otherwise it is a real hole (inland area
more than 20 km from the coast, or sea more than 50 km out). Also reports overlap (sum of feature
areas minus union area), which simplification can introduce instead of gaps.

    python3 tilecheck.py <file.pmtiles> z/x/y [z/x/y ...]
"""
import json, math, subprocess, sys, warnings

import numpy as np
import shapely
from shapely.geometry import shape
from shapely.ops import transform

warnings.filterwarnings("ignore", category=DeprecationWarning)


def tile_px(z, x, y):
    n = 2 ** z
    def f(lng, lat, *_):
        lng, lat = np.asarray(lng), np.asarray(lat)
        px = ((lng + 180.0) / 360.0 * n - x) * 256
        lr = np.radians(lat)
        py = ((1 - np.log(np.tan(lr) + 1 / np.cos(lr)) / math.pi) / 2 * n - y) * 256
        return px, py
    return f


def px_to_lnglat(z, x, y, px, py):
    n = 2 ** z
    lng = (np.asarray(px) / 256 + x) / n * 360 - 180
    lat = np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * (np.asarray(py) / 256 + y) / n))))
    return lng, lat


def sample_points(poly, k=25, seed=0):
    """Up to k random points inside poly (rejection sampling) plus a guaranteed interior point."""
    rng = np.random.default_rng(seed)
    x0, y0, x1, y1 = poly.bounds
    pts = [poly.representative_point()]
    for _ in range(40):
        cand = shapely.points(rng.uniform(x0, x1, 200), rng.uniform(y0, y1, 200))
        pts.extend(cand[shapely.contains(poly, cand)])
        if len(pts) > k:
            break
    return pts[: k + 1]


def check(path, z, x, y, in_band=None):
    """in_band(lng_array, lat_array) -> bool array: whether each point lies in a band cell.
    With it, a hole of the tile's union is a GAP when most sample points inside it fall in band
    cells (the source data is continuous there), and a real hole otherwise."""
    d = subprocess.run(["tippecanoe-decode", "-c", path, str(z), str(x), str(y)], capture_output=True, text=True)
    if d.returncode != 0 or "instead of" in d.stderr:
        return {"tile": f"{z}/{x}/{y}", "missing": True}
    proj = tile_px(z, x, y)
    geoms = []
    for line in d.stdout.splitlines():
        if line.startswith('{ "type": "Feature"'):
            g = shape(json.loads(line.rstrip().rstrip(","))["geometry"])
            g = transform(proj, g)
            if not g.is_valid:
                g = shapely.make_valid(g)
            geoms.append(g)
    tile = shapely.box(0, 0, 256, 256)
    geoms = [g.intersection(tile) for g in geoms]
    u = shapely.union_all(geoms)
    holes = []
    for p in getattr(u, "geoms", [u]):
        if p.geom_type != "Polygon":
            continue
        for r in p.interiors:
            h = shapely.Polygon(r)
            holes.append((h.area, 2 * h.area / max(h.length, 1e-12)))  # area px^2, mean thickness px
    gaps = []
    if in_band is not None:
        for p in getattr(u, "geoms", [u]):
            if p.geom_type != "Polygon":
                continue
            for r in p.interiors:
                h = shapely.Polygon(r)
                pts = sample_points(h)
                lng, lat = px_to_lnglat(z, x, y, shapely.get_x(pts), shapely.get_y(pts))
                if np.mean(in_band(lng, lat)) > 0.5:
                    gaps.append(h.area)
    overlap = sum(g.area for g in geoms) - u.area
    return {"tile": f"{z}/{x}/{y}", "features": len(geoms), "covered_px2": round(u.area, 1),
            "holes": len(holes), "gap_holes": len(gaps) if in_band else None,
            "gap_area_px2": round(sum(gaps), 4) if in_band else None,
            "overlap_px2": round(overlap, 4)}


if __name__ == "__main__":
    path = sys.argv[1]
    for t in sys.argv[2:]:
        z, x, y = map(int, t.split("/"))
        print(json.dumps(check(path, z, x, y)), flush=True)


def tile_of(lat, lng, z):
    n = 2 ** z
    lr = math.radians(lat)
    return (int((lng + 180) / 360 * n) % n,
            min(n - 1, max(0, int((1 - math.log(math.tan(lr) + 1 / math.cos(lr)) / math.pi) / 2 * n))))


def spot_check(path, places, zooms=(0, 2, 4, 6, 8, 10), radius=1, in_band=None):
    """Check a (2*radius+1)^2 block of tiles around each place at each zoom; return worst gap area."""
    worst = 0.0
    for name, (lat, lng) in places.items():
        for z in zooms:
            cx, cy = tile_of(lat, lng, z)
            n = 2 ** z
            seen = set()
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    x, y = (cx + dx) % n, cy + dy
                    if not 0 <= y < n or (x, y) in seen:
                        continue
                    seen.add((x, y))
                    r = check(path, z, x, y, in_band)
                    r["place"] = name
                    print(json.dumps(r), flush=True)
                    worst = max(worst, r.get("gap_area_px2") or 0)
    return worst
