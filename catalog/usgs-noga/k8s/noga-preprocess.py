#!/usr/bin/env python3
"""Stage raw and merge the USGS NOGA Assessment Unit releases (issue #700).

`cng-convert-to-parquet` takes one source, and the national assessment is published
one province/formation release at a time, so this job does the merge:

  1. download each US release's shapefile parts, Tbl_FS_Results.csv and FGDC XML
  2. stage them under s3://<BUCKET>/raw/noga-assessment-units/<sciencebase-id>/
  3. merge the AU polygons into one WGS84 GeoPackage, joining the per-AU
     undiscovered-volume fractiles from Tbl_FS_Results.csv on
     ASSESSCODE = ASSESSAREACODE
  4. drop AUs superseded by a newer release (same ASSESSCODE, older pubdate)
  5. upload the GeoPackage + a build report for the STAC

The release manifest (`manifest.json`, pinned by ../build-manifest.py) is the edition
record: a merged national product has no single upstream edition.

Env: BUCKET, MANIFEST (default /config/manifest.json), OUT (default /tmp/noga.gpkg),
     NOGA_LIMIT (test only: process the first N releases), NOGA_NO_UPLOAD=1.
"""

import csv
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request

from osgeo import ogr, osr

ogr.UseExceptions()
osr.UseExceptions()

BUCKET = os.environ.get("BUCKET", "public-usgs")
DATASET = "noga-assessment-units"
MANIFEST = os.environ.get("MANIFEST", "/config/manifest.json")
OUT = os.environ.get("OUT", "/tmp/noga.gpkg")
RAW = "/tmp/raw"
LIMIT = int(os.environ.get("NOGA_LIMIT", "0"))
NO_UPLOAD = os.environ.get("NOGA_NO_UPLOAD") == "1"

# Boundary attributes carried by every release's AU shapefile, oldest to newest.
BOUNDARY_COLS = [
    "REGNUM",
    "REGNAME",
    "PROVCODE",
    "PROVNAME",
    "TPSCODE",
    "TPSNAME",
    "ASSESSCODE",
    "ASSESSNAME",
]

# Descriptive columns from Tbl_FS_Results.csv (issue #700 column contract).
RESULT_INT_COLS = ["ASSESSYEAR"]
RESULT_TEXT_COLS = [
    "ASSESSMETHOD",
    "ACCUMTYPE",
    "RESERVOIRTYPE",
    "STATUS",
]

# Undiscovered-volume fractiles. MMB = million barrels, BCF = billion cubic feet.
VOLUME_COLS = [
    f"{prefix}_{fractile}_{unit}"
    for prefix, unit in (
        ("OIL", "MMB"),
        ("GAS", "BCF"),
        ("AG", "BCF"),
        ("NAGAS", "BCF"),
        ("NGL", "MMB"),
        ("AGL", "MMB"),
        ("NAGL", "MMB"),
    )
    for fractile in ("F95", "F50", "F5", "MN")
]

DERIVED_COLS = ["sciencebase_id", "release_pubdate", "source_shapefile"]

SHP_PARTS = ("shp", "shx", "dbf", "prj", "cpg")


def log(msg):
    print(msg, flush=True)


def download(url, dest, attempts=6):
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cng-datasets/noga-ingest"})
            with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as fh:
                while chunk := r.read(1 << 20):
                    fh.write(chunk)
            return
        except Exception as exc:  # noqa: BLE001 - any transport failure is retryable
            if attempt == attempts - 1:
                raise
            log(f"    retry {attempt + 1}/{attempts} ({exc})")
            time.sleep(10 * (attempt + 1))


def clean(value):
    """Source string fields carry trailing newlines ('North America\\n'). A few
    releases type the code columns (REGNUM, PROVCODE, ...) as numbers rather than
    strings, so normalise those to their digit string."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value or None


def to_number(value):
    """CSV numerics are quoted with thousands separators ('2,319'); blank means
    'not assessed', which is not zero, so it stays null."""
    if value is None:
        return None
    value = value.strip().replace(",", "")
    if value in ("", "NA", "N/A", "-"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def read_results(path):
    """Tbl_FS_Results.csv keyed by ASSESSAREACODE."""
    rows = {}
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.DictReader(fh):
            code = clean(row.get("ASSESSAREACODE"))
            if not code:
                continue
            rec = {c: clean(row.get(c)) for c in RESULT_TEXT_COLS}
            for c in RESULT_INT_COLS:
                value = to_number(row.get(c))
                rec[c] = int(value) if value is not None else None
            rec.update({c: to_number(row.get(c)) for c in VOLUME_COLS})
            rows[code] = rec
    return rows


def open_source(path):
    """Shapefile, or the Esri JSON one 2020 Alaska release ships instead."""
    if path.lower().endswith((".json", ".geojson")):
        try:
            return ogr.Open(path)
        except RuntimeError:
            return ogr.Open(f"ESRIJSON:{path}")
    return ogr.Open(path)


def fetch_release(release):
    """Download a release's files into RAW/<id>/ and return local paths."""
    iid = release["id"]
    dest = os.path.join(RAW, iid)
    os.makedirs(dest, exist_ok=True)
    vectors, results_csv = [], None

    for shp in release["shapefiles"]:
        if shp.get("wfs_geojson"):
            # CloudShapefileFacet releases serve no shapefile bytes; the GeoServer
            # GeoJSON export of the same layer is the retrievable raw form.
            path = os.path.join(dest, f"{shp['name']}.geojson")
            download(shp["wfs_geojson"], path)
            with open(path, "rb") as fh:
                head = fh.read(16).lstrip()
            if not head.startswith(b"{"):
                raise RuntimeError(f"{iid} {shp['name']} WFS export is not JSON")
            vectors.append((shp["name"], path))
        elif shp["parts"]:
            for ext in SHP_PARTS:
                url = shp["parts"].get(ext)
                if not url:
                    continue
                path = os.path.join(dest, f"{shp['name']}.{ext}")
                download(url, path)
            vectors.append((shp["name"], os.path.join(dest, f"{shp['name']}.shp")))
        elif shp.get("fallback"):
            path = os.path.join(dest, shp["fallback"]["name"])
            download(shp["fallback"]["url"], path)
            vectors.append((shp["name"], path))
        else:
            raise RuntimeError(f"{iid} {shp['name']} has no downloadable geometry")

    if release["results_csv"]:
        results_csv = os.path.join(dest, release["results_csv"]["name"])
        download(release["results_csv"]["url"], results_csv)

    for xml in release["metadata_xml"]:
        download(xml["url"], os.path.join(dest, xml["name"]))

    return dest, vectors, results_csv


def rclone(src, dst):
    subprocess.run(["rclone", "copy", src, dst, "--checksum"], check=True)


def read_release(release, features, report, wgs84):
    """Stage one release's raw files and append its AU polygons to `features`."""
    iid = release["id"]
    dest, vectors, results_csv = fetch_release(release)
    if not NO_UPLOAD:
        rclone(dest, f"nrp:{BUCKET}/raw/{DATASET}/{iid}/")

    results = read_results(results_csv) if results_csv else {}
    kept, matched = 0, 0
    for shp_name, path in vectors:
        src = open_source(path)
        if src is None:
            raise RuntimeError(f"cannot open {path}")
        src_layer = src.GetLayer(0)
        transform = osr.CoordinateTransformation(src_layer.GetSpatialRef(), wgs84)
        src_defn = src_layer.GetLayerDefn()
        present = {
            src_defn.GetFieldDefn(i).GetName().upper(): src_defn.GetFieldDefn(i).GetName()
            for i in range(src_defn.GetFieldCount())
        }
        for feat in src_layer:
            geom = feat.GetGeometryRef()
            if geom is None or geom.IsEmpty():
                continue
            geom = geom.Clone()
            geom.Transform(transform)
            geom.FlattenTo2D()  # some releases carry a constant Z
            if not geom.IsValid():
                geom = geom.MakeValid()
            geom = ogr.ForceToMultiPolygon(geom)
            attrs = {
                c: clean(feat.GetField(present[c])) if c in present else None
                for c in BOUNDARY_COLS
            }
            code = attrs.get("ASSESSCODE")
            res = results.get(code)
            if res:
                matched += 1
                attrs.update(res)
            attrs["sciencebase_id"] = iid
            attrs["release_pubdate"] = release["pubdate"]
            attrs["source_shapefile"] = shp_name
            features.append((attrs, geom.ExportToWkb()))
            kept += 1
        src = None

    report.append(
        {
            "sciencebase_id": iid,
            "title": release["title"],
            "pubdate": release["pubdate"],
            "shapefiles": [s["name"] for s in release["shapefiles"]],
            "features": kept,
            "results_csv": bool(results_csv),
            "results_matched": matched,
        }
    )
    log(f"    {kept} AU polygons, {matched} joined to Tbl_FS_Results.csv")


def main():
    with open(MANIFEST) as fh:
        manifest = json.load(fh)
    releases = manifest["releases"]
    if LIMIT:
        releases = releases[:LIMIT]
    log(f"{len(releases)} US releases ({manifest['excluded_non_us_releases']} non-US excluded)")

    os.makedirs(RAW, exist_ok=True)
    wgs84 = osr.SpatialReference()
    wgs84.ImportFromEPSG(4326)
    wgs84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    driver = ogr.GetDriverByName("GPKG")
    if os.path.exists(OUT):
        os.remove(OUT)
    ds = driver.CreateDataSource(OUT)
    layer = ds.CreateLayer(DATASET.replace("-", "_"), wgs84, ogr.wkbMultiPolygon)
    for name in BOUNDARY_COLS + RESULT_TEXT_COLS + DERIVED_COLS:
        layer.CreateField(ogr.FieldDefn(name, ogr.OFTString))
    for name in RESULT_INT_COLS:
        layer.CreateField(ogr.FieldDefn(name, ogr.OFTInteger))
    for name in VOLUME_COLS:
        layer.CreateField(ogr.FieldDefn(name, ogr.OFTReal))
    defn = layer.GetLayerDefn()

    features, report, failures = [], [], []
    for n, release in enumerate(releases, 1):
        iid = release["id"]
        log(f"[{n}/{len(releases)}] {iid} {release['pubdate']} {release['title'][:70]}")
        try:
            features_before = len(features)
            read_release(release, features, report, wgs84)
        except Exception as exc:  # noqa: BLE001 - report every bad release in one pass
            del features[features_before:]
            failures.append((iid, repr(exc)))
            log(f"    FAILED: {exc!r}")

    if failures:
        log("\n%d of %d releases failed:" % (len(failures), len(releases)))
        for iid, err in failures:
            log(f"  {iid}: {err}")
        sys.exit("ERROR: refusing to publish a partial merge")

    # AU codes recur across revised releases; the newest release wins.
    newest = {}
    for attrs, _ in features:
        code = attrs["ASSESSCODE"]
        key = (attrs["release_pubdate"] or "", attrs["sciencebase_id"])
        if code and key > newest.get(code, ("", "")):
            newest[code] = key

    superseded = {}
    published = {}
    written = 0
    layer.StartTransaction()
    for attrs, wkb in features:
        code = attrs["ASSESSCODE"]
        iid = attrs["sciencebase_id"]
        key = (attrs["release_pubdate"] or "", iid)
        if code and key != newest[code]:
            superseded.setdefault(iid, set()).add(code)
            continue
        published[iid] = published.get(iid, 0) + 1
        feat = ogr.Feature(defn)
        for name, value in attrs.items():
            if value is not None:
                feat.SetField(name, value)
        feat.SetGeometry(ogr.CreateGeometryFromWkb(wkb))
        layer.CreateFeature(feat)
        feat = None
        written += 1
    layer.CommitTransaction()
    ds = None

    for entry in report:
        iid = entry["sciencebase_id"]
        entry["superseded_assesscodes"] = sorted(superseded.get(iid, set()))
        entry["features_published"] = published.get(iid, 0)

    log(f"\nmerged {len(features)} AU polygons -> {written} published "
        f"({len(features) - written} superseded by a newer release)")
    full_run = len(releases) == manifest["us_releases"]
    if full_run and written < 200:
        sys.exit(f"ERROR: only {written} features written on a full run, expected several hundred")

    size = os.path.getsize(OUT)
    digest = hashlib.sha256()
    with open(OUT, "rb") as fh:
        while chunk := fh.read(1 << 22):
            digest.update(chunk)
    log(f"{OUT}: {size} bytes sha256={digest.hexdigest()}")

    summary = {
        "access_date": manifest["access_date"],
        "community": manifest["community"],
        "us_releases": len(releases),
        "excluded_non_us_releases": manifest["excluded_non_us_releases"],
        "releases_with_results_csv": sum(1 for r in report if r["results_csv"]),
        "au_polygons_merged": len(features),
        "au_polygons_published": written,
        "gpkg": {
            "path": f"s3://{BUCKET}/raw/{DATASET}.gpkg",
            "bytes": size,
            "sha256": digest.hexdigest(),
        },
        "releases": report,
    }
    with open("/tmp/build-report.json", "w") as fh:
        json.dump(summary, fh, indent=1)

    if not NO_UPLOAD:
        subprocess.run(
            ["rclone", "copyto", OUT, f"nrp:{BUCKET}/raw/{DATASET}.gpkg", "-P"], check=True
        )
        subprocess.run(
            [
                "rclone",
                "copyto",
                "/tmp/build-report.json",
                f"nrp:{BUCKET}/raw/{DATASET}/build-report.json",
            ],
            check=True,
        )
    log("DONE")


if __name__ == "__main__":
    main()
