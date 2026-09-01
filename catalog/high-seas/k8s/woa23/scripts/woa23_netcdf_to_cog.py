#!/usr/bin/env python3
"""World Ocean Atlas 2023 netCDF -> WGS84 float32 COG (data-workflows #643).

One task per VARIABLE (8 of them); each task emits one COG per target depth
(0 m, 200 m, 1000 m), so 8 tasks produce 24 COGs. Localizing each 46-82 MB
netCDF once and slicing three depths out of it beats 24 tasks that each
re-download the same file.

Three things are verified rather than assumed, because each has a failure mode
that no structural check downstream would catch:

1. **Depth-to-band mapping.** The variable is (time=1, depth=102, lat, lon), so
   GDAL exposes 102 bands. The band for a given depth is found by reading each
   band's `NETCDF_DIM_depth` metadata, never by trusting a hardcoded index.
   A silent off-by-one would publish 5 m data labelled as the surface.
2. **Orientation.** WOA stores latitude ascending (south to north); a north-up
   GeoTIFF needs row 0 at maximum latitude. GDAL's netCDF driver normally
   resolves this, and the land/ocean probe below proves it did. No symmetric
   check (pole-vs-pole, row means) can see a vertical flip.
3. **Physical plausibility.** The `_FillValue` is 9.96921e+36. A leaked sentinel
   passes every row-count and partition check but destroys any mean, so each
   variable declares the range its quantity can actually occupy and the build
   fails if the data leaves it.
"""
import argparse
import json
import os
import sys

import numpy as np
from osgeo import gdal, osr

gdal.UseExceptions()

# NaN rather than a numeric sentinel: AOU is legitimately negative in
# supersaturated surface water and temperature reaches -2 C, so no negative
# sentinel is safely outside every variable's real range.
NODATA = float("nan")

TARGET_DEPTHS = (0.0, 200.0, 1000.0)

# (short_name, raw_file, netcdf_variable, value_column, units, lo, hi)
# lo/hi are physical plausibility bounds, deliberately a little generous: they
# exist to catch a leaked 9.96921e+36 fill or a double-applied transform, not to
# second-guess the analysed field at the margins.
VARIABLES = [
    ("temperature",       "woa23_decav91C0_t00_01.nc", "t_an", "temperature",       "degree_Celsius",         -3.0,   40.0),
    ("salinity",          "woa23_decav91C0_s00_01.nc", "s_an", "salinity",          "1",                       0.0,   45.0),
    ("oxygen",            "woa23_all_o00_01.nc",       "o_an", "oxygen",            "micromoles_per_kilogram", -10.0, 600.0),
    ("oxygen-saturation", "woa23_all_O00_01.nc",       "O_an", "oxygen_saturation", "percent",                 0.0,  150.0),
    ("aou",               "woa23_all_A00_01.nc",       "A_an", "aou",               "micromoles_per_kilogram", -150.0, 500.0),
    ("silicate",          "woa23_all_i00_01.nc",       "i_an", "silicate",          "micromoles_per_kilogram", -1.0,  300.0),
    ("phosphate",         "woa23_all_p00_01.nc",       "p_an", "phosphate",         "micromoles_per_kilogram", -0.5,   10.0),
    ("nitrate",           "woa23_all_n00_01.nc",       "n_an", "nitrate",           "micromoles_per_kilogram", -1.0,   80.0),
]

# 100 degE / 40 degN is inland Asia: no marine value at any depth. 100 degE /
# 40 degS is open Indian Ocean: a valid value at 0 m and 200 m. A vertical flip
# swaps the two.
PROBE_LON, PROBE_LAT_LAND, PROBE_LAT_SEA = 100.0, 40.0, -40.0


def depth_band_index(ds, target):
    """1-based GDAL band whose NETCDF_DIM_depth equals `target`, or exit."""
    for b in range(1, ds.RasterCount + 1):
        md = ds.GetRasterBand(b).GetMetadata()
        raw = md.get("NETCDF_DIM_depth")
        if raw is None:
            continue
        if abs(float(raw) - target) < 1e-6:
            return b
    sys.exit(
        f"no band with NETCDF_DIM_depth == {target}; "
        f"available: {[ds.GetRasterBand(b).GetMetadata().get('NETCDF_DIM_depth') for b in range(1, min(ds.RasterCount, 8) + 1)]}..."
    )


def probe(data, gt, lon, lat):
    col = int((lon - gt[0]) / gt[1])
    row = int((lat - gt[3]) / gt[5])
    return data[row, col]


def build_one(var, depth, raw_dir, out_dir):
    short, raw_file, ncvar, column, units, lo, hi = var
    name = f"{short}-{int(depth)}m"
    src = os.path.join(raw_dir, raw_file)
    print(f"[{name}] reading {ncvar} depth={depth} from {src}", flush=True)

    ds = gdal.Open(f'NETCDF:"{src}":{ncvar}')
    if ds is None:
        sys.exit(f"[{name}] could not open {ncvar} in {src}")
    if ds.RasterCount != 102:
        sys.exit(f"[{name}] expected 102 depth bands, got {ds.RasterCount}")

    band_no = depth_band_index(ds, depth)
    print(f"[{name}] depth {depth} m -> GDAL band {band_no}", flush=True)

    gt = ds.GetGeoTransform()
    if gt[5] > 0:
        sys.exit(f"[{name}] geotransform is bottom-up (gt[5]={gt[5]}); expected north-up")
    expected = (-180.0, 1.0, 0.0, 90.0, 0.0, -1.0)
    if not all(abs(a - b) < 1e-6 for a, b in zip(gt, expected)):
        sys.exit(f"[{name}] unexpected geotransform {gt}, wanted {expected}")

    band = ds.GetRasterBand(band_no)
    fill = band.GetNoDataValue()
    data = band.ReadAsArray().astype("float64")
    print(f"[{name}] {ds.RasterXSize}x{ds.RasterYSize} fill={fill}", flush=True)

    # Fold the upstream fill into NaN so one sentinel carries through to the COG.
    if fill is not None:
        data[np.isclose(data, fill, rtol=1e-9)] = np.nan
    # Belt and braces: anything still at WOA's 9.96921e+36 magnitude is a fill
    # the declared _FillValue did not cover.
    data[np.abs(data) > 1e30] = np.nan

    land = probe(data, gt, PROBE_LON, PROBE_LAT_LAND)
    sea = probe(data, gt, PROBE_LON, PROBE_LAT_SEA)
    print(f"[{name}] probe land(100E,40N)={land} sea(100E,40S)={sea}", flush=True)
    if not np.isnan(land):
        sys.exit(f"[{name}] orientation probe failed: inland Asia holds {land}, expected nodata")
    if depth <= 200.0 and np.isnan(sea):
        sys.exit(f"[{name}] orientation probe failed: open Indian Ocean at {depth} m is nodata")

    valid = data[~np.isnan(data)]
    if valid.size == 0:
        sys.exit(f"[{name}] COG would be entirely nodata")
    vmin, vmax, vmean = float(valid.min()), float(valid.max()), float(valid.mean())
    print(f"[{name}] valid={valid.size} min={vmin:.4f} max={vmax:.4f} mean={vmean:.4f} units={units}", flush=True)
    if vmin < lo or vmax > hi:
        sys.exit(f"[{name}] outside plausible range [{lo}, {hi}]: got [{vmin}, {vmax}] -- fill leak or wrong band?")

    tmp = os.path.join(out_dir, f"{name}.tmp.tif")
    out = os.path.join(out_dir, f"woa23-{name}-cog.tif")
    drv = gdal.GetDriverByName("GTiff")
    dst = drv.Create(tmp, ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Float32)
    dst.SetGeoTransform(gt)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    dst.SetProjection(srs.ExportToWkt())
    ob = dst.GetRasterBand(1)
    ob.SetNoDataValue(NODATA)
    ob.WriteArray(data.astype("float32"))
    ob.SetDescription(column)
    ob.SetUnitType(units)
    dst.SetMetadata({
        "WOA23_VARIABLE": ncvar,
        "WOA23_DEPTH_M": str(int(depth)),
        "WOA23_SOURCE_FILE": raw_file,
        "WOA23_VALUE_COLUMN": column,
        "UNITS": units,
    })
    dst.FlushCache()
    dst = None

    gdal.Translate(out, tmp, format="COG", creationOptions=["COMPRESS=DEFLATE", "BLOCKSIZE=256"])
    os.remove(tmp)
    print(f"[{name}] wrote {out} ({os.path.getsize(out)} bytes)", flush=True)
    return {"name": name, "column": column, "units": units,
            "min": vmin, "max": vmax, "mean": vmean, "valid_pixels": int(valid.size)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="emit the task manifest as JSON")
    ap.add_argument("--index", type=int, help="variable index to build (0-7)")
    ap.add_argument("--raw-dir", default="/tmp/raw")
    ap.add_argument("--out-dir", default="/tmp/cog")
    args = ap.parse_args()

    if args.list:
        print(json.dumps([
            {"index": i, "short": v[0], "raw": v[1], "ncvar": v[2],
             "outputs": [f"{v[0]}-{int(d)}m" for d in TARGET_DEPTHS]}
            for i, v in enumerate(VARIABLES)
        ]))
        return

    if args.index is None or not 0 <= args.index < len(VARIABLES):
        sys.exit(f"--index must be 0..{len(VARIABLES) - 1}")

    var = VARIABLES[args.index]
    os.makedirs(args.out_dir, exist_ok=True)
    summary = [build_one(var, d, args.raw_dir, args.out_dir) for d in TARGET_DEPTHS]
    print("SUMMARY " + json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
