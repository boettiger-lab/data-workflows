#!/usr/bin/env python3
"""Emit the duckdb-geo MCP queries that verify a published #627 hex layer.

    python3 verify_hex.py wrc-2-bp-ak            # one layer
    python3 verify_hex.py --all                  # all six, as one query each

Run the output through the **duckdb-geo MCP** (AGENTS.md HARD BOUNDARY 0), never a local duckdb:
these scans are hundreds of millions of rows over S3 parquet.

What each check is for, since a passing structural check on an EMPTY build is the failure this
whole pipeline is shaped around (#586 hexed an Albers raster, wrote zero rows and exited 0):

  rows / distinct_h10     equal means one row per cell; fewer distinct means the merge
                          double-counted a cell across chunk boundaries, which is the new risk
                          the sub-h0 layout introduces and the h0-per-pod layout did not have.
  null_*                  a NULL finest parent means the rollup did not run.
  leak_9999               any value at or below the sentinel is a nodata leak.
  min / max               must sit inside the COG's own exact measured range; the cell value is
                          an area-weighted MEAN of ~17 pixels, so the hex max is <= the COG max
                          rather than equal to it.
  zero_frac               recorded, not gated: #592 found 11.0% (CONUS) / 18.2% (Alaska) exact
                          zeros in RPS, and that population is why a naive percentile comparison
                          against the source table disagrees.
  bbox                    from cell CENTROIDS, never the COG corners -- a COG's corners include
                          its nodata margin, and on #586 that was 2.4 degrees out.
  h0 coverage             the partition set, to compare against h0-selection.json. An h0 that was
                          selected but comes out EMPTY is fine and expected (the selection is a
                          superset); an h0 that is populated but was NOT selected is impossible
                          and would mean the fan-out and the merge disagree.
"""
from __future__ import annotations

import argparse
import sys

S3 = "s3://public-fire"
LAYERS = {
    "wrc-2-bp-conus": "bp", "wrc-2-bp-ak": "bp",
    "wrc-2-cfl-conus": "cfl", "wrc-2-cfl-ak": "cfl",
    "wrc-2-exposure-conus": "exposure", "wrc-2-exposure-ak": "exposure",
}


def query(ds: str, col: str) -> str:
    hexp = f"{S3}/{ds}/hex/h0=*/data_0.parquet"
    return f"""-- {ds}
WITH h AS (SELECT * FROM read_parquet('{hexp}', hive_partitioning := true))
SELECT
  '{ds}'                                              AS dataset,
  count(*)                                            AS rows,
  count(DISTINCT h10)                                 AS distinct_h10,
  count(*) - count(DISTINCT h10)                      AS dup_cells,
  count(*) FILTER (WHERE h9 IS NULL)                  AS null_h9,
  count(*) FILTER (WHERE h8 IS NULL)                  AS null_h8,
  count(*) FILTER (WHERE h0 IS NULL)                  AS null_h0,
  count(*) FILTER (WHERE {col} IS NULL)               AS null_value,
  count(*) FILTER (WHERE {col} <= -9998)              AS leak_9999,
  min({col})                                          AS min_value,
  max({col})                                          AS max_value,
  avg({col})                                          AS mean_value,
  count(*) FILTER (WHERE {col} = 0) / count(*)::DOUBLE AS zero_frac,
  count(DISTINCT h0)                                  AS n_h0,
  min(h3_cell_to_lng(h10)) AS bbox_xmin, min(h3_cell_to_lat(h10)) AS bbox_ymin,
  max(h3_cell_to_lng(h10)) AS bbox_xmax, max(h3_cell_to_lat(h10)) AS bbox_ymax
FROM h;"""


def partitions(ds: str) -> str:
    return f"""-- {ds}: populated h0 partitions, to compare with h0-selection.json
SELECT '{ds}' AS dataset, h0, count(*) AS cells
FROM read_parquet('{S3}/{ds}/hex/h0=*/data_0.parquet', hive_partitioning := true)
GROUP BY ALL ORDER BY cells DESC;"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("datasets", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--partitions", action="store_true")
    a = ap.parse_args()
    ds_list = sorted(LAYERS) if a.all else a.datasets
    if not ds_list:
        sys.exit("give dataset ids or --all")
    for ds in ds_list:
        if ds not in LAYERS:
            sys.exit(f"unknown dataset {ds}")
        print(partitions(ds) if a.partitions else query(ds, LAYERS[ds]))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
