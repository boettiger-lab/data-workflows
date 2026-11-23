#!/usr/bin/env python3
"""Stage one Ocean Tipping Points layer from PacIOOS GeoServer WCS (#851).

Usage: stage.py <layer> <out_dir>

Asks WCS DescribeCoverage for the layer's native grid, requests the full envelope at exactly
that width and height (so GeoServer returns the stored pixels, not a resample), and writes:
  <out_dir>/<layer>.tif         the GeoTIFF as delivered
  <out_dir>/<layer>.tif.json    request URL, access time, bytes, sha256, grid, nodata, stats
  <out_dir>/<short>-cog.tif     WGS84 COG (EPSG:4326 assigned; WCS delivers no CRS), source nodata kept
<short> is the layer name without the hi_otp_all_ prefix.
"""
import hashlib
import json
import re
import subprocess
import sys
import time

from osgeo import gdal

gdal.UseExceptions()
OWS = "https://geo.pacioos.hawaii.edu/geoserver/PACIOOS/ows"


def fetch(url, path):
    # PacIOOS GeoServer offers only a weak DH key, which OpenSSL's default level rejects
    subprocess.run(["curl", "-sS", "--fail", "--retry", "5", "--retry-all-errors",
                    "--ciphers", "DEFAULT@SECLEVEL=1", "-o", path, url], check=True)


def main():
    layer, out = sys.argv[1:3]
    short = layer.removeprefix("hi_otp_all_")
    fetch(f"{OWS}?service=WCS&version=1.0.0&request=DescribeCoverage&coverage=PACIOOS:{layer}",
          f"{out}/describe.xml")
    x = open(f"{out}/describe.xml").read()
    # The native grid is origin (centre of the top-left pixel) + offset vectors + grid limits.
    # Some layers' EPSG:4326 Envelope is wider than the grid, so it is not used.
    ox, oy = map(float, re.search(r"<gml:origin><gml:pos>([^<]+)</gml:pos>", x).group(1).split())
    (dx, _), (_, dy) = (map(float, v.split()) for v in re.findall(r"<gml:offsetVector>([^<]+)</gml:offsetVector>", x))
    hx, hy = map(int, re.search(r"<gml:high>([^<]+)</gml:high>", x).group(1).split())
    w, h = hx + 1, hy + 1
    x0, y1 = ox - dx / 2, oy - dy / 2
    x1, y0 = x0 + w * dx, y1 + h * dy
    url = (f"{OWS}?service=WCS&version=1.0.0&request=GetCoverage&coverage=PACIOOS:{layer}"
           f"&format=GeoTIFF&crs=EPSG:4326&bbox={x0!r},{y0!r},{x1!r},{y1!r}&width={w}&height={h}")
    raw = f"{out}/{layer}.tif"
    fetch(url, raw)
    accessed = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    ds = gdal.Open(raw)
    gt = ds.GetGeoTransform()
    assert (ds.RasterXSize, ds.RasterYSize) == (w, h), (ds.RasterXSize, ds.RasterYSize, w, h)
    assert abs(gt[1] - dx) < 1e-12 and abs(gt[5] - dy) < 1e-12 and abs(gt[0] - x0) < 1e-9 and abs(gt[3] - y1) < 1e-9, (gt, x0, y1, dx)
    b = ds.GetRasterBand(1)
    nodata = b.GetNoDataValue()
    mn, mx, mean, sd = b.ComputeStatistics(False)
    valid = float(b.GetMetadataItem("STATISTICS_VALID_PERCENT") or "nan")
    dtype = gdal.GetDataTypeName(b.DataType)
    ds = None

    gdal.Translate(f"{out}/{short}-cog.tif", raw, format="COG", outputSRS="EPSG:4326",
                   creationOptions=["COMPRESS=ZSTD", "BLOCKSIZE=512", "OVERVIEW_RESAMPLING=AVERAGE"]
                   + (["PREDICTOR=FLOATING_POINT"] if dtype.startswith("Float") else []))
    c = gdal.Open(f"{out}/{short}-cog.tif")
    assert c.GetGeoTransform() == gt and c.GetRasterBand(1).GetNoDataValue() == nodata
    c = None

    data = open(raw, "rb").read()
    meta = {"layer": layer, "source_url": url, "accessed": accessed, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "width": w, "height": h,
            "geotransform": gt, "dtype": dtype, "nodata": nodata,
            "min": mn, "max": mx, "mean": mean, "std": sd, "valid_percent": valid}
    json.dump(meta, open(f"{raw}.json", "w"), indent=1)
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
