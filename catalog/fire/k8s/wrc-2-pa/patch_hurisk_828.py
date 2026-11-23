#!/usr/bin/env python3
"""Patch a LIVE wrc-2-pa-hurisk collection for the #828 `sum` rebuild, in place.

    patch_hurisk_828.py {conus|ak} COLLECTION.json COG_SIZE RESCALE_HI

#611 published HURisk as an index: `-r near` warp, `mean` hex. #828 rebuilt it as the per-pixel
amount it is (HUImpact x burn probability, metadata Process step 13): `-r sum` warp to Float32,
`sum` hex. This rewrites only what the rebuild changed -- the reducer wording in the description,
the COG and hex asset descriptions, `raster:bands`, the hex row count, the `hurisk` column
description and the render's upper bound -- and leaves the styles, renders' other fields,
thumbnail, links and everything else as published. Every number is measured: COG statistics from
make-cogs.yaml's exact blockwise pass, row counts from the duckdb-geo gate (BUILD.md, #828), the
render bound from the new COG's 98th percentile. Refuses a collection whose text it does not
recognise, so a later hand edit is never overwritten blind.
"""
import json
import sys
from datetime import datetime, timezone

FACTS = {
    "conus": {"max": 8500093.0, "mean": 1080.2427726410403, "rows": 134660430, "place": "the United States"},
    "ak": {"max": 311670.8125, "mean": 2157.480019771585, "rows": 389755, "place": "Alaska"},
}

domain, path, cog_size, hi = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4])
f = FACTS[domain]
doc = json.load(open(path))
ds = doc["id"]


def swap(text: str, old: str, new: str, where: str) -> str:
    if new in text:
        return text
    if old not in text:
        sys.exit(f"{ds}: {where}: expected text not found, refusing to patch:\n  {old[:120]}")
    return text.replace(old, new)


d = doc["description"]
d = swap(d, "The value is a relative index with no physical unit, so it is meaningful for ranking and "
            "comparison rather than as a quantity. Combine cells by averaging; there is no meaningful "
            "total.",
         "The producers call it a relative index, so it is for comparison rather than a count of homes "
         "lost. It is computed as Housing Unit Impact multiplied by burn probability, and Housing Unit "
         "Impact is built from the number of housing units in each pixel, so it is an amount rather "
         "than an intensity: cells add, and summing over an area gives that area's total risk in the "
         "same relative units.", "description")
d = swap(d, "using an area-weighted mean of the source pixels in each cell",
         "using a coverage-weighted sum of the source pixels in each cell", "description")
d = swap(d, "so each cell averages roughly 17 source pixels.",
         "so each cell gathers roughly 17 source pixels. Because the source value is an amount held by "
         "each pixel rather than an intensity, both the reprojection and the hex aggregation conserve "
         "the total, and the sum over any set of cells is the amount within them.", "description")
d = swap(d, "using nearest-neighbour resampling before hexing",
         "using the overlap-weighted sum of contributing source pixels before hexing", "description")
doc["description"] = d

cog = doc["assets"][f"{ds}-cog"]
src = cog["description"].split(" from ", 1)[1].split(" using ", 1)[0]
cog["description"] = (
    f"Housing Unit Risk reprojected to EPSG:4326 from {src} using the overlap-weighted sum of "
    "contributing source pixels, at approximately the source 30 metre ground resolution. "
    "Nearest-neighbour resampling would not have preserved the total, because reprojection changes "
    "both the pixel count and the per-pixel ground area by an amount that varies with latitude. Each "
    "pixel holds the amount within its own footprint, and reprojected pixels do not all cover the "
    "same ground area, so the per-pixel maximum here is not the per-pixel maximum of the source "
    "grid. The total across the raster is preserved.")
cog["file:size"] = cog_size
cog["created"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
band = cog["raster:bands"][0]
band.update({"data_type": "float32", "unit": "relative index (an amount per pixel)",
             "statistics": {"minimum": 0.0, "maximum": f["max"], "mean": f["mean"]}})

hexa = doc["assets"][f"{ds}-hex"]
hexa["description"] = (
    "H3 resolution 10 hex cells carrying the housing unit risk held by each cell, as a "
    "coverage-weighted sum of the source pixels, with rollup columns at resolutions 9, 8 and 0. One "
    "row per cell. The value is an amount rather than an intensity, so cells add: sum the column to "
    "total an area, and roll up to a coarser resolution with a sum rather than an average. A cell is "
    "present only where the source raster holds data, so a cell whose value is zero is a measured "
    "zero, meaning housing units present with no risk from fire, while a cell with no row means no "
    "housing units.\n\n```sql\n-- total housing unit risk inside inventoried roadless areas\n"
    "SELECT SUM(w.hurisk) AS hurisk_total\n"
    f"FROM read_parquet('https://s3-west.nrp-nautilus.io/public-fire/{ds}/hex/h0=*/data_0.parquet') w\n"
    "JOIN (\n  SELECT DISTINCT h10\n"
    "  FROM read_parquet('https://s3-west.nrp-nautilus.io/public-usfs/roadless-areas-2001/hex/h0=*/data_0.parquet')\n"
    ") r USING (h10);\n```")
hexa["table:row_count"] = f["rows"]

for c in doc.get("table:columns", []):
    if c["name"] == "hurisk":
        rng = c["description"].split("Source values span ", 1)[1]
        c["description"] = ("Housing Unit Risk (relative index, an amount per pixel) held by the cell, "
                            "as the coverage-weighted sum of the 30 metre source pixels falling in it. "
                            "Cells add: summing this column over an area gives that area's total. "
                            f"Source values span {rng}")

for r in (doc.get("renders") or {}).values():
    if f"{ds}-cog" in r.get("assets", []):
        r["rescale"] = [[0, hi]]

with open(path, "w") as fh:
    fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
print(f"{ds}: patched (rows {f['rows']:,}, COG {cog_size:,} bytes, render 0..{hi:g})")
