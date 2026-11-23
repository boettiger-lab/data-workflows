-- Sample reefs for #1020: 200 on the Great Barrier Reef, 200 in the Caribbean
-- (dense, narrow, overlapping), and every reef that reaches the antimeridian.
-- {src} is the source table; returns (fid, tag).
(SELECT _cng_fid AS fid, 'gbr' AS tag FROM {src}
 WHERE ST_XMin(geom) BETWEEN 142 AND 155 AND ST_YMin(geom) BETWEEN -25 AND -9
 ORDER BY hash(_cng_fid) LIMIT 200)
UNION ALL
(SELECT _cng_fid, 'caribbean' FROM {src}
 WHERE ST_XMin(geom) BETWEEN -90 AND -59 AND ST_YMin(geom) BETWEEN 9 AND 28
 ORDER BY hash(_cng_fid) LIMIT 200)
UNION ALL
(SELECT _cng_fid, 'antimeridian' FROM {src} WHERE ST_XMax(geom) > 179.9 OR ST_XMin(geom) < -179.9)
