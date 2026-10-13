"""Author the STAC for public-gye/priority-areas and the public-gye bucket collection (#769).

Writes two files to $OUT (default /tmp/gye-stac): priority-areas.json (the dataset
collection) and bucket.json (the public-gye bucket collection). The LICENSE.md terms statement is
authored by hand. Publishing is a separate step (rclone copyto).

Measured values (row counts, bbox, build times, raw checksum) are recorded in BUILD.md and
set below; nothing is transcribed from the old public-wyoming STAC except the producer
identity. The old licence link pointed at Wyoming Game & Fish's data page, which is not
this producer's terms, so it is not carried over.
"""
import json
import os

NRP = "https://s3-west.nrp-nautilus.io"
BUCKET = "public-gye"
DS = "priority-areas"
ROOT = f"{NRP}/public-data/stac/catalog.json"
BUCKET_URL = f"{NRP}/{BUCKET}/stac-collection.json"
SELF = f"{NRP}/{BUCKET}/{DS}/stac-collection.json"
OUT = os.environ.get("OUT", "/tmp/gye-stac")

TABLE_EXT = "https://stac-extensions.github.io/table/v1.2.0/schema.json"

# --- measured (see BUILD.md) ----------------------------------------------------------
BBOX = [-110.987, 41.596, -108.337, 44.974]
RAW_SHA256 = "496e143c4bb8df1f16b90b20f6ca738b137c3821b2e483d282d9b5a9c1bb08ca"
RAW_BYTES = 98304
BUILT = {  # LastModified of each published object
    "parquet": os.environ.get("BUILT_PARQUET"),
    "pmtiles": os.environ.get("BUILT_PMTILES"),
    "hex": os.environ.get("BUILT_HEX"),
}
NAMES = ["Absaroka Front", "Upper Green", "Upper Wind River"]

# --- one schema, written identically to every parquet asset ---------------------------
COL = {
    "_cng_fid": {"name": "_cng_fid", "type": "int64",
                 "description": "Feature id assigned during conversion, one per priority area "
                                "(3 in total)."},
    "Name": {"name": "Name", "type": "string",
             "description": "Priority area name. Values: Absaroka Front, Upper Green, "
                            "Upper Wind River.",
             "values": NAMES},
    "fid": {"name": "fid", "type": "int64",
            "description": "Feature number from the source GeoPackage (1-3); identical to "
                           "the feature id for this dataset."},
    "geometry": {"name": "geometry", "type": "geometry",
                 "description": "Priority-area polygon (GeoParquet, longitude/latitude WGS84)."},
    "h11": {"name": "h11", "type": "uint64", "description": "H3 cell ID at resolution 11."},
    "h10": {"name": "h10", "type": "uint64", "description": "H3 cell ID at resolution 10."},
    "h9": {"name": "h9", "type": "uint64", "description": "H3 cell ID at resolution 9."},
    "h8": {"name": "h8", "type": "uint64", "description": "H3 cell ID at resolution 8."},
    "h0": {"name": "h0", "type": "int64",
           "description": "H3 cell ID at resolution 0, used as the partition key for "
                          "hive-partitioned reads."},
}

DESCRIPTION = (
    "Three priority conservation areas in the Greater Yellowstone Ecosystem, in western "
    "Wyoming: Absaroka Front, Upper Green and Upper Wind River. They mark landscape-scale "
    "zones identified for coordinated wildlife habitat conservation, and are used to select "
    "the private parcels that fall inside each area. The dataset is the three polygons in "
    "full, with one attribute, the area name.\n\n"
    "Terms of use: no licence or published terms have been located for these boundaries, "
    "and no public source, citation or DOI. They were catalogued as produced by Arthur "
    "Middleton (Middleton Lab, UC Berkeley). No redistribution right has been recorded, so "
    "reuse or republication outside this catalog should be cleared with the producer first. "
    "The linked terms statement records these facts and grants nothing.\n\n"
    "Provenance: built from the GeoPackage PriorityAreas_GYE.gpkg (layer PriorityAreas_GYE, "
    "three polygons), held as s3://public-gye/raw/PriorityAreas_GYE.gpkg — "
    f"{RAW_BYTES:,} bytes, SHA-256 {RAW_SHA256}. No edition label or publication date is "
    "known for the boundaries, so the temporal extent is left open."
)

HEX_DESC = (
    "The three priority areas indexed to H3 hexagons at resolution 11, with parent cells at "
    "resolutions 10, 9, 8 and 0. There is one row per (priority area, resolution-11 cell) "
    "pair, so the area name and feature ids are repeated on every cell the area covers. "
    "Because the areas were indexed at the finer resolution 11, the resolution-10 cells "
    "include boundary cells whose centre lies just outside an area, so joining another "
    "resolution-10 dataset on h10 also picks up features along the edges of each area.\n\n"
    "```sql\n"
    "-- number of priority areas: count distinct features, not rows\n"
    "SELECT COUNT(DISTINCT _cng_fid) FROM read_parquet('…/hex/h0=*/data_0.parquet');\n"
    "-- which priority area each cell of another resolution-10 dataset falls in\n"
    "SELECT d.*, pa.Name FROM other d\n"
    "JOIN (SELECT DISTINCT h10, h0, Name FROM read_parquet('…/hex/h0=*/data_0.parquet')) pa\n"
    "  USING (h10, h0);\n"
    "```"
)


def cols(*names):
    return [dict(COL[n]) for n in names]


def collection():
    pm_cols = [{k: v for k, v in COL[n].items() if k != "description"} for n in ("Name", "fid", "_cng_fid")]
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": [TABLE_EXT],
        "id": "gye-priority-areas",
        "title": "Greater Yellowstone Ecosystem Priority Areas",
        "description": DESCRIPTION,
        "license": "other",
        "keywords": ["Greater Yellowstone Ecosystem", "GYE", "Wyoming", "priority areas",
                     "conservation", "wildlife", "habitat"],
        "providers": [
            {"name": "Arthur Middleton (Middleton Lab, UC Berkeley)", "roles": ["producer"],
             "url": "https://middletonlab.org/"},
            {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"],
             "url": "https://github.com/boettiger-lab"},
        ],
        "extent": {"spatial": {"bbox": [BBOX]}, "temporal": {"interval": [[None, None]]}},
        "links": [
            {"rel": "self", "href": SELF, "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": BUCKET_URL, "type": "application/json"},
            {"rel": "license", "href": f"{NRP}/{BUCKET}/{DS}/LICENSE.md",
             "type": "text/markdown",
             "title": "Terms of use (no licence located; statement of known facts)"},
        ],
        "assets": {
            "priority-areas-parquet": {
                "href": f"{NRP}/{BUCKET}/{DS}.parquet",
                "type": "application/vnd.apache.parquet",
                "title": "GYE Priority Areas (GeoParquet)",
                "description": "The three priority-area polygons, one row per area.",
                "roles": ["data"],
                "created": BUILT["parquet"],
                "table:columns": cols("_cng_fid", "fid", "Name", "geometry"),
            },
            "priority-areas-pmtiles": {
                "href": f"{NRP}/{BUCKET}/{DS}.pmtiles",
                "type": "application/vnd.pmtiles",
                "title": "GYE Priority Areas (PMTiles)",
                "description": "Vector tiles of the three priority areas for web maps "
                               "(source layer: priority-areas).",
                "roles": ["visual"],
                "created": BUILT["pmtiles"],
                "vector:layers": [DS],
                "table:columns": pm_cols,
            },
            "priority-areas-hex": {
                "href": f"{NRP}/{BUCKET}/{DS}/hex/h0=*/data_0.parquet",
                "type": "application/vnd.apache.parquet",
                "title": "GYE Priority Areas (H3 hexagons, resolution 11)",
                "description": HEX_DESC,
                "roles": ["data"],
                "created": BUILT["hex"],
                "h3:native_resolution": 11,
                "h3:parent_resolutions": [10, 9, 8, 0],
                "table:storage_options": {"partitioning": "h0"},
                "table:columns": cols("_cng_fid", "fid", "Name", "h11", "h10", "h9", "h8", "h0"),
            },
        },
        "table:row_count": 3,
    }


def bucket():
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "id": "gye",
        "title": "Greater Yellowstone Ecosystem (GYE)",
        "description": "Conservation planning datasets for the Greater Yellowstone Ecosystem. "
                       "Each dataset here carries its own licence and provenance.",
        "license": "other",
        "extent": {"spatial": {"bbox": [BBOX]}, "temporal": {"interval": [[None, None]]}},
        "providers": [{"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"],
                       "url": "https://github.com/boettiger-lab"}],
        "links": [
            {"rel": "self", "href": BUCKET_URL, "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": ROOT, "type": "application/json"},
            {"rel": "child", "href": SELF, "type": "application/json",
             "title": "Greater Yellowstone Ecosystem Priority Areas"},
        ],
    }


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name, doc in (("priority-areas.json", collection()), ("bucket.json", bucket())):
        with open(os.path.join(OUT, name), "w") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
    print(f"wrote {OUT}/priority-areas.json, {OUT}/bucket.json")
