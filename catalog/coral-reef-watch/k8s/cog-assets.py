#!/usr/bin/env python3
"""Publish the CRW COGs as STAC assets, so map apps can find them (data-workflows#802).

    cog-assets.py <bucket> <tier prefix> <daily|monthly|annual> <product> [<product> ...]

The hex table is each product collection's only other asset; geo-agent builds a raster layer
only from a STAC asset, so the COGs need entries of their own.

- daily and monthly: copies the newest dated COG to cog/<product>-latest.tif (server-side, on
  NRP) and points the asset <product>-cog at it. The key and href stay fixed as the series rolls
  forward, so an app config never has to change; the title carries the date shown.
- annual: one asset per published year, <product>-cog-YYYY. Years are separate composites
  published side by side, not one refreshed edition, so the year belongs in the key.

Idempotent: it rebuilds every COG asset from the bucket listing on each run, leaves the hex
asset and everything else in the collection untouched, and skips the upload when nothing changed.
Uses only the standard library and rclone (remote `nrp`), so it runs in the build image and locally.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

DRY_RUN = os.environ.get("DRY_RUN") == "1"  # write the STAC to a local temp dir; upload nothing
PUBLIC = "https://s3-west.nrp-nautilus.io"
COG_TYPE = "image/tiff; application=geotiff; profile=cloud-optimized"
EXT = {
    "raster": "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
    "classification": "https://stac-extensions.github.io/classification/v2.0.0/schema.json",
}
# Bleaching Alert Area colours. Levels 0-4 follow Coral Reef Watch's published map colours;
# levels 5-7 (the five-level annual product only) extend the ramp to darker reds and purple.
BAA_COLOURS = ["C8FAFA", "FFF000", "FAAA0A", "F00000", "960000", "640000", "50003C", "320050"]


def rclone(*args, check=True):
    return subprocess.run(["rclone", *args], check=check, capture_output=True, text=True).stdout


def band(product, values_note):
    """raster:bands for one product. Measured from the published COGs on 2026-11-02 (BUILD.md)."""
    if product.startswith("baa"):
        b = {"name": "bleaching_alert_area", "data_type": "uint8", "nodata": 251}
        levels = dict(re.findall(r"(\d+)=([^,.]+)", values_note or ""))
        if levels:
            b["classification:classes"] = [
                {"value": int(v), "name": n.strip(), "description": n.strip(),
                 "color_hint": BAA_COLOURS[int(v)]}
                for v, n in sorted(levels.items(), key=lambda kv: int(kv[0]))]
        return b
    unit = "Celsius-weeks" if product.startswith("dhw") else "Celsius"
    return {"data_type": "int16", "nodata": -32768, "scale": 0.01, "offset": 0, "unit": unit}


def encoding_note(product):
    if product.startswith("baa"):
        return ("Each pixel holds a Bleaching Alert Area level as a whole number. "
                "Land, sea ice and missing pixels hold 251, the declared no-data value.")
    unit = "degree Celsius-weeks" if product.startswith("dhw") else "degrees Celsius"
    return (f"Pixels are stored as whole numbers in hundredths of {unit}: a stored 377 is 3.77. "
            "The scale factor of 0.01 is declared in the file, so a reader that applies it "
            "(GDAL, rasterio, or TiTiler with unscale=true) sees the real values. "
            "Land, sea ice and missing pixels hold -32768, the declared no-data value.")


def main():
    bucket, prefix, tier, *products = sys.argv[1:]
    if tier not in ("daily", "monthly", "annual") or not products:
        sys.exit(__doc__)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    work = os.environ.get("OUT_DIR") or tempfile.mkdtemp()
    for p in products:
        base = f"{prefix}/{p}"
        stac_path = f"{work}/{p}.json"
        try:
            text = rclone("cat", f"nrp:{bucket}/{base}/stac-collection.json")
        except subprocess.CalledProcessError:
            print(f"{p}: no stac-collection.json, skipping")
            continue
        coll = json.loads(text)
        before = json.dumps(coll, sort_keys=True)

        # The value column's description lists the BAA levels (0=No Stress, ...).
        values_note = next((c.get("description", "") for a in coll.get("assets", {}).values()
                            for c in a.get("table:columns", []) if c["name"] == "bleaching_alert_area"), "")
        name = coll["title"].split(" (")[0]
        files = rclone("lsf", "--files-only", f"nrp:{bucket}/{base}/cog/").split()
        digits = {"daily": 8, "monthly": 6, "annual": 4}[tier]
        dated = sorted(f for f in files if re.fullmatch(rf"{re.escape(p)}-\d{{{digits}}}\.tif", f))
        if not dated:
            print(f"{p}: no COGs yet, skipping")
            continue
        assets = {k: v for k, v in coll.get("assets", {}).items()
                  if not re.fullmatch(rf"{re.escape(p)}-cog(-\d{{4}})?", k)}
        b = band(p, values_note)
        note = encoding_note(p)

        if tier == "annual":
            for f in dated:
                y = f[len(p) + 1:-4]
                partial = (y == "1985" and p in ("dhw-max", "baa-max", "baa5-max"))
                span = "25 March to 31 December 1985" if partial else y
                assets[f"{p}-cog-{y}"] = {
                    "href": f"{PUBLIC}/{bucket}/{base}/cog/{f}",
                    "type": COG_TYPE, "roles": ["data"],
                    "title": f"{name}, {y}",
                    "description": (f"Map image (Cloud-Optimized GeoTIFF, WGS84, 0.05 degree) of the composite "
                                    f"for {span}. {note}"),
                    "start_datetime": f"{'1985-03-25' if partial else y + '-01-01'}T00:00:00Z",
                    "end_datetime": f"{y}-12-31T23:59:59Z",
                    "raster:bands": [b],
                }
        else:
            newest = dated[-1]
            stamp = newest[len(p) + 1:-4]
            if tier == "daily":
                when = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"
                label, period = f"latest day, {when}", "the most recent day published"
            else:
                when = datetime.strptime(stamp, "%Y%m").strftime("%B %Y")
                label, period = f"latest month, {when}", "the most recent month published"
            latest = f"{p}-latest.tif"
            if not DRY_RUN:
                rclone("copyto", f"nrp:{bucket}/{base}/cog/{newest}", f"nrp:{bucket}/{base}/cog/{latest}")
            pattern = "YYYYMMDD" if tier == "daily" else "YYYYMM"
            unit = "day" if tier == "daily" else "month"
            assets[f"{p}-cog"] = {
                "href": f"{PUBLIC}/{bucket}/{base}/cog/{latest}",
                "type": COG_TYPE, "roles": ["data"],
                "title": f"{name} ({label})",
                "description": (f"Map image (Cloud-Optimized GeoTIFF, WGS84, 0.05 degree) of {period}, "
                                f"currently {when}. The file at this address is replaced each time a newer "
                                f"{unit} is added; every {unit} also keeps its own file at {PUBLIC}/{bucket}/{base}/cog/{p}-{pattern}.tif. {note}"),
                "raster:bands": [b],
            }
        coll["assets"] = assets
        exts = coll.setdefault("stac_extensions", [])
        for key in ("raster", "classification"):
            if (key == "raster" or "classification:classes" in b) and EXT[key] not in exts:
                exts.append(EXT[key])
        if json.dumps(coll, sort_keys=True) == before:
            print(f"{p}: COG assets unchanged")
            continue
        coll["updated"] = now
        json.dump(coll, open(stac_path, "w"), indent=2, ensure_ascii=False)
        if DRY_RUN:
            print(f"{p}: dry run, wrote {stac_path}")
            continue
        rclone("copyto", stac_path, f"nrp:{bucket}/{base}/stac-collection.json")
        print(f"{p}: {len(dated)} COGs, assets {sorted(k for k in assets if '-cog' in k)[:3]}...")


if __name__ == "__main__":
    main()
