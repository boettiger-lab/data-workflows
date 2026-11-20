"""Build the private gye-priority-areas collection for the wyoming app's bundled catalog (#994).

Reads the live public collection and rewrites it for private-wyoming: s3:// hrefs for the
parquet and hex (read by wyoming-mcp with its private-wyoming key), the app's /tiles/ proxy
for the PMTiles, licence proprietary, and wyoming.nrp-nautilus.io navigation links.
usage: make_collection.py <public-collection.json> <out.json>
"""
import json, sys

APP = "https://wyoming.nrp-nautilus.io"
CAT = f"{APP}/stac/catalog.json"
SELF = f"{APP}/stac/gye-priority-areas/collection.json"
S3 = "s3://private-wyoming/priority-areas"
TILES = f"{APP}/tiles/priority-areas"

c = json.load(open(sys.argv[1]))
c["license"] = "proprietary"
c["description"] = c["description"].split("\n\nTerms of use:")[0] + (
    "\n\nTerms of use: for internal use only. The boundaries were drawn by Arthur Middleton "
    "(Middleton Lab, UC Berkeley) and provided directly; they have no public source, citation, "
    "DOI or licence, and no redistribution right has been granted. The linked terms statement "
    "records these facts and grants nothing.\n\n"
    "Provenance: built from the GeoPackage PriorityAreas_GYE.gpkg (layer PriorityAreas_GYE, "
    f"three polygons), held as {S3}/raw/PriorityAreas_GYE.gpkg (98,304 bytes, SHA-256 "
    "496e143c4bb8df1f16b90b20f6ca738b137c3821b2e483d282d9b5a9c1bb08ca). No edition label or "
    "publication date is known for the boundaries, so the temporal extent is left open.")
assert "Provenance:" in c["description"] and "s3-west" not in c["description"]

href = {
    "priority-areas-parquet": f"{S3}/priority-areas.parquet",
    "priority-areas-pmtiles": f"{TILES}/priority-areas.pmtiles",
    "priority-areas-hex": f"{S3}/hex/h0=*/data_0.parquet",
    "style-priority-areas": f"{TILES}/styles/priority-areas.json",
    "thumbnail": f"{TILES}/thumbnail.png",
}
assert set(c["assets"]) == set(href), set(c["assets"]) ^ set(href)
for k, h in href.items():
    c["assets"][k]["href"] = h

links = [
    {"rel": "self", "href": SELF, "type": "application/json"},
    {"rel": "root", "href": CAT, "type": "application/json"},
    {"rel": "parent", "href": CAT, "type": "application/json"},
    {"rel": "license", "href": f"{TILES}/LICENSE.md", "type": "text/markdown",
     "title": "Terms of use (internal use only)"},
]
for l in c["links"]:
    if l["rel"] == "pmtiles":
        links.append({**l, "href": f"{TILES}/priority-areas.pmtiles"})
    elif l["rel"] not in ("self", "root", "parent", "license"):
        raise SystemExit(f"unhandled link {l}")
c["links"] = links

s = json.dumps(c, indent=2, ensure_ascii=False)
assert "public-gye" not in s and "s3-west" not in s, "public reference left"
open(sys.argv[2], "w").write(s + "\n")
