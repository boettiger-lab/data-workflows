import json, sys
sys.path.insert(0, '.')
from common import *

B = "public-seagrass"
BASE = f"{S3}/{B}"
BUCKET_SELF = f"{BASE}/stac-collection.json"
ITEM_PAGE = "https://data-gis.unep-wcmc.org/portal/home/item.html?id=aaa46cd3d3d640b2916b8f0a0ffe07cb"

SENTINEL_NOTE = (
    'Unsurveyed or unreported attributes carry the literal string "Not Reported" rather than a '
    "null. In the VERIF column the sentinel appears in two capitalisations, \"Not Reported\" and "
    "\"Not reported\", so match it case-insensitively:\n\n"
    "```sql\n"
    "-- correct: catches both spellings\n"
    "WHERE lower(VERIF) <> 'not reported'\n"
    "-- wrong: VERIF <> 'Not Reported' still returns the rows spelled 'Not reported'\n"
    "```")

TAXON = [
    {"name": "FAMILY", "type": "string",
     "description": "Taxonomic family of the seagrass recorded at this feature. Values: "
                    "Zosteraceae, Cymodoceaceae, Hydrocharitaceae, Posidoniaceae, "
                    "Potamogetonaceae, Not Reported = the source did not identify a family.",
     "values": ["Zosteraceae", "Cymodoceaceae", "Hydrocharitaceae", "Posidoniaceae",
                "Potamogetonaceae", "Not Reported"]},
    {"name": "GENUS", "type": "string",
     "description": "Taxonomic genus of the seagrass recorded at this feature, or Not Reported "
                    "where the source did not identify one.",
     "values": ["Zostera", "Halophila", "Cymodocea", "Halodule", "Syringodium", "Enhalus",
                "Thalassia", "Posidonia", "Thalassodendron", "Phyllospadix", "Amphibolis",
                "Heterozostera", "Potamogeton", "Not Reported"]},
    {"name": "scientific", "type": "string",
     "description": "Scientific name of the seagrass recorded at this feature, as given by the "
                    "contributing source."},
]

DATASETID = {"name": "datasetID", "type": "double",
             "description": "Identifier of the contributing source dataset. Global Distribution of "
                            "Seagrasses is a compilation, so one collection mixes many independent "
                            "surveys, each with its own method and date."}
EVENTDATE = {"name": "eventDate", "type": "string",
             "description": "Date or date range of the survey that recorded this feature, as given "
                            "by the contributing source. Formats vary between sources."}
VERIF = {"name": "VERIF", "type": "string",
         "description": "Whether the record was checked by a subject expert. Values: Not Reported "
                        "= no review recorded. The sentinel occurs in two capitalisations in this "
                        "layer, \"Not Reported\" and \"Not reported\"; match it "
                        "case-insensitively.",
         "values": ["Not Reported", "Not reported"]}

def build(name, title, desc, bbox, temporal, cols, extra_flat, hex_desc, flat_desc):
    ds = f"unep-wcmc-seagrass/{name}"
    self_href = f"{BASE}/{ds}/stac-collection.json"
    flat_cols = cols + [FID, GEOM]
    hex_cols = cols + [FID] + h3_columns()
    a = {
        f"{name}-parquet": {
            "href": f"{BASE}/{ds}.parquet", "type": "application/x-parquet", "roles": ["data"],
            "title": f"{title} — GeoParquet", "description": flat_desc,
            "table:columns": flat_cols},
        f"{name}-pmtiles": {
            "href": f"{BASE}/{ds}.pmtiles", "type": "application/vnd.pmtiles", "roles": ["visual"],
            "title": f"{title} — PMTiles",
            "description": f"Vector tiles for web mapping. The MapLibre source-layer is \"{name}\".",
            "vector:layers": [name], "table:columns": lean(cols + [FID])},
        f"{name}-hex": {
            "href": f"{BASE}/{ds}/hex/h0=*/data_0.parquet", "type": "application/x-parquet",
            "roles": ["data"], "title": f"{title} — H3 hex parquet (resolution 8)",
            "description": hex_desc, "h3:native_resolution": 8, "h3:parent_resolutions": [0],
            "table:columns": hex_cols},
    }
    return {
        "type": "Collection", "stac_version": "1.0.0", "stac_extensions": EXTENSIONS,
        "id": f"unep-wcmc-seagrass-{name}", "title": title, "description": desc,
        "license": "other", "version": "7.1",
        "sci:citation": (
            "UNEP-WCMC, Short FT (2020). Global Distribution of Seagrasses (version 7). Seventh "
            "update to the data layer used in Green and Short (2003), superseding version 6. "
            f"Cambridge (UK): UN Environment World Conservation Monitoring Centre. Accessed {ACCESS_DATE}."),
        "providers": PROVIDERS_SEAGRASS,
        "extent": {"spatial": {"bbox": [bbox]}, "temporal": {"interval": [temporal]}},
        "links": nav_links(self_href, BUCKET_SELF) + [
            LICENSE_LINK,
            {"rel": "about", "href": ITEM_PAGE, "type": "text/html",
             "title": "UNEP-WCMC Global Distribution of Seagrasses — dataset page"},
            {"rel": "cite-as", "href": "https://doi.org/10.34892/x6r3-d211"},
        ],
        "assets": a,
    }

PROVENANCE = (
    "\n\n**Provenance.** Downloaded from the UNEP-WCMC ArcGIS portal on " + ACCESS_DATE + " via the "
    "publisher's `https://wcmc.io/WCMC_013_014` link, which supplies the point and polygon layers "
    "in a single archive. The source archive is kept at "
    "`s3://public-seagrass/raw/WCMC013-014_SeagrassPtPy2021_v7_1.zip` (485,748,212 bytes, sha256 "
    "`25b9d1cfecbd0b51af58a3b2b0c11e643074bf02ea084ab634e5d092f5f02d2d`). Upstream labels this "
    "release inconsistently — the bundled README says version 8.0 released March 2021 while the "
    "filename and the requested citation say version 7.1 and version 7 — so the edition recorded "
    "here is the one in the distributed filename, v7.1.\n\n" + LICENCE_NOTE)

print("seagrass.py loaded (call build() from the fill script)")
