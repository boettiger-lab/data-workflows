"""Stage the USGS 2011 Paradox Basin AU release to NRP and merge it into one GeoPackage (issue #722).

Reads the pinned manifest (../manifest.json, mounted at /config/manifest.json), downloads every
shapefile part and the FGDC metadata from ScienceBase, checks each size against the manifest,
stages them under s3://public-usgs/raw/paradox-basin-assessment-units/, then merges the 10
single-AU shapefiles into s3://public-usgs/raw/paradox-basin-assessment-units.gpkg with a
`source_shapefile` column. Checksums in build-report.json are recomputed from the stored objects.
"""
import hashlib
import json
import os
import subprocess
import time
import urllib.request

BUCKET = os.environ.get("BUCKET", "public-usgs")
DATASET = "paradox-basin-assessment-units"
RAW = f"nrp:{BUCKET}/raw/{DATASET}"
WORK = "/tmp/paradox"
LAYER = DATASET


def run(*cmd, capture=False):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, capture_output=capture).stdout


def fetch(url, dest, size):
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as f:
                f.write(r.read())
            got = os.path.getsize(dest)
            if got != size:
                raise RuntimeError(f"{dest}: {got} bytes, manifest says {size}")
            return
        except Exception as e:  # noqa: BLE001
            print(f"retry {attempt + 1} {url}: {e}", flush=True)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}")


def stored_hashes(remote):
    data = run("rclone", "cat", remote, capture=True)
    return {"size": len(data), "md5": hashlib.md5(data).hexdigest(),
            "sha256": hashlib.sha256(data).hexdigest()}


def main():
    manifest = json.load(open("/config/manifest.json"))
    os.makedirs(WORK, exist_ok=True)
    report = {"sciencebase_id": manifest["sciencebase_id"], "doi": manifest["doi"],
              "accessed": manifest["accessed"], "raw_prefix": f"s3://{BUCKET}/raw/{DATASET}/",
              "files": {}}

    for f in manifest["files"]:
        fetch(f["url"], f"{WORK}/{f['name']}", f["size"])
    for shp in manifest["shapefiles"]:
        for p in shp["parts"]:
            fetch(p["url"], f"{WORK}/{p['name']}", p["size"])

    run("rclone", "copy", WORK, RAW)

    for name in sorted(os.listdir(WORK)):
        report["files"][name] = stored_hashes(f"{RAW}/{name}")

    gpkg = f"/tmp/{DATASET}.gpkg"
    for i, shp in enumerate(manifest["shapefiles"]):
        name = shp["name"]
        sql = f"SELECT *, '{name}' AS source_shapefile FROM \"{name}\""
        mode = [] if i == 0 else ["-update", "-append"]
        run("ogr2ogr", *mode, "-f", "GPKG", gpkg, f"{WORK}/{name}.shp", "-sql", sql,
            "-nln", LAYER, "-nlt", "MULTIPOLYGON", "-t_srs", "EPSG:4326",
            *([] if i else ["-lco", "GEOMETRY_NAME=geom"]))

    count = run("ogrinfo", "-so", gpkg, LAYER, capture=True).decode()
    print(count, flush=True)

    run("rclone", "copyto", gpkg, f"nrp:{BUCKET}/raw/{DATASET}.gpkg")
    report["merged"] = {"path": f"s3://{BUCKET}/raw/{DATASET}.gpkg",
                        **stored_hashes(f"nrp:{BUCKET}/raw/{DATASET}.gpkg")}

    with open("/tmp/build-report.json", "w") as f:
        json.dump(report, f, indent=2)
    run("rclone", "copyto", "/tmp/build-report.json", f"{RAW}/build-report.json")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
