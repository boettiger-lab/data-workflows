#!/usr/bin/env python3
"""Turn a COG's measured valid-pixel footprint into the h0 index list for its hex Job.

    kubectl -n geo-workflows logs job/wrc-2-make-cogs-rest --all-containers \
      | grep '^FOOTPRINT ' > footprints.jsonl
    python3 h0_select.py footprints.jsonl            # prints the SQL to run
    python3 h0_select.py footprints.jsonl --boxes    # prints the boxes, for eyeballing

WHY THIS EXISTS. At H3 resolution 10 an h0 index that holds no data is NOT free: `cng-datasets`
prunes only h0 cells whose footprint misses the raster's BOUNDING BOX, and every surviving cell
enumerates all 282,475,249 res-10 children before discovering they are nodata -- about five hours
at 192Gi. A CONUS raster's bounding box touches twice as many h0 cells as its land does, so the
122-completion fan-out, and even a bounding-box-derived one, spends most of its pods writing
nothing.

The tempting fix is to reuse a neighbouring layer's populated h0 set. #592 measured why that is
unsafe: RPS Alaska populates FIVE h0, but `whp-2023-classified-ak` over the identical clip box
populates THREE, and trimming to the borrowed set would have dropped 4.25 M cells across two
partitions. `check-hex-coverage.sh` could not have caught it -- it verifies that expected
partitions are PRESENT, never that unexpected ones are ABSENT. Two products over one clip box are
not co-extensive.

So the list is derived from the layer's OWN pixels. make-cogs-bp-cfl-exposure.yaml records, during
the full-resolution statistics pass it is already doing, which 512x512 tiles hold at least one
valid pixel. A tile is reported if ANY pixel in it is valid, so the union of reported tiles
contains every valid pixel: an h0 that misses it provably holds no valid pixel. The trim is a
proof, not an inference, and the direction of any error is safe -- a tile is over-reported, never
under-reported.

⚠️ THE ANTIMERIDIAN IS NOT A CORNER CASE HERE. 17 of the 122 h0 cells straddle it, including
Alaska's index 105, which is Alaska's DENSEST partition (107.8 M cells on the RPS build). Their
polygons are stored in planar lat/lon, so the raw envelope is ~360 deg wide: it prunes nothing and
simultaneously EXCLUDES the +/-180 strip where the data lives. A plain
`ST_Intersects(geom, ST_MakeEnvelope(...))` gets these cells wrong in both directions. The SQL
emitted below reproduces `cog.py:_cell_footprint` exactly -- unwrap longitudes (negatives +360),
and a span > 180 deg becomes two intervals on [-180, 180] -- so the selection and the tool agree
about where a cell is.

Run the emitted SQL through the duckdb-geo MCP (AGENTS.md HARD BOUNDARY 0), never a local duckdb.
"""
from __future__ import annotations

import argparse
import json
import sys

H0_GRID = "s3://public-grids/hex/h0-valid.parquet"


def boxes(fp: dict) -> list:
    """Valid-pixel tile ranges -> lon/lat boxes, one per contiguous run.

    The geotransform is north-up (gt[2] == gt[4] == 0, gt[5] < 0), which the COG job asserts by
    construction: it writes EPSG:4326 with no rotation. Each box is the exact ground extent of
    its tile run, so the union of boxes is the union of reported tiles.
    """
    gt, (nx, ny), tile = fp["gt"], fp["size"], fp["tile"]
    if gt[2] != 0.0 or gt[4] != 0.0:
        sys.exit(f"FATAL: rotated geotransform {gt}; the tile -> lon/lat mapping assumes north-up")
    out = []
    for ty_s, runs in fp["rows"].items():
        ty = int(ty_s)
        # Clamp to the raster: the last tile row/column is usually partial.
        y0, y1 = ty * tile, min((ty + 1) * tile, ny)
        lat_hi = gt[3] + y0 * gt[5]
        lat_lo = gt[3] + y1 * gt[5]
        for cx0, cx1 in runs:
            x0, x1 = cx0 * tile, min((cx1 + 1) * tile, nx)
            lon_lo = gt[0] + x0 * gt[1]
            lon_hi = gt[0] + x1 * gt[1]
            out.append((min(lon_lo, lon_hi), min(lat_lo, lat_hi),
                        max(lon_lo, lon_hi), max(lat_lo, lat_hi)))
    return out


def sql_for(dataset: str, bx: list) -> str:
    vals = ",".join(f"({a!r},{b!r},{c!r},{d!r})" for a, b, c, d in bx)
    return f"""-- {dataset}: {len(bx)} valid-pixel boxes from its own COG
WITH box(xlo, ylo, xhi, yhi) AS (VALUES {vals}),
g AS (
  SELECT i, h0, geom, ST_XMin(geom) AS minx, ST_XMax(geom) AS maxx,
         ST_YMin(geom) AS miny, ST_YMax(geom) AS maxy
  FROM read_parquet('{H0_GRID}')
),
pts AS (
  SELECT g.i, ST_X(p.geom) AS x
  FROM g, LATERAL UNNEST(ST_Dump(ST_Points(g.geom))) AS t(p)
),
-- cog.py:_cell_footprint, exactly: unwrap negatives by +360, and a span > 180 deg means the
-- cell straddles the antimeridian, so its longitude footprint is two intervals on [-180, 180].
u AS (
  SELECT i, MIN(CASE WHEN x < 0 THEN x + 360 ELSE x END) AS umin,
            MAX(CASE WHEN x < 0 THEN x + 360 ELSE x END) AS umax
  FROM pts GROUP BY i
),
cell AS (
  SELECT g.i, g.h0, g.miny, g.maxy,
         CASE WHEN g.maxx - g.minx > 180
              THEN CASE WHEN u.umax > 180
                        THEN [[u.umin, 180.0], [-180.0, u.umax - 360.0]]
                        ELSE [[u.umin, 180.0]] END
              ELSE [[g.minx, g.maxx]] END AS lon,
         (g.maxx - g.minx > 180) AS straddles
  FROM g JOIN u USING (i)
)
SELECT c.i, c.h0, c.straddles, count(*) AS boxes_hit
FROM cell c JOIN box b
  ON NOT (b.yhi < c.miny OR b.ylo > c.maxy)
 AND len(list_filter(c.lon, iv -> NOT (b.xhi < iv[1] OR b.xlo > iv[2]))) > 0
GROUP BY ALL ORDER BY c.i;"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("footprints", help="file of FOOTPRINT <json> lines from the COG job's logs")
    ap.add_argument("--boxes", action="store_true", help="print the boxes instead of the SQL")
    ap.add_argument("--dataset", action="append", default=[], help="limit to these datasets")
    a = ap.parse_args()

    seen = {}
    for line in open(a.footprints):
        line = line.strip()
        if not line:
            continue
        # Tolerate `kubectl logs --prefix` and any leading pod name.
        idx = line.find("FOOTPRINT ")
        if idx < 0:
            continue
        fp = json.loads(line[idx + len("FOOTPRINT "):])
        ds = fp["dataset"]
        if ds in seen:
            sys.exit(f"FATAL: two FOOTPRINT lines for {ds}; a retry left both, keep one")
        seen[ds] = fp
    if not seen:
        sys.exit("FATAL: no FOOTPRINT lines found")

    for ds in sorted(seen):
        if a.dataset and ds not in a.dataset:
            continue
        bx = boxes(seen[ds])
        tiles = sum(hi - lo + 1 for runs in seen[ds]["rows"].values() for lo, hi in runs)
        lon = (min(b[0] for b in bx), max(b[2] for b in bx))
        lat = (min(b[1] for b in bx), max(b[3] for b in bx))
        print(f"-- {ds}: {tiles} valid tiles -> {len(bx)} boxes; "
              f"lon {lon[0]:.6f}..{lon[1]:.6f}  lat {lat[0]:.6f}..{lat[1]:.6f}", file=sys.stderr)
        if a.boxes:
            for b in bx:
                print(f"{ds}\t" + "\t".join(f"{v:.6f}" for v in b))
        else:
            print(sql_for(ds, bx))
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
