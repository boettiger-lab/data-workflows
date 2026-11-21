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
"""
import argparse
import duckdb
from cng_datasets.storage.s3 import configure_s3_credentials

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

con.execute("""CREATE TABLE pf AS SELECT s.fid, floor(log10(greatest(s.GIS_AREA, 1e-6)))::INT AS decade,
                 s.GIS_AREA, s.km2_poly, g.n_rows, g.km2_hex, g.km2_hex / nullif(s.km2_poly, 0) - 1 AS rel_err
               FROM src s JOIN agg g USING (fid)""")
con.execute(f"COPY pf TO '{a.out}/per-feature.parquet' (FORMAT PARQUET)")
show("area from fractions vs ST_Area_Spheroid, by decade of GIS_AREA (km2)", """
  SELECT decade, count(*) AS n, sum(n_rows) AS rows,
         round(median(abs(rel_err)), 8) AS med_abs_err, round(quantile_cont(abs(rel_err), 0.99), 8) AS p99_abs_err,
         round(max(abs(rel_err)), 6) AS max_abs_err, round(sum(km2_hex) / sum(km2_poly) - 1, 8) AS total_rel_err
  FROM pf GROUP BY ALL ORDER BY decade""")
show("parcels with |error| > 1%", """
  SELECT count(*) AS n, count(*) FILTER (WHERE GIS_AREA >= 1000) AS over_1000_km2,
         max(abs(rel_err)) AS worst FROM pf WHERE abs(rel_err) > 0.01""")
show("worst 10 parcels", """
  SELECT fid, decade, round(km2_poly, 4) AS km2_poly, round(km2_hex, 4) AS km2_hex, rel_err, n_rows
  FROM pf ORDER BY abs(rel_err) DESC NULLS FIRST LIMIT 10""")
