#!/usr/bin/env python3
"""Generate the rap-pfg-biomass STAC collection (#677).

bbox comes from the measured hex extent, not the COG envelope; band count is checked through a
cache-busted TiTiler call. Both for the reasons documented in catalog/rap/k8s/rap-bands/.
"""
import json, subprocess, email.utils, datetime, pathlib, urllib.parse, urllib.request, importlib.util

_vs = pathlib.Path(__file__).resolve().parents[4] / "scripts" / "verify-stac.py"
_spec = importlib.util.spec_from_file_location("verify_stac", _vs)
_m = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_m)
MCP = _m.MCPClient()

BASE = "https://s3-west.nrp-nautilus.io/public-rap"
DS = "rap-pfg-biomass"
COG = f"{BASE}/{DS}-cog.tif"
HEX = f"{BASE}/{DS}/hex/h0=*/data_0.parquet"
NOW = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
LANDING = "https://rangeland.ntsg.umt.edu/data/rap/rap-vegetation-biomass/v3/"

RAW = "s3://public-rap/raw/rap-vegetation-biomass-v3-2024.tif"
RAW_BYTES = 36_568_800_616
RAW_SHA = "08ffbe787a588897253f4a2ef125eee4faf6c61eddd00307efd86e825b2be1ac"
ACCESSED = "2026-06-08"
RELEASED = "2025-02-05"   # upstream changelog: "2024 data release"

def bust(u):
    return f"{u}?cachebust={int(datetime.datetime.now().timestamp())}"

def cog_info():
    q = urllib.parse.quote(bust(COG), safe="")
    with urllib.request.urlopen(f"https://titiler.nrp-nautilus.io/cog/info?url={q}", timeout=180) as r:
        d = json.load(r)
    return d["count"], [round(x, 4) for x in d["bounds"]]

def head(url):
    r = subprocess.run(["curl", "-sI", "--max-time", "60", url], capture_output=True, text=True).stdout
    created = size = None
    for line in r.splitlines():
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "last-modified":
            created = email.utils.parsedate_to_datetime(v).astimezone(
                datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        elif k == "content-length":
            size = int(v)
    return created, size

def hex_extent():
    r = MCP.query(
        "SELECT round(min(h3_cell_to_lng(h10)),4) w, round(min(h3_cell_to_lat(h10)),4) s, "
        "round(max(h3_cell_to_lng(h10)),4) e, round(max(h3_cell_to_lat(h10)),4) n "
        f"FROM read_parquet('s3://public-rap/{DS}/hex/h0=*/data_0.parquet', hive_partitioning=true)")[0]
    return [float(r["w"]), float(r["s"]), float(r["e"]), float(r["n"])]

nbands, cog_bbox = cog_info()
if nbands != 1:
    raise SystemExit(f"COG reports {nbands} bands; expected 1. Do not publish.")
bbox = hex_extent()
cog_created, cog_size = head(COG)
hex_created, _ = head(f"{BASE}/{DS}/hex/h0=576812596024311807/data_0.parquet")
print(f"bands={nbands}  cog bbox east {cog_bbox[2]}  data east {bbox[2]}")

CITATION = (
    "Jones, M.O., N.P. Robinson, D.E. Naugle, J.D. Maestas, M.C. Reeves, R.W. Lankston, and "
    "B.W. Allred. 2021. Annual and 16-Day Rangeland Production Estimates for the Western United "
    "States. Rangeland Ecology & Management 77:112-117. https://doi.org/10.1016/j.rama.2021.04.003. "
    f"RAP Vegetation Biomass v3.0, 2024 edition (released {RELEASED}); accessed {ACCESSED}.")

DESC = "\n\n".join([
    "Aboveground biomass of perennial forbs and grasses across the conterminous United States for "
    "2024, aggregated to H3 hexagonal cells. Values are pounds per acre.",

    "Source: Rangeland Analysis Platform (RAP) Vegetation Biomass version 3.0 from NTSG at the "
    "University of Montana, band 2 of two. Pixels are approximately 30 metres in WGS84. Values are "
    "uint16 pounds per acre; 65535 marks no data.",

    "The estimate is biomass accumulated during that year only. It does not include biomass "
    "carried over from previous years, so it is a measure of annual production rather than "
    "standing stock.",

    "The producers note these estimates are produced across a broad region but are primarily "
    "intended for rangeland ecosystems and may not be suitable in others, such as forests. They "
    "state that estimates over agricultural land should not be used, and that no masking has been "
    "applied — selecting the areas of interest is left to the user.",

    "The companion collections rap-afg-cover and rap-pfg-cover hold percent cover rather than "
    "biomass, from a different upstream product and a different year, so the two are not directly "
    "comparable without care.",

    "The hex layer is an area-weighted aggregation to H3 resolution 10 using the mean reducer. "
    "Pounds per acre is a density, so cells combine by averaging weighted by cell area, not by "
    "adding. The h3-guide gives the current method for cell area.",

    f"Provenance: retrieved from {LANDING} on {ACCESSED}. Upstream republishes each annual edition "
    f"in place at a stable URL with no dated archive, so the staged copy is the citable artifact: "
    f"{RAW}, {RAW_BYTES:,} bytes, SHA-256 {RAW_SHA}. The 2024 edition was released upstream on "
    f"{RELEASED}.",
])

COL_DESC = ("Area-weighted mean aboveground biomass of perennial forbs and grasses in the cell, "
            "in pounds per acre. This is a density, so averaging across cells weighted by cell "
            "area is meaningful; adding cell values together is not.")

col = {
    "type": "Collection",
    "stac_version": "1.0.0",
    "id": DS,
    "title": "RAP Perennial Forb & Grass Biomass 2024 (CONUS)",
    "description": DESC,
    "license": "CC0-1.0",
    "version": "3.0",
    "keywords": ["rangeland", "biomass", "production", "RAP", "NTSG", "H3",
                 "perennial forb and grass"],
    "providers": [
        {"name": "NTSG, University of Montana", "roles": ["producer", "licensor"],
         "url": "https://rangeland.ntsg.umt.edu/"},
        {"name": "Boettiger Lab", "roles": ["processor", "host"],
         "url": "https://s3-west.nrp-nautilus.io"},
    ],
    "extent": {
        "spatial": {"bbox": [bbox]},
        "temporal": {"interval": [["2024-01-01T00:00:00Z", "2024-12-31T23:59:59Z"]]},
    },
    "sci:doi": "10.1016/j.rama.2021.04.003",
    "sci:citation": CITATION,
    "created": cog_created or NOW,
    "updated": NOW,
    "stac_extensions": [
        "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
        "https://stac-extensions.github.io/table/v1.2.0/schema.json",
        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
        "https://stac-extensions.github.io/version/v1.2.0/schema.json",
        "https://stac-extensions.github.io/file/v2.1.0/schema.json",
    ],
    "links": [
        {"rel": "self", "href": f"{BASE}/{DS}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",
         "type": "application/json"},
        {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
        {"rel": "license", "href": "https://creativecommons.org/publicdomain/zero/1.0/",
         "type": "text/html", "title": "Creative Commons CC0 1.0 Universal"},
        {"rel": "about", "href": LANDING, "type": "text/html",
         "title": "RAP Vegetation Biomass v3 — product documentation"},
        {"rel": "cite-as", "href": "https://doi.org/10.1016/j.rama.2021.04.003", "type": "text/html"},
    ],
    "assets": {
        f"{DS}-cog": {
            "href": COG,
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "title": "RAP Perennial Forb & Grass Biomass 2024 (CONUS) — cloud-optimized GeoTIFF",
            "roles": ["data"],
            "description": ("Single-band cloud-optimized GeoTIFF in EPSG:4326, extracted as band 2 "
                            "of the two-band RAP vegetation-biomass product. Values are uint16 "
                            "pounds per acre, with 65535 as no data."),
            "raster:bands": [{"name": "biomass", "data_type": "uint16", "nodata": 65535,
                              "unit": "lbs/acre"}],
            **({"created": cog_created} if cog_created else {}),
            **({"file:size": cog_size} if cog_size else {}),
        },
        f"{DS}-hex": {
            "href": HEX,
            "type": "application/x-parquet",
            "title": "RAP Perennial Forb & Grass Biomass 2024 (CONUS) — H3 hex, resolution 10",
            "roles": ["data"],
            "description": (
                "One row per H3 cell at resolution 10, holding the area-weighted mean of the "
                "source pixels in that cell. Because the value is a density in pounds per acre, "
                "combine cells by averaging weighted by cell area rather than by adding them; the "
                "h3-guide gives the current method for cell area.\n\n"
                "Cells covering only no-data pixels are absent rather than present with a fill "
                "value, so there are no sentinel values to filter. Partitioned by h0 for "
                "hive-partitioned reads; h8 is the resolution shared with the rest of the catalog "
                "for joins."),
            "h3:native_resolution": 10,
            "h3:parent_resolutions": [9, 8, 0],
            "table:columns": [
                {"name": "biomass", "type": "double", "description": COL_DESC},
                {"name": "h10", "type": "uint64",
                 "description": "H3 cell ID at resolution 10, the native resolution of this layer."},
                {"name": "h9", "type": "uint64", "description": "H3 cell ID at resolution 9."},
                {"name": "h8", "type": "uint64", "description": "H3 cell ID at resolution 8."},
                {"name": "h0", "type": "int64",
                 "description": "H3 cell ID at resolution 0, used as the partition key for "
                                "hive-partitioned reads."},
            ],
            **({"created": hex_created} if hex_created else {}),
        },
    },
}

out = pathlib.Path(__file__).parent / "stac" / f"{DS}-stac-collection.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(col, indent=2, ensure_ascii=False) + "\n")
print(f"wrote {out}")
