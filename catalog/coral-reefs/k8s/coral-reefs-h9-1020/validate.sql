-- Validation of the staged h9 coral reef hex (#1020). Run on the shared DuckDB
-- query server (not locally). Replace staging-1020/full/hex with hex after the swap.

-- 1. Every polygon present, parents consistent with h9, cover_frac in (0, 1],
--    one row per (polygon, cell); per-polygon ratio of sum(cover_frac x h9 cell
--    area) to the polygon's ST_Area_Spheroid; reef area with overlaps capped
--    at 1 per h9 against the 151,390 km2 polygon sum.
WITH x AS (SELECT * FROM read_parquet('s3://public-coral-reefs/unep-wcmc-coral-reefs/polygons/staging-1020/full/hex/h0=*/data_0.parquet')),
h AS (SELECT _cng_fid, sum(cover_frac * h3_cell_area(h9,'km^2')) km2 FROM x GROUP BY 1),
p AS (SELECT _cng_fid, ST_Area_Spheroid(ST_FlipCoordinates(geom))/1e6 a FROM read_parquet('s3://public-coral-reefs/unep-wcmc-coral-reefs/polygons.parquet')),
r AS (SELECT p._cng_fid, p.a, coalesce(h.km2,0) km2, coalesce(h.km2,0)/p.a ratio FROM p LEFT JOIN h USING (_cng_fid)),
c AS (SELECT h9, least(sum(cover_frac),1) f, sum(cover_frac) s FROM x GROUP BY h9),
g AS (SELECT count(*) nrows, count(DISTINCT _cng_fid) nfid, count(DISTINCT h9) ncell,
        count(*) FILTER (WHERE h3_cell_to_parent(h9,8) <> h8 OR h3_cell_to_parent(h9,0)::BIGINT <> h0) nbad,
        count(*) FILTER (WHERE cover_frac IS NULL OR cover_frac <= 0 OR cover_frac > 1) nout,
        min(cover_frac) minf, max(cover_frac) maxf, count(*) FILTER (WHERE cover_frac = 1) nfull,
        count(*) - count(DISTINCT (_cng_fid, h9)) ndup FROM x)
SELECT g.*,
 (SELECT sum(f * h3_cell_area(h9,'km^2')) FROM c) capped_km2,
 (SELECT sum(s * h3_cell_area(h9,'km^2')) FROM c) uncapped_km2,
 (SELECT count(*) FILTER (WHERE s > 1.000001) FROM c) cells_over1,
 (SELECT sum(a) FROM r) poly_km2,
 (SELECT count(*) FILTER (WHERE km2 = 0) FROM r) missing,
 (SELECT min(ratio) FROM r) rmin, (SELECT quantile_cont(ratio,[0.001,0.01,0.5,0.99,0.999]) FROM r) rq, (SELECT max(ratio) FROM r) rmax,
 (SELECT count(*) FILTER (WHERE abs(ratio-1) > 0.01) FROM r) off1pct
FROM g;

-- 2. Share of reef area in no-take WDPA parcels (trim(NO_TAKE)='All'), the
--    glen-benchmark question bosl-coral-notake-share. Reef reduction per h9:
--    per polygon (sum, as the exact per-polygon answer), MAX, or capped SUM;
--    WDPA reduction per h9: MAX or capped SUM, with all statuses or without
--    STATUS = 'Proposed'. Exact-geometry answer: 8.66%.
WITH x AS (SELECT _cng_fid, h9, h0, cover_frac FROM read_parquet('s3://public-coral-reefs/unep-wcmc-coral-reefs/polygons/staging-1020/full/hex/h0=*/data_0.parquet')),
rc AS (SELECT h9, max(cover_frac) rmax, least(sum(cover_frac), 1) rcap, sum(cover_frac) rsum, h3_cell_area(h9,'km^2') a FROM x GROUP BY h9),
w0 AS (SELECT h9, cover_frac, STATUS FROM read_parquet('s3://public-wdpa/wdpa/hex/h0=*/data_0.parquet', hive_partitioning=true)
       WHERE h0 IN (SELECT DISTINCT h0 FROM x) AND trim(NO_TAKE) = 'All' AND h9 IN (SELECT h9 FROM rc)),
w AS (SELECT h9,
        coalesce(max(cover_frac), 0) wmax_all, least(coalesce(sum(cover_frac), 0), 1) wcap_all,
        coalesce(max(cover_frac) FILTER (WHERE STATUS <> 'Proposed'), 0) wmax_np,
        least(coalesce(sum(cover_frac) FILTER (WHERE STATUS <> 'Proposed'), 0), 1) wcap_np,
        count(*) FILTER (WHERE STATUS = 'Proposed') nprop
      FROM w0 GROUP BY h9),
j AS (SELECT rc.*, coalesce(wmax_all,0) wmax_all, coalesce(wcap_all,0) wcap_all, coalesce(wmax_np,0) wmax_np, coalesce(wcap_np,0) wcap_np, coalesce(nprop,0) nprop
      FROM rc LEFT JOIN w USING (h9))
SELECT
 sum(rsum*wmax_all*a)/sum(rsum*a) perpoly_max_all, sum(rsum*wcap_all*a)/sum(rsum*a) perpoly_cap_all,
 sum(rsum*wmax_np*a)/sum(rsum*a)  perpoly_max_np,  sum(rsum*wcap_np*a)/sum(rsum*a)  perpoly_cap_np,
 sum(rmax*wmax_all*a)/sum(rmax*a) rmax_max_all, sum(rmax*wcap_all*a)/sum(rmax*a) rmax_cap_all,
 sum(rmax*wmax_np*a)/sum(rmax*a)  rmax_max_np,  sum(rmax*wcap_np*a)/sum(rmax*a)  rmax_cap_np,
 sum(rcap*wmax_all*a)/sum(rcap*a) rcap_max_all, sum(rcap*wcap_all*a)/sum(rcap*a) rcap_cap_all,
 sum(rcap*wmax_np*a)/sum(rcap*a)  rcap_max_np,  sum(rcap*wcap_np*a)/sum(rcap*a)  rcap_cap_np,
 sum(rcap*a) reef_km2, sum(rcap*wmax_all*a) nt_km2_max_all, count(*) FILTER (WHERE nprop>0) cells_with_proposed
FROM j
;
