"""Build the forest-to-grass-shrub STAC collection (data-workflows #738)."""
import json, sys

BASE = "https://s3-west.nrp-nautilus.io/public-land-cover/forest-to-grass-shrub"
binary_created = sys.argv[1] if len(sys.argv) > 1 else "2026-10-02T00:00:00Z"

H3COLS = [
    {"name": "h10", "type": "uint64", "description": "H3 cell ID at resolution 10 (native resolution)."},
    {"name": "h9", "type": "uint64", "description": "H3 cell ID at resolution 9."},
    {"name": "h8", "type": "uint64", "description": "H3 cell ID at resolution 8, the catalog's common join resolution."},
    {"name": "h0", "type": "uint64", "description": "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."},
]

COMMON_HEX = (
    "One row per resolution 10 H3 cell (about 15,000 m², roughly 17 source pixels). "
    "A cell is present only if at least one qualifying 30 m pixel falls in it, so the count or area of "
    "cells overstates converted area; the converted area itself is about 43,840 km² "
    "(48,709,853 qualifying pixels of 900 m²). Values are whole numbers stored as double."
)

def cog(key, title, band, created, desc):
    return key, {
        "href": f"{BASE}/{key.replace('-cog', '')}-cog.tif",
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "title": title, "roles": ["data"], "created": created,
        "description": desc, "raster:bands": [band],
    }

def hex_asset(key, layer, title, col, created, desc):
    return key, {
        "href": f"{BASE}/{layer}/hex/h0=*/data_0.parquet",
        "type": "application/x-parquet", "title": title, "roles": ["data"], "created": created,
        "h3:native_resolution": 10, "h3:parent_resolutions": [9, 8, 0],
        "description": desc, "table:columns": [col] + H3COLS,
    }

assets = dict([
    cog("forest-to-grass-shrub-binary-cog", "Forest to grass/shrub conversion, qualifying pixels (30 m COG)",
        {"name": "forest_to_grass", "data_type": "uint8", "nodata": 255,
         "classification:classes": [
             {"value": 1, "name": "Converted", "description": "Tree Cover in 2001, then at least 10 consecutive years of Grass/Shrub.", "color_hint": "D95F02"},
             {"value": 0, "name": "Not converted", "description": "Did not meet the rule. Also used upstream for areas outside the mapped region.", "color_hint": "F0F0F0"}]},
        "2026-10-01T19:56:12Z",
        "Pixels that met the conversion rule (1) or did not (0), reprojected to WGS84 with nearest-neighbour resampling. "
        "Upstream uses 0 both for pixels that did not qualify and for areas outside the mapped region; 255 marks the fill added by reprojection."),
    cog("forest-to-grass-shrub-max-run-years-cog", "Longest grass/shrub run after 2001, qualifying pixels (30 m COG)",
        {"name": "max_run_years", "data_type": "uint8", "nodata": 0, "unit": "years",
         "statistics": {"minimum": 10, "maximum": 20}},
        "2026-10-01T19:55:30Z",
        "Longest run of consecutive years in Grass/Shrub between 2002 and 2021, from 10 to 20 years. "
        "Kept only where the conversion rule is met; upstream computes this for every pixel, including land that was never forest, "
        "and those pixels are set to nodata (0) here so all three layers cover the same pixels."),
    cog("forest-to-grass-shrub-change-year-cog", "First year of the qualifying grass/shrub run (30 m COG)",
        {"name": "change_year", "data_type": "uint16", "nodata": 0, "unit": "year",
         "statistics": {"minimum": 2002, "maximum": 2012}},
        "2026-10-01T19:56:52Z",
        "Calendar year the qualifying Grass/Shrub run begins, from 2002 to 2012. 0 is nodata."),
    hex_asset("forest-to-grass-shrub-binary-hex", "binary", "Forest to grass/shrub conversion, H3 hex (resolution 10)",
        {"name": "forest_to_grass", "type": "double",
         "description": "1 where at least one pixel in the cell converted from Tree Cover in 2001 to at least 10 consecutive years of Grass/Shrub. Cells without a converted pixel are absent.",
         "values": [1]},
        binary_created,
        COMMON_HEX + " Every row has forest_to_grass = 1 (max reducer), so this asset is a footprint: count or join cells rather than summing the value."),
    hex_asset("forest-to-grass-shrub-max-run-years-hex", "max-run-years", "Longest grass/shrub run after 2001, H3 hex (resolution 10)",
        {"name": "max_run_years", "type": "double",
         "description": "Longest run of consecutive years in Grass/Shrub between 2002 and 2021 among the converted pixels in the cell, from 10 to 20 years."},
        "2026-10-02T14:27:07Z",
        COMMON_HEX + " Cell value is the maximum over its converted pixels. To roll up to a coarser cell, take MAX again:\n"
        "SELECT h8, MAX(max_run_years) FROM ... GROUP BY h8"),
    hex_asset("forest-to-grass-shrub-change-year-hex", "change-year", "First year of the qualifying grass/shrub run, H3 hex (resolution 10)",
        {"name": "change_year", "type": "double",
         "description": "Earliest year, among the converted pixels in the cell, that a qualifying run of at least 10 consecutive years in Grass/Shrub began. From 2002 to 2012."},
        "2026-10-02T09:28:46Z",
        COMMON_HEX + " Cell value is the earliest onset over its converted pixels (min reducer). To roll up to a coarser cell, take MIN again:\n"
        "SELECT h8, MIN(change_year) FROM ... GROUP BY h8"),
])

desc = """Where forest in the western United States turned into grass or shrubland and stayed that way, 2001-2021. A 30 m pixel qualifies when it was Tree Cover in 2001 and, at any point afterwards, spent at least 10 consecutive years as Grass/Shrub, according to the USGS LCMAP Land Cover Primary (LCPRI) annual maps for 1985-2021. Only 2002-2021 are scanned, so the longest possible run is 20 years and a qualifying run starts no later than 2012. Classes between 2001 and the start of the run are not restricted. About 43,840 km² qualify (48,709,853 pixels).

Three layers, each as a map COG and an H3 hex table at resolution 10 (parents 9, 8 and 0): whether a pixel qualifies (`binary`), the longest Grass/Shrub run in years (`max_run_years`), and the year the qualifying run began (`change_year`). All three cover the same qualifying pixels. Upstream computes the longest run for every pixel, including land that was never forest; here it is kept only where the rule is met.

Coverage is the western conterminous US, from about 124.7°W to 97.0°W and 25.8°N to 49.0°N, on the LCMAP Albers grid; it is not clipped to state boundaries. Rasters were reprojected to WGS84 with nearest-neighbour resampling.

Source: Ilangakoon, N. (2026), Zenodo record 10.5281/zenodo.23045000, published 2026-09-29 with no edition label, accessed 2026-10-01. Raw files staged at s3://public-land-cover/raw/forest-to-grass-shrub/ (sha256): forest_to_grassshrub_binary.tif 56,867,440 bytes 86a7ca5f03936b41cfd89a0c3594ca6c76aed907e5b4df5076e7184d3d3f115a; forest_to_grassshrub_max_run_years.tif 580,895,176 bytes 84ecb2e10efd63a148db9d699834abe533eea4ddac7f61f99770109032f4b5da; forest_to_grassshrub_change_year.tif 96,972,304 bytes 8e0438efec9d36aee945673c9a7480591ab7f294923a54b38c009ed7f96bfaa5; forest_to_grassshrub_metadata.xml 20,836 bytes 463c5f7c8bd5d4a12889da051003f2dbb1238a7a2b22b075266626daa7be6d15. Licensed CC-BY-4.0."""

stac = {
    "type": "Collection", "stac_version": "1.0.0",
    "stac_extensions": [
        "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
        "https://stac-extensions.github.io/classification/v2.0.0/schema.json",
        "https://stac-extensions.github.io/table/v1.2.0/schema.json",
        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
    ],
    "id": "forest-to-grass-shrub",
    "title": "Persistent Forest to Grass/Shrub Conversion, Western US 2001-2021 (LCMAP-derived)",
    "description": desc,
    "license": "CC-BY-4.0",
    "keywords": ["land cover change", "forest loss", "type conversion", "grass/shrub", "LCMAP", "western US", "H3"],
    "sci:doi": "10.5281/zenodo.23045000",
    "sci:citation": "Ilangakoon, N. (2026). Forest to Grass/Shrub transformation in the Western US from 2001-2012 [Data set]. Zenodo. https://doi.org/10.5281/zenodo.23045000 (accessed 2026-10-01)",
    "created": "2026-10-01T19:55:30Z",
    "updated": binary_created,
    "extent": {
        "spatial": {"bbox": [[-124.72, 25.84, -97.04, 49.01]]},
        "temporal": {"interval": [["2001-01-01T00:00:00Z", "2021-12-31T23:59:59Z"]]},
    },
    "providers": [
        {"name": "Nayani Ilangakoon", "roles": ["producer", "licensor"], "url": "https://zenodo.org/records/23045000"},
        {"name": "USGS EROS, Land Change Monitoring, Assessment, and Projection (LCMAP)", "roles": ["producer"], "url": "https://www.usgs.gov/special-topics/lcmap"},
        {"name": "Zenodo", "roles": ["host"], "url": "https://zenodo.org/records/23045000"},
        {"name": "Boettiger Lab (cng-datasets H3 processing)", "roles": ["processor"], "url": f"{BASE}/"},
    ],
    "links": [
        {"rel": "self", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json"},
        {"rel": "parent", "href": "https://s3-west.nrp-nautilus.io/public-land-cover/stac-collection.json", "type": "application/json"},
        {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/", "type": "text/html", "title": "CC-BY-4.0, as stated on the Zenodo record"},
        {"rel": "about", "href": "https://zenodo.org/records/23045000", "type": "text/html", "title": "Zenodo record"},
        {"rel": "cite-as", "href": "https://doi.org/10.5281/zenodo.23045000"},
        {"rel": "describedby", "href": f"{BASE}/README.md", "type": "text/markdown"},
    ],
    "assets": assets,
}
json.dump(stac, open(sys.argv[2] if len(sys.argv) > 2 else "/dev/stdout", "w"), indent=2)
