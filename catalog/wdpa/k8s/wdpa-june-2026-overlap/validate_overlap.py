#!/usr/bin/env python3
"""Validate an overlap + cover_frac hex build against its source polygons (#1000).

    validate_overlap.py --source S --plan P --chunks 'PREFIX/*.parquet' --out PREFIX

Prints, and writes as parquet under --out:
  per-feature.parquet  rows, rows at the h8 parent, area from fractions vs
                       ST_Area_Spheroid of the polygon (relative error), tag, decade
  pairs.parquet        Ramsar / National pairs in the sample: exact intersection
                       area vs what the hex says (shared cells, lower and upper bound)
Cell areas are ellipsoidal (ST_Area_Spheroid of the cell polygon), so the
comparison is not blurred by H3's spherical h3_cell_area (~0.5% off WGS84).
H3 and the fractions treat polygon edges as straight lines in lon/lat while
ST_Area_Spheroid treats them as geodesics, so a large polygon with few vertices
(long edges) differs by up to ~1.5%; that is the edge convention, not an error.
Bounds are checked to a relative tolerance of 1e-4 (planar vs ellipsoidal area).
"""
import argparse
import duckdb
from cng_datasets.storage.s3 import configure_s3_credentials

ap = argparse.ArgumentParser()
ap.add_argument("--source", required=True)
ap.add_argument("--plan", required=True)
ap.add_argument("--chunks", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--id", default="_cng_fid")
a = ap.parse_args()

con = duckdb.connect("/tmp/val.duckdb")
con.execute("INSTALL spatial; LOAD spatial; INSTALL h3 FROM community; LOAD h3")
configure_s3_credentials(con)
con.execute("SET geometry_always_xy = true; SET preserve_insertion_order = false")


def show(title, sql):
    print(f"\n== {title}", flush=True)
    con.sql(sql).show(max_width=250, max_rows=60)


con.execute(f"CREATE TABLE plan AS SELECT * FROM read_parquet('{a.plan}')")
con.execute(f"CREATE TABLE h AS SELECT * FROM read_parquet('{a.chunks}')")
con.execute(f"""CREATE TABLE src AS SELECT {a.id} AS fid, DESIG_TYPE, DESIG_ENG, SHAPE AS g
                FROM read_parquet('{a.source}') WHERE {a.id} IN (SELECT fid FROM plan)""")
# Ellipsoidal area of every distinct cell once.
con.execute("""CREATE TABLE ca AS SELECT h9, ST_Area_Spheroid(ST_GeomFromWKB(h3_cell_to_boundary_wkb(h9))) / 1e6 AS km2
               FROM (SELECT DISTINCT h9 FROM h)""")

con.execute(f"""
  CREATE TABLE pf AS
  WITH agg AS (SELECT {a.id} AS fid, count(*) AS n_rows, count(DISTINCT h8) AS n_h8,
                      count(*) FILTER (WHERE cover_frac = 1) AS n_full,
                      count(*) FILTER (WHERE cover_frac IS NULL) AS n_null,
                      sum(cover_frac * ca.km2) AS km2_hex
               FROM h JOIN ca USING (h9) GROUP BY 1)
  SELECT p.fid, p.tag, p.chunk, p.area_km2 AS gis_area, p.npts,
         floor(log10(greatest(p.area_km2, 1e-6)))::INT AS decade,
         ST_Area_Spheroid(s.g) / 1e6 AS km2_poly,
         coalesce(agg.n_rows, 0) AS n_rows, agg.n_h8, agg.n_full, agg.n_null, agg.km2_hex,
         agg.km2_hex / nullif(ST_Area_Spheroid(s.g) / 1e6, 0) - 1 AS rel_err
  FROM plan p JOIN src s USING (fid) LEFT JOIN agg USING (fid)
""")
con.execute(f"COPY pf TO '{a.out}/per-feature.parquet' (FORMAT PARQUET)")

show("coverage: features with no row, rows, cover_frac range", f"""
  SELECT (SELECT count(*) FROM plan) AS features_planned,
         (SELECT count(*) FROM pf WHERE n_rows = 0) AS features_no_rows,
         (SELECT sum(n_null) FROM pf) AS rows_frac_null,
         count(*) AS rows, min(cover_frac) AS frac_min, max(cover_frac) AS frac_max,
         count(*) FILTER (WHERE cover_frac <= 0 OR cover_frac > 1) AS frac_out_of_range,
         count(*) - count(DISTINCT ({a.id}, h9)) AS duplicate_rows
  FROM h""")
show("area from fractions vs ST_Area_Spheroid, by decade of GIS_AREA (km2)", """
  SELECT decade, count(*) AS n, sum(n_rows) AS rows,
         round(median(abs(rel_err)), 8) AS med_abs_err, round(quantile_cont(abs(rel_err), 0.99), 8) AS p99_abs_err,
         round(max(abs(rel_err)), 8) AS max_abs_err,
         round(sum(km2_hex) / sum(km2_poly) - 1, 8) AS total_rel_err
  FROM pf GROUP BY ALL ORDER BY decade""")
show("worst 10 features by |relative error|", """
  SELECT fid, tag, round(km2_poly, 6) AS km2_poly, round(km2_hex, 6) AS km2_hex, rel_err, n_rows, npts
  FROM pf ORDER BY abs(rel_err) DESC NULLS FIRST LIMIT 10""")

# Ramsar vs National pairs inside the sample.
con.execute("""
  CREATE TABLE pairs AS
  WITH r AS (SELECT fid, g FROM src WHERE DESIG_TYPE = 'International'
               AND DESIG_ENG = 'Wetland of International Importance (Ramsar Site)'),
       n AS (SELECT fid, g FROM src WHERE DESIG_TYPE = 'National'),
       p AS (SELECT r.fid AS rf, n.fid AS nf, ST_Intersects(r.g, n.g) AS intersects,
                    CASE WHEN ST_Intersects(r.g, n.g) THEN ST_Area_Spheroid(ST_Intersection(r.g, n.g)) ELSE 0 END AS exact_m2
             FROM r JOIN n ON ST_DWithin(r.g, n.g, 0.005)),
       hx AS (SELECT p.rf, p.nf, count(hr.h9) AS shared_cells,
                     sum(greatest(hr.cover_frac + hn.cover_frac - 1, 0) * ca.km2) * 1e6 AS lower_m2,
                     sum(least(hr.cover_frac, hn.cover_frac) * ca.km2) * 1e6 AS upper_m2
              FROM p JOIN h hr ON hr._cng_fid = p.rf
                     JOIN h hn ON hn._cng_fid = p.nf AND hn.h9 = hr.h9
                     JOIN ca ON ca.h9 = hr.h9
              GROUP BY ALL)
  SELECT p.*, coalesce(hx.shared_cells, 0) AS shared_cells,
         coalesce(hx.lower_m2, 0) AS lower_m2, coalesce(hx.upper_m2, 0) AS upper_m2
  FROM p LEFT JOIN hx USING (rf, nf)
""")
con.execute(f"COPY pairs TO '{a.out}/pairs.parquet' (FORMAT PARQUET)")
show("Ramsar x National pairs: exact polygon overlap vs hex", """
  SELECT CASE WHEN exact_m2 >= 1e5 THEN 'e >10 ha' WHEN exact_m2 >= 1e4 THEN 'd 1-10 ha'
              WHEN exact_m2 > 0 THEN 'c <1 ha' WHEN intersects THEN 'b touch only' ELSE 'a disjoint' END AS exact,
         count(*) AS pairs,
         count(*) FILTER (WHERE shared_cells > 0) AS share_a_cell,
         count(*) FILTER (WHERE lower_m2 > 0) AS lower_bound_positive,
         count(*) FILTER (WHERE lower_m2 >= 1e4) AS lower_ge_1ha,
         count(*) FILTER (WHERE upper_m2 >= 1e4) AS upper_ge_1ha,
         count(*) FILTER (WHERE exact_m2 < lower_m2 - greatest(1, 1e-4 * exact_m2)
                            OR exact_m2 > upper_m2 + greatest(1, 1e-4 * exact_m2)) AS bound_violations
  FROM pairs GROUP BY 1 ORDER BY 1""")
