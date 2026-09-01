#!/usr/bin/env python3
"""Generate the seafloor-carbon-flux STAC collections (data-workflows #642)."""
import json

BASE = "https://s3-west.nrp-nautilus.io/public-high-seas"
LANDING = "https://zenodo.org/records/6513616"
DOI = "10.5281/zenodo.6513616"
ACCESS = "2026-08-29"
CITATION = ("Yool, A. (2022). Seafloor organic carbon flux output from the NEMO-MEDUSA model "
            "(Version 1.0) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.6513616 "
            f"Accessed {ACCESS} from {LANDING}.")
RAW = ("s3://public-high-seas/raw/nemo-medusa/MEDUSA_ORCA0083_REGRID_2006-2015_flux.nc "
       "(373,248,916 bytes, md5 d854c277c68be1a1d20c653a92224e37)")
PROVIDERS = [
    {"name": "Andrew Yool, National Oceanography Centre, Southampton",
     "roles": ["producer", "licensor"], "url": "https://noc.ac.uk"},
    {"name": "Zenodo", "roles": ["host"], "url": LANDING},
    {"name": "Boettiger Lab, University of California, Berkeley",
     "roles": ["processor", "host"], "url": f"{BASE}/"},
]
EXT = ["https://stac-extensions.github.io/raster/v1.1.0/schema.json",
       "https://stac-extensions.github.io/table/v1.2.0/schema.json",
       "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"]

MODEL = (
    "The flux is the sum of slow- and fast-sinking detrital particles reaching the base of the "
    "water column in MEDUSA-2, an intermediate-complexity plankton ecosystem model coupled to the "
    "NEMO ocean physics model in its global 1/12 degree ORCA0083 configuration. Away from water "
    "shallower than 200 metres the flux is dominated by fast-sinking material. The hindcast was "
    "forced with the DRAKKAR forcing set version 5.2 over 1958-2015, with the biogeochemistry "
    "initialised in 1990; this dataset is the 2006-2015 decadal subset, regridded from the "
    "non-uniform model grid to a regular 1/12 degree grid."
)

RESOLUTION_NOTE = (
    "The hex layer is at H3 resolution 6, which matches the 1/12 degree source pixel: a source "
    "cell is about 86 square kilometres at the equator and about 43 at 60 degrees latitude, "
    "against 36 square kilometres for a resolution 6 cell. It therefore has no resolution 8 "
    "column, the resolution most other datasets in this catalog use as a join key, because "
    "resolution 8 would be roughly 120 cells per source pixel and would imply detail the model "
    "does not have. To combine this layer with finer data, roll the finer data up to resolution 6 "
    "or 5 with h3_cell_to_parent rather than refining this layer down."
)

COVERAGE = (
    "Coverage is the full global ocean as published, with no regional clipping, and it is ocean "
    "only: land carries no value, so the layer covers 10,085,050 H3 cells across 117 of the 122 "
    "resolution 0 partitions. The five absent partitions are centred on continental interiors "
    "(the Amazon basin, Sudan, the central United States, Kazakhstan and Mongolia)."
)

VALUE_SQL = (
    "This is a rate per unit area rather than a per-cell amount, so it combines across cells as "
    "an average:\n"
    "```sql\n"
    "-- correct: mean flux over a region\n"
    "SELECT AVG({col}) FROM read_parquet('...');\n"
    "-- correct: roll up to a coarser resolution\n"
    "SELECT h5, AVG({col}) FROM read_parquet('...') GROUP BY h5;\n"
    "-- wrong: SUM({col}) adds rates and has no physical meaning\n"
    "```\n"
    "A regional total of carbon arriving per day is this rate times the area of each cell; "
    "the H3 area method is in the h3-guide."
)

VARIANTS = [
    {"key": "avg", "col": "flux_avg", "stat": "mean",
     "title": "Seafloor Organic Carbon Flux, decadal mean (NEMO-MEDUSA, 2006-2015)",
     "short": "decadal mean seafloor organic carbon flux",
     "lead": ("The decadal mean flux of organic carbon reaching the seafloor across the global "
              "ocean, 2006-2015, from the NEMO-MEDUSA coupled ocean physics and biogeochemistry "
              "model. Values are in millimoles of carbon per square metre per day."),
     "cog_size": 23584545, "cog_created": "2026-08-29T04:43:28.512995549Z",
     "hex_created": "2026-08-29T04:57:46.523000000Z",
     "cog_min": 5.33206e-33, "cog_max": 113.047, "cog_mean": 0.913266,
     "hex_min": 5.332064049e-33, "hex_max": 110.0714233, "hex_mean": 0.9345900945,
     "p02": 2.745571536e-05, "p50": 0.1299964739, "p98": 12.42628111},
    {"key": "min", "col": "flux_min", "stat": "minimum",
     "title": "Seafloor Organic Carbon Flux, decadal minimum (NEMO-MEDUSA, 2006-2015)",
     "short": "decadal minimum seafloor organic carbon flux",
     "lead": ("The decadal minimum flux of organic carbon reaching the seafloor across the global "
              "ocean, 2006-2015, from the NEMO-MEDUSA coupled ocean physics and biogeochemistry "
              "model: at each model grid cell, the lowest value seen over the decade. Values are "
              "in millimoles of carbon per square metre per day. Read alongside the decadal mean "
              "and maximum layers, this one shows the floor of the seasonal and interannual "
              "range."),
     "cog_size": 25250603, "cog_created": "2026-08-29T04:43:30.110010255Z",
     "hex_created": "2026-08-29T05:00:33.622000000Z",
     "cog_min": 1.26139e-38, "cog_max": 74.5115, "cog_mean": 0.205369,
     "hex_min": 1.261390584e-38, "hex_max": 72.91321568, "hex_mean": 0.2675466007,
     "p02": 3.418917158e-08, "p50": 0.007313209843, "p98": 3.690373418},
    {"key": "max", "col": "flux_max", "stat": "maximum",
     "title": "Seafloor Organic Carbon Flux, decadal maximum (NEMO-MEDUSA, 2006-2015)",
     "short": "decadal maximum seafloor organic carbon flux",
     "lead": ("The decadal maximum flux of organic carbon reaching the seafloor across the global "
              "ocean, 2006-2015, from the NEMO-MEDUSA coupled ocean physics and biogeochemistry "
              "model: at each model grid cell, the highest value seen over the decade. Values are "
              "in millimoles of carbon per square metre per day. Read alongside the decadal mean "
              "and minimum layers, this one shows the ceiling of the seasonal and interannual "
              "range."),
     "cog_size": 24236443, "cog_created": "2026-08-29T04:43:31.657024497Z",
     "hex_created": "2026-08-29T05:03:38.379000000Z",
     "cog_min": 5.84826e-32, "cog_max": 166.513, "cog_mean": 2.38578,
     "hex_min": 5.848260132e-32, "hex_max": 163.1077785, "hex_mean": 2.225242948,
     "p02": 0.0005049279292, "p50": 0.4908565258, "p98": 26.90736021},
]

EXTENT = {"spatial": {"bbox": [[-180, -90, 180, 90]]},
          "temporal": {"interval": [["2006-01-01T00:00:00Z", "2015-12-31T23:59:59Z"]]}}


def leaf(v):
    name = f"seafloor-carbon-flux-{v['key']}"
    desc = "\n\n".join([
        v["lead"],
        MODEL,
        COVERAGE,
        RESOLUTION_NOTE,
        (f"Measured range across the 10,085,050 hex cells: {v['hex_min']:.6g} to {v['hex_max']:.6g} "
         f"millimoles of carbon per square metre per day, mean {v['hex_mean']:.4f}. The 2nd, 50th "
         f"and 98th percentiles are {v['p02']:.6g}, {v['p50']:.6g} and {v['p98']:.6g}, so the "
         "distribution is strongly skewed: most of the deep seafloor receives very little carbon "
         "while continental margins and upwelling regions receive orders of magnitude more."),
        (f"Source version 1.0 published on Zenodo 2022-05-03, accessed {ACCESS}. The upstream "
         f"netCDF was staged unmodified to {RAW}; that staged copy and its checksum are the "
         "edition record. The published GeoTIFF and hex layers were derived from it by extracting "
         f"the {v['col']} variable to a WGS84 float32 cloud-optimized GeoTIFF and aggregating that "
         "to H3."),
    ])
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": EXT,
        "id": name,
        "title": v["title"],
        "description": desc,
        "license": "CC-BY-4.0",
        "version": "1.0",
        "created": v["cog_created"],
        "updated": v["hex_created"],
        "sci:citation": CITATION,
        "sci:doi": DOI,
        "providers": PROVIDERS,
        "keywords": ["ocean", "biogeochemistry", "carbon", "seafloor", "deep sea",
                     "NEMO", "MEDUSA", "particulate organic carbon", "high seas"],
        "links": [
            {"rel": "self", "href": f"{BASE}/seafloor-carbon-flux/{v['key']}/stac-collection.json",
             "type": "application/json"},
            {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",
             "type": "application/json", "title": "NRP Public Data Catalog"},
            {"rel": "parent", "href": f"{BASE}/seafloor-carbon-flux/stac-collection.json",
             "type": "application/json", "title": "Seafloor Organic Carbon Flux (NEMO-MEDUSA)"},
            {"rel": "about", "href": LANDING, "type": "text/html",
             "title": "Seafloor organic carbon flux output from the NEMO-MEDUSA model (Zenodo record)"},
            {"rel": "cite-as", "href": f"https://doi.org/{DOI}", "type": "text/html",
             "title": "DOI 10.5281/zenodo.6513616"},
            {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/",
             "type": "text/html", "title": "Creative Commons Attribution 4.0 International"},
        ],
        "extent": EXTENT,
        "assets": {
            f"{name}-cog": {
                "href": f"{BASE}/seafloor-carbon-flux/{v['key']}/{name}-cog.tif",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "title": f"Seafloor organic carbon flux, decadal {v['stat']}, cloud-optimized GeoTIFF",
                "description": (
                    f"Decadal {v['stat']} seafloor organic carbon flux on the regular 1/12 degree "
                    "grid, 4320 by 2160 pixels, EPSG:4326. Values in millimoles of carbon per "
                    "square metre per day. Land and cells with no model value are nodata (not a "
                    "number); the upstream netCDF fill value 9.96921e+36 was folded into nodata "
                    "during conversion."),
                "roles": ["data", "visual"],
                "created": v["cog_created"],
                "file:size": v["cog_size"],
                "raster:bands": [{
                    "name": v["col"],
                    "data_type": "float32",
                    "nodata": "nan",
                    "unit": "mmol C m-2 d-1",
                    "spatial_resolution": 0.08333333333333333,
                    "description": (
                        f"Decadal {v['stat']} downward flux of organic carbon at the seafloor, in "
                        f"millimoles of carbon per square metre per day. Measured range "
                        f"{v['cog_min']:.6g} to {v['cog_max']:.6g}, mean {v['cog_mean']:.6g}."),
                }],
            },
            f"{name}-hex": {
                "href": f"{BASE}/seafloor-carbon-flux/{v['key']}/hex/h0=*/data_0.parquet",
                "type": "application/x-parquet",
                "title": f"Seafloor organic carbon flux, decadal {v['stat']}, H3 hex parquet (resolution 6)",
                "description": (
                    f"Decadal {v['stat']} seafloor organic carbon flux aggregated to H3 resolution "
                    "6 with an area-weighted mean of the 1/12 degree source pixels. One row per "
                    "cell, hive-partitioned by h0, 10,085,050 cells across 117 partitions. Ocean "
                    "only, so partitions covering continental interiors are absent. Resolution 6 "
                    "is the native resolution and matches the source pixel; there is no resolution "
                    "8 column, so joins to finer datasets should roll the finer side up with "
                    "h3_cell_to_parent. The value is a rate per unit area, and averages across "
                    "cells rather than sums; for a total, weight each cell by its area."),
                "roles": ["data", "overview"],
                "created": v["hex_created"],
                "h3:native_resolution": 6,
                "h3:parent_resolutions": [5, 0],
                "table:columns": [
                    {"name": v["col"], "type": "double",
                     "description": (
                         f"Area-weighted mean of the source pixels in the cell, giving the decadal "
                         f"{v['stat']} downward flux of organic carbon at the seafloor in "
                         f"millimoles of carbon per square metre per day. "
                         + VALUE_SQL.format(col=v["col"]))},
                    {"name": "h6", "type": "uint64",
                     "description": ("H3 cell index at resolution 6, the native resolution of this "
                                     "dataset. One row per cell; resolution 6 cells average about "
                                     "36 square kilometres, which matches the 1/12 degree source "
                                     "pixel.")},
                    {"name": "h5", "type": "uint64",
                     "description": "H3 cell index at resolution 5, the parent of h6."},
                    {"name": "h0", "type": "int64",
                     "description": ("H3 cell index at resolution 0, used as the partition key for "
                                     "hive-partitioned reads.")},
                ],
            },
        },
    }


PARENT = {
    "type": "Collection",
    "stac_version": "1.0.0",
    "stac_extensions": ["https://stac-extensions.github.io/scientific/v1.0.0/schema.json"],
    "id": "seafloor-carbon-flux",
    "title": "Seafloor Organic Carbon Flux (NEMO-MEDUSA, 2006-2015)",
    "description": "\n\n".join([
        ("The flux of organic carbon reaching the seafloor across the global ocean over 2006-2015, "
         "simulated by the NEMO-MEDUSA coupled ocean physics and biogeochemistry model. This is "
         "the carbon that sinks out of the surface ocean and arrives at the sea bed, which sets "
         "how much food reaches deep-sea life and how much carbon is available for long-term "
         "burial. Values are in millimoles of carbon per square metre per day."),
        ("This collection holds three layers, all on the same grid and the same cells: the decadal "
         "mean, minimum and maximum flux. The minimum and maximum bracket the seasonal and "
         "interannual range that the mean conceals; at every cell the minimum is at or below the "
         "mean and the maximum at or above it."),
        MODEL,
        ("Each layer is published as a cloud-optimized GeoTIFF on the 1/12 degree source grid and "
         "as H3 hex parquet at resolution 6. " + RESOLUTION_NOTE.split(" It therefore")[0] +
         " Resolution 6 is the native resolution and there is no resolution 8 column, so joins to "
         "finer catalog data should roll the finer side up with h3_cell_to_parent."),
        COVERAGE,
        (f"Source version 1.0 published on Zenodo 2022-05-03, accessed {ACCESS}. The upstream "
         f"netCDF was staged unmodified to {RAW}. The companion bathymetry and grid-cell-area file "
         "from the same Zenodo record is staged beside it but is not published as a layer: "
         "bathymetry for this catalog comes from GEBCO 2025, and the area field is a property of "
         "the source grid rather than of the published cells."),
    ]),
    "license": "CC-BY-4.0",
    "version": "1.0",
    "sci:citation": CITATION,
    "sci:doi": DOI,
    "providers": PROVIDERS,
    "keywords": ["ocean", "biogeochemistry", "carbon", "seafloor", "deep sea",
                 "NEMO", "MEDUSA", "particulate organic carbon", "high seas"],
    "extent": EXTENT,
    "links": [
        {"rel": "self", "href": f"{BASE}/seafloor-carbon-flux/stac-collection.json",
         "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",
         "type": "application/json", "title": "NRP Public Data Catalog"},
        {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json",
         "title": "High Seas & Ocean Governance Datasets"},
        {"rel": "about", "href": LANDING, "type": "text/html",
         "title": "Seafloor organic carbon flux output from the NEMO-MEDUSA model (Zenodo record)"},
        {"rel": "cite-as", "href": f"https://doi.org/{DOI}", "type": "text/html",
         "title": "DOI 10.5281/zenodo.6513616"},
        {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/",
         "type": "text/html", "title": "Creative Commons Attribution 4.0 International"},
    ] + [
        {"rel": "child", "id": f"seafloor-carbon-flux-{v['key']}",
         "href": f"{BASE}/seafloor-carbon-flux/{v['key']}/stac-collection.json",
         "type": "application/json", "title": v["title"]}
        for v in VARIANTS
    ],
    "assets": {},
}

for v in VARIANTS:
    p = f"/tmp/scf-{v['key']}-stac-collection.json"
    with open(p, "w") as f:
        json.dump(leaf(v), f, indent=2)
    print("wrote", p)
with open("/tmp/scf-parent-stac-collection.json", "w") as f:
    json.dump(PARENT, f, indent=2)
print("wrote /tmp/scf-parent-stac-collection.json")
