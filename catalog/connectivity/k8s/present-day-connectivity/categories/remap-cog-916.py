"""#916: rewrite the present-day connectivity COG with fill code 0 mapped to its declared nodata 255.

The COG carries two fill codes: 0 (outside California's land) and 255 (outside the source
raster), and a band declares only one. A VRT lookup table maps 0 -> 255 and every other value
to itself; gdal_translate writes a COG with the original's structure. The whole raster is
compared with the original (it is 12,179 x 13,063 bytes), then the original is backed up to
staging/916-backup/ and replaced.
"""
import subprocess

import numpy as np
from osgeo import gdal

gdal.UseExceptions()
B, KEY = "public-connectivity", "present-day-connectivity-categories-cog.tif"
src, vrt, out = f"/vsis3/{B}/{KEY}", "/scratch/in.vrt", "/scratch/out-cog.tif"
gdal.Translate(vrt, src, format="VRT")
t = open(vrt).read()
assert t.count("<SimpleSource") == 1
t = t.replace("<SimpleSource", "<ComplexSource").replace(
    "</SimpleSource>", "<LUT>0:255,1:1,255:255</LUT></ComplexSource>")
open(vrt, "w").write(t)
subprocess.run(["gdal_translate", "-of", "COG", "-co", "COMPRESS=DEFLATE", "-co", "BLOCKSIZE=512",
                "-co", "OVERVIEW_RESAMPLING=NEAREST", "-a_nodata", "255", vrt, out], check=True)
a = gdal.Open(src).ReadAsArray()
b = gdal.Open(out).ReadAsArray()
assert a.shape == b.shape and gdal.Open(out).GetGeoTransform() == gdal.Open(src).GetGeoTransform()
assert np.array_equal(b, np.where(a == 0, 255, a)), "remap differs from 0 -> 255"
print(f"whole raster checked: {int((a == 0).sum())} zero pixels -> 255; no 0 left: {not (b == 0).any()}", flush=True)
r = lambda *args: subprocess.run(["rclone", *args, "-v"], check=True)
r("copyto", f"nrp:{B}/{KEY}", f"nrp:{B}/staging/916-backup/{KEY}")
r("copyto", out, f"nrp:{B}/{KEY}")
print("=== done", flush=True)
