"""Generate the STAC collection and README for public-high-seas/bathymetric-features.

Usage: gen_stac.py <out_dir>
Writes <out_dir>/stac-collection.json and <out_dir>/README.md. Every number below was measured
from the built parquet or the staged raw (see BUILD.md), not copied from the paper.
"""
import json, sys

out = sys.argv[1]
B = "https://s3-west.nrp-nautilus.io/public-high-seas"
N = "bathymetric-features"
RAW = {
    "bathymetry_peaks_GEBCO2025_15s.gpkg": (23_797_760, "9dc975a25a4fc21945940338a193f1e3549520dc3621f65a87d1a55cb009896a"),
    "bathymetry_features_GEBCO2025_15s.gpkg": (2_683_092_992, "e1837a7ded65ac1a9357e1cf74fff7f4626f663a12976222552a07502371c4f0"),
}
ACCESSED = "2026-10-09"
CITE = ("Souche, A., Hartz, E.H., Schmid, D.W. (2026). A Global Dataset of Bathymetric Features Identified with "
        "Prominence and Isobaths Analysis. PANGAEA. doi:10.1594/PANGAEA.992546. Supplement to Scientific Data 13: 902, "
        f"doi:10.1038/s41597-026-07241-z. Accessed {ACCESSED}.")

fid = {"name": "_cng_fid", "type": "int64", "description": "Row identifier assigned at conversion, one per row. Use it to join the hex back to the GeoParquet."}
gpkg_fid = {"name": "fid", "type": "int64", "description": "Row number in the source GeoPackage."}
h = [{"name": "h8", "type": "uint64", "description": "H3 cell ID at resolution 8."},
     {"name": "h0", "type": "int64", "description": "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."}]

peaks = [
    fid, gpkg_fid,
    {"name": "peak_id", "type": "int64", "description": "Peak identifier (1 to 145,190, with gaps), the key that links peaks and contours."},
    {"name": "latitude", "type": "double", "description": "Peak latitude in decimal degrees, after the peak was moved to the local summit."},
    {"name": "longitude", "type": "double", "description": "Peak longitude in decimal degrees, after the peak was moved to the local summit."},
    {"name": "depth", "type": "double", "description": "Depth of the peak in metres, negative downward (-9,460 to 0). 23 peaks reach 0, where the summit meets sea level; land was set to 0 before processing."},
    {"name": "key_saddle_latitude", "type": "double", "description": "Latitude of the key saddle, the lowest point on the highest path to higher terrain. Its depth sets the base of the feature."},
    {"name": "key_saddle_longitude", "type": "double", "description": "Longitude of the key saddle."},
    {"name": "prominence", "type": "double", "description": "Topographic prominence in metres: the height of the peak above its key saddle (300 to 5,435). Peaks under 300 m were not detected."},
    {"name": "original_lon", "type": "double", "description": "Longitude of the peak as first detected, before it was moved to the local summit. 604 peaks were moved."},
    {"name": "original_lat", "type": "double", "description": "Latitude of the peak as first detected, before it was moved to the local summit."},
    {"name": "original_depth", "type": "double", "description": "Depth in metres of the peak as first detected, before it was moved to the local summit."},
    {"name": "error_with_contours", "type": "boolean", "description": "True when contours were extracted for the peak but failed the quality check, for example a missing level or a higher contour enclosing a larger area than a lower one. These peaks have no contours. 17,186 peaks."},
    {"name": "error_no_contours", "type": "boolean", "description": "True when no contours could be extracted for the peak. These peaks have no contours. 1,188 peaks."},
]
geom = {"name": "geom", "type": "geometry", "description": "Geometry in WGS 84: a point for a peak, a polygon or multipolygon for a contour."}

contours = [
    fid, gpkg_fid,
    {"name": "contour name", "type": "string", "description": "Display label, for example 'feature id 84792, ctr 100%'. The name contains a space, so quote it in SQL: \"contour name\"."},
    {"name": "feature_id", "type": "int64", "description": "Feature identifier. Equal to peak_id, and shared by all contours of one feature."},
    {"name": "peak_id", "type": "int64", "description": "Peak identifier (1 to 145,190, with gaps), the key that links peaks and contours."},
    {"name": "nested_on_feature_id", "type": "string", "description": "feature_id of the larger feature whose base contour fully encloses this feature's base contour, as text. Empty string when the feature is not nested in another (63,335 of 125,514 features)."},
    {"name": "peak_longitude", "type": "double", "description": "Longitude of the feature's peak."},
    {"name": "peak_latitude", "type": "double", "description": "Latitude of the feature's peak."},
    {"name": "peak_depth", "type": "double", "description": "Depth of the feature's peak in metres, negative downward (-9,070 to 0)."},
    {"name": "peak_prominence", "type": "double", "description": "Prominence of the feature in metres, the height of its peak above its key saddle (300 to 5,435)."},
    {"name": "contour_depth", "type": "double", "description": "Depth of this contour in metres, negative downward (-9,406 to -79.25)."},
    {"name": "prominence_percentage", "type": "int64", "description": "Contour level, as a percentage of the feature's prominence measured down from the peak. 100=base (depth of the key saddle), 90=near the base, a more reliable base outline when the 100 contour is missing, 75=lower flank, 50=mid flank, 25=near the summit.", "values": [25, 50, 75, 90, 100]},
    {"name": "area_sq_km", "type": "double", "description": "Area enclosed by this contour in square kilometres, measured in a projected coordinate system (0.13 to 807,516)."},
    {"name": "circularity_percent", "type": "double", "description": "How close the contour is to a circle: 4 pi x area / perimeter squared, x 100 (0.5 to 99.9). 100 is a perfect circle; low values are elongated or irregular shapes such as ridges."},
    {"name": "bbox_orientation_deg", "type": "double", "description": "Azimuth of the long axis of the contour's minimum bounding rectangle, in degrees (0 to 180)."},
    {"name": "bbox_length_m", "type": "double", "description": "Length of the contour's minimum bounding rectangle in metres."},
    {"name": "bbox_width_m", "type": "double", "description": "Width of the contour's minimum bounding rectangle in metres."},
    {"name": "mean_slope_deg", "type": "double", "description": "Mean seafloor slope along the contour line, in degrees."},
    {"name": "min_slope_deg", "type": "double", "description": "Minimum seafloor slope along the contour line, in degrees."},
    {"name": "max_slope_deg", "type": "double", "description": "Maximum seafloor slope along the contour line, in degrees."},
    {"name": "centroid_lon", "type": "double", "description": "Longitude of the contour's centroid, as published. For 68 contours that cross the date line the value lies slightly outside -180 to 180."},
    {"name": "centroid_lat", "type": "double", "description": "Latitude of the contour's centroid."},
    {"name": "window_size_used", "type": "double", "description": "Size in degrees of the square search window around the peak in which the contours were extracted (1 to 25). The window grew until all levels were found, up to 25 degrees."},
]


def lean(cols):
    return [{k: c[k] for k in ("name", "type", "values") if k in c} for c in cols]


desc = (
    "A global inventory of seamounts, knolls and other undersea peaks, found by measuring topographic prominence "
    "on the GEBCO 2025 bathymetry grid (15 arc-second, about 450 m). A peak counts when it rises at least 300 m "
    "above its key saddle, the lowest point that connects it to higher seafloor. Two layers:\n\n"
    "- **Peaks**: 143,888 points, one per detected peak, with depth, prominence and key saddle. Of these, 125,514 passed the "
    "quality check and have contours; the other 18,374 are kept and flagged (error_with_contours, error_no_contours).\n"
    "- **Contours**: 627,471 polygons outlining the 125,514 accepted features. Each feature has up to five nested outlines, "
    "at 100% (the base), 90%, 75%, 50% and 25% (near the summit) of its prominence, with area, circularity, orientation, "
    "bounding-box size and slope. 57 features have no 100% outline; use the 90% outline as their base.\n\n"
    "The layers join on peak_id. Features nest: a small cone on the flank of a large seamount is its own feature, "
    "with nested_on_feature_id naming the larger one.\n\n"
    "**Selecting seamounts.** The dataset holds every peak of 300 m or more, so it includes small knolls. "
    "A common seamount definition is a feature at least 1,000 m high with a near-circular base:\n\n"
    "```sql\n"
    "SELECT peak_id, peak_prominence, circularity_percent, area_sq_km\n"
    "FROM read_parquet('s3://public-high-seas/bathymetric-features/contours.parquet')\n"
    "WHERE prominence_percentage = 100 AND peak_prominence >= 1000\n"
    "```\n\n"
    "**Limitations.** Detection depends on the GEBCO grid, which is sharper where ships have mapped the seafloor with multibeam "
    "sonar and coarser elsewhere, so well-surveyed areas show more features. Contours were searched for within a window of at most "
    "25 degrees around each peak, so the base outline of the largest plateaus and ridges can be incomplete.\n\n"
    "**Processing.** Converted from the published GeoPackages with all attributes kept. Two changes to geometry only: "
    "429 contours that crossed the date line were published with longitudes out to 190 degrees and were split at -180/180 "
    "with the overflow shifted by 360 degrees (same shape, standard coordinates), and 2 contours stored as geometry collections "
    "of two polygons became multipolygons.\n\n"
    f"**Source.** PANGAEA, doi:10.1594/PANGAEA.992546, accessed {ACCESSED}. No edition label is published beyond the DOI. Staged raw: "
    + "; ".join(f"s3://public-high-seas/raw/{f} ({s:,} bytes, sha256 {c})" for f, (s, c) in RAW.items()) + "."
)

hex_note_peaks = (
    "Each peak is assigned to one H3 cell at resolution 8 (about 0.74 km² per cell), hive-partitioned by h0. "
    "One row per peak; peaks in the same cell are kept as separate rows. Depth and prominence are per-peak values: "
    "average or filter them, but a SUM has no meaning."
)
hex_note_contours = (
    "Each contour polygon is filled with H3 cells at resolution 8 (about 0.74 km² per cell), hive-partitioned by h0. "
    "One row per (contour, cell) pair. Because a feature's five contours are nested, a cell near a summit is repeated for "
    "every contour that encloses it, and nested features add more rows. Per-contour values (area_sq_km, bbox_length_m, "
    "bbox_width_m) are repeated on every cell of that contour, and per-feature values (peak_depth, peak_prominence) on every "
    "cell of every contour of that feature, so never SUM them on the hex. Pick one level and count distinct features:\n\n"
    "```sql\n"
    "-- feature footprints: one outline per feature\n"
    "SELECT h8, COUNT(DISTINCT peak_id) AS features FROM read_parquet('s3://public-high-seas/bathymetric-features/contours/hex/h0=*/data_0.parquet')\n"
    "WHERE prominence_percentage = 100 GROUP BY h8\n"
    "```"
)

c = {
    "type": "Collection", "id": N, "stac_version": "1.0.0",
    "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json",
                        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"],
    "title": "Global seamounts and undersea peaks (prominence analysis of GEBCO 2025)",
    "description": desc,
    "license": "CC-BY-4.0",
    "keywords": ["seamounts", "knolls", "bathymetry", "prominence", "GEBCO", "seafloor", "geomorphology", "high seas", "ocean"],
    "sci:doi": "10.1594/PANGAEA.992546",
    "sci:citation": CITE,
    "sci:publications": [{"doi": "10.1038/s41597-026-07241-z",
                          "citation": "Souche, A., Hartz, E.H., Schmid, D.W. (2026). A Global Dataset of Bathymetric Features Identified with Prominence and Isobaths Analysis. Scientific Data 13: 902."}],
    "providers": [
        {"name": "Souche, Hartz and Schmid (2026)", "roles": ["producer", "licensor"], "url": "https://doi.org/10.1594/PANGAEA.992546"},
        {"name": "PANGAEA", "roles": ["host"], "url": "https://www.pangaea.de"},
        {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"], "url": "https://github.com/boettiger-lab"}],
    "extent": {"spatial": {"bbox": [[-180.0, -78.80833, 180.0, 89.57251]]},
               "temporal": {"interval": [["2025-01-01T00:00:00Z", "2025-12-31T23:59:59Z"]]}},
    "links": [
        {"rel": "self", "href": f"{B}/{N}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json"},
        {"rel": "parent", "href": f"{B}/stac-collection.json", "type": "application/json", "title": "High Seas & Ocean Governance Datasets"},
        {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/", "type": "text/html", "title": "CC-BY-4.0"},
        {"rel": "cite-as", "href": "https://doi.org/10.1594/PANGAEA.992546", "type": "text/html"},
        {"rel": "about", "href": "https://doi.org/10.1594/PANGAEA.992546", "type": "text/html", "title": "PANGAEA dataset record"},
        {"rel": "related", "href": "https://doi.org/10.1038/s41597-026-07241-z", "type": "text/html", "title": "Souche et al. 2026, Scientific Data"},
        {"rel": "describedby", "href": f"{B}/{N}/README.md", "type": "text/markdown"}],
    "assets": {
        "bathymetric-peaks-parquet": {
            "href": f"{B}/{N}/peaks.parquet", "type": "application/x-parquet", "roles": ["data"],
            "title": "Undersea peaks GeoParquet",
            "description": "143,888 peak points in GeoParquet (WGS 84), one row per peak, including the 18,374 rejected in quality control. "
                           "The point can differ from the latitude and longitude columns by up to about 0.01 degrees, typically half a 15 arc-second grid cell.",
            "table:columns": peaks + [geom]},
        "bathymetric-peaks-pmtiles": {
            "href": f"{B}/{N}/peaks.pmtiles", "type": "application/vnd.pmtiles", "roles": ["visual"],
            "title": "Undersea peaks PMTiles",
            "description": "Vector tiles of the peak points for web maps. MapLibre source-layer name: 'peaks'.",
            "vector:layers": ["peaks"], "table:columns": lean(peaks)},
        "bathymetric-peaks-hex": {
            "href": f"{B}/{N}/peaks/hex/h0=*/data_0.parquet", "type": "application/x-parquet", "roles": ["data"],
            "title": "Undersea peaks H3 hex (resolution 8)", "description": hex_note_peaks,
            "h3:native_resolution": 8, "h3:parent_resolutions": [0],
            "table:columns": peaks + h},
        "bathymetric-contours-parquet": {
            "href": f"{B}/{N}/contours.parquet", "type": "application/x-parquet", "roles": ["data"],
            "title": "Seamount and undersea feature contours GeoParquet",
            "description": "627,471 contour polygons in GeoParquet (WGS 84), up to five per feature. Feature-level columns "
                           "(peak_id, peak_longitude, peak_latitude, peak_depth, peak_prominence, nested_on_feature_id) are repeated "
                           "on each of a feature's contours: count features with COUNT(DISTINCT peak_id), or filter to one prominence_percentage. "
                           "Contours that cross the date line are split into multipolygons at -180/180.",
            "table:columns": contours + [geom]},
        "bathymetric-contours-pmtiles": {
            "href": f"{B}/{N}/contours.pmtiles", "type": "application/vnd.pmtiles", "roles": ["visual"],
            "title": "Seamount and undersea feature contours PMTiles",
            "description": "Vector tiles of the contour polygons for web maps. MapLibre source-layer name: 'contours'. "
                           "Filter on prominence_percentage to draw one level, for example the base outlines.",
            "vector:layers": ["contours"], "table:columns": lean(contours)},
        "bathymetric-contours-hex": {
            "href": f"{B}/{N}/contours/hex/h0=*/data_0.parquet", "type": "application/x-parquet", "roles": ["data"],
            "title": "Seamount and undersea feature contours H3 hex (resolution 8)", "description": hex_note_contours,
            "h3:native_resolution": 8, "h3:parent_resolutions": [0],
            "table:columns": contours + h}},
}
json.dump(c, open(f"{out}/stac-collection.json", "w"), indent=2)

readme = f"""# Global seamounts and undersea peaks (GEBCO 2025)

Undersea peaks and the nested contours that outline them, found by topographic prominence on the
GEBCO 2025 15 arc-second bathymetry grid. 143,888 peaks; 125,514 accepted features with up to five
contours each (627,471 polygons). Peaks and contours join on `peak_id`.

Source: {CITE}
License: CC-BY-4.0. Cite Souche et al. 2026.

## Files

| layer | GeoParquet | PMTiles (source-layer) | H3 hex (resolution 8) |
|---|---|---|---|
| peaks | `{B}/{N}/peaks.parquet` | `{B}/{N}/peaks.pmtiles` (`peaks`) | `{B}/{N}/peaks/hex/h0=*/data_0.parquet` |
| contours | `{B}/{N}/contours.parquet` | `{B}/{N}/contours.pmtiles` (`contours`) | `{B}/{N}/contours/hex/h0=*/data_0.parquet` |

## MapLibre

```js
map.addSource('contours', {{ type: 'vector', url: 'pmtiles://{B}/{N}/contours.pmtiles' }});
map.addLayer({{
  id: 'seamount-bases', type: 'line', source: 'contours',
  'source-layer': 'contours',                       // last segment of the dataset path
  filter: ['==', ['get', 'prominence_percentage'], 100],
  paint: {{ 'line-color': '#1f6feb', 'line-width': 1 }}
}});
map.addSource('peaks', {{ type: 'vector', url: 'pmtiles://{B}/{N}/peaks.pmtiles' }});
map.addLayer({{ id: 'peaks', type: 'circle', source: 'peaks', 'source-layer': 'peaks',
  paint: {{ 'circle-radius': 2, 'circle-color': '#d1242f' }} }});
```

## DuckDB

```sql
INSTALL spatial; LOAD spatial;
-- seamounts at least 1,000 m high, base outline only
SELECT peak_id, peak_prominence, circularity_percent, area_sq_km
FROM read_parquet('{B}/{N}/contours.parquet')
WHERE prominence_percentage = 100 AND peak_prominence >= 1000;
```

Each feature has up to five nested contours, so count features with `COUNT(DISTINCT peak_id)` or
filter to one `prominence_percentage`. On the hex, a cell is repeated for every contour that covers it.
"""
open(f"{out}/README.md", "w").write(readme)
