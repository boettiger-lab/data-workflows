#!/usr/bin/env python3
"""Prepare one Hansen GFC-2025-v1.13 granule for the global mosaic (#434).

    prep_tile.py <layer> <datamask.tif> <value.tif | -> <out.tif>

layer is `loss-year` or `tree-cover-2000`. The value is kept only where the data mask says
mapped land (1). For loss-year, permanent water (mask 2) becomes class 254, so that a
hexagon's class shares are shares of its mapped area (land plus water). Everything else
(mask 0, no data) becomes 255, the nodata value. A missing loss-year granule (`-`) means no
loss anywhere in it, so land is 0.

The output is 512 x 512 tiled, ZSTD, sparse: blocks with no mapped pixels are never written
and read back as nodata. The source tiles are row-striped (40000 x 1 blocks), which a VRT
reads very slowly, so this is also the re-tiling step.

Prints one JSON line: the granule, whether it holds any mapped pixel, and its pixel count
per output class (the reference the hex is checked against). Exits 0 with no file written
when the granule holds no mapped pixel.
"""
import json
import os
import sys

import numpy as np
from osgeo import gdal

gdal.UseExceptions()

STEP = 2048  # rows per read; a multiple of the 512 block height


def main() -> None:
    layer, mask_path, value_path, out_path = sys.argv[1:5]
    assert layer in ("loss-year", "tree-cover-2000"), layer
    m_ds = gdal.Open(mask_path)
    m_band = m_ds.GetRasterBand(1)
    v_ds = gdal.Open(value_path) if value_path != "-" else None
    v_band = v_ds.GetRasterBand(1) if v_ds else None
    w, h = m_ds.RasterXSize, m_ds.RasterYSize
    if v_ds:
        assert (v_ds.RasterXSize, v_ds.RasterYSize) == (w, h), "value and mask grids differ"
        assert v_ds.GetGeoTransform() == m_ds.GetGeoTransform(), "value and mask grids differ"

    counts = np.zeros(256, dtype=np.int64)
    out_ds = None
    for y in range(0, h, STEP):
        rows = min(STEP, h - y)
        mask = m_band.ReadAsArray(0, y, w, rows)
        if not (mask > 0).any():
            continue
        if out_ds is None:
            out_ds = gdal.GetDriverByName("GTiff").Create(
                out_path, w, h, 1, gdal.GDT_Byte,
                ["TILED=YES", "BLOCKXSIZE=512", "BLOCKYSIZE=512", "COMPRESS=ZSTD",
                 "SPARSE_OK=TRUE", "BIGTIFF=YES"])
            out_ds.SetGeoTransform(m_ds.GetGeoTransform())
            out_ds.SetProjection(m_ds.GetProjection())
            out_band = out_ds.GetRasterBand(1)
            out_band.SetNoDataValue(255)
            out_band.SetDescription(layer.replace("-", "_"))
        value = (v_band.ReadAsArray(0, y, w, rows) if v_band
                 else np.zeros(mask.shape, dtype=np.uint8))
        out = np.full(mask.shape, 255, dtype=np.uint8)
        land = mask == 1
        out[land] = value[land]
        if layer == "loss-year":
            out[mask == 2] = 254
        out_band.WriteArray(out, 0, y)
        counts += np.bincount(out.ravel(), minlength=256)

    if out_ds is not None:
        out_ds.FlushCache()
        out_ds = None
    hist = {int(k): int(c) for k, c in enumerate(counts) if c and k != 255}
    if layer == "loss-year":
        bad = [k for k in hist if not (k <= 25 or k == 254)]
    else:
        bad = [k for k in hist if k > 100]
    print(json.dumps({"granule": os.path.basename(mask_path), "mapped": bool(hist),
                      "counts": hist}))
    if bad:
        sys.exit(f"unexpected values {bad} in {value_path}")


if __name__ == "__main__":
    main()
