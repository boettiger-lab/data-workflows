#!/usr/bin/env python3
"""Rewrite the WD-OECM collection and README for the overlap + cover_frac hex (#879).

    stac_update.py LIVE_COLLECTION LIVE_README OUT_COLLECTION OUT_README --rows N --max-geodesic-pct P

Modelled on catalog/wdpa/k8s/wdpa-june-2026-overlap/stac_update.py (#1000).
Edits only the hex text: the collection's hex paragraphs, the hex asset
(title, description, h3:* fields, columns), the shared h8 column text, and the
README's hex passages. Everything else in the live files is kept as is, so the
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
ap.add_argument("--rows", type=int, required=True, help="hex row count, read from the published hex")
ap.add_argument("--max-gis-pct", type=float, required=True,
                help="largest |hex area / GIS_AREA - 1| over parcels, in percent, from the validation")
ap.add_argument("--max-geodesic-pct", type=float, required=True,
                help="largest |hex area / ST_Area_Spheroid - 1| over parcels, in percent, from the validation")
a = ap.parse_args()
rows_m = f"{a.rows / 1e6:.1f}M"
geo = f"{a.max_geodesic_pct:.1f}%"
gis = f"{a.max_gis_pct:.1f}%"


def cut(text, start, end, new, what):
    """Replace text from `start` up to (not including) `end`; end=None means to the end."""
    i = text.find(start)
    if i < 0:
        sys.exit(f"anchor not found for {what}: {start[:40]!r}")
    if end is None:
        return text[:i] + new
    j = text.find(end, i + 1)
    if j < 0:
        sys.exit(f"anchor not found for {what}: {end[:40]!r}")
    return text[:i] + new + text[j:]


def swap(text, old, new, what):
    if text.count(old) != 1:
        sys.exit(f"expected exactly one {what}: {old[:50]!r}")
    return text.replace(old, new)


HEX = "…/wdoecm-may-2026/hex/h0=*/data_0.parquet"
WDPA = "…/wdpa/hex/h0=*/data_0.parquet"

COLLECTION_H3 = f"""H3 indexing: every parcel is indexed at resolution 9, with one hex row for every resolution-9 cell the parcel overlaps, including cells it covers only in part, so no parcel is left without a cell however small it is. Each row carries `cover_frac`, the share of that cell's area lying inside the parcel: 1 for a cell wholly inside it, between 0 and 1 for a cell on its boundary. `h8` and `h0` are the parents of `h9`, and `h0` is the partition key. This build replaced, in November 2026, an earlier one at resolution 8 that assigned a cell to a parcel only when the cell's centre lay inside it, which left out the 4,784 parcels too small to hold a cell centre.

A parcel's area from the hex is the sum over its rows of `cover_frac` times the cell's area. It agrees with `GIS_AREA` to within 0.1% for all but a few parcels (at most about {gis}). Like H3 itself, it treats polygon edges as straight lines in longitude and latitude, so a geodesic area of the polygon (curved edges, as `ST_Area_Spheroid` computes it) differs by up to about {geo} on a large parcel drawn with long straight edges. Use `GIS_AREA` for a parcel's official area and the hex for areas inside other cells, masks or regions.

The WDPA sibling hex is built the same way (resolution 9, `cover_frac`), so the two combine cell by cell. Within one cell, parcels from either layer whose fractions are fa and fb overlap by at least (fa + fb − 1) and at most the smaller of the two, as shares of the cell's area, so the protected-or-conserved share of a cell lies between the largest fraction in it and the sum of the fractions capped at 1. Sharing a cell alone does not mean two parcels overlap.

```sql
-- protected-area plus OECM share of each resolution-9 cell, as a lower and an upper bound;
-- weight each cell by its area for km² (see the h3-guide)
WITH f AS (SELECT h9, cover_frac FROM read_parquet('{WDPA}')
           UNION ALL
           SELECT h9, cover_frac FROM read_parquet('{HEX}'))
SELECT h9, MAX(cover_frac) AS share_at_least, LEAST(SUM(cover_frac), 1) AS share_at_most
FROM f GROUP BY h9;
```

One hex row is one (parcel, cell) pair, so several OECMs can share a cell and a parcel spans many cells. Count OECMs with COUNT(DISTINCT SITE_ID), weight a cell by `cover_frac` when measuring area, and never SUM the per-parcel area columns on hex data without first deduplicating by `_cng_fid`. See the hex asset notes.
"""

HEX_ASSET = (
    f"Hive-partitioned (by h0) hex parquet. One row per (parcel, H3 resolution-9 cell the parcel overlaps), "
    f"{rows_m} rows. Every one of the 7,378 parcels is indexed at resolution 9 and has at least one cell. "
    "`cover_frac` is the share of the cell's area inside the parcel (1 for cells wholly inside, below 1 on the "
    "parcel's boundary); weight a cell by it when measuring area, since an unweighted count of cells overstates "
    "the area of every parcel by its boundary cells. Area from the hex agrees with GIS_AREA to within 0.1% for "
    f"all but a few parcels (at most about {gis}); it treats polygon edges as straight lines in longitude "
    f"and latitude, as H3 does, so a geodesic area can differ by up to about {geo} on a large parcel with long "
    "straight edges. Within a shared cell, two parcels with fractions fa and fb overlap by at "
    "least (fa + fb − 1) and at most the smaller of the two, as shares of the cell's area; sharing a cell alone "
    "does not mean they overlap. The WDPA sibling hex is built the same way, so combine the two per h9 cell as "
    "shown in the collection description. h8 and h0 are parents of h9 for every row: for a resolution-8 result, "
    "sum cover_frac times each h9 cell's area within the h8 cell rather than treating any h8 cell a parcel "
    "touches as covered. All flat-table attributes are carried on every row (same columns as the wdoecm-parquet "
    "asset, minus geometry), and `_cng_fid` joins back to it. To count OECMs use COUNT(DISTINCT SITE_ID), since "
    "one OECM can be split into several parcels (`_cng_fid` and `SITE_PID` count parcels). The per-parcel area "
    "columns (GIS_AREA, GIS_M_AREA, REP_AREA, REP_M_AREA, NO_TK_AREA) are repeated on every hex cell a parcel "
    "covers, so deduplicate by `_cng_fid` before summing them. This build replaced, in November 2026, a "
    "centre-of-cell build at resolution 8 that held only the 2,594 parcels large enough to contain a cell centre."
)

COL = {
    "h9": "H3 cell ID at resolution 9, the native cell for every parcel: each cell the parcel overlaps, in whole or in part.",
    "cover_frac": ("Share of the h9 cell's area that lies inside the parcel, from just above 0 to 1 "
                   "(1 when the cell is wholly inside). Polygon edges are taken as straight lines in "
                   "longitude and latitude, as in H3."),
    "h8": "H3 cell ID at resolution 8, the parent of h9.",
}

d = json.load(open(a.live_collection))
d["description"] = cut(d["description"], "Hex native resolution is 8.", None, COLLECTION_H3.rstrip("\n"),
                       "collection hex paragraphs")
hexa = d["assets"]["wdoecm-hex"]
hexa["title"] = "WD-OECM May 2026 — H3 hex parquet (native res 9, with cover_frac)"
hexa["description"] = HEX_ASSET
hexa["h3:native_resolution"] = 9
hexa["h3:parent_resolutions"] = [8, 0]


def set_cols(cols, with_text):
    """Add h9 and cover_frac before h8 and update the h8 text. The collection
    list carries the texts; the asset list carries names and types only, as it
    does live."""
    names = [c["name"] for c in cols]
    if "h8" not in names:
        sys.exit("no h8 column to place h9 and cover_frac before")
    for c in cols:
        if c["name"] == "h8" and with_text:
            c["description"] = COL["h8"]
    new = []
    for name, typ in (("h9", "uint64"), ("cover_frac", "float")):
        if name not in names:
            col = {"name": name, "type": typ}
            if with_text:
                col["description"] = COL[name]
            new.append(col)
    i = names.index("h8")
    cols[i:i] = new


set_cols(d["table:columns"], True)
set_cols(hexa["table:columns"], False)
json.dump(d, open(a.out_collection, "w"), indent=2, ensure_ascii=False)
open(a.out_collection, "a").write("\n")

r = open(a.live_readme).read()
r = swap(r, "- **Hex resolution**: H3 native resolution 8. WDPA is finer (resolution 9 for most parcels), "
            "so combine the two at each layer's finest cell (below)",
         "- **Hex resolution**: H3 resolution 9 for every parcel, one row per cell the parcel overlaps, "
         "with `cover_frac`, the share of the cell inside the parcel. WDPA is built the same way",
         "README hex resolution bullet")
r = cut(r, "-- Hex coverage: area of the h8 cells inside any OECM", "```\n", """-- Hex coverage (km²) inside any OECM. Within a cell, overlapping parcels cannot be
-- told apart, so the union lies between the largest share and the capped sum of shares.
INSTALL h3 FROM community; LOAD h3;
WITH cell AS (
  SELECT h9, MAX(cover_frac) AS lo, LEAST(SUM(cover_frac), 1) AS hi
  FROM read_parquet('https://s3-west.nrp-nautilus.io/public-wdpa/wdoecm-may-2026/hex/h0=*/data_0.parquet')
  GROUP BY h9
)
SELECT SUM(lo * h3_cell_area(h9, 'km^2')) AS oecm_km2_at_least,
       SUM(hi * h3_cell_area(h9, 'km^2')) AS oecm_km2_at_most
FROM cell;
""", "README DuckDB hex example")
r = cut(r, "## Combining with WDPA", "## Data dictionary", """## Combining with WDPA

The WDPA hex is built the same way as this one: every parcel at resolution 9, one row per cell it
overlaps, with `cover_frac`. Combine the two per `h9` cell. Parcels from either layer whose
fractions in a cell are fa and fb overlap by at least fa + fb − 1 and at most min(fa, fb) of the
cell, so the protected-or-conserved share of a cell lies between its largest fraction and the sum
of its fractions capped at 1.

```sql
-- PA + OECM area (km²), the currently-conserved baseline, as a lower and an upper bound
WITH f AS (
  SELECT h9, cover_frac FROM read_parquet('https://s3-west.nrp-nautilus.io/public-wdpa/wdpa/hex/h0=*/data_0.parquet')
  UNION ALL
  SELECT h9, cover_frac FROM read_parquet('https://s3-west.nrp-nautilus.io/public-wdpa/wdoecm-may-2026/hex/h0=*/data_0.parquet')
),
cell AS (SELECT h9, MAX(cover_frac) AS lo, LEAST(SUM(cover_frac), 1) AS hi FROM f GROUP BY h9)
SELECT SUM(lo * h3_cell_area(h9, 'km^2')) AS pa_plus_oecm_km2_at_least,
       SUM(hi * h3_cell_area(h9, 'km^2')) AS pa_plus_oecm_km2_at_most
FROM cell;
```

""", "README combining section")
r = cut(r, "## Hex usage notes", "## Citation", f"""## Hex usage notes

- **Every parcel is indexed at resolution 9** (about 0.1 km² per cell), with one row for every
  `h9` cell the parcel overlaps, in whole or in part. No parcel is left without a cell, however small.
- **`cover_frac`** is the share of the cell's area inside the parcel: 1 for cells wholly inside,
  between 0 and 1 for boundary cells. Weight each cell by it when measuring area; an unweighted
  count of cells overstates every parcel by its boundary cells.
- **`h8` and `h0` are parents of `h9`** on every row; `h0` is the hive partition key.
- **Area.** Hex area agrees with `GIS_AREA` to within 0.1% for all but a few parcels
  (at most about {gis}). Like H3, the fractions treat polygon edges as straight lines in longitude
  and latitude, so a geodesic area differs by up to about {geo} on a large parcel drawn with long
  straight edges. Use `GIS_AREA` for a parcel's official area.
- Attribute columns are repeated on every hex row of a parcel; `_cng_fid` joins back to the GeoParquet.
  **Do not** `SUM(GIS_AREA)` over hex rows: deduplicate by `_cng_fid` first.
- This build (November 2026) replaced one at resolution 8 that assigned cells by their centre
  point and left out the 4,784 parcels too small to contain a cell centre.

""", "README hex usage notes")
open(a.out_readme, "w").write(r)
print("ok")
