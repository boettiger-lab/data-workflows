"""STAC collection and README for the Eger et al. (2026) kelp coastline zones (#1040).

usage: gen_stac.py <outdir>     writes <outdir>/stac-collection.json and <outdir>/README.md
"""
import json
import sys

OUT = sys.argv[1]
B = "https://s3-west.nrp-nautilus.io/public-coastal"
N = "kelp-zones-eger-2026"
D = f"{B}/{N}"
ACCESSED = "2026-11-24"
CREATED = sys.argv[2] if len(sys.argv) > 2 else "2026-11-24T06:20:09Z"
CITE = ("Eger, A. M., Filbee-Dexter, K., Fraschetti, S., & Vergés, A. (2026). Where kelp forests meet people: "
        "an analysis of the spatial overlap among human population, global economies, and threats to kelp "
        "forest ecosystems. Annals of Botany, mcag226. https://doi.org/10.1093/aob/mcag226")

KELP = {"laminarian": "Laminarian kelps (order Laminariales), the large canopy-forming kelps.",
        "fucoid": "Fucoid seaweed forests (order Fucales).",
        "both": "Both laminarian and fucoid kelp forests."}
COLS = [
    {"name": "kelptype", "type": "string",
     "description": "Kelp forest type on the segment: laminarian (laminarian kelps, order Laminariales, the large canopy-forming kelps), fucoid (fucoid seaweed forests, order Fucales) or both.",
     "values": list(KELP)},
    {"name": "major_minor", "type": "string",
     "description": "Whether kelp forests are a major or a minor feature of this stretch of coast, as classed by the authors: major or minor.",
     "values": ["major", "minor"]},
    {"name": "combo", "type": "string",
     "description": "The authors' concatenation of kelptype and major_minor. 66 segments spell it laminariamajor rather than laminarianmajor; use kelptype and major_minor instead.",
     "values": [v for v in
                ["bothmajor", "bothminor", "fucoidmajor", "fucoidminor", "laminariamajor", "laminarianmajor", "laminarianminor"]]},
    {"name": "featurecla", "type": "string", "description": "Natural Earth feature class of the coastline segment.",
     "values": ["Coastline"]},
    {"name": "scalerank", "type": "int64", "description": "Natural Earth scale rank of the coastline segment (0 shows at the smallest map scales)."},
    {"name": "min_zoom", "type": "double", "description": "Natural Earth minimum web-map zoom at which the coastline segment is meant to show."},
    {"name": "fid", "type": "int64", "description": "Feature id of the segment in the authors' GeoPackage."},
    {"name": "_cng_fid", "type": "int64", "description": "Unique row id assigned at conversion, one per coastline segment."},
    {"name": "h8", "type": "uint64", "description": "H3 resolution-8 cell id (about 0.7 km²)."},
    {"name": "h0", "type": "int64", "description": "H3 resolution-0 cell id, the partition key."},
]
ATTR = [c for c in COLS if c["name"] not in ("h8", "h0")]
DICT = COLS + [{"name": "geom", "type": "geometry", "description": "Coastline segment, multilinestring in WGS84 longitude and latitude."},
               {"name": "bbox", "type": "struct", "description": "Bounding box of the segment (xmin, ymin, xmax, ymax)."}]
cols = lambda cs: [{"name": c["name"], "type": c["type"]} for c in cs]

DESC = f"""Where kelp forests grow along the world's coasts: 1,874 stretches of coastline marked as laminarian kelp, fucoid seaweed or both, and as a major or minor kelp coast, from Eger, Filbee-Dexter, Fraschetti and Vergés (2026). Together they run 461,582 km, 330,574 km of it major laminarian kelp coast. The authors drew these zones from the literature and expert knowledge onto Natural Earth's 10 m coastline, so they show which coasts carry kelp forests, not the forests' observed area or canopy. The lines follow Natural Earth's generalised coast, which can sit some distance off a detailed shoreline.

Lengths by type, as a short example:

```sql
SELECT kelptype, major_minor, COUNT(*) AS segments,
       SUM(ST_Length_Spheroid(ST_FlipCoordinates(geom))) / 1000 AS km
FROM read_parquet('{B}/{N}.parquet') GROUP BY ALL ORDER BY km DESC
```

The hex layer places each segment in every H3 resolution-8 cell it passes through: line features were hexed to H3 resolution 8 by buffering each segment by the H3 cell circumradius before polyfill. A segment's attributes are repeated on every cell it crosses, so count segments with COUNT(DISTINCT _cng_fid).

Please cite the paper when using these data: {CITE}. Data and code archive: https://osf.io/csngb/. The data are the authors' copyright, published openly on OSF.

Source: the OSF archive kelp_people_osf.zip (294,651,336 bytes, sha256 80b40f73d58c5ba8bf24391955c4a10fb41a2d920161083f843c026638096df2), file data/kelp/new_kelp_zones_major_minor_6933.gpkg (layer coastline_kelp_intersection, EPSG:6933, reprojected to WGS84), accessed {ACCESSED}."""

assets = {
    f"{N}-parquet": {"href": f"{B}/{N}.parquet", "type": "application/x-parquet", "roles": ["data"],
                     "title": "Kelp coastline zones — GeoParquet", "created": CREATED,
                     "description": "One row per kelp coastline segment, in WGS84.",
                     "table:columns": cols(ATTR) + [{"name": "geom", "type": "geometry"}, {"name": "bbox", "type": "struct"}]},
    f"{N}-pmtiles": {"href": f"{B}/{N}.pmtiles", "type": "application/vnd.pmtiles", "roles": ["visual"],
                     "title": "Kelp coastline zones — PMTiles", "created": CREATED,
                     "description": f"Vector tiles of the kelp coastline segments for web maps; the source layer is {N}.",
                     "vector:layers": [N],
                     "table:columns": [{"name": c["name"], "type": "Number" if c["type"] in ("int64", "double") else "String"} for c in ATTR]},
    f"{N}-hex": {"href": f"{D}/hex/h0=*/data_0.parquet", "type": "application/x-parquet", "roles": ["data"],
                 "title": "Kelp coastline zones — H3 hex (resolution 8)", "created": CREATED,
                 "description": ("Every H3 resolution-8 cell a kelp coastline segment passes through, one row per "
                                 "segment and cell, with the segment's attributes repeated on every cell it crosses. "
                                 "Count segments with COUNT(DISTINCT _cng_fid), and cells with COUNT(DISTINCT h8)."),
                 "h3:native_resolution": 8, "h3:parent_resolutions": [0],
                 "table:columns": cols(ATTR) + [{"name": "h8", "type": "uint64"}, {"name": "h0", "type": "int64"}]},
    f"style-{N}-kelptype": {"href": f"{D}/styles/{N}-kelptype.json", "type": "application/vnd.mapbox.style+json",
                            "roles": ["style", "default"], "title": "Kelp coastline zones — PMTiles by kelp type",
                            "description": ("Coastline coloured by kelp type: brown for laminarian kelp, olive for fucoid "
                                            "seaweed, dark orange where both occur. Kelp type is the authors' main "
                                            "classification of these coasts.")},
}

col = {
    "stac_version": "1.0.0",
    "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json",
                        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"],
    "type": "Collection", "id": N,
    "title": "Kelp forest coastline zones (Eger et al. 2026)",
    "description": DESC, "license": "proprietary",
    "keywords": ["kelp", "kelp forests", "seaweed", "Laminariales", "Fucales", "coastline", "marine", "global"],
    "sci:doi": "10.1093/aob/mcag226",
    "sci:citation": CITE,
    "providers": [{"name": "Eger, Filbee-Dexter, Fraschetti and Vergés", "roles": ["producer", "licensor"], "url": "https://osf.io/csngb/"},
                  {"name": "Boettiger Lab", "roles": ["processor", "host"], "url": "https://github.com/boettiger-lab"}],
    "extent": {"spatial": {"bbox": [[-180, -59.473, 180, 83]]},
               "temporal": {"interval": [[None, "2026-03-02T00:00:00Z"]]}},
    "created": CREATED, "updated": CREATED,
    "table:columns": DICT,
    "links": [
        {"rel": "self", "href": f"{D}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json"},
        {"rel": "parent", "href": f"{B}/stac-collection.json", "type": "application/json"},
        {"rel": "license", "href": "https://osf.io/csngb/", "type": "text/html", "title": "Authors' data archive (copyright the authors)"},
        {"rel": "about", "href": "https://osf.io/csngb/", "type": "text/html", "title": "Where Kelp Forests Meet People — OSF archive"},
        {"rel": "cite-as", "href": "https://doi.org/10.1093/aob/mcag226", "type": "text/html"},
        {"rel": "describedby", "href": f"{D}/README.md", "type": "text/markdown", "title": "README"},
        {"rel": "pmtiles", "href": f"{B}/{N}.pmtiles", "type": "application/vnd.pmtiles",
         "title": "Kelp coastline zones — PMTiles", "pmtiles:layers": [N]},
    ],
    "assets": assets,
}
json.dump(col, open(f"{OUT}/stac-collection.json", "w"), indent=2, ensure_ascii=False)

open(f"{OUT}/README.md", "w").write(f"""# Kelp forest coastline zones (Eger et al. 2026)

{DESC}

## Files

| File | Contents |
|---|---|
| `{B}/{N}.parquet` | GeoParquet, one row per coastline segment |
| `{B}/{N}.pmtiles` | Vector tiles, source layer `{N}` |
| `{D}/hex/h0=*/data_0.parquet` | H3 resolution-8 cells each segment passes through |

## Map (MapLibre GL JS)

```js
map.addSource('kelp', {{ type: 'vector', url: 'pmtiles://{B}/{N}.pmtiles' }});
map.addLayer({{ id: 'kelp', type: 'line', source: 'kelp', 'source-layer': '{N}',
  paint: {{ 'line-width': 2, 'line-color': ['match', ['get', 'kelptype'],
    'laminarian', '#8c510a', 'fucoid', '#808000', 'both', '#d95f02', '#999999'] }} }});
```

## Query (DuckDB)

```sql
INSTALL spatial; LOAD spatial;
SELECT kelptype, major_minor, COUNT(*) FROM read_parquet('{B}/{N}.parquet') GROUP BY ALL;
```
""")
print("ok")
