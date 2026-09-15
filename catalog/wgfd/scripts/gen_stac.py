"""Author the STAC for the three public-wgfd crucial-range collections (#578).

Every value here is MEASURED from the published data (schemas, RANGE value sets, bboxes,
feature counts, build times, raw sha256) — nothing transcribed from the old public-wyoming
STAC except the licence fact and the provider identities, which are statements about
upstream rather than about our build.

One schema is written identically to every asset (the mcp-data-server#303 fold is
first-seen-wins, so divergent text silently drops a version). Hex-only guidance therefore
lives in the hex asset DESCRIPTION, never as a per-column clause.
"""
import json

NRP = "https://s3-west.nrp-nautilus.io"
BUCKET = "public-wgfd"
ROOT = f"{NRP}/public-data/stac/catalog.json"
PARENT = f"{NRP}/{BUCKET}/stac-collection.json"

TABLE_EXT = "https://stac-extensions.github.io/table/v1.2.0/schema.json"
SCI_EXT = "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"

# --- measured -------------------------------------------------------------------------
D = {
    "elk-crucial": dict(
        species="elk", Species="Elk",
        features=150, h8=28617, cells=1159248,
        bbox=[-111.049, 40.999, -104.981, 44.988],
        ranges={"CRUWYL": 91, "CRUWIN": 57, "CRUSWR": 2},
        acres=(747.09, 592503.3, 4442987),
        sha256="3d56458f6bf2d6d6bcd1b648c1716cf7188bd40ab2641e85d370172f35b03fd2",
        raw_bytes=2324827,
        built={"parquet": "2026-08-21T23:29:26Z", "pmtiles": "2026-08-21T23:29:37Z",
               "hex": "2026-08-21T23:31:13Z"},
        partitions=2,
    ),
    "mule-deer-crucial": dict(
        species="mule deer", Species="Mule deer",
        features=145, h8=40955, cells=None,
        bbox=[-111.048, 40.996, -104.056, 45.0],
        ranges={"CRUWYL": 116, "CRUWIN": 29},
        acres=(231.46, 1352702.2, 6431769),
        sha256="e464111b26c949cfd81e060ab9ddea0b98fb303b9f154dd99ca0c1474b2ce81b",
        raw_bytes=2619807,
        built={"parquet": "2026-08-21T23:32:13Z", "pmtiles": "2026-08-21T23:32:26Z",
               "hex": "2026-08-21T23:33:52Z"},
        partitions=1,
    ),
    "pronghorn-crucial": dict(
        species="pronghorn", Species="Pronghorn",
        features=105, h8=36879, cells=None,
        bbox=[-111.047, 40.998, -104.305, 44.857],
        ranges={"CRUWYL": 101, "CRUSWR": 3, "CRUWIN": 1},
        acres=(730.41, 1327564.2, 5972722),
        sha256="16f9a3dcb61a48ca315072615c1f4cdf4ce5da8701582fdb5a8f16576d848350",
        raw_bytes=3110805,
        built={"parquet": "2026-08-21T23:34:54Z", "pmtiles": "2026-08-21T23:35:08Z",
               "hex": "2026-08-21T23:36:21Z"},
        partitions=1,
    ),
}

# WGFD seasonal-range terminology. CRU = crucial; the suffix is the seasonal type.
RANGE_DEFS = {
    "CRUWIN": "crucial winter range",
    "CRUWYL": "crucial winter/yearlong range",
    "CRUSWR": "crucial severe winter relief range",
    "CRUSSF": "crucial spring/summer/fall range",
    "CRUYRL": "crucial yearlong range",
    "CRUOUT": "crucial range outside other seasonal types",
}

ACCESS_DATE = "2026-02-25"   # when the source GeoJSON was pulled from the WGFD ArcGIS Hub


def col_defs(ds):
    d = D[ds]
    present = sorted(d["ranges"], key=lambda c: -d["ranges"][c])
    listed = ", ".join(f"{c}={RANGE_DEFS[c]}" for c in present)
    return {
        "_cng_fid": ("int64",
            "Identifier assigned to every polygon during conversion, unique within this "
            "dataset. Count features or remove repeated rows with COUNT(DISTINCT _cng_fid)."),
        "OGC_FID": ("int64",
            "Sequential record number carried over from the source GeoJSON export."),
        "OBJECTID": ("int32",
            "Feature identifier assigned by the Wyoming Game & Fish Department in the "
            "published layer. Unique for every polygon in this dataset."),
        "RANGE": ("string",
            "Seasonal range designation. Every polygon here is crucial range, so each code "
            f"combines the crucial prefix CRU with the seasonal type. Values: {listed}."),
        "Acres": ("double",
            "Area of the range polygon in acres, as published by the Wyoming Game & Fish "
            "Department."),
        "SQMiles": ("double",
            "Area of the range polygon in square miles, as published by the Wyoming Game & "
            "Fish Department."),
        "geom": ("geometry", "Polygon geometry of the range, in EPSG:4326."),
        "h10": ("uint64",
            "H3 cell identifier at resolution 10, the native resolution of this hex table."),
        "h9": ("uint64", "H3 cell identifier at resolution 9."),
        "h8": ("uint64",
            "H3 cell identifier at resolution 8, the resolution shared across this catalog "
            "for joining datasets to one another."),
        "h0": ("int64",
            "H3 cell identifier at resolution 0, used as the partition key for "
            "hive-partitioned reads."),
    }


FLAT_COLS = ["_cng_fid", "OGC_FID", "OBJECTID", "RANGE", "Acres", "SQMiles", "geom"]
HEX_COLS = ["_cng_fid", "OGC_FID", "OBJECTID", "RANGE", "Acres", "SQMiles",
            "h10", "h9", "h8", "h0"]
PMT_COLS = ["_cng_fid", "OGC_FID", "OBJECTID", "RANGE", "Acres", "SQMiles"]


def columns(ds, names, lean=False):
    defs = col_defs(ds)
    present = sorted(D[ds]["ranges"], key=lambda c: -D[ds]["ranges"][c])
    out = []
    for n in names:
        t, desc = defs[n]
        c = {"name": n, "type": t}
        if not lean:
            c["description"] = desc
        if n == "RANGE":
            c["values"] = present
        out.append(c)
    return out


def collection(ds):
    d = D[ds]
    sp, Sp = d["species"], d["Species"]
    lo, hi, total = d["acres"]
    present = sorted(d["ranges"], key=lambda c: -d["ranges"][c])
    breakdown = ", ".join(f"{c} ({d['ranges'][c]})" for c in present)

    description = (
        f"Crucial seasonal habitat range for {sp} in Wyoming, mapped by the Wyoming Game & "
        f"Fish Department. Crucial ranges are the seasonal habitats the department identifies "
        f"as a determining factor in the population's ability to sustain itself, so they carry "
        f"more management weight than ordinary seasonal range. This dataset holds "
        f"{d['features']:,} polygons covering about {total:,.0f} acres, broken down by range "
        f"type as {breakdown}.\n\n"
        f"Coverage is the state of Wyoming. That is the full extent of the source: the Wyoming "
        f"Game & Fish Department maps range within its own jurisdiction, so this is a complete "
        f"dataset rather than a regional excerpt of something larger.\n\n"
        f"The department publishes crucial range as a separate layer from full {sp} seasonal "
        f"range, and every polygon here is crucial, which is why each RANGE code begins with "
        f"CRU."
    )

    citation = (
        f"Wyoming Game & Fish Department, {Sp} Crucial Range. Accessed {ACCESS_DATE} from the "
        f"WGFD ArcGIS Hub (wyoming-wgfd.opendata.arcgis.com). The department publishes through "
        f"an ArcGIS Hub endpoint with no stable versioned download URL, so the retained source "
        f"is the anchor: s3://{BUCKET}/raw/{ds}.geojson, {d['raw_bytes']:,} bytes, SHA-256 "
        f"{d['sha256']}. Converted to GeoParquet, PMTiles and H3 by the Boettiger Lab, "
        f"UC Berkeley."
    )

    hex_desc = (
        f"{Sp} crucial range as H3 cells at resolution 10, with resolution 9, 8 and 0 "
        f"identifiers alongside for rolling up or joining to other datasets. There is one row "
        f"for each combination of a range polygon and a cell it covers, so a polygon that spans "
        f"many cells appears on many rows, and the per-polygon values Acres and SQMiles are "
        f"repeated on every one of its cells. Reduce to one row per polygon before totalling "
        f"either of them:\n\n"
        f"SELECT SUM(Acres) FROM (SELECT DISTINCT _cng_fid, Acres FROM …)\n\n"
        f"For the ground area of a set of cells, aggregate the cell areas over distinct cells "
        f"rather than these published columns. Covers {d['h8']:,} resolution 8 cells across "
        f"{d['partitions']} resolution 0 partition"
        f"{'s' if d['partitions'] != 1 else ''}."
    )

    assets = {
        f"{ds}-parquet": {
            "href": f"{NRP}/{BUCKET}/{ds}.parquet",
            "type": "application/x-parquet",
            "roles": ["data"],
            "title": f"{Sp} crucial range — GeoParquet",
            "created": d["built"]["parquet"],
            "description": (
                f"{Sp} crucial range polygons as GeoParquet, one row per polygon, in EPSG:4326. "
                f"Query directly with DuckDB over HTTP."),
            "table:columns": columns(ds, FLAT_COLS),
        },
        f"{ds}-pmtiles": {
            "href": f"{NRP}/{BUCKET}/{ds}.pmtiles",
            "type": "application/vnd.pmtiles",
            "roles": ["visual"],
            "title": f"{Sp} crucial range — PMTiles",
            "created": d["built"]["pmtiles"],
            "description": (
                f"Vector tiles for web maps. In MapLibre GL JS the source layer is "
                f"\"{ds}\"; style or filter on RANGE to separate the crucial range types."),
            "vector:layers": [ds],
            "table:columns": columns(ds, PMT_COLS, lean=True),
        },
        f"{ds}-hex": {
            "href": f"{NRP}/{BUCKET}/{ds}/hex/h0=*/data_0.parquet",
            "type": "application/x-parquet",
            "roles": ["data"],
            "title": f"{Sp} crucial range — H3 resolution 10",
            "created": d["built"]["hex"],
            "description": hex_desc,
            "h3:native_resolution": 10,
            "h3:parent_resolutions": [9, 8, 0],
            "table:columns": columns(ds, HEX_COLS),
        },
    }

    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": [TABLE_EXT, SCI_EXT],
        "id": f"wgfd-{ds}",
        "title": f"{Sp} Crucial Range (Wyoming)",
        "description": description,
        "license": "other",
        "sci:citation": citation,
        "created": d["built"]["parquet"],
        "updated": d["built"]["hex"],
        "keywords": ["Wyoming", sp, "wildlife", "habitat", "crucial range", "seasonal range",
                     "WGFD", "big game"],
        "extent": {
            "spatial": {"bbox": [d["bbox"]]},
            "temporal": {"interval": [["2024-01-01T00:00:00Z", None]]},
        },
        "providers": [
            {"name": "Wyoming Game & Fish Department", "roles": ["producer", "licensor"],
             "url": "https://wyoming-wgfd.opendata.arcgis.com/"},
            {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"],
             "url": "https://github.com/boettiger-lab"},
        ],
        "links": [
            {"rel": "self", "href": f"{NRP}/{BUCKET}/{ds}/stac-collection.json",
             "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": PARENT, "type": "application/json"},
            {"rel": "license", "href": "https://wgfd.wyo.gov/geospatial-data",
             "type": "text/html"},
            {"rel": "about", "href": "https://wyoming-wgfd.opendata.arcgis.com/",
             "type": "text/html", "title": "WGFD ArcGIS Hub (upstream distribution)"},
        ],
        "assets": assets,
    }


def bucket_collection():
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "id": "wgfd",
        "title": "Wyoming Game & Fish Department (WGFD)",
        "description": (
            "Wildlife habitat data published by the Wyoming Game & Fish Department. The "
            "department maps big-game seasonal ranges and other habitat layers across Wyoming, "
            "its area of jurisdiction, so these datasets cover the state in full rather than "
            "being regional excerpts of a national product.\n\n"
            "Datasets are grouped here by the agency that produces them, which is how they are "
            "found and cited upstream."),
        "license": "other",
        "extent": {
            "spatial": {"bbox": [[-111.049, 40.996, -104.056, 45.0]]},
            "temporal": {"interval": [["2024-01-01T00:00:00Z", None]]},
        },
        "providers": [
            {"name": "Wyoming Game & Fish Department", "roles": ["producer", "licensor"],
             "url": "https://wyoming-wgfd.opendata.arcgis.com/"},
            {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"],
             "url": "https://github.com/boettiger-lab"},
        ],
        "links": [
            {"rel": "self", "href": PARENT, "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": ROOT, "type": "application/json"},
            {"rel": "license", "href": "https://wgfd.wyo.gov/geospatial-data",
             "type": "text/html"},
        ] + [
            {"rel": "child", "href": f"{NRP}/{BUCKET}/{ds}/stac-collection.json",
             "type": "application/json", "title": collection(ds)["title"]}
            for ds in D
        ],
    }


if __name__ == "__main__":
    import os
    out = os.environ.get("OUT", "/tmp/wgfd-stac")
    os.makedirs(out, exist_ok=True)
    for ds in D:
        p = f"{out}/{ds}.json"
        json.dump(collection(ds), open(p, "w"), indent=2)
        print("wrote", p)
    json.dump(bucket_collection(), open(f"{out}/bucket.json", "w"), indent=2)
    print("wrote", f"{out}/bucket.json")
