-- Sample include for #1000: Ramsar parcels near National parcels, with every
-- National parcel within ~500 m of each, so the Ramsar-vs-National overlap
-- test can be checked against exact polygon intersections. Up to 12 Ramsar
-- parcels per class of their largest overlap with any National parcel
-- (near-but-disjoint, touching, <1 ha, 1-10 ha, >10 ha), each with <= 6
-- National neighbours. {src} is the source table. Returns (fid, tag).
WITH r AS (SELECT _cng_fid AS fid, SHAPE AS g,
                  ST_MakeEnvelope(ST_XMin(SHAPE) - 0.005, ST_YMin(SHAPE) - 0.005,
                                  ST_XMax(SHAPE) + 0.005, ST_YMax(SHAPE) + 0.005) AS env
           FROM {src} WHERE DESIG_TYPE = 'International'
             AND DESIG_ENG = 'Wetland of International Importance (Ramsar Site)'),
n AS (SELECT _cng_fid AS fid, SHAPE AS g FROM {src} WHERE DESIG_TYPE = 'National'),
pr AS (SELECT r.fid AS rf, n.fid AS nf, ST_Intersects(r.g, n.g) AS it,
              ST_Distance(r.g, n.g) AS d
       FROM r JOIN n ON ST_Intersects(r.env, n.g)),
pa AS (SELECT pr.*, CASE WHEN it THEN ST_Area_Spheroid(ST_Intersection(r.g, n.g)) ELSE 0 END AS ia
       FROM pr JOIN r ON r.fid = pr.rf JOIN n ON n.fid = pr.nf WHERE d <= 0.005),
cls AS (SELECT rf, count(*) AS nn,
               CASE WHEN max(ia) >= 1e5 THEN 'over10ha' WHEN max(ia) >= 1e4 THEN '1to10ha'
                    WHEN max(ia) > 0 THEN 'under1ha' WHEN bool_or(it) THEN 'touch' ELSE 'near' END AS c
        FROM pa GROUP BY rf),
pick AS (SELECT rf, c FROM (SELECT *, row_number() OVER (PARTITION BY c ORDER BY hash(rf * 31)) AS k
                            FROM cls WHERE nn <= 6) WHERE k <= 12)
SELECT rf AS fid, 'ramsar-' || c AS tag FROM pick
UNION ALL
SELECT DISTINCT pa.nf, 'national-neighbour' FROM pa JOIN pick USING (rf)
