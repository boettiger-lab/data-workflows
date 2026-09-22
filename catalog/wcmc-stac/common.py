"""Shared STAC building blocks for the UNEP-WCMC coral/seagrass collections (#444)."""

S3 = "https://s3-west.nrp-nautilus.io"
ROOT = f"{S3}/public-data/stac/catalog.json"
LICENSE_URL = "https://www.unep-wcmc.org/en/general-data-license"
ACCESS_DATE = "2026-09-15"

EXTENSIONS = [
    "https://stac-extensions.github.io/table/v1.2.0/schema.json",
    "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
    "https://stac-extensions.github.io/version/v1.2.0/schema.json",
]

LICENSE_LINK = {"rel": "license", "href": LICENSE_URL, "type": "text/html"}

PROVIDERS_CORAL = [
    {"name": "UNEP World Conservation Monitoring Centre (UNEP-WCMC)",
     "roles": ["producer", "licensor"], "url": "https://www.unep-wcmc.org/"},
    {"name": "WorldFish Centre, World Resources Institute, The Nature Conservancy",
     "roles": ["producer"], "url": "https://www.unep-wcmc.org/"},
    {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"],
     "url": "https://s3-west.nrp-nautilus.io/"},
]
PROVIDERS_SEAGRASS = [
    {"name": "UNEP World Conservation Monitoring Centre (UNEP-WCMC)",
     "roles": ["producer", "licensor"], "url": "https://www.unep-wcmc.org/"},
    {"name": "Frederick T. Short", "roles": ["producer"],
     "url": "https://www.unep-wcmc.org/"},
    {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"],
     "url": "https://s3-west.nrp-nautilus.io/"},
]

# The licence paragraph every collection carries, so the terms travel with the data.
LICENCE_NOTE = (
    "Distributed under the UNEP-WCMC General Data License (excluding WDPA). The licence "
    "prohibits commercial use and prohibits redistributing the data, and permits publication "
    "only where the data are not made downloadable and attribution is clearly visible. It also "
    "asks that anyone planning a global-scale analysis, or an analysis using the dataset in its "
    "entirety, notify the Director of UNEP-WCMC. Read the full terms at "
    f"{LICENSE_URL} before using or citing this collection."
)

def nav_links(self_href, parent_href):
    return [
        {"rel": "self", "href": self_href, "type": "application/json"},
        {"rel": "root", "href": ROOT, "type": "application/json"},
        {"rel": "parent", "href": parent_href, "type": "application/json"},
    ]

def h3_columns(native=8, parents=(0,)):
    """Grain-neutral H3 column descriptions — identical text across every asset (#303)."""
    cols = [{"name": f"h{native}", "type": "uint64",
             "description": f"H3 cell identifier at resolution {native}."}]
    for p in parents:
        if p == 0:
            cols.append({"name": "h0", "type": "int64",
                         "description": "H3 cell identifier at resolution 0, used as the "
                                        "partition key for hive-partitioned reads."})
        else:
            cols.append({"name": f"h{p}", "type": "uint64",
                         "description": f"H3 cell identifier at resolution {p}."})
    return cols

FID = {"name": "_cng_fid", "type": "int64",
       "description": "Synthetic per-feature identifier assigned during conversion, unique for "
                      "every row of the source layer. Use it to count or de-duplicate features."}
GEOM = {"name": "geom", "type": "geometry",
        "description": "Feature geometry (GeoParquet, EPSG:4326)."}
BBOX = {"name": "bbox", "type": "struct",
        "description": "Bounding box of the feature geometry, as xmin, ymin, xmax, ymax."}

def lean(cols):
    """PMTiles mirror: name + type + values only, no prose, geometry dropped (#283/#320)."""
    out = []
    for c in cols:
        if c["name"] == "geom":
            continue
        lc = {"name": c["name"], "type": c["type"]}
        if "values" in c:
            lc["values"] = c["values"]
        out.append(lc)
    return out
