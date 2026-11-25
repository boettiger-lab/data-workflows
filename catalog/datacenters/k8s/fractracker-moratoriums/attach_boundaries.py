"""Attach Census 2024 boundaries to the matched FracTracker moratorium records.

usage: attach_boundaries.py MATCHED_CSV TIGER_DIR OUT_PARQUET

MATCHED_CSV is match_jurisdictions.py output. State, county and place boundaries come
from the catalog's Census 2024 GeoParquet (TIGER/Line 2024) on NRP S3; county
subdivisions and American Indian / Alaska Native areas from TIGER/Line 2024 zips already
downloaded into TIGER_DIR (tl_2024_<ss>_cousub.zip, tl_2024_us_aiannh.zip). Every input
row is written; unmatched rows keep a null geometry.

The TIGER zips are NAD83 (EPSG:4269) and the catalog parquet is WGS84; the two differ by
under 2 m across the United States, so geometries are combined without their CRS tags and the
output is written as WGS84 longitude/latitude, the GeoParquet default.
"""
import glob
import os
import sys

import duckdb

CENSUS = 's3://public-census/census-2024'


def main(matched, tiger, out):
    c = duckdb.connect()
    c.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;")
    c.execute(f"""CREATE SECRET (TYPE s3, KEY_ID '{os.environ["AWS_ACCESS_KEY_ID"]}',
                 SECRET '{os.environ["AWS_SECRET_ACCESS_KEY"]}', ENDPOINT '{os.environ["AWS_S3_ENDPOINT"]}',
                 URL_STYLE 'path', USE_SSL false)""")
    c.execute(f"CREATE TABLE m AS SELECT * FROM read_csv('{matched}', all_varchar=true, header=true)")

    c.execute(f"""CREATE TABLE b AS
        SELECT 'state' AS lvl, GEOID AS geoid, ST_GeomFromWKB(ST_AsWKB(geom)) AS geom FROM read_parquet('{CENSUS}/state.parquet')
          WHERE GEOID IN (SELECT geoid FROM m WHERE geo_level = 'state')
        UNION ALL
        SELECT 'county', GEOID, ST_GeomFromWKB(ST_AsWKB(geom)) FROM read_parquet('{CENSUS}/county.parquet')
          WHERE GEOID IN (SELECT geoid FROM m WHERE geo_level = 'county')
        UNION ALL
        SELECT 'place', GEOID, ST_GeomFromWKB(ST_AsWKB(geom)) FROM read_parquet('{CENSUS}/place.parquet')
          WHERE GEOID IN (SELECT geoid FROM m WHERE geo_level = 'place')""")
    for z in sorted(glob.glob(f'{tiger}/tl_2024_*_cousub.zip')):
        c.execute(f"""INSERT INTO b SELECT 'county_subdivision', GEOID, ST_GeomFromWKB(ST_AsWKB(geom))
                      FROM ST_Read('/vsizip/{z}')
                      WHERE GEOID IN (SELECT geoid FROM m WHERE geo_level = 'county_subdivision')""")
    # reservation (R) and off-reservation trust land (T) share an AIANNH code: union them
    c.execute(f"""INSERT INTO b SELECT 'aiannh', AIANNHCE, ST_Union_Agg(ST_GeomFromWKB(ST_AsWKB(geom)))
                  FROM ST_Read('/vsizip/{tiger}/tl_2024_us_aiannh.zip')
                  WHERE AIANNHCE IN (SELECT geoid FROM m WHERE geo_level = 'aiannh')
                  GROUP BY AIANNHCE""")

    dup = c.execute("SELECT lvl, geoid, count(*) FROM b GROUP BY 1, 2 HAVING count(*) > 1").fetchall()
    assert not dup, f'duplicate boundaries: {dup}'
    missing = c.execute("""SELECT geo_level, geoid, census_name FROM m
                           WHERE geo_level <> '' AND (geo_level, geoid) NOT IN (SELECT lvl, geoid FROM b)""").fetchall()
    assert not missing, f'matched GEOIDs with no boundary: {missing}'

    c.execute(f"""COPY (
        SELECT m.jurisdiction, m.state, m.action, m.status,
               COALESCE(try_strptime(NULLIF(m."date enacted", ''), '%Y-%m-%d %H:%M:%S'),
                        try_strptime(NULLIF(m."date enacted", ''), '%Y-%m-%d'),
                        try_strptime(NULLIF(m."date enacted", ''), '%m/%d/%Y'))::DATE AS date_enacted,
               NULLIF(m.duration, '') AS duration,
               COALESCE(try_strptime(NULLIF(m."expiration date", ''), '%Y-%m-%d %H:%M:%S'),
                        try_strptime(NULLIF(m."expiration date", ''), '%Y-%m-%d'),
                        try_strptime(NULLIF(m."expiration date", ''), '%m/%d/%Y'))::DATE AS expiration_date,
               NULLIF(m."source link 1", '') AS source_link_1,
               NULLIF(m."source link 2", '') AS source_link_2,
               NULLIF(m."source link 3", '') AS source_link_3,
               NULLIF(m.notes, '') AS notes,
               NULLIF(m.geo_level, '') AS geo_level,
               NULLIF(m.geoid, '') AS geoid,
               NULLIF(m.census_name, '') AS census_name,
               b.geom
        FROM m LEFT JOIN b ON b.lvl = m.geo_level AND b.geoid = m.geoid
    ) TO '{out}' (FORMAT parquet)""")
    bad = c.execute(f"""SELECT count(*) FROM m WHERE NULLIF("date enacted", '') IS NOT NULL
                         AND jurisdiction NOT IN (SELECT jurisdiction FROM read_parquet('{out}') WHERE date_enacted IS NOT NULL)""").fetchone()[0]
    assert bad == 0, f'{bad} enactment dates did not parse'
    n, g = c.execute(f"SELECT count(*), count(geom) FROM read_parquet('{out}')").fetchone()
    print(f'{n} records, {g} with a boundary, {n - g} without')


if __name__ == '__main__':
    main(*sys.argv[1:4])
