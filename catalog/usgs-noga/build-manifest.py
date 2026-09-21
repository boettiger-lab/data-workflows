#!/usr/bin/env python3
"""Pin the release manifest for the USGS NOGA Assessment Units ingest (issue #700).

A merged national product has no single upstream edition, so the list of source
releases IS the edition record. This script regenerates manifest.json from the
ScienceBase community; the committed manifest.json is what the build reads.

Usage: python3 build-manifest.py > manifest.json
"""
import json
import re
import sys
import time
import urllib.request

COMMUNITY = "59cab03de4b017cf314094df"  # USGS National and Global Oil and Gas Assessment Project
ITEMS_URL = (
    "https://www.sciencebase.gov/catalog/items?parentId={}&format=json&max=500"
    "&fields=title,dates,tags,files,facets,spatial"
)

# An AU-boundary release is identified by its shapefile name, not its title:
# titles vary ("National Assessment of Oil and Gas Project - ..."), the shapefile
# is always <Something>AUs / <Something>_AU / au<digits>.
AU_SHAPEFILE = re.compile(r"(AUs?$|^au\d|_AU(_|$))", re.I)

# US releases carry a Place tag naming the country or a state. Non-US releases
# name their own countries instead. Verified geometrically against a US boundary
# in the preprocess job.
US_PLACE = re.compile(r"^(United States|U\.S\.A\.|State of |California)")

SHP_PARTS = (".shp", ".shx", ".dbf", ".prj", ".cpg")

# A release published through the newer CloudShapefileFacet exposes a manager *page*
# at "url"; only "downloadUri" returns the bytes. Older facets set both the same.
def href(f):
    return f.get("downloadUri") or f["url"]


# One 2020 Alaska release (NanushukTorokAUs) ships no .shp at all, only Esri JSON,
# GML and a file geodatabase. GDAL reads the Esri JSON via the ESRIJSON driver.
VECTOR_FALLBACK = (".geojson", ".json", ".gdb.zip", ".gml")

# Releases published through the newer CloudShapefileFacet do not serve their
# shapefile bytes: every file route (manager/download, the item-level zip) returns
# the manager SPA or a zero-length entry. Their geometry is retrievable only from
# the ScienceBase GeoServer, which exports the same layer as GeoJSON.
WFS = (
    "https://api.sciencebase.gov/geoserver/sb-{item}/ows?service=WFS&version=1.0.0"
    "&request=GetFeature&typeName=sb-{item}:{layer}&outputFormat=application/json"
    "&maxFeatures=100000"
)


def is_cloud_facet(facet):
    return "Cloud" in str(facet.get("className")) or bool(facet.get("capabilitiesUrlWFS"))


def fetch(url, attempts=6):
    """ScienceBase's catalog API is intermittently slow; retry rather than half-pin."""
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.load(r)
        except Exception as exc:  # noqa: BLE001 - any transport failure is retryable
            if attempt == attempts - 1:
                raise
            print(f"retry {attempt + 1}/{attempts} after {exc}", file=sys.stderr)
            time.sleep(10 * (attempt + 1))


def main():
    data = fetch(ITEMS_URL.format(COMMUNITY))
    releases, excluded = [], []
    for item in data["items"]:
        facets = [
            f
            for f in (item.get("facets") or [])
            if "hapefile" in str(f.get("facetName"))
            and AU_SHAPEFILE.search((f.get("name") or "").strip())
        ]
        if not facets:
            continue
        places = [t["name"] for t in item.get("tags", []) if t.get("type") == "Place"]
        pub = next(
            (d["dateString"] for d in item.get("dates", []) if d.get("type") == "Publication"),
            None,
        )
        entry = {
            "id": item["id"],
            "title": item["title"],
            "pubdate": pub,
            "places": places,
            "bbox": (item.get("spatial") or {}).get("boundingBox"),
        }
        if not any(US_PLACE.match(p) for p in places):
            excluded.append(entry)
            continue

        shapefiles = []
        for facet in facets:
            layer = facet["name"].strip()
            if is_cloud_facet(facet):
                shapefiles.append(
                    {
                        "name": layer,
                        "parts": {},
                        "wfs_geojson": WFS.format(item=item["id"], layer=layer),
                    }
                )
                continue
            parts = {
                f["name"].rsplit(".", 1)[-1].lower(): href(f)
                for f in facet.get("files", [])
                if f["name"].lower().endswith(SHP_PARTS)
            }
            shp = {"name": layer, "parts": parts}
            if not {"shp", "shx", "dbf", "prj"} <= set(parts):
                shp["parts"] = {}
                shp["fallback"] = next(
                    (
                        {"name": f["name"], "url": href(f)}
                        for ext in VECTOR_FALLBACK
                        for f in (item.get("files") or [])
                        if f["name"].lower().endswith(ext)
                        and f["name"].lower().startswith(layer.lower())
                    ),
                    None,
                )
            shapefiles.append(shp)

        item_files = item.get("files") or []
        entry["shapefiles"] = shapefiles
        entry["results_csv"] = next(
            (
                {"name": f["name"], "url": href(f)}
                for f in item_files
                if re.search(r"FS_Results\.csv$", f["name"], re.I)
            ),
            None,
        )
        # FGDC XML lives among the item files on older releases and inside the
        # shapefile facet on CloudShapefileFacet releases.
        xml_sources = item_files + [f for fa in facets for f in fa.get("files", [])]
        seen, metadata_xml = set(), []
        for f in xml_sources:
            if not f["name"].lower().endswith(".xml") or "ColumnDescriptions" in f["name"]:
                continue
            if f["name"] in seen:
                continue
            seen.add(f["name"])
            metadata_xml.append({"name": f["name"], "url": href(f)})
        entry["metadata_xml"] = metadata_xml
        releases.append(entry)

    releases.sort(key=lambda r: (r["pubdate"] or "", r["id"]))
    excluded.sort(key=lambda r: (r["pubdate"] or "", r["id"]))
    json.dump(
        {
            "community": f"https://www.sciencebase.gov/catalog/item/{COMMUNITY}",
            "access_date": "2026-09-21",
            "us_releases": len(releases),
            "excluded_non_us_releases": len(excluded),
            "releases": releases,
            "excluded": [
                {k: v for k, v in e.items() if k in ("id", "title", "pubdate", "places")}
                for e in excluded
            ],
        },
        sys.stdout,
        indent=1,
    )
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
