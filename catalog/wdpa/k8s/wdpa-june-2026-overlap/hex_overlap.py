#!/usr/bin/env python3
"""H3 'overlap' hex with a per-(feature, cell) coverage fraction (#1000).

HAND-ROLLED: cng-datasets polyfills polygons by cell centre only and has no
coverage fraction; this is the shape requested from the tool in
boettiger-lab/datasets#363 (#1000).

For every polygon feature of a GeoParquet, write one row per H3 cell the
feature's interior overlaps:

    <id>  BIGINT   feature key (default _cng_fid)
    h<R>  UBIGINT  the cell at native resolution R (default 9)
    cover_frac FLOAT   share of the cell's area inside the feature, in (0, 1]
    h<P>  UBIGINT  one column per parent resolution (default 8, 0)

Cells are found with H3's polygon-to-cells in 'overlap' containment, per part
after ST_Dump. Cells H3 also returns in 'full' containment lie wholly inside
the part, so their fraction is exactly 1 and no intersection is computed.
Only the remaining boundary cells are intersected with the part, after
clipping the part to the bounding box of each group of boundary cells that
share a coarse ancestor (h<R-4>), so a 100k-vertex coastline is never
intersected whole against each cell. Fractions are planar lon/lat area ratios,
which at res 9 differ from geodesic ratios by well under 0.1%. Parts of one
feature are summed per cell and capped at 1; cells whose overlap has zero area
(touching only along an edge or at a vertex) are dropped. A feature left with
no row (zero-area geometry) gets the cell at its point-on-surface with
cover_frac NULL, and the count of those is printed.

Antimeridian: WDPA splits features at +/-180, so a part never crosses it, but
a cell can. Such a cell's boundary is unwrapped to x in [180 - e, 180 + e] and
intersected with the part both as-is and shifted by +360, and the two areas
are summed.

Modes
  plan   --source S --plan-out P --target-cells N [--max-features M]
         Assign every feature to a chunk so that each chunk's estimated cell
         count stays near N; features estimated above N get a chunk alone.
  sample --source S --plan-out P --per-stratum K [--top T] [--target-cells N]
         Area-stratified sample (K per GIS_AREA decade + the T largest
         features), chunked the same way as plan. Writes the plan only.
  hex    --source S --plan P --chunk C --out PREFIX
         Process chunk C of the plan, write PREFIX/chunk_<C>.parquet.
"""
import argparse
import os
import resource
import subprocess
import sys
import time

import duckdb

CELL_KM2 = {8: 0.7373, 9: 0.1053, 10: 0.01504}  # H3 average cell area


def connect(mem_limit=None, threads=None, db=":memory:"):
    con = duckdb.connect(db)
    con.execute("INSTALL spatial; LOAD spatial; INSTALL h3 FROM community; LOAD h3")
    from cng_datasets.storage.s3 import configure_s3_credentials
    configure_s3_credentials(con)
    try:
        con.execute("SET geometry_always_xy = true")  # DuckDB >= 2.0 requires it explicitly
    except duckdb.Error:
        pass
    con.execute("SET preserve_insertion_order = false")
    con.execute("SET temp_directory = '/tmp/duckdb_tmp'")
    con.execute("SET http_timeout = 120; SET http_retries = 10; SET http_retry_wait_ms = 2000")
    if mem_limit:
        con.execute(f"SET memory_limit = '{mem_limit}'")
    if threads:
        con.execute(f"SET threads = {int(threads)}")
    return con


def log(msg, t0=[time.time()]):
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576
    print(f"[{time.time() - t0[0]:8.1f}s maxrss={rss:6.2f}GiB] {msg}", flush=True)


# Estimated cells of a feature: area cells plus a boundary allowance. The
# boundary term (one ring of cells per edge-length of perimeter, approximated
# from the vertex count and area) only matters for the many small features.
EST_SQL = """
  ceil({area} / {cell}) + 8 + least(ST_NPoints(SHAPE), 4 * sqrt({area} / {cell}) + 8)
"""


def write_plan(con, src_sql, a):
    """Chunk the features of src_sql (which must carry a `tag` column).

    A feature weighs est/target_cells + vertices/target_vertices: rows drive
    the output and the fraction step, vertices drive the polyfill (a probe
    chunk of 44.8M vertices filled for >10 min on 4 cores). Features weighing
    >= 1 get a chunk each (heaviest first); the rest are packed in id order
    (contiguous ids, so each chunk reads few row groups) until a chunk's
    weight reaches 1."""
    est = EST_SQL.format(cell=CELL_KM2[a.res], area=a.area_col)
    w = f"(est / {a.target_cells} + npts / {a.target_vertices})"
    con.execute(f"""
      CREATE TEMP TABLE b AS
      WITH f AS (SELECT {a.id} AS fid, tag, {a.area_col} AS area_km2, ST_NPoints(SHAPE) AS npts,
                        {est} AS est FROM ({src_sql})),
      o AS (SELECT *, {w} AS weight, sum({w}) FILTER (WHERE {w} < 1)
                        OVER (ORDER BY fid ROWS UNBOUNDED PRECEDING) AS cum FROM f)
      SELECT *, CASE WHEN weight >= 1 THEN NULL ELSE floor(cum) END AS bucket FROM o
    """)
    con.execute("""
      CREATE TEMP TABLE plan AS
      WITH g AS (SELECT * EXCLUDE (cum, bucket), row_number() OVER (ORDER BY weight DESC) - 1 AS chunk
                 FROM b WHERE bucket IS NULL),
           r AS (SELECT * EXCLUDE (cum, bucket),
                        (SELECT count(*) FROM g) + dense_rank() OVER (ORDER BY bucket) - 1 AS chunk
                 FROM b WHERE bucket IS NOT NULL)
      SELECT * FROM g UNION ALL SELECT * FROM r
    """)
    con.execute(f"COPY (SELECT * FROM plan ORDER BY chunk, fid) TO '{a.plan_out}' (FORMAT PARQUET)")
    r = con.execute("SELECT count(DISTINCT chunk), count(*), sum(est)::BIGINT, max(est)::BIGINT FROM plan").fetchone()
    log(f"plan: {r[0]} chunks, {r[1]:,} features, est {r[2]:,} cells, max/feature {r[3]:,}")
    for row in con.execute("SELECT tag, count(*) FROM plan GROUP BY 1 ORDER BY 1").fetchall():
        log(f"  {row[0]}: {row[1]}")


def mode_plan(a):
    con = connect()
    write_plan(con, f"SELECT *, 'all' AS tag FROM read_parquet('{a.source}')", a)


def mode_sample(a):
    """Area-stratified sample: --per-stratum random features per decade of
    area, the --top largest, and (optional) the features --include-sql picks.
    The tag column says why each feature is in the sample, so estimates can
    weight the stratified part by stratum size."""
    con = connect()
    con.execute(f"CREATE VIEW src AS SELECT * FROM read_parquet('{a.source}')")
    inc = a.include_sql.replace("{src}", "src") if a.include_sql else "SELECT NULL::BIGINT AS fid, NULL AS tag WHERE false"
    con.execute(f"CREATE TEMP TABLE inc AS {inc}")
    log(f"include-sql picked {con.execute('SELECT count(*) FROM inc').fetchone()[0]} features")
    con.execute(f"""
      CREATE TEMP TABLE pick AS
      WITH r AS (SELECT {a.id} AS fid,
                   row_number() OVER (PARTITION BY floor(log10(greatest({a.area_col}, 1e-6)))
                                      ORDER BY hash({a.id} * 7919)) AS rk,
                   row_number() OVER (ORDER BY {a.area_col} DESC) AS top FROM src)
      SELECT fid, 'top' AS tag FROM r WHERE top <= {a.top}
      UNION ALL SELECT fid, 'strat' FROM r WHERE rk <= {a.per_stratum} AND top > {a.top}
      UNION ALL SELECT fid, any_value(tag) FROM inc
        WHERE fid NOT IN (SELECT fid FROM r WHERE top <= {a.top} OR rk <= {a.per_stratum}) GROUP BY fid
    """)
    write_plan(con, f"SELECT s.*, p.tag FROM src s JOIN pick p ON s.{a.id} = p.fid", a)
    con.execute(f"""COPY (SELECT floor(log10(greatest({a.area_col}, 1e-6)))::INT AS decade, count(*) AS n,
                          sum({a.area_col}) AS area_km2 FROM src GROUP BY 1 ORDER BY 1)
                    TO '{a.plan_out.replace('.parquet', '-strata.parquet')}' (FORMAT PARQUET)""")


# A part whose polyfill would be slow is cut into boxes first. H3 tests each
# candidate cell against the polygon's edges, so fill time grows with
# cells x vertices: one 15M-cell, 7,100-vertex part did not finish in 7 min
# single-threaded, and cut into boxes it filled in 11 s, since a box in the
# interior has 4 vertices. Cutting repeats (up to CUT_ROUNDS) on any piece
# whose est. cells x vertices still exceeds PIECE_WORK. A round cuts a piece
# into at most CUT_CLIP_WORK / vertices boxes (4 to CUT_MAX_BOXES), so a
# 144k-vertex coastline is quartered a few times rather than clipped against
# a thousand boxes at once (79 s and 8 GiB). A cell
# that straddles a box edge is a boundary cell of each box it meets and gets
# its fraction from each, summed per feature below, so cutting changes no
# result.
PIECE_WORK = 2_000_000  # 2e7 left chunk 80 of the full plan at 304 s of fill; 2e6 took 117 s
CUT_MAX_BOXES = 1024
CUT_ROUNDS = 8
CUT_CLIP_WORK = 4_000_000  # boxes x vertices clipped per piece per round
MIN_SIDE = 0.02  # degrees
SNAP = 1e-6                  # summed fractions within SNAP of 1 are written as 1


def mode_hex(a):
    import concurrent.futures as cf
    os.makedirs("/tmp/duckdb_tmp", exist_ok=True)
    if os.path.exists("/tmp/work.duckdb"):
        os.remove("/tmp/work.duckdb")
    con = connect(a.memory_limit, a.threads, db="/tmp/work.duckdb")
    nthreads = int(a.threads or os.cpu_count() or 1)
    R = a.res
    C = max(R - 4, 0)  # clip-group ancestor resolution
    parents = [int(p) for p in a.parents.split(",") if p.strip()]
    fids = [r[0] for r in con.execute(
        f"SELECT fid FROM read_parquet('{a.plan}') WHERE chunk = {a.chunk}").fetchall()]
    if not fids:
        log(f"chunk {a.chunk}: not in plan, nothing to do")
        return
    log(f"chunk {a.chunk}: {len(fids)} features")
    con.execute("CREATE TABLE want (fid BIGINT)")
    con.executemany("INSERT INTO want VALUES (?)", [(f,) for f in fids])
    con.execute(f"""
      CREATE TABLE parts AS
      SELECT fid, row_number() OVER () AS pid, g, ST_NPoints(g) AS npts,
             ST_Area_Spheroid(g) / 1e6 / {CELL_KM2[R]} AS est
      FROM (SELECT s.{a.id} AS fid, UNNEST(ST_Dump(ST_Multi(ST_Force2D(s.SHAPE)))).geom AS g
            FROM read_parquet('{a.source}') s SEMI JOIN want w ON s.{a.id} = w.fid
            WHERE s.{a.id} BETWEEN {min(fids)} AND {max(fids)})
      WHERE NOT ST_IsEmpty(g)
    """)
    n_parts, n_pts = con.execute("SELECT count(*), sum(npts) FROM parts").fetchone()
    log(f"read {n_parts} parts, {n_pts:,} vertices")

    # 0. Pieces: cut parts whose fill would be slow into boxes, repeatedly.
    con.execute("CREATE TABLE pc AS SELECT row_number() OVER () AS qid, pid, fid, g, npts, est FROM parts")
    for rnd in range(CUT_ROUNDS):
        heavy = f"est * npts > {a.piece_work}"
        n_heavy = con.execute(f"SELECT count(*) FROM pc WHERE {heavy}").fetchone()[0]
        if not n_heavy:
            break
        con.execute(f"""
          CREATE OR REPLACE TABLE boxes AS
          WITH h AS (SELECT qid, pid, fid, g, ST_XMin(g) AS x0, ST_XMax(g) AS x1, ST_YMin(g) AS y0, ST_YMax(g) AS y1,
                            greatest(sqrt((ST_XMax(g) - ST_XMin(g)) * (ST_YMax(g) - ST_YMin(g))
                                          / least(ceil(est * npts / {a.piece_work}),
                                                greatest(ceil({CUT_CLIP_WORK} / npts), 4), {CUT_MAX_BOXES})),
                                     {MIN_SIDE}) AS sd
                     FROM pc WHERE {heavy}),
          x AS (SELECT *, UNNEST(range(floor(x0 / sd)::BIGINT, ceil(x1 / sd)::BIGINT)) AS ix FROM h),
          xy AS (SELECT *, UNNEST(range(floor(y0 / sd)::BIGINT, ceil(y1 / sd)::BIGINT)) AS iy FROM x)
          SELECT pid, fid, g, ST_MakeEnvelope(ix * sd, iy * sd, (ix + 1) * sd, (iy + 1) * sd) AS box FROM xy
        """)
        con.execute(f"""
          CREATE OR REPLACE TABLE pc2 AS
          SELECT pid, fid, g FROM pc WHERE NOT ({heavy})
          UNION ALL
          SELECT pid, fid, UNNEST(ST_Dump(ST_CollectionExtract(ST_Intersection(g, box), 3))).geom
          FROM boxes WHERE ST_Intersects(g, box)
        """)
        con.execute(f"""
          CREATE OR REPLACE TABLE pc AS
          SELECT row_number() OVER () AS qid, pid, fid, g, ST_NPoints(g) AS npts,
                 ST_Area_Spheroid(g) / 1e6 / {CELL_KM2[R]} AS est
          FROM pc2 WHERE NOT ST_IsEmpty(g)
        """)
        log(f"cut round {rnd + 1}: {n_heavy} heavy pieces -> {con.execute('SELECT count(*) FROM pc').fetchone()[0]:,} pieces")
    con.execute("DROP TABLE IF EXISTS boxes; DROP TABLE IF EXISTS pc2")
    # Deal pieces to threads heaviest first (qid % threads), so one thread
    # does not end up holding most of the work.
    con.execute("""CREATE OR REPLACE TABLE pc AS
                   SELECT row_number() OVER (ORDER BY est * npts DESC) AS qid, pid, fid, g, npts, est FROM pc""")
    n_pc, pc_pts = con.execute("SELECT count(*), sum(ST_NPoints(g)) FROM pc").fetchone()
    log(f"{n_pc:,} pieces, {pc_pts:,} vertices")

    # 1. Polyfill each piece in 'overlap' and 'full' containment, spread over
    #    threads (DuckDB runs a scalar over a small table on one thread).
    con.execute("CREATE TABLE ov (qid BIGINT, cell UBIGINT); CREATE TABLE fu (qid BIGINT, cell UBIGINT)")

    def fill(k):
        cur = con.cursor()
        for tbl, mode in (("ov", "overlap"), ("fu", "full")):
            cur.execute(f"""INSERT INTO {tbl} SELECT qid,
                UNNEST(h3_polygon_wkb_to_cells_experimental(ST_AsWKB(g), '{mode}', {R}))
                FROM pc WHERE qid % {nthreads} = {k}""")
        cur.close()
    with cf.ThreadPoolExecutor(nthreads) as ex:
        list(ex.map(fill, range(nthreads)))
    n_ov = con.execute("SELECT count(*) FROM ov").fetchone()[0]
    n_fu = con.execute("SELECT count(*) FROM fu").fetchone()[0]
    log(f"polyfill: overlap {n_ov:,} (piece, cell) pairs, full {n_fu:,}")

    # 2. Boundary cells = overlap minus full, with each cell's polygon,
    #    unwrapped if it crosses the antimeridian.
    con.execute(f"""
      CREATE TABLE bnd AS
      WITH b AS (SELECT qid, cell FROM ov ANTI JOIN fu USING (qid, cell)),
      g AS (SELECT qid, cell, ST_GeomFromWKB(h3_cell_to_boundary_wkb(cell)) AS cg FROM b)
      SELECT qid, cell, h3_cell_to_parent(cell, {C}) AS grp,
             CASE WHEN ST_XMax(cg) - ST_XMin(cg) > 180 THEN
               ST_MakePolygon(ST_MakeLine(list_transform(
                 range(1, ST_NPoints(ST_ExteriorRing(cg)) + 1),
                 lambda i: ST_Point(
                   CASE WHEN ST_X(ST_PointN(ST_ExteriorRing(cg), i::INTEGER)) < 0
                        THEN ST_X(ST_PointN(ST_ExteriorRing(cg), i::INTEGER)) + 360
                        ELSE ST_X(ST_PointN(ST_ExteriorRing(cg), i::INTEGER)) END,
                   ST_Y(ST_PointN(ST_ExteriorRing(cg), i::INTEGER))))))
             ELSE cg END AS cg,
             ST_XMax(cg) - ST_XMin(cg) > 180 AS am
      FROM g
    """)
    con.execute("DROP TABLE ov")
    n_b, n_am = con.execute("SELECT count(*), count(*) FILTER (WHERE am) FROM bnd").fetchone()
    log(f"boundary (piece, cell) pairs {n_b:,} ({n_am} cross the antimeridian)")

    # 3. Clip each piece to the bbox of each group of its boundary cells
    #    (shared h<R-4> ancestor), then intersect each cell with its group's
    #    clip only. Crossing cells also meet the piece shifted by +360.
    con.execute("""
      CREATE TABLE clip AS
      WITH e AS (SELECT qid, grp, am, ST_GeomFromWKB(ST_AsWKB(ST_Extent_Agg(cg))) AS env
                 FROM bnd GROUP BY qid, grp, am)
      SELECT e.qid, e.grp, e.am, ST_Intersection(p.g, e.env) AS c0,
             CASE WHEN e.am THEN ST_Intersection(ST_Translate(p.g, 360, 0), e.env) END AS c1
      FROM e JOIN pc p USING (qid)
    """)
    log("clipped pieces to boundary groups")
    con.execute("""
      CREATE TABLE bfrac AS
      SELECT b.qid, b.cell,
             (ST_Area(ST_Intersection(b.cg, c.c0))
              + coalesce(ST_Area(ST_Intersection(b.cg, c.c1)), 0)) / ST_Area(b.cg) AS frac
      FROM bnd b JOIN clip c USING (qid, grp, am)
    """)
    log("boundary fractions done")

    # 4. Per feature: sum pieces per cell, snap/cap at 1, drop zero area.
    pcols = ", ".join(f"h3_cell_to_parent(cell, {p}) AS h{p}" for p in parents)
    out = f"/tmp/chunk_{a.chunk:06d}.parquet"
    con.execute(f"""
      CREATE TABLE res AS
      WITH u AS (SELECT qid, cell, 1.0::DOUBLE AS frac FROM fu
                 UNION ALL SELECT qid, cell, frac FROM bfrac),
      f AS (SELECT p.fid, u.cell, sum(u.frac) AS frac
            FROM u JOIN pc p USING (qid) GROUP BY p.fid, u.cell)
      SELECT fid, cell, CASE WHEN frac >= 1 - {SNAP} THEN 1.0 ELSE frac END::FLOAT AS frac
      FROM f WHERE frac > 0
    """)
    # Zero-area features keep one cell, at a point on their largest part, frac NULL.
    con.execute(f"""
      INSERT INTO res
      SELECT fid, h3_latlng_to_cell(ST_Y(pos), ST_X(pos), {R}), NULL
      FROM (SELECT fid, ST_PointOnSurface(arg_max(g, npts)) AS pos FROM parts GROUP BY fid)
      ANTI JOIN (SELECT DISTINCT fid FROM res) r USING (fid)
    """)
    # Features whose geometry is empty or missing never made a part.
    n_nogeom = con.execute("SELECT count(*) FROM want ANTI JOIN (SELECT DISTINCT fid FROM res) r USING (fid)").fetchone()[0]
    if n_nogeom:
        log(f"WARNING: {n_nogeom} features have no geometry and no row")
    nf, nrows, n1, nnull = con.execute(
        "SELECT count(DISTINCT fid), count(*), count(*) FILTER (WHERE frac = 1), "
        "count(*) FILTER (WHERE frac IS NULL) FROM res").fetchone()
    con.execute(f"""
      COPY (SELECT fid AS {a.id}, cell AS h{R}, frac AS cover_frac, {pcols}
            FROM res ORDER BY h0, {a.id}, h{R})
      TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE {a.row_group_size})
    """)
    log(f"chunk {a.chunk}: {nf}/{len(fids)} features, {nrows:,} rows "
        f"({n1:,} with cover_frac 1, {nrows - n1 - nnull:,} partial), {nnull} with no area; "
        f"{os.path.getsize(out) / 1e6:.1f} MB")
    if a.out.startswith(("s3://", "nrp:")):
        dest = a.out.replace("s3://", "nrp:").rstrip("/") + f"/chunk_{a.chunk:06d}.parquet"
        subprocess.run(["rclone", "copyto", out, dest, "--retries", "10",
                        "--low-level-retries", "20"], check=True)
        log(f"uploaded {dest}")
    else:
        os.makedirs(a.out, exist_ok=True)
        os.replace(out, os.path.join(a.out, os.path.basename(out)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["plan", "sample", "hex"])
    ap.add_argument("--source", required=True)
    ap.add_argument("--id", default="_cng_fid")
    ap.add_argument("--res", type=int, default=9)
    ap.add_argument("--parents", default="8,0")
    ap.add_argument("--plan")
    ap.add_argument("--plan-out")
    ap.add_argument("--target-cells", type=int, default=8_000_000)
    ap.add_argument("--target-vertices", type=int, default=4_000_000)
    ap.add_argument("--per-stratum", type=int, default=60)
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--area-col", default="GIS_AREA", help="feature area in km2, used only to plan chunks")
    ap.add_argument("--include-sql", default="",
                    help="sample: SQL returning (fid, tag) of extra features; {src} names the source table")
    ap.add_argument("--chunk", type=int)
    ap.add_argument("--out")
    ap.add_argument("--memory-limit")
    ap.add_argument("--threads")
    ap.add_argument("--piece-work", type=float, default=PIECE_WORK,
                    help="cut a part whose est. cells x vertices exceeds this")
    ap.add_argument("--row-group-size", type=int, default=100_000)
    a = ap.parse_args()
    {"plan": mode_plan, "sample": mode_sample, "hex": mode_hex}[a.mode](a)


if __name__ == "__main__":
    sys.exit(main())
