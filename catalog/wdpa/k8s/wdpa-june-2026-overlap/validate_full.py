#!/usr/bin/env python3
"""Validate the full overlap + cover_frac hex against the source (#1000).

    validate_full.py --source S --hex 'PREFIX/h0=*/data_0.parquet' --reference 'PUBLISHED/h0=*/data_0.parquet' --out PREFIX

Checks every parcel is present, cover_frac is in (0, 1] with no NULLs, no
(parcel, h9) pair repeats, the schema equals the reference hex plus cover_frac,
and area from fractions agrees with ST_Area_Spheroid per decade of GIS_AREA.

Cell areas: h3_cell_area is spherical (authalic radius), ~0.5% off WGS84 by
latitude. Over 680M cells ST_Area_Spheroid per cell is too slow, so each cell's
spherical area is scaled by the WGS84 / sphere area-element ratio at its
centre, a2(1-e2) / (R2 (1 - e2 sin2 lat)2). The script first checks that
scaling against ST_Area_Spheroid on 20,000 sampled cells.

Two reference areas per parcel: ST_Area_Spheroid (geodesic edges, as GIS_AREA)
and the straight-edge area, the WGS84 area of the polygon with every edge
densified to 0.01 degree in lon/lat (shapely.segmentize + pyproj.Geod), which
is the convention H3 and the fractions use. The hex should match the
straight-edge area to ~1e-4; the geodesic one differs by up to ~1.6% on large
parcels with long edges.
"""
import argparse
import os
import duckdb
from cng_datasets.storage.s3 import configure_s3_credentials

import multiprocessing as mp


def _straight(batch):
    """Straight-edge WGS84 area (km2) of each polygon: edges densified to 0.01 degree."""
    import shapely
    from pyproj import Geod
    geod = Geod(ellps="WGS84")
    fids, wkbs = batch
    geoms = shapely.segmentize(shapely.from_wkb(wkbs), 0.01)
    return [(f, abs(geod.geometry_area_perimeter(g)[0]) / 1e6) for f, g in zip(fids, geoms)]


if __name__ == "__main__":
    # Fork the workers before DuckDB starts its threads.
    POOL = mp.get_context("fork").Pool(int(os.environ.get("CNG_POD_CPU", "8")))

    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--hex", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--id", default="_cng_fid")
    a = ap.parse_args()

    con = duckdb.connect("/tmp/valfull.duckdb")
    con.execute("INSTALL spatial; LOAD spatial; INSTALL h3 FROM community; LOAD h3")
    configure_s3_credentials(con)
    con.execute("SET geometry_always_xy = true; SET preserve_insertion_order = false; SET temp_directory = '/tmp/duckdb_tmp'")
    A, E2, R = 6378.137, 0.00669437999014, 6371.007180918475
    con.execute(f"""CREATE MACRO ell_km2(c) AS h3_cell_area(c, 'km^2') * {A * A * (1 - E2)} /
                    ({R * R} * pow(1 - {E2} * pow(sin(radians(h3_cell_to_lat(c))), 2), 2))""")


    def show(title, sql):
        print(f"\n== {title}", flush=True)
        con.sql(sql).show(max_width=250, max_rows=80)


    show("schema: reference (published) vs new hex", f"""
      WITH r AS (SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM read_parquet('{a.reference}', hive_partitioning = false))),
           n AS (SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM read_parquet('{a.hex}', hive_partitioning = false)))
      SELECT coalesce(r.column_name, n.column_name) AS col, r.column_type AS reference, n.column_type AS new
      FROM r FULL JOIN n USING (column_name)
      WHERE r.column_type IS DISTINCT FROM n.column_type""")

    show("ellipsoid scaling vs ST_Area_Spheroid of the cell polygon (20,000 cells)", f"""
      WITH c AS (SELECT h9 FROM read_parquet('{a.hex}') USING SAMPLE 20000 ROWS)
      SELECT max(abs(ell_km2(h9) / (ST_Area_Spheroid(ST_GeomFromWKB(h3_cell_to_boundary_wkb(h9))) / 1e6) - 1)) AS max_rel_diff,
             avg(abs(ell_km2(h9) / (ST_Area_Spheroid(ST_GeomFromWKB(h3_cell_to_boundary_wkb(h9))) / 1e6) - 1)) AS mean_rel_diff
      FROM c""")

    con.execute(f"""
      CREATE TABLE agg AS
      SELECT {a.id} AS fid, count(*) AS n_rows,
             count(*) FILTER (WHERE cover_frac = 1) AS n_full,
             count(*) FILTER (WHERE cover_frac IS NULL) AS n_null,
             count(*) FILTER (WHERE cover_frac <= 0 OR cover_frac > 1) AS n_out,
             min(cover_frac) AS fmin, max(cover_frac) AS fmax,
             sum(cover_frac * ell_km2(h9)) AS km2_hex
      FROM read_parquet('{a.hex}') GROUP BY 1
    """)
    con.execute(f"""CREATE TABLE src AS SELECT {a.id} AS fid, GIS_AREA, ST_Area_Spheroid(SHAPE) / 1e6 AS km2_poly
                    FROM read_parquet('{a.source}')""")
    show("coverage and cover_frac", """
      SELECT (SELECT count(*) FROM src) AS source_parcels,
             (SELECT count(*) FROM agg) AS hex_parcels,
             (SELECT count(*) FROM src ANTI JOIN agg USING (fid)) AS parcels_missing,
             (SELECT count(*) FROM agg ANTI JOIN src USING (fid)) AS parcels_unknown,
             sum(n_rows) AS rows, sum(n_full) AS rows_frac_1, sum(n_null) AS rows_null,
             sum(n_out) AS rows_out_of_range, min(fmin) AS frac_min, max(fmax) AS frac_max
      FROM agg""")

    # Duplicates: a (parcel, h9) pair lives in one h0 partition, so check per partition.
    parts = [r[0] for r in con.execute(f"SELECT DISTINCT filename FROM read_parquet('{a.hex}', filename = true)").fetchall()]
    dups = 0
    for f in parts:
        dups += con.execute(f"""SELECT count(*) - count(DISTINCT ({a.id}, h9)) FROM read_parquet('{f}')""").fetchone()[0]
    print(f"\n== duplicate (parcel, h9) rows across {len(parts)} partitions: {dups}", flush=True)

    # Straight-edge reference area per parcel, in the worker pool.
    def _batches():
        # Localize id + geometry once, in 2,000-row groups: reading id ranges
        # from S3 re-downloaded each large row group dozens of times.
        con.execute(f"""COPY (SELECT {a.id} AS fid, ST_AsWKB(SHAPE) AS wkb FROM read_parquet('{a.source}'))
                        TO '/tmp/src_geom.parquet' (FORMAT PARQUET, ROW_GROUP_SIZE 2000)""")
        lo, hi = con.execute("SELECT min(fid), max(fid) FROM '/tmp/src_geom.parquet'").fetchone()
        for start in range(lo, hi + 1, 2000):
            rows_ = con.execute(f"""SELECT fid, wkb FROM '/tmp/src_geom.parquet'
                                    WHERE fid BETWEEN {start} AND {start + 1999}""").fetchall()
            if rows_:
                yield ([r[0] for r in rows_], [bytes(r[1]) for r in rows_])


    import pyarrow as pa
    rows = []
    for r in POOL.imap_unordered(_straight, _batches()):
        rows.extend(r)
    POOL.close()
    straight_tbl = pa.table({"fid": [r[0] for r in rows], "km2_straight": [r[1] for r in rows]})
    con.register("straight_arrow", straight_tbl)
    con.execute("CREATE TABLE straight AS SELECT fid::BIGINT AS fid, km2_straight FROM straight_arrow")
    print(f"straight-edge areas: {len(rows):,}", flush=True)

    con.execute("""CREATE TABLE pf AS SELECT s.fid, floor(log10(greatest(s.GIS_AREA, 1e-6)))::INT AS decade,
                     s.GIS_AREA, s.km2_poly, t.km2_straight, g.n_rows, g.n_full, g.km2_hex,
                     g.km2_hex / nullif(s.km2_poly, 0) - 1 AS rel_err,
                     g.km2_hex / nullif(t.km2_straight, 0) - 1 AS rel_err_straight
                   FROM src s JOIN agg g USING (fid) JOIN straight t USING (fid)""")
    con.execute(f"COPY pf TO '{a.out}/per-feature.parquet' (FORMAT PARQUET)")
    show("area from fractions vs ST_Area_Spheroid, by decade of GIS_AREA (km2)", """
      SELECT decade, count(*) AS n, sum(n_rows) AS rows,
             round(median(abs(rel_err)), 8) AS med_abs_err, round(quantile_cont(abs(rel_err), 0.99), 8) AS p99_abs_err,
             round(max(abs(rel_err)), 6) AS max_abs_err, round(sum(km2_hex) / sum(km2_poly) - 1, 8) AS total_rel_err
      FROM pf GROUP BY ALL ORDER BY decade""")
    show("hex vs STRAIGHT-EDGE area, by decade of GIS_AREA", """
      SELECT decade, count(*) AS n,
             round(median(abs(rel_err_straight)), 9) AS med_abs_err, round(max(abs(rel_err_straight)), 6) AS max_abs_err,
             count(*) FILTER (WHERE abs(rel_err_straight) > 1e-4) AS over_1e4,
             count(*) FILTER (WHERE abs(rel_err_straight) > 1e-3) AS over_1e3,
             count(*) FILTER (WHERE abs(rel_err_straight) > 1e-2) AS over_1e2,
             count(*) FILTER (WHERE rel_err_straight < -1e-4) AS short_1e4
      FROM pf GROUP BY ALL ORDER BY decade""")
    show("hex vs straight-edge area: all parcels", """
      SELECT count(*) AS n, count(*) FILTER (WHERE abs(rel_err_straight) > 1e-4) AS over_1e4,
             count(*) FILTER (WHERE rel_err_straight < -1e-4) AS short_1e4,
             count(*) FILTER (WHERE abs(rel_err_straight) > 1e-3) AS over_1e3,
             count(*) FILTER (WHERE abs(rel_err_straight) > 1e-2) AS over_1e2
      FROM pf""")
    show("worst 15 parcels vs straight-edge area", """
      SELECT fid, decade, round(km2_straight, 6) AS km2_straight, round(km2_hex, 6) AS km2_hex,
             rel_err_straight, rel_err AS rel_err_geodesic, n_rows
      FROM pf ORDER BY abs(rel_err_straight) DESC NULLS FIRST LIMIT 15""")
    show("parcels with |error| > 1% vs geodesic area", """
      SELECT count(*) AS n, count(*) FILTER (WHERE GIS_AREA >= 1000) AS over_1000_km2,
             max(abs(rel_err)) AS worst FROM pf WHERE abs(rel_err) > 0.01""")
    show("worst 10 parcels", """
      SELECT fid, decade, round(km2_poly, 4) AS km2_poly, round(km2_hex, 4) AS km2_hex, rel_err, n_rows
      FROM pf ORDER BY abs(rel_err) DESC NULLS FIRST LIMIT 10""")
