"""Author the STAC for all seven public-wgfd collections plus the bucket collection (#578).

Covers the three crucial-range layers (elk, mule deer, pronghorn), the three full
seasonal-range layers for the same species, and the sage-grouse Core Management Areas.
Running it writes eight JSON documents to $OUT (default /tmp/wgfd-stac): one per
collection and bucket.json, the public-wgfd bucket collection with all seven as children.
The output reproduces the live S3 STAC; publishing it is a separate step (rclone copyto).

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
        kind="crucial",
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
        kind="crucial",
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
        kind="crucial",
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
    # Full seasonal range: the non-crucial codes as well as the CRU ones. `ranges` is in
    # descending count order (ties as measured), which is the order the codes are listed in.
    "elk-seasonal": dict(
        kind="seasonal",
        species="elk", Species="Elk",
        features=484, h8=253709,
        bbox=[-111.05, 40.995, -104.053, 45.007],
        ranges={"WYL": 135, "CRUWYL": 91, "WIN": 77, "CRUWIN": 57, "OUT": 55, "SSF": 35,
                "YRL": 24, "SWR": 6, "CRUSWR": 2, "UND": 2},
        acres=(None, None, 47213966.86),
        sha256="3788f003cd26547fd984b17003318940a1858e0693a074d0e1b4fe7550208c1c",
        raw_bytes=10686561,
        built={"parquet": "2026-08-22T00:12:26Z", "pmtiles": "2026-08-22T00:12:47Z",
               "hex": "2026-08-22T00:25:39Z"},
        partitions=2,
        note="Elk is the only species here whose data includes undetermined (UND) areas.",
    ),
    "mule-deer-seasonal": dict(
        kind="seasonal",
        species="mule deer", Species="Mule deer",
        features=512, h8=325192,
        bbox=[-111.05, 40.995, -104.052, 45.007],
        ranges={"WYL": 154, "CRUWYL": 116, "OUT": 81, "YRL": 79, "SSF": 31, "CRUWIN": 29,
                "WIN": 21, "SWR": 1},
        acres=(None, None, 60688616.36),
        sha256="a0ad5426b3924f1a945c26f48e5a4c8943e1aa182bfd6f4350ba15482b980ea0",
        raw_bytes=15910922,
        built={"parquet": "2026-08-22T00:26:40Z", "pmtiles": "2026-08-22T00:26:55Z",
               "hex": "2026-08-22T00:48:00Z"},
        partitions=2,
        note=None,
    ),
    "pronghorn-seasonal": dict(
        kind="seasonal",
        species="pronghorn", Species="Pronghorn",
        features=502, h8=302185,
        bbox=[-111.048, 40.995, -104.052, 45.007],
        ranges={"OUT": 186, "WYL": 103, "CRUWYL": 101, "YRL": 52, "SSF": 38, "WIN": 10,
                "SWR": 8, "CRUSWR": 3, "CRUWIN": 1},
        acres=(None, None, 120774532.1),
        sha256="5b3fdbaccf91296eb3735be66e65fd0135b3bfe0b62dc87c49ddf04b939a9a88",
        raw_bytes=16662444,
        built={"parquet": "2026-08-22T00:51:41Z", "pmtiles": "2026-08-22T00:51:57Z",
               "hex": "2026-08-22T01:06:14Z"},
        partitions=1,
        note="Upstream the department publishes this layer under the common name antelope.",
    ),
    # Named Core Management Areas: a different schema from the range layers.
    "sage-grouse-priority": dict(
        kind="sage",
        features=33, h8=86934,
        bbox=[-111.047, 41.0, -104.291, 45.0],
        acres=(None, None, 15409173.42),
        sha256="4c7796900bf33208d58541c574aa503481f090caafbc051b663b0428d6a9cfde",
        raw_bytes=1321198,
        built={"parquet": "2026-08-22T01:07:10Z", "pmtiles": "2026-08-22T01:07:29Z",
               "hex": "2026-08-22T01:08:47Z"},
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
    "WIN": "winter range",
    "WYL": "winter/yearlong range",
    "SWR": "severe winter relief range",
    "SSF": "spring/summer/fall range",
    "YRL": "yearlong range",
    "OUT": "out — occupied only occasionally, outside the identified seasonal ranges",
    "UND": "undetermined",
}


ACCESS_DATE = "2026-02-25"   # when the source GeoJSON was pulled from the WGFD ArcGIS Hub


def present_codes(ds):
    """RANGE codes present in the data, in descending count order."""
    r = D[ds]["ranges"]
    return sorted(r, key=lambda c: -r[c])


SHARED_DEFS = {
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


def col_defs(ds):
    kind = D[ds]["kind"]
    if kind == "sage":
        return {
            "_cng_fid": ("int64",
                "Identifier assigned to every polygon during conversion, unique within this "
                "dataset. Count areas or remove repeated rows with COUNT(DISTINCT _cng_fid)."),
            "OGC_FID": ("int64", "Sequential record number carried over from the source export."),
            "ID": ("int64", "Core Management Area identifier from the published layer."),
            "NAME": ("string",
                "Name of the Core Management Area, for example a landscape or basin the area "
                "is known by."),
            "Acres": ("double", "Area of the Core Management Area in acres, as published."),
            "Shape_Leng": ("double",
                "Perimeter of the area polygon in the units of the source projection, carried "
                "over from the published layer."),
            "Shape_Area": ("double",
                "Area of the polygon in the units of the source projection, carried over from "
                "the published layer. Acres is the interpretable value."),
            "geom": ("geometry",
                "Polygon geometry of the Core Management Area, in EPSG:4326."),
            **SHARED_DEFS,
        }

    listed = ", ".join(f"{c}={RANGE_DEFS[c]}" for c in present_codes(ds))
    if kind == "crucial":
        range_desc = (
            "Seasonal range designation. Every polygon here is crucial range, so each code "
            f"combines the crucial prefix CRU with the seasonal type. Values: {listed}.")
    else:
        range_desc = (
            "Seasonal range designation assigned by the Wyoming Game & Fish Department. A CRU "
            "prefix marks crucial range, the habitat the department identifies as a "
            "determining factor in the population's ability to sustain itself. "
            f"Values: {listed}.")
    return {
        "_cng_fid": ("int64",
            "Identifier assigned to every polygon during conversion, unique within this "
            "dataset. Count features or remove repeated rows with COUNT(DISTINCT _cng_fid)."),
        "OGC_FID": ("int64",
            "Sequential record number carried over from the source GeoJSON export."),
        "OBJECTID": ("int32",
            "Feature identifier assigned by the Wyoming Game & Fish Department in the "
            "published layer. Unique for every polygon in this dataset."),
        "RANGE": ("string", range_desc),
        "Acres": ("double",
            "Area of the range polygon in acres, as published by the Wyoming Game & Fish "
            "Department."),
        "SQMiles": ("double",
            "Area of the range polygon in square miles, as published by the Wyoming Game & "
            "Fish Department."),
        "geom": ("geometry", "Polygon geometry of the range, in EPSG:4326."),
        **SHARED_DEFS,
    }


RANGE_ATTRS = ["_cng_fid", "OGC_FID", "OBJECTID", "RANGE", "Acres", "SQMiles"]
SAGE_ATTRS = ["_cng_fid", "OGC_FID", "ID", "NAME", "Acres", "Shape_Leng", "Shape_Area"]
H3_COLS = ["h10", "h9", "h8", "h0"]


def attrs(ds):
    return SAGE_ATTRS if D[ds]["kind"] == "sage" else RANGE_ATTRS


def columns(ds, names, lean=False):
    defs = col_defs(ds)
    out = []
    for n in names:
        t, desc = defs[n]
        c = {"name": n, "type": t}
        if not lean:
            c["description"] = desc
        if n == "RANGE":
            c["values"] = present_codes(ds)
        out.append(c)
    return out


def text(ds):
    """Per-kind prose: collection title/description/citation and asset wording."""
    d = D[ds]
    kind = d["kind"]
    total = d["acres"][2]
    hexnote_tail = (
        f"For the ground area of a set of cells, aggregate the cell areas over distinct cells "
        f"rather than these published columns. Covers {d['h8']:,} resolution 8 cells across "
        f"{d['partitions']} resolution 0 partition"
        f"{'s' if d['partitions'] != 1 else ''}.")

    if kind == "sage":
        label = "Sage-grouse Core Management Areas"
        return dict(
            title="Greater Sage-Grouse Core Management Areas v4 (Wyoming)",
            description=(
                f"Greater sage-grouse Core Management Areas in Wyoming, version 4. These are "
                f"the highest-priority sage-grouse habitat areas, {d['features']} named areas "
                f"covering about {total:,.0f} acres, identified jointly by the Wyoming Game & "
                f"Fish Department and the Bureau of Land Management to focus conservation and "
                f"management. Each polygon is one named Core Management Area.\n\n"
                f"This is Wyoming's own Core Area designation — a state policy instrument "
                f"rather than a clip of a range-wide product. Sage-grouse habitat is mapped "
                f"across the western states by other programs, but those are separate datasets "
                f"built on different criteria, not wider extents of this one."),
            citation=(
                f"Wyoming Game & Fish Department and Bureau of Land Management, Greater "
                f"Sage-Grouse Core Management Areas version 4. Accessed {ACCESS_DATE} from the "
                f"WGFD ArcGIS Hub (wyoming-wgfd.opendata.arcgis.com). Distribution is through "
                f"an ArcGIS Hub endpoint with no stable versioned download URL, so the retained "
                f"source is the anchor: s3://{BUCKET}/raw/{ds}.zip, SHA-256 {d['sha256']}. "
                f"Converted to GeoParquet, PMTiles and H3 by the Boettiger Lab, UC Berkeley."),
            keywords=["Wyoming", "sage-grouse", "greater sage-grouse", "core areas", "habitat",
                      "WGFD", "BLM", "sagebrush"],
            parquet_title=f"{label} — GeoParquet",
            parquet_desc=("Core Management Area polygons as GeoParquet, one row per area, in "
                          "EPSG:4326. Query directly with DuckDB over HTTP."),
            pmtiles_title=f"{label} — PMTiles",
            pmtiles_desc=(f"Vector tiles for web maps. In MapLibre GL JS the source layer is "
                          f"\"{ds}\"; label features with NAME."),
            hex_title=f"{label} — H3 resolution 10",
            hex_desc=(
                f"Core Management Areas as H3 cells at resolution 10, with resolution 9, 8 and "
                f"0 identifiers alongside for rolling up or joining to other datasets. There is "
                f"one row for each combination of a Core Management Area and a cell it covers, "
                f"so a polygon spanning many cells appears on many rows, and the per-polygon "
                f"values Acres, Shape_Leng and Shape_Area are repeated on every one of its "
                f"cells. Reduce to one row per polygon before totalling any of them:\n\n"
                f"SELECT SUM(Acres) FROM (SELECT DISTINCT _cng_fid, Acres FROM …)\n\n"
                + hexnote_tail),
        )

    sp, Sp = d["species"], d["Species"]
    present = present_codes(ds)

    if kind == "crucial":
        breakdown = ", ".join(f"{c} ({d['ranges'][c]})" for c in present)
        return dict(
            title=f"{Sp} Crucial Range (Wyoming)",
            description=(
                f"Crucial seasonal habitat range for {sp} in Wyoming, mapped by the Wyoming "
                f"Game & Fish Department. Crucial ranges are the seasonal habitats the "
                f"department identifies as a determining factor in the population's ability to "
                f"sustain itself, so they carry more management weight than ordinary seasonal "
                f"range. This dataset holds {d['features']:,} polygons covering about "
                f"{total:,.0f} acres, broken down by range type as {breakdown}.\n\n"
                f"Coverage is the state of Wyoming. That is the full extent of the source: the "
                f"Wyoming Game & Fish Department maps range within its own jurisdiction, so this "
                f"is a complete dataset rather than a regional excerpt of something larger.\n\n"
                f"The department publishes crucial range as a separate layer from full {sp} "
                f"seasonal range, and every polygon here is crucial, which is why each RANGE "
                f"code begins with CRU."),
            citation=(
                f"Wyoming Game & Fish Department, {Sp} Crucial Range. Accessed {ACCESS_DATE} "
                f"from the WGFD ArcGIS Hub (wyoming-wgfd.opendata.arcgis.com). The department "
                f"publishes through an ArcGIS Hub endpoint with no stable versioned download "
                f"URL, so the retained source is the anchor: s3://{BUCKET}/raw/{ds}.geojson, "
                f"{d['raw_bytes']:,} bytes, SHA-256 {d['sha256']}. Converted to GeoParquet, "
                f"PMTiles and H3 by the Boettiger Lab, UC Berkeley."),
            keywords=["Wyoming", sp, "wildlife", "habitat", "crucial range", "seasonal range",
                      "WGFD", "big game"],
            parquet_title=f"{Sp} crucial range — GeoParquet",
            parquet_desc=(f"{Sp} crucial range polygons as GeoParquet, one row per polygon, in "
                          f"EPSG:4326. Query directly with DuckDB over HTTP."),
            pmtiles_title=f"{Sp} crucial range — PMTiles",
            pmtiles_desc=(f"Vector tiles for web maps. In MapLibre GL JS the source layer is "
                          f"\"{ds}\"; style or filter on RANGE to separate the crucial range "
                          f"types."),
            hex_title=f"{Sp} crucial range — H3 resolution 10",
            hex_desc=(
                f"{Sp} crucial range as H3 cells at resolution 10, with resolution 9, 8 and 0 "
                f"identifiers alongside for rolling up or joining to other datasets. There is "
                f"one row for each combination of a range polygon and a cell it covers, so a "
                f"polygon that spans many cells appears on many rows, and the per-polygon values "
                f"Acres and SQMiles are repeated on every one of its cells. Reduce to one row per "
                f"polygon before totalling either of them:\n\n"
                f"SELECT SUM(Acres) FROM (SELECT DISTINCT _cng_fid, Acres FROM …)\n\n"
                + hexnote_tail),
        )

    # seasonal
    crucial_ds = ds.replace("-seasonal", "-crucial")
    cru = ", ".join(c for c in present if c.startswith("CRU"))
    description = (
        f"Seasonal habitat range for {sp} in Wyoming, mapped by the Wyoming Game & Fish "
        f"Department. This is the full seasonal picture — winter, yearlong, "
        f"spring/summer/fall and severe-winter-relief range — across {d['features']:,} "
        f"polygons and about {total:,.0f} acres. Read the RANGE column to tell the types "
        f"apart.\n\n"
        f"Codes beginning with CRU mark crucial range, the subset the department treats as a "
        f"determining factor in the population's ability to sustain itself. Those codes here "
        f"are {cru}. The department also publishes crucial range on its own, which is the "
        f"wgfd-{crucial_ds} collection in this catalog; filtering this layer to CRU codes covers "
        f"the same ground.\n\n"
        f"Coverage is the state of Wyoming, which is the full extent of the source: the "
        f"department maps range within its own jurisdiction, so this is complete rather than a "
        f"regional excerpt of something larger.")
    if d.get("note"):
        description += "\n\n" + d["note"]
    return dict(
        title=f"{Sp} Seasonal Range (Wyoming)",
        description=description,
        citation=(
            f"Wyoming Game & Fish Department, {Sp} Seasonal Range. Accessed {ACCESS_DATE} from "
            f"the WGFD ArcGIS Hub (wyoming-wgfd.opendata.arcgis.com). The department publishes "
            f"through an ArcGIS Hub endpoint with no stable versioned download URL, so the "
            f"retained source is the anchor: s3://{BUCKET}/raw/{ds}.geojson, SHA-256 "
            f"{d['sha256']}. Converted to GeoParquet, PMTiles and H3 by the Boettiger Lab, "
            f"UC Berkeley."),
        keywords=["Wyoming", sp, "wildlife", "habitat", "seasonal range", "crucial range",
                  "WGFD", "big game"],
        parquet_title=f"{Sp} seasonal range — GeoParquet",
        parquet_desc=(f"{Sp} seasonal range polygons as GeoParquet, one row per polygon, in "
                      f"EPSG:4326. Query directly with DuckDB over HTTP."),
        pmtiles_title=f"{Sp} seasonal range — PMTiles",
        pmtiles_desc=(f"Vector tiles for web maps. In MapLibre GL JS the source layer is "
                      f"\"{ds}\"; style or filter on RANGE to separate the seasonal range "
                      f"types, or to show only the crucial (CRU) ones."),
        hex_title=f"{Sp} seasonal range — H3 resolution 10",
        hex_desc=(
            f"{Sp} seasonal range as H3 cells at resolution 10, with resolution 9, 8 and 0 "
            f"identifiers alongside for rolling up or joining to other datasets. There is one "
            f"row for each combination of a range polygon and a cell it covers, so a polygon "
            f"spanning many cells appears on many rows, and the per-polygon values Acres and "
            f"SQMiles are repeated on every one of its cells. Reduce to one row per polygon "
            f"before totalling any of them:\n\n"
            f"SELECT SUM(Acres) FROM (SELECT DISTINCT _cng_fid, Acres FROM …)\n\n"
            + hexnote_tail),
    )


def collection(ds):
    d = D[ds]
    t = text(ds)
    a = attrs(ds)

    assets = {
        f"{ds}-parquet": {
            "href": f"{NRP}/{BUCKET}/{ds}.parquet",
            "type": "application/x-parquet",
            "roles": ["data"],
            "title": t["parquet_title"],
            "created": d["built"]["parquet"],
            "description": t["parquet_desc"],
            "table:columns": columns(ds, a + ["geom"]),
        },
        f"{ds}-pmtiles": {
            "href": f"{NRP}/{BUCKET}/{ds}.pmtiles",
            "type": "application/vnd.pmtiles",
            "roles": ["visual"],
            "title": t["pmtiles_title"],
            "created": d["built"]["pmtiles"],
            "description": t["pmtiles_desc"],
            "vector:layers": [ds],
            "table:columns": columns(ds, a, lean=True),
        },
        f"{ds}-hex": {
            "href": f"{NRP}/{BUCKET}/{ds}/hex/h0=*/data_0.parquet",
            "type": "application/x-parquet",
            "roles": ["data"],
            "title": t["hex_title"],
            "created": d["built"]["hex"],
            "description": t["hex_desc"],
            "h3:native_resolution": 10,
            "h3:parent_resolutions": [9, 8, 0],
            "table:columns": columns(ds, a + H3_COLS),
        },
    }

    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": [TABLE_EXT, SCI_EXT],
        "id": f"wgfd-{ds}",
        "title": t["title"],
        "description": t["description"],
        "license": "other",
        "sci:citation": t["citation"],
        "created": d["built"]["parquet"],
        "updated": d["built"]["hex"],
        "keywords": t["keywords"],
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
