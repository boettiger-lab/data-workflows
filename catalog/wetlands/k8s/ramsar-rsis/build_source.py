"""Assemble the Ramsar source GeoParquet from the RSIS download (#1074).

  build_source.py <rsis_dir> <out.parquet>

Rows:
- one per RSIS boundary feature (ramsar_sdi:features_published), source = 'RSIS boundary';
- one per RSIS site centroid (ramsar_sdi:features_centroid_published) for a site with no boundary
  feature, source = 'RSIS centroid'.
Attributes come from the site-details table (s3://public-wetlands/ramsar/site-details.parquet, the
RSIS site export the July 2026 build used), joined on ramsarid. A site missing from it keeps the
WFS name, country and official area. The earlier build's fallback to fuzzy-matched WDPA polygons is
not used: every geometry here is the Ramsar Secretariat's own.
"""
import os, sys
import duckdb

rsis, out = sys.argv[1], sys.argv[2]
con = duckdb.connect()
con.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs")
con.execute("CREATE SECRET s3 (TYPE S3, KEY_ID '{}', SECRET '{}', ENDPOINT '{}', URL_STYLE 'path', USE_SSL false)".format(
    os.environ["AWS_ACCESS_KEY_ID"], os.environ["AWS_SECRET_ACCESS_KEY"], os.environ["AWS_S3_ENDPOINT"]))
con.execute(f"CREATE TABLE poly AS SELECT * FROM ST_Read('{rsis}/features_published.geojson')")
con.execute(f"CREATE TABLE cent AS SELECT * FROM ST_Read('{rsis}/features_centroid_published.geojson')")
con.execute("CREATE TABLE sd AS SELECT * EXCLUDE (Latitude, Longitude) FROM read_parquet('s3://public-wetlands/ramsar/site-details.parquet')")
for t in ("poly", "cent"):
    print(t, con.execute(f"SELECT COUNT(*), COUNT(DISTINCT ramsarid), string_agg(DISTINCT ST_GeometryType(geom)::VARCHAR, ',') FROM {t}").fetchone())

sd_types = {r[0]: r[1] for r in con.execute("DESCRIBE sd").fetchall()}
sd_cols = [c for c in sd_types if c != "ramsarid"]
fill = {"Site name": "officialname", "Country": "country_en", "Area (ha)": "area_off"}
sel = ", ".join(
    f'COALESCE(sd."{c}", TRY_CAST(g.{fill[c]} AS {sd_types[c]})) AS "{c}"' if c in fill else f'sd."{c}"'
    for c in sd_cols)
con.execute(f"""
  CREATE TABLE src AS
  SELECT CAST(g.ramsarid AS BIGINT) AS ramsarid, {sel}, g.source, g.geom FROM (
    SELECT *, 'RSIS boundary' AS source FROM poly
    UNION ALL BY NAME
    SELECT *, 'RSIS centroid' AS source FROM cent
    WHERE CAST(ramsarid AS BIGINT) NOT IN (SELECT CAST(ramsarid AS BIGINT) FROM poly)
  ) g LEFT JOIN sd ON sd.ramsarid = CAST(g.ramsarid AS BIGINT)
  ORDER BY ramsarid""")
print("rows / sites by source:", con.execute(
    "SELECT source, COUNT(*), COUNT(DISTINCT ramsarid) FROM src GROUP BY 1 ORDER BY 1").fetchall())
print("sites without site-details:", con.execute(
    "SELECT COUNT(DISTINCT ramsarid) FROM src WHERE ramsarid NOT IN (SELECT ramsarid FROM sd)").fetchone()[0])
print("site-details sites not in RSIS:", con.execute(
    "SELECT COUNT(*) FROM sd WHERE ramsarid NOT IN (SELECT ramsarid FROM src)").fetchone()[0])
print("invalid geometries:", con.execute("SELECT COUNT(*) FROM src WHERE NOT ST_IsValid(geom)").fetchone()[0])
con.execute(f"COPY src TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 2000)")
print("wrote", out)
