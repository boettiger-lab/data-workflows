-- Validation of the staged h8 high-seas hex (#1016). Run on the shared DuckDB
-- query server (not locally). Replace staging-1016/full/hex with hex after the swap.

-- 1. Rows, distinct cells (must be equal), fraction range, h0 consistency,
--    fraction-weighted area (H3 sphere) against the polygon's 222,496,418 km2 (WGS 84 ellipsoid).
SELECT count(*) AS n_rows, count(DISTINCT h8) AS n_cells,
       count(*) FILTER (WHERE cover_frac < 1) AS n_partial,
       min(cover_frac) AS min_frac, max(cover_frac) AS max_frac,
       count(*) FILTER (WHERE h3_cell_to_parent(h8, 0)::BIGINT <> h0) AS bad_h0,
       sum(cover_frac * h3_cell_area(h8, 'km^2')) AS km2_weighted,
       sum(h3_cell_area(h8, 'km^2')) AS km2_any_touch
FROM read_parquet('s3://public-high-seas/iho/high-seas/staging-1016/full/hex/h0=*/data_00.parquet');

-- 2. The issue's WDPA test: share of the high seas inside WDPA (h9 x cover_frac,
--    overlaps capped at 1), weighted by the high-seas cover_frac of each h9's h8 parent.
WITH hs AS (SELECT h8, cover_frac AS hf
            FROM read_parquet('s3://public-high-seas/iho/high-seas/staging-1016/full/hex/h0=*/data_00.parquet')),
w AS (SELECT h9, h8, least(1.0, sum(cover_frac)) AS f
      FROM read_parquet('s3://public-wdpa/wdpa/hex/**/*.parquet') GROUP BY h9, h8)
SELECT sum(w.f * h3_cell_area(w.h9, 'km^2')) AS wdpa_km2_any,
       sum(w.f * hs.hf * h3_cell_area(w.h9, 'km^2')) AS wdpa_km2_weighted,
       sum(w.f * h3_cell_area(w.h9, 'km^2')) / 222496418 AS share_any,
       sum(w.f * hs.hf * h3_cell_area(w.h9, 'km^2')) / 222496418 AS share_weighted
FROM w JOIN hs USING (h8);
