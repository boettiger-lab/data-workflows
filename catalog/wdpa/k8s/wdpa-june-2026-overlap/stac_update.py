#!/usr/bin/env python3
"""Rewrite the WDPA collection and README for the overlap + cover_frac hex (#1000).

    stac_update.py LIVE_COLLECTION LIVE_README OUT_COLLECTION OUT_README --rows N

Edits only the hex text: the collection's H3 paragraphs, the hex asset
description and columns, the shared h9/h8 column texts, and the README's H3
and DuckDB sections. Everything else in the live files is kept as is, so the
publish job can run this against whatever is live at the time. Fails loudly if
an anchor it edits is missing, rather than writing a half-updated file.
"""
import argparse
import json
import sys

ap = argparse.ArgumentParser()
ap.add_argument("live_collection")
ap.add_argument("live_readme")
ap.add_argument("out_collection")
ap.add_argument("out_readme")
ap.add_argument("--rows", type=int, required=True, help="hex row count, from the validation")
a = ap.parse_args()
rows_m = f"{a.rows / 1e6:.1f}M"


def cut(text, start, end, new, what):
    i = text.find(start)
    j = text.find(end, i + 1) if i >= 0 else -1
    if i < 0 or j < 0:
        sys.exit(f"anchor not found for {what}: {start[:40]!r} .. {end[:40]!r}")
    return text[:i] + new + text[j:]


HEX = "…/wdpa/hex/h0=*/data_0.parquet"

COLLECTION_H3 = f"""H3 indexing: every parcel is indexed at resolution 9, with one hex row for every resolution-9 cell the parcel overlaps, including cells it covers only in part, so no parcel is left without a cell however small it is. Each row carries `cover_frac`, the share of that cell's area lying inside the parcel: 1 for a cell wholly inside it, between 0 and 1 for a cell on its boundary. `h8` and `h0` are the parents of `h9`, and `h0` is the partition key. This build replaced, in November 2026, an earlier one that assigned a cell to a parcel only when the cell's centre lay inside it and indexed the 1,297 parcels of 5,000 km² or more at resolution 8 only.

A parcel's area from the hex is the sum over its rows of `cover_frac` times the cell's area. Like H3 itself, it treats polygon edges as straight lines in longitude and latitude, while `GIS_AREA` follows curved (geodesic) edges, so the two differ by up to about 1.6% on a few large parcels drawn with long straight edges and by far less on the rest. Use `GIS_AREA` for a parcel's official area and the hex for areas inside other cells, masks or regions.

Two parcels that share a cell do not necessarily overlap: each may cover a different part of it. Within one cell, parcels with fractions fa and fb overlap by at least (fa + fb − 1) and at most the smaller of fa and fb, as shares of the cell's area. Summed over their shared cells this bounds the overlap of two parcels, or of two groups of parcels, without the polygons. A minimum overlap, such as 1 ha, separates real overlaps from boundaries the two datasets traced slightly differently.

```sql
-- overlap of two parcels, as shares of a resolution-9 cell (about 0.1 km² each):
-- multiply each row by its cell's area for km²
WITH hex AS (SELECT _cng_fid, h9, cover_frac FROM read_parquet('{HEX}'))
SELECT SUM(GREATEST(a.cover_frac + b.cover_frac - 1, 0)) AS overlap_cells_at_least,
       SUM(LEAST(a.cover_frac, b.cover_frac))            AS overlap_cells_at_most
FROM hex a JOIN hex b ON a.h9 = b.h9
WHERE a._cng_fid = 1 AND b._cng_fid = 2;
```

One hex row is one (parcel, cell) pair, so several protected areas can share a cell and a parcel spans many cells. Count protected areas with COUNT(DISTINCT SITE_ID), weight a cell by `cover_frac` when measuring area, and never SUM the per-parcel area columns on hex data without first deduplicating by `_cng_fid`. See the hex asset notes.

"""

HEX_ASSET = (
    f"One row per (parcel, H3 resolution-9 cell the parcel overlaps), {rows_m} rows. Every parcel is "
    "indexed at resolution 9, including the largest marine reserves, and has at least one cell. "
    "`cover_frac` is the share of the cell's area inside the parcel (1 for cells wholly inside, below 1 on "
    "the parcel's boundary); weight a cell by it when measuring area, since an unweighted count of cells "
    "overstates the area of every parcel by its boundary cells. Area from the hex treats polygon edges as "
    "straight lines in longitude and latitude, as H3 does, and can differ from the geodesic GIS_AREA by up "
    "to about 1.6% on a few large parcels with long straight edges. Within a shared cell, two parcels with "
    "fractions fa and fb overlap by at least (fa + fb − 1) and at most the smaller of the two, as shares of "
    "the cell's area; sharing a cell alone does not mean they overlap. h8 and h0 are parents of h9 for "
    "every row: for a resolution-8 result, sum cover_frac times each h9 cell's area within the h8 cell "
    "rather than treating any h8 cell a parcel touches as covered. All flat-table attributes are carried "
    "on every row (same columns as the wdpa-parquet asset, minus geometry), and `_cng_fid` joins back to "
    "it. To count protected areas use COUNT(DISTINCT SITE_ID), since one protected area can be split into "
    "several parcels (`_cng_fid` and `SITE_PID` count parcels). The per-parcel area columns (GIS_AREA, "
    "GIS_M_AREA, REP_AREA, REP_M_AREA, NO_TK_AREA) are repeated on every hex cell a parcel covers, so "
    "deduplicate by `_cng_fid` before summing them. This build replaced, in November 2026, a "
    "centre-of-cell build that indexed the 1,297 parcels of 5,000 km² or more at resolution 8 only."
)

COL = {
    "h9": "H3 cell ID at resolution 9, the native cell for every parcel: each cell the parcel overlaps, in whole or in part.",
    "h8": "H3 cell ID at resolution 8, the parent of h9.",
    "cover_frac": ("Share of the h9 cell's area that lies inside the parcel, from just above 0 to 1 "
                   "(1 when the cell is wholly inside). Polygon edges are taken as straight lines in "
                   "longitude and latitude, as in H3."),
}

d = json.load(open(a.live_collection))
d["description"] = cut(d["description"], "H3 indexing uses an adaptive resolution",
                       "WDPA includes Ramsar sites", COLLECTION_H3, "collection H3 paragraphs")
hexa = d["assets"]["wdpa-hex"]
hexa["description"] = HEX_ASSET
hexa["h3:native_resolution"] = 9
hexa["h3:parent_resolutions"] = [8, 0]


def set_cols(cols, with_text):
    """Update h9/h8 texts and add cover_frac after h9. The collection-level
    list carries the texts; the asset-level list carries names and types only,
    as it does live."""
    names = [c["name"] for c in cols]
    for c in cols:
        if c["name"] in ("h9", "h8") and "description" in c:
            c["description"] = COL[c["name"]]
    if "cover_frac" not in names:
        if "h9" not in names:
            sys.exit("no h9 column to place cover_frac after")
        col = {"name": "cover_frac", "type": "float"}
        if with_text:
            col["description"] = COL["cover_frac"]
        cols.insert(names.index("h9") + 1, col)


set_cols(d["table:columns"], True)
set_cols(hexa["table:columns"], False)
json.dump(d, open(a.out_collection, "w"), indent=2, ensure_ascii=False)
open(a.out_collection, "a").write("\n")

r = open(a.live_readme).read()
r = cut(r, "## H3 indexing (adaptive resolution + guaranteed coverage)", "## DuckDB", """## H3 indexing (resolution 9, every cell a parcel overlaps, with coverage fractions)

- **Every parcel is indexed at resolution 9**, including EEZ-scale marine reserves of
  up to 4.5M km², with one row for **every `h9` cell the parcel overlaps**, in whole or
  in part. No parcel is left without a cell, however small.
- **`cover_frac`** is the share of the cell's area inside the parcel: 1 for cells wholly
  inside, between 0 and 1 for boundary cells.
- **`h8` and `h0` are parents of `h9`** on every row; `h0` is the hive partition key.
- **Area convention.** Like H3, the fractions treat polygon edges as straight lines in
  longitude and latitude. `GIS_AREA` follows geodesic edges, so hex areas differ from it by
  up to ~1.6% on a few large parcels drawn with long straight edges, and by far less
  elsewhere. Use `GIS_AREA` for a parcel's official area.
- This build (November 2026) replaced one that assigned cells by their centre point and
  indexed the 1,297 parcels of 5,000 km² or more at resolution 8 only.

### ⚠️ One hex row = one (parcel, cell) pair

Multiple protected areas can share a cell, and a parcel spans many cells. So:

- **Count distinct protected areas:** `COUNT(DISTINCT SITE_ID)`. Use `_cng_fid` for joins
  to the flat table and PMTiles; it counts parcels.
- **Area:** weight each cell by `cover_frac` (example below). An unweighted count of
  cells overstates every parcel by its boundary cells.
- **Overlap:** two parcels sharing a cell need not overlap. In a shared cell they overlap
  by at least `fa + fb − 1` and at most `min(fa, fb)` of the cell's area.
- **Per-feature totals** (`GIS_AREA`, `GIS_M_AREA`, `REP_AREA`, `REP_M_AREA`,
  `NO_TK_AREA`) are repeated on every hex row of a parcel — dedup first:
  `SELECT DISTINCT _cng_fid, GIS_AREA ...` before summing.

""", "README H3 section")
r = cut(r, "-- Protected area for a country (km²), each parcel at its finest cell", "## MapLibre GL JS", """-- Protected area for a country (km²). Within a cell, overlapping parcels cannot be
-- told apart, so the union lies between the largest share and the capped sum of shares.
WITH cell AS (
  SELECT h9, MAX(cover_frac) AS lo, LEAST(SUM(cover_frac), 1) AS hi
  FROM read_parquet('https://s3-west.nrp-nautilus.io/public-wdpa/wdpa/hex/h0=*/data_0.parquet')
  WHERE ISO3 = 'BRA'
  GROUP BY h9
)
SELECT SUM(lo * h3_cell_area(h9, 'km^2')) AS protected_km2_at_least,
       SUM(hi * h3_cell_area(h9, 'km^2')) AS protected_km2_at_most
FROM cell;

-- Overlap (km²) between Ramsar sites and National protected areas, lower bound
WITH hex AS (
  SELECT _cng_fid, h9, cover_frac, DESIG_TYPE, DESIG_ENG
  FROM read_parquet('https://s3-west.nrp-nautilus.io/public-wdpa/wdpa/hex/h0=*/data_0.parquet')
)
SELECT r._cng_fid,
       SUM(GREATEST(r.cover_frac + n.cover_frac - 1, 0) * h3_cell_area(r.h9, 'km^2')) AS overlap_km2_at_least
FROM hex r JOIN hex n ON r.h9 = n.h9
WHERE r.DESIG_ENG = 'Wetland of International Importance (Ramsar Site)' AND n.DESIG_TYPE = 'National'
GROUP BY r._cng_fid;
```

The lower bound sums over National parcels one at a time, so where several National
parcels overlap each other it can count the same ground twice; group the National
parcels' fractions per cell first (as in the country example) for a union.

""", "README DuckDB hex examples")
open(a.out_readme, "w").write(r)
print("ok")
