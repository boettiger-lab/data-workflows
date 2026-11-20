-- Off-state check for LandVote geometry (#747). Read-only; run through the duckdb-geo MCP.
-- Every non-statewide row must have its point-on-surface inside a Census 2024 county
-- of the row's own state. Returns the offending rows; a clean build returns none.
-- 2026-11-20 on s3://public-tpl/landvote.parquet: 1,103 of 3,772 rows, 603 of 2,976
-- measures (567 Municipal, 35 Special District, 0 County). Cause: places matched by
-- name without the state (Austin TX -> Austin MN, Claremont CA -> Claremont NH).
WITH f AS (SELECT * FROM (VALUES ('01','AL'),('02','AK'),('04','AZ'),('05','AR'),('06','CA'),('08','CO'),('09','CT'),('10','DE'),('11','DC'),('12','FL'),('13','GA'),('15','HI'),('16','ID'),('17','IL'),('18','IN'),('19','IA'),('20','KS'),('21','KY'),('22','LA'),('23','ME'),('24','MD'),('25','MA'),('26','MI'),('27','MN'),('28','MS'),('29','MO'),('30','MT'),('31','NE'),('32','NV'),('33','NH'),('34','NJ'),('35','NM'),('36','NY'),('37','NC'),('38','ND'),('39','OH'),('40','OK'),('41','OR'),('42','PA'),('44','RI'),('45','SC'),('46','SD'),('47','TN'),('48','TX'),('49','UT'),('50','VT'),('51','VA'),('53','WA'),('54','WV'),('55','WI'),('56','WY'),('60','AS'),('66','GU'),('69','MP'),('72','PR'),('78','VI')) f(fp,st)),
lv AS (
  SELECT _cng_fid, landvote_id, state, county, municipal, jurisdiction, ST_PointOnSurface(geom) AS p
  FROM read_parquet('s3://public-tpl/landvote.parquet')
  WHERE jurisdiction <> 'State'
),
c AS (SELECT STATEFP, NAMELSAD, geom FROM read_parquet('s3://public-census/census-2024/county.parquet'))
SELECT lv._cng_fid, lv.landvote_id, lv.state, lv.county, lv.municipal, lv.jurisdiction,
       f.st AS geo_state, c.NAMELSAD AS geo_county
FROM lv
LEFT JOIN c ON ST_Contains(c.geom, lv.p)
LEFT JOIN f ON f.fp = c.STATEFP
WHERE f.st IS DISTINCT FROM lv.state
ORDER BY lv.state, lv.landvote_id;
