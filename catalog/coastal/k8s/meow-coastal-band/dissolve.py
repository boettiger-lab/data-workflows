"""MEOW coastal band display layer (data-workflows #774).

Dissolves the meow-coastal-band H3 resolution 8 hex (#730) into one (multi)polygon per
ECO_CODE x side x distance class, writes a GeoParquet and a PMTiles of those features.
Runs inside the cluster job (dissolve.yaml) against the internal S3 endpoint.

Distance classes (upper-inclusive, so `dist_max_km <= X` selects exactly the hex cells with
`dist_km <= X`; coastline cells, dist_km = 0, fall in the first class):
  sea : [0,5]  (5,10]  (10,20]  (20,50]
  land: [0,5]  (5,10]  (10,20]

Geometry: exact cell-set -> polygon conversion per group with h3 `cells_to_h3shape` (no
ST_Union of hexagons), so adjacent groups share identical H3 edge vertices. Polygons that
cross the antimeridian are unwrapped to a continuous longitude range and split at 180.
area_km2 = SUM(h3_cell_area(h8, 'km^2')) over the feature's cells (DuckDB h3 extension).

Env: SRC, OUT_PARQUET, OUT_PMTILES (rclone targets), DUCKDB_MEM, AWS_* secrets.
"""
import json, os, subprocess, sys, time

import duckdb
import numpy as np
import h3.api.basic_int as h3i
import shapely
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.affinity import translate
from pyproj import Geod

SRC = os.environ.get("SRC", "s3://public-coastal/meow-coastal-band/hex/h0=*/data_0.parquet")
OUT_PARQUET = os.environ.get("OUT_PARQUET", "nrp:public-coastal/meow-coastal-band.parquet")
OUT_PMTILES = os.environ.get("OUT_PMTILES", "nrp:public-coastal/meow-coastal-band.pmtiles")
LAYER = "meow-coastal-band"
WORK = os.environ.get("WORK", "/tmp/work")
LOCAL = os.environ.get("LOCAL") == "1"          # local synthetic test: no S3, no upload
os.makedirs(WORK, exist_ok=True)

t0 = time.time()
def log(msg):
    print(f"[{(time.time() - t0) / 60:6.1f} min] {msg}", flush=True)

con = duckdb.connect(f"{WORK}/dissolve.duckdb")
for ext in ("h3 FROM community", "spatial", "httpfs"):
    con.execute(f"INSTALL {ext}; LOAD {ext.split()[0]}")
con.execute(f"SET temp_directory = '{WORK}/duckdb-tmp'; SET memory_limit = '{os.environ.get('DUCKDB_MEM', '24GB')}'")
if not LOCAL:
    con.execute("SET http_retries = 10; SET http_retry_wait_ms = 3000")
    con.execute(f"""CREATE OR REPLACE SECRET s3 (TYPE S3, KEY_ID '{os.environ["AWS_ACCESS_KEY_ID"]}',
        SECRET '{os.environ["AWS_SECRET_ACCESS_KEY"]}', ENDPOINT '{os.environ["AWS_S3_ENDPOINT"]}',
        URL_STYLE 'path', USE_SSL false)""")
q = lambda sql: con.execute(sql).fetchall()

# ---------------------------------------------------------------- classes
con.execute(f"""CREATE OR REPLACE TABLE cells AS
    SELECT h8::UBIGINT AS h8, ECO_CODE, ECOREGION, PROVINCE, REALM, side, dist_km,
           h3_cell_area(h8::UBIGINT, 'km^2') AS area
    FROM read_parquet('{SRC}')""")
n, nd = q("SELECT COUNT(*), COUNT(DISTINCT h8) FROM cells")[0]
log(f"hex cells: {n:,} ({nd:,} distinct)")
assert n == nd, "hex has duplicate h8"
bad = q("""SELECT COUNT(*) FROM cells WHERE dist_km IS NULL OR dist_km < 0 OR side NOT IN ('sea','land')
           OR (side = 'land' AND dist_km > 20) OR (side = 'sea' AND dist_km > 50)
           OR ECO_CODE IS NULL OR ECOREGION IS NULL OR PROVINCE IS NULL OR REALM IS NULL""")[0][0]
assert bad == 0, f"{bad} cells outside the expected side/distance domain or with NULL labels"
multi = q("""SELECT COUNT(*) FROM (SELECT ECO_CODE FROM cells GROUP BY 1
             HAVING COUNT(DISTINCT (ECOREGION, PROVINCE, REALM)) > 1)""")[0][0]
assert multi == 0, "an ECO_CODE carries more than one ECOREGION/PROVINCE/REALM"

con.execute("""CREATE OR REPLACE TABLE classed AS
    SELECT h8, ECO_CODE, side, area,
           CASE WHEN dist_km <= 5 THEN 0 WHEN dist_km <= 10 THEN 5 WHEN dist_km <= 20 THEN 10 ELSE 20 END::DOUBLE AS dist_min_km,
           CASE WHEN dist_km <= 5 THEN 5 WHEN dist_km <= 10 THEN 10 WHEN dist_km <= 20 THEN 20 ELSE 50 END::DOUBLE AS dist_max_km
    FROM cells""")
con.execute("""CREATE OR REPLACE TABLE groups AS
    SELECT (ROW_NUMBER() OVER (ORDER BY g.ECO_CODE, g.side DESC, g.dist_min_km) - 1)::INTEGER AS gid, g.*,
           l.ECOREGION, l.PROVINCE, l.REALM
    FROM (SELECT ECO_CODE, side, dist_min_km, dist_max_km, COUNT(*) AS n_cells, SUM(area) AS area_km2
          FROM classed GROUP BY ALL) g
    JOIN (SELECT DISTINCT ECO_CODE, ECOREGION, PROVINCE, REALM FROM cells) l USING (ECO_CODE)""")
ng, ne = q("SELECT COUNT(*), COUNT(DISTINCT ECO_CODE) FROM groups")[0]
log(f"groups (features): {ng:,} over {ne} ecoregions")
for r in q("SELECT side, dist_min_km, dist_max_km, COUNT(*), SUM(n_cells), MAX(n_cells), ROUND(SUM(area_km2)) FROM groups GROUP BY ALL ORDER BY 1 DESC, 2"):
    print("  class", r, flush=True)
log("largest groups by cell count:")
for r in q("SELECT gid, ECOREGION, side, dist_max_km, n_cells FROM groups ORDER BY n_cells DESC LIMIT 10"):
    print("  ", r, flush=True)
# reference for the acceptance check (per ecoregion and side, straight from the hex)
ref = {(r[0], r[1]): r[2] for r in q("SELECT ECO_CODE, side, SUM(area) FROM cells GROUP BY ALL")}

h8 = con.execute("""SELECT c.h8, g.gid FROM classed c JOIN groups g USING (ECO_CODE, side, dist_min_km)
                    ORDER BY g.gid""").fetchnumpy()
cells_arr, gid_arr = h8["h8"].astype(np.uint64), h8["gid"].astype(np.int64)
del h8
bounds = np.searchsorted(gid_arr, np.arange(ng + 1))
groups = con.execute("SELECT gid, ECO_CODE, ECOREGION, PROVINCE, REALM, side, dist_min_km, dist_max_km, n_cells, area_km2 FROM groups ORDER BY gid").fetchall()
con.execute("DROP TABLE classed; DROP TABLE cells")
log(f"cell ids loaded ({len(cells_arr):,})")

# ---------------------------------------------------------------- polygons
WORLD = box(-180, -90, 180, 90)
EAST = box(180, -90, 540, 90)

def ring_xy(ring):
    return [(lng, lat) for lat, lng in ring]

def crosses(xy):
    xs = [p[0] for p in xy]
    return any(abs(a - b) > 180 for a, b in zip(xs, xs[1:] + xs[:1]))

n_split = 0
def to_shapely(shape):
    """h3 LatLngPoly/LatLngMultiPoly -> shapely (Multi)Polygon in [-180, 180], split at 180."""
    global n_split
    polys = list(shape) if hasattr(shape, "__iter__") else [shape]
    out = []
    for p in polys:
        rings = [ring_xy(p.outer)] + [ring_xy(h) for h in p.holes]
        if any(crosses(r) for r in rings):
            n_split += 1
            rings = [[(x + 360 if x < 0 else x, y) for x, y in r] for r in rings]
            poly = Polygon(rings[0], rings[1:])
            xs = [x for r in rings for x, _ in r]
            assert max(xs) - min(xs) < 180, f"antimeridian polygon spans {max(xs)-min(xs):.1f} deg of longitude"
            if not poly.is_valid:
                poly = shapely.make_valid(poly)
            west = poly.intersection(WORLD)
            east = translate(poly.intersection(EAST), xoff=-360)
            for part in (west, east):
                out.extend(g for g in getattr(part, "geoms", [part]) if g.geom_type == "Polygon" and not g.is_empty)
        else:
            out.append(Polygon(rings[0], rings[1:]))
    # consistent orientation (exterior counter-clockwise, as RFC 7946 asks); the antimeridian
    # split's intersection() can return clockwise exteriors
    return shapely.orient_polygons(MultiPolygon(out), exterior_cw=False)

geod = Geod(ellps="WGS84")
gj = open(f"{WORK}/{LAYER}.geojsonl", "w")
rows = []
ratios, invalid = [], 0
for gid, eco, ecoregion, province, realm, side, dmin, dmax, ncell, area in groups:
    cs = cells_arr[bounds[gid]:bounds[gid + 1]].tolist()
    assert len(cs) == ncell
    geom = to_shapely(h3i.cells_to_h3shape(cs))
    if not geom.is_valid:
        invalid += 1
        print(f"  invalid geometry gid={gid} {ecoregion}/{side}/{dmax}: {shapely.is_valid_reason(geom)}; make_valid", flush=True)
        geom = shapely.make_valid(geom)
        geom = MultiPolygon([g for g in getattr(geom, "geoms", [geom]) if g.geom_type == "Polygon"])
    garea = abs(geod.geometry_area_perimeter(geom)[0]) / 1e6
    ratios.append(garea / area)
    if abs(garea / area - 1) > 0.02:
        print(f"  area outlier gid={gid} {ecoregion}/{side}/{dmax}: polygon {garea:.1f} km2 vs cells {area:.1f} km2", flush=True)
    props = {"_cng_fid": gid, "ECO_CODE": int(eco), "ECOREGION": ecoregion, "PROVINCE": province,
             "REALM": realm, "side": side, "dist_min_km": int(dmin), "dist_max_km": int(dmax),
             "area_km2": round(area, 3)}
    gj.write(json.dumps({"type": "Feature", "properties": props,
                         "geometry": shapely.geometry.mapping(geom)}) + "\n")
    rows.append((gid, eco, ecoregion, province, realm, side, dmin, dmax, area, shapely.to_wkb(geom)))
    if gid % 200 == 0:
        log(f"polygonized {gid + 1}/{ng}")
gj.close()
ratios = np.array(ratios)
log(f"polygonized {ng} features; antimeridian splits: {n_split}; invalid fixed: {invalid}; "
    f"geodesic polygon area / cell-area sum: min {ratios.min():.5f} median {np.median(ratios):.5f} max {ratios.max():.5f}")

# acceptance: per ecoregion and side, features' area_km2 sum == hex cell-area sum
acc = {}
for g in groups:
    acc[(g[1], g[5])] = acc.get((g[1], g[5]), 0) + g[9]
worst = max(abs(acc[k] / ref[k] - 1) for k in ref)
assert set(acc) == set(ref)
log(f"area check: {len(ref)} ecoregion x side pairs, worst relative difference {worst:.2e}")

# ---------------------------------------------------------------- GeoParquet (DuckDB-native)
import pyarrow as pa
tbl = pa.table({
    "_cng_fid": pa.array([r[0] for r in rows], pa.int64()),
    "ECO_CODE": pa.array([r[1] for r in rows], pa.float64()),
    "ECOREGION": [r[2] for r in rows], "PROVINCE": [r[3] for r in rows], "REALM": [r[4] for r in rows],
    "side": [r[5] for r in rows],
    "dist_min_km": pa.array([r[6] for r in rows], pa.float64()),
    "dist_max_km": pa.array([r[7] for r in rows], pa.float64()),
    "area_km2": pa.array([r[8] for r in rows], pa.float64()),
    "wkb": pa.array([r[9] for r in rows], pa.binary()),
})
con.register("feat", tbl)
con.execute(f"""COPY (SELECT * EXCLUDE (wkb), ST_GeomFromWKB(wkb) AS geom FROM feat ORDER BY _cng_fid)
    TO '{WORK}/{LAYER}.parquet' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 50)""")
log(f"GeoParquet written: {os.path.getsize(f'{WORK}/{LAYER}.parquet') / 1e6:.1f} MB")
print(q(f"SELECT COUNT(*), SUM(area_km2), COUNT(*) FILTER (WHERE NOT ST_IsValid(geom)) FROM read_parquet('{WORK}/{LAYER}.parquet')"), flush=True)

# ---------------------------------------------------------------- PMTiles
# os.cpu_count() reports the node's cores, not the container's; tippecanoe then aborts with
# "N shards not a power of 2". Use the container's CPU limit (a power of 2).
os.environ["TIPPECANOE_MAX_THREADS"] = os.environ.get("TIPPECANOE_MAX_THREADS", "16")
TIPPECANOE = ["tippecanoe", "-o", f"{WORK}/{LAYER}.pmtiles", "-l", LAYER, "--force", "-q",
              "-Z0", "-z10",
              f"--low-detail={os.environ.get('LOW_DETAIL', '14')}",  # finer grid below z10 so 5 km strips survive at z0-z2
              "--detect-shared-borders",              # simplify shared class/ecoregion edges identically
              "--no-simplification-of-shared-nodes",  # keep the nodes where three features meet
              "--no-feature-limit",
              "--no-tile-size-limit",                 # never drop or coalesce: one feature per class everywhere
              "--no-tiny-polygon-reduction",          # keep small island parts as drawn; dust leaves holes in
                                                      # the surrounding feature (z0 gap area 1.28 -> 0.19 px^2)
              f"{WORK}/{LAYER}.geojsonl"]
print(" ".join(TIPPECANOE), flush=True)
subprocess.run(["bash", "-c", "ulimit -n 65536 || true; exec \"$@\"", "_"] + TIPPECANOE, check=True)
log(f"PMTiles written: {os.path.getsize(f'{WORK}/{LAYER}.pmtiles') / 1e6:.1f} MB")
try:
    from pmtiles.reader import Reader, MmapSource, all_tiles
    with open(f"{WORK}/{LAYER}.pmtiles", "rb") as fh:
        rd = Reader(MmapSource(fh))
        print("  header:", {k: v for k, v in rd.header().items() if "zoom" in k or k.endswith("_e7")}, flush=True)
        sizes = {}
        for (z, x, y), data in all_tiles(rd.get_bytes):
            sizes.setdefault(z, []).append(len(data))
    for z in sorted(sizes):
        v = sizes[z]
        print(f"  z{z}: {len(v)} tiles, max {max(v) / 1e6:.2f} MB, mean {sum(v) / len(v) / 1e3:.0f} KB (compressed)", flush=True)
except ImportError:
    print("  (pmtiles reader not installed; tile sizes not reported)", flush=True)

# tile stats at low zoom: every feature must be present at z0, z1 and z2
for z in (0, 1, 2):
    seen = set()
    for x in range(2 ** z):
        for y in range(2 ** z):
            d = subprocess.run(["tippecanoe-decode", "-c", f"{WORK}/{LAYER}.pmtiles", str(z), str(x), str(y)],
                               capture_output=True, text=True)
            if d.returncode != 0 or "instead of" in d.stderr:   # tile absent (decode falls back to a parent)
                continue
            ids = [json.loads(l.rstrip().rstrip(","))["properties"]["_cng_fid"]
                   for l in d.stdout.splitlines() if l.startswith('{ "type": "Feature"')]
            print(f"  z{z}/{x}/{y}: {len(ids)} features, {len(set(ids))} distinct", flush=True)
            seen.update(ids)
    log(f"z{z}: {len(seen)} of {ng} features present")

# gap check: holes thinner than a pixel in the union of features = simplification gaps
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tilecheck import spot_check
PLACES = json.loads(os.environ.get("CHECK_PLACES", json.dumps({
    "Norway (Lofoten)": [68.2, 14.5], "Indonesia (Sulawesi)": [-2.5, 119.0], "Fiji (antimeridian)": [-16.8, 179.9]})))
band_sorted = np.sort(cells_arr)
def in_band(lng, lat):
    c = np.array([h3i.latlng_to_cell(float(a), float(b), 8) for a, b in zip(lat, lng)], dtype=np.uint64)
    i = np.clip(np.searchsorted(band_sorted, c), 0, len(band_sorted) - 1)
    return band_sorted[i] == c
worst = spot_check(f"{WORK}/{LAYER}.pmtiles", PLACES, in_band=in_band)
log(f"gap check: worst gap area (holes where the source cells are continuous) in any checked tile = {worst} px^2")

if not LOCAL and os.environ.get("UPLOAD", "1") == "1":
    for src, dst in ((f"{WORK}/{LAYER}.parquet", OUT_PARQUET), (f"{WORK}/{LAYER}.pmtiles", OUT_PMTILES)):
        subprocess.run(["rclone", "copyto", "--s3-no-check-bucket", src, dst], check=True)
        log(f"uploaded {dst}")
log("done")
