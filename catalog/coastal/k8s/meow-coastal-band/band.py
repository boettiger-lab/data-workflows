"""MEOW coastal band (data-workflows #730): one row per H3 h8 cell within 50 km (sea) /
20 km (land) of the ECU coastline, labelled with its MEOW ecoregion.

Runs inside the cluster job (band.yaml) against the internal S3 endpoint. Steps:
  1. seeds = distinct ECU h8 cells (k = 0, nearest coast cell = itself)
  2. multi-source ring expansion: each new cell takes, among its visited neighbours'
     nearest-coast cells, the one closest to its own centre. Expansion stops on distance
     (dist_km <= limit + MARGIN_KM), not on ring count, then the output is cut at the limit.
  3. side / land_frac from the Copernicus GLO-90 Water Body Mask hex (fractions reducer)
  4. MEOW label: single ecoregion -> 'polygon'; several -> centre-point containment,
     on_boundary = true; none -> nearest ecoregion polygon, label_source = 'nearest'
  5. depth_m (GEBCO, sea; positive down) and elevation_m (GLO-90 h9 -> h8 mean, land)
"""
import os, time
import duckdb

SEA_KM, LAND_KM, MARGIN_KM = 50.0, 20.0, 1.5
ECU = "s3://public-coastal/ecu/hex/h0=*/data_0.parquet"
WBM = "s3://public-dem/copernicus-glo90/wbm/hex/h0=*/data_0.parquet"
MEOW_HEX = "s3://public-high-seas/meow/ecoregions/hex/h0=*/data_00.parquet"
MEOW_POLY = "s3://public-high-seas/meow/ecoregions.parquet"
GEBCO = "s3://public-high-seas/gebco-2025/hex/h0=*/data_0.parquet"
GLO90 = "s3://public-dem/copernicus-glo90/hex/h0=*/data_0.parquet"
OUT = "s3://public-coastal/meow-coastal-band/hex"

t0 = time.time()
def log(msg):
    print(f"[{(time.time() - t0) / 60:6.1f} min] {msg}", flush=True)

con = duckdb.connect("/tmp/band.duckdb")
for ext in ("h3 FROM community", "spatial", "httpfs"):
    con.execute(f"INSTALL {ext}; LOAD {ext.split()[0]}")
con.execute(f"SET temp_directory = '/tmp/duckdb-tmp'; SET memory_limit = '{os.environ.get('DUCKDB_MEM', '100GB')}'")
con.execute("SET preserve_insertion_order = false; SET http_retries = 10; SET http_retry_wait_ms = 3000")
con.execute(f"""CREATE OR REPLACE SECRET s3 (TYPE S3, KEY_ID '{os.environ["AWS_ACCESS_KEY_ID"]}',
    SECRET '{os.environ["AWS_SECRET_ACCESS_KEY"]}', ENDPOINT '{os.environ["AWS_S3_ENDPOINT"]}',
    URL_STYLE 'path', USE_SSL false)""")
q = lambda sql: con.execute(sql).fetchall()

# --- land fraction per h8 (WBM classes: 0 not water, 1 ocean, 2 lake, 3 river; 255 no tile) ---
con.execute(f"""CREATE OR REPLACE TABLE land AS
    SELECT h8::UBIGINT AS h8, SUM(frac) FILTER (WHERE wbm_class IN (0, 2, 3)) AS land_frac
    FROM read_parquet('{WBM}') GROUP BY 1""")
log(f"land table: {q('SELECT COUNT(*) FROM land')[0][0]:,} cells")

# --- seeds ---
con.execute(f"""CREATE OR REPLACE TABLE visited AS
    SELECT h8, 0::USMALLINT AS k, h8 AS src,
           h3_cell_to_lat(h8) AS src_lat, h3_cell_to_lng(h8) AS src_lng, 0.0::DOUBLE AS dist_km
    FROM (SELECT DISTINCT h8::UBIGINT AS h8 FROM read_parquet('{ECU}'))""")
con.execute("CREATE OR REPLACE TABLE frontier AS SELECT * FROM visited")
log(f"seeds: {q('SELECT COUNT(*) FROM visited')[0][0]:,}")

# --- multi-source ring expansion ---
k = 0
while True:
    k += 1
    con.execute(f"""CREATE OR REPLACE TABLE cand AS
        WITH nb AS (
            SELECT UNNEST(h3_grid_disk(f.h8, 1)) AS h8, f.src, f.src_lat, f.src_lng FROM frontier f
        ), fresh AS (
            SELECT nb.* FROM nb ANTI JOIN visited v USING (h8)
        ), d AS (
            SELECT h8, src, src_lat, src_lng,
                   h3_great_circle_distance(h3_cell_to_lat(h8), h3_cell_to_lng(h8), src_lat, src_lng, 'km') AS dist_km
            FROM fresh
        )
        SELECT h8, arg_min(src, dist_km) AS src, arg_min(src_lat, dist_km) AS src_lat,
               arg_min(src_lng, dist_km) AS src_lng, MIN(dist_km) AS dist_km
        FROM d GROUP BY h8""")
    # side decides the limit; no WBM row = open ocean = sea
    con.execute(f"""CREATE OR REPLACE TABLE frontier AS
        SELECT c.h8, {k}::USMALLINT AS k, c.src, c.src_lat, c.src_lng, c.dist_km
        FROM cand c LEFT JOIN land l USING (h8)
        WHERE c.dist_km <= CASE WHEN COALESCE(l.land_frac, 0) >= 0.5 THEN {LAND_KM} ELSE {SEA_KM} END + {MARGIN_KM}""")
    n = q("SELECT COUNT(*) FROM frontier")[0][0]
    if n == 0:
        break
    con.execute("INSERT INTO visited SELECT * FROM frontier")
    if k % 5 == 0:
        log(f"ring {k}: +{n:,} (visited {q('SELECT COUNT(*) FROM visited')[0][0]:,})")
log(f"expansion done after {k - 1} rings; visited {q('SELECT COUNT(*) FROM visited')[0][0]:,}")

# --- side + exact cut ---
con.execute(f"""CREATE OR REPLACE TABLE band AS
    SELECT v.h8, h3_cell_to_parent(v.h8, 0)::BIGINT AS h0, v.k, v.dist_km,
           COALESCE(l.land_frac, 0) AS land_frac,
           CASE WHEN COALESCE(l.land_frac, 0) >= 0.5 THEN 'land' ELSE 'sea' END AS side
    FROM visited v LEFT JOIN land l USING (h8)
    WHERE v.dist_km <= CASE WHEN COALESCE(l.land_frac, 0) >= 0.5 THEN {LAND_KM} ELSE {SEA_KM} END""")
log(f"band: {q('SELECT COUNT(*) FROM band')[0][0]:,} cells")

# --- MEOW labels ---
con.execute(f"""CREATE OR REPLACE TABLE meow AS
    SELECT DISTINCT m.h8::UBIGINT AS h8, m.ECO_CODE, m.ECOREGION, m.PROVINCE, m.REALM
    FROM read_parquet('{MEOW_HEX}') m SEMI JOIN band b ON b.h8 = m.h8::UBIGINT""")
con.execute(f"CREATE OR REPLACE TABLE poly AS SELECT ECO_CODE, ECOREGION, PROVINCE, REALM, geom FROM read_parquet('{MEOW_POLY}')")
con.execute("""CREATE OR REPLACE TABLE lab AS
    WITH n AS (SELECT h8, COUNT(*) AS n FROM meow GROUP BY h8)
    SELECT m.h8, m.ECO_CODE, m.ECOREGION, m.PROVINCE, m.REALM, false AS on_boundary, 'polygon' AS label_source
    FROM meow m JOIN n USING (h8) WHERE n.n = 1""")
# boundary cells: ecoregion whose polygon contains the cell centre; ties/gaps -> lowest ECO_CODE among the cell's ecoregions
con.execute("""INSERT INTO lab
    WITH multi AS (SELECT h8 FROM meow GROUP BY h8 HAVING COUNT(*) > 1),
    cand AS (
        SELECT m.*, ST_Contains(p.geom, ST_Point(h3_cell_to_lng(m.h8), h3_cell_to_lat(m.h8))) AS contains
        FROM meow m SEMI JOIN multi USING (h8) JOIN poly p USING (ECO_CODE))
    SELECT h8, arg_min(ECO_CODE, (NOT contains, ECO_CODE)), arg_min(ECOREGION, (NOT contains, ECO_CODE)),
           arg_min(PROVINCE, (NOT contains, ECO_CODE)), arg_min(REALM, (NOT contains, ECO_CODE)), true, 'polygon'
    FROM cand GROUP BY h8""")
# cells in no MEOW hex cell: nearest polygon (bbox-limited candidates, widen if none)
con.execute("CREATE OR REPLACE TABLE orphan AS SELECT h8 FROM band ANTI JOIN lab USING (h8)")
log(f"orphans (no MEOW cell): {q('SELECT COUNT(*) FROM orphan')[0][0]:,}")
con.execute("""INSERT INTO lab
    WITH pts AS (SELECT h8, ST_Point(h3_cell_to_lng(h8), h3_cell_to_lat(h8)) AS pt FROM orphan),
    d AS (SELECT pts.h8, p.ECO_CODE, p.ECOREGION, p.PROVINCE, p.REALM, ST_Distance(p.geom, pts.pt) AS dd
          FROM pts JOIN poly p ON ST_DWithin(p.geom, pts.pt, 2.0))
    SELECT h8, arg_min(ECO_CODE, dd), arg_min(ECOREGION, dd), arg_min(PROVINCE, dd), arg_min(REALM, dd), false, 'nearest'
    FROM d GROUP BY h8""")
left = q("SELECT COUNT(*) FROM band ANTI JOIN lab USING (h8)")[0][0]
assert left == 0, f"{left} cells still unlabelled (no MEOW polygon within 2 degrees)"

# --- depth / elevation ---
con.execute(f"""CREATE OR REPLACE TABLE geb AS
    SELECT g.h8::UBIGINT AS h8, g.elevation FROM read_parquet('{GEBCO}') g SEMI JOIN band b ON b.h8 = g.h8::UBIGINT""")
con.execute(f"""CREATE OR REPLACE TABLE glo AS
    SELECT g.h8::UBIGINT AS h8, AVG(g.elevation) AS elevation FROM read_parquet('{GLO90}') g
    SEMI JOIN band b ON b.h8 = g.h8::UBIGINT GROUP BY 1""")

# --- write ---
con.execute(f"""COPY (
    SELECT b.h8, l.ECO_CODE, l.ECOREGION, l.PROVINCE, l.REALM, l.on_boundary, l.label_source,
           b.side, b.land_frac, b.k, b.dist_km,
           CASE WHEN b.side = 'sea' THEN -geb.elevation END AS depth_m,
           CASE WHEN b.side = 'land' THEN glo.elevation END AS elevation_m,
           b.h0
    FROM band b JOIN lab l USING (h8) LEFT JOIN geb USING (h8) LEFT JOIN glo USING (h8)
    ORDER BY b.h0, b.h8
) TO '{OUT}' (FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY (h0), FILENAME_PATTERN 'data_{{i}}', OVERWRITE_OR_IGNORE)""")
log("written")
for row in q(f"""SELECT side, label_source, on_boundary, COUNT(*), MAX(dist_km), MAX(k)
               FROM read_parquet('{OUT}/h0=*/data_0.parquet') GROUP BY ALL ORDER BY ALL"""):
    print(row)
print(q(f"SELECT COUNT(*), COUNT(DISTINCT h8), COUNT(DISTINCT ECO_CODE) FROM read_parquet('{OUT}/h0=*/data_0.parquet')"))
