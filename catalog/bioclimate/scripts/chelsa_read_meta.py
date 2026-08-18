"""Print scale, offset and nodata for a CHELSA raster (data-workflows #564).

CHELSA declares these per file and they differ per variable -- bio1/bio4/bio12 use nodata 0
while bio15 uses 65535, and bio1 carries offset -273.15 where the others carry 0. The build
reads them from the file rather than carrying a table, so a new variable cannot silently
inherit the wrong sentinel.

Emits one shell-eval-able line: SCALE=<f> OFFSET=<f> NODATA=<v>
(NODATA is empty when the source declares none.)
"""
import argparse
import sys

from osgeo import gdal

gdal.UseExceptions()


def fmt_nodata(v):
    if v is None:
        return ""
    # GDAL returns a float; emit an integer when the sentinel is integral so the value
    # round-trips into `cng-datasets --nodata` as e.g. "0", never "0.0".
    return str(int(v)) if float(v).is_integer() else repr(v)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    args = ap.parse_args()

    # Hold the Dataset for the lifetime of the band: chaining
    # `gdal.Open(p).GetRasterBand(1)` lets the Dataset be garbage-collected and leaves the
    # band dangling, which surfaces as a TypeError inside the SWIG shim rather than as a
    # clean failure.
    ds = gdal.Open(args.input)
    if ds is None:
        print(f"ERROR: could not open {args.input}", file=sys.stderr)
        return 1
    band = ds.GetRasterBand(1)
    if band is None:
        print(f"ERROR: no band 1 in {args.input}", file=sys.stderr)
        return 1

    scale = band.GetScale()
    offset = band.GetOffset()
    nodata = band.GetNoDataValue()

    print(f"SCALE={1.0 if scale is None else scale} "
          f"OFFSET={0.0 if offset is None else offset} "
          f"NODATA={fmt_nodata(nodata)}")
    del band
    del ds
    return 0


if __name__ == "__main__":
    sys.exit(main())
