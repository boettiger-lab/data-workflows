#!/usr/bin/env python3
"""Merge the FMMP 2022 per-county FGDB layers into one GeoPackage layer (#615).

DOC publishes the 2022 edition as a File Geodatabase with one layer per county
(`<county>2022`) and adds counties to it in place as each is released. The build
needs a single layer, so this appends every layer into `fmmp_2022` in EPSG:4326.

A short read must fail the job, not produce a small file: the merged count is
checked against the FGDB's own layer counts and against the
CaliforniaImportantFarmland_2022 FeatureServer's returnCountOnly, and the number
of distinct counties is checked against the number of layers.

Usage: merge_fgdb.py <path.gdb> <out.gpkg> <counts.json>
"""

import json
import sys
import time
import urllib.parse
import urllib.request

from osgeo import gdal, ogr

gdal.UseExceptions()

SERVICE = (
    "https://gis.conservation.ca.gov/server/rest/services/DLRP/"
    "CaliforniaImportantFarmland_2022/FeatureServer/0/query"
)
LAYER = "fmmp_2022"


def service_count():
    """Feature count the FeatureServer reports, with retries."""
    url = f"{SERVICE}?{urllib.parse.urlencode({'where': '1=1', 'returnCountOnly': 'true', 'f': 'json'})}"
    last = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                payload = json.loads(r.read())
            if "error" in payload:
                raise RuntimeError(payload["error"])
            return payload["count"]
        except Exception as e:  # noqa: BLE001 - retry any transient failure
            last = e
            print(f"  count attempt {attempt + 1}/6 failed ({e})", flush=True)
            time.sleep(2 ** attempt)
    sys.exit(f"FATAL: could not read the service count: {last}")


def main():
    gdb, out, counts_path = sys.argv[1:4]

    src = ogr.Open(gdb)
    layers = {}
    for i in range(src.GetLayerCount()):
        lyr = src.GetLayerByIndex(i)
        layers[lyr.GetName()] = lyr.GetFeatureCount()
    src = None
    expected = sum(layers.values())
    print(f"FGDB: {len(layers)} layers, {expected} features", flush=True)

    first = True
    for name in sorted(layers):
        sql = (
            "SELECT CAST(upd_year AS integer) AS upd_year, county_nam, polygon_ac, "
            f'polygon_ty, Shape_Length, Shape_Area FROM "{name}"'
        )
        gdal.VectorTranslate(
            out,
            gdb,
            format="GPKG",
            SQLStatement=sql,
            layerName=LAYER,
            dstSRS="EPSG:4326",
            geometryType="MULTIPOLYGON",
            dim="XY",  # calaveras2022 is 3D Measured
            accessMode=None if first else "append",
        )
        first = False
        print(f"  appended {name}: {layers[name]}", flush=True)

    ds = ogr.Open(out)
    got = ds.GetLayerByName(LAYER).GetFeatureCount()
    per_county = {}
    res = ds.ExecuteSQL(f"SELECT county_nam, COUNT(*) AS n FROM {LAYER} GROUP BY county_nam")
    for f in res:
        per_county[f.GetField("county_nam")] = f.GetField("n")
    ds.ReleaseResultSet(res)
    ds = None

    fs = service_count()
    print(f"merged={got} fgdb_layers_sum={expected} featureserver={fs} "
          f"counties={len(per_county)} layers={len(layers)}", flush=True)

    with open(counts_path, "w") as fh:
        json.dump({"layers": layers, "per_county": per_county, "merged": got,
                   "featureserver_count": fs}, fh, indent=1, sort_keys=True)

    if got != expected:
        sys.exit(f"FATAL: merged {got} features, FGDB layers hold {expected}")
    if fs != expected:
        sys.exit(f"FATAL: FGDB holds {expected} features, FeatureServer reports {fs}")
    if len(per_county) != len(layers):
        sys.exit(f"FATAL: {len(per_county)} distinct counties for {len(layers)} layers")


if __name__ == "__main__":
    main()
