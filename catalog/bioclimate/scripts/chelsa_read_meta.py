"""Print scale, offset and nodata for a CHELSA raster (data-workflows #564).

CHELSA declares these per file and they differ per variable -- bio1/bio4/bio12 use nodata 0
while bio15 uses 65535, and bio1 carries offset -273.15 where the others carry 0. The build
reads them from the file rather than carrying a table, so a new variable cannot silently
inherit the wrong sentinel.

Emits one shell-eval-able line: SCALE=<f> OFFSET=<f> NODATA=<v>
"""
import argparse

from osgeo import gdal

gdal.UseExceptions()

ap = argparse.ArgumentParser()
ap.add_argument("--input", required=True)
args = ap.parse_args()

band = gdal.Open(args.input).GetRasterBand(1)
scale = band.GetScale()
offset = band.GetOffset()
nodata = band.GetNoDataValue()

print(f"SCALE={1.0 if scale is None else scale} "
      f"OFFSET={0.0 if offset is None else offset} "
      f"NODATA={'' if nodata is None else repr(nodata).rstrip('0').rstrip('.') if nodata == int(nodata) else nodata}")
