#!/usr/bin/env python3
"""Emit STAC collections for the WRC v2 populated-areas (RDS-2020-0060-2) hex + COG datasets.

Writes to /tmp only -- this repo never contains STAC JSON (AGENTS.md Hard Boundary 1).
Upload with:

    rclone copyto /tmp/<dataset>-stac-collection.json nrp:public-fire/<dataset>/stac-collection.json

⚠️ A DIFFERENT DOI from catalog/fire/k8s/wrc-2/gen_stac.py. That one emits the LANDSCAPE-WIDE
publication RDS-2020-0016-2 (RPS, BP, CFL, Exposure). This one emits RDS-2020-0060-2, the
populated-areas publication, whose dataset ids all carry `-pa-`.

Every number that describes the *ingested data* (row counts, value ranges, pixel sums, footprints)
is read from `facts.json`, which is populated from measured job output and duckdb-geo MCP results
and is committed alongside this script as evidence. Nothing here invents a measurement. Object
sizes and ETags are read live from S3.

    python3 gen_stac.py                # all datasets present in facts.json
    python3 gen_stac.py wrc-2-pa-hurisk-conus
    python3 gen_stac.py --bucket-patch # patch the public-fire bucket collection's child links
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request

S3 = "https://s3-west.nrp-nautilus.io"
BUCKET = "public-fire"
ROOT = f"{S3}/public-data/stac/catalog.json"
PARENT = f"{S3}/{BUCKET}/stac-collection.json"
HERE = os.path.dirname(os.path.abspath(__file__))

DOI = "https://doi.org/10.2737/RDS-2020-0060-2"
CATALOG_PAGE = "https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0060-2"
ACCESS_DATE = "2026-09-16"

CITATION = (
    "Scott, Joe H.; Brough, April M.; Gilbertson-Day, Julie W.; Dillon, Gregory K.; "
    "Moran, Christopher. 2024. Wildfire Risk to Communities: Spatial datasets of wildfire "
    "risk for populated areas in the United States, 2nd Edition. Fort Collins, CO: Forest "
    f"Service Research Data Archive. {DOI}. Accessed {ACCESS_DATE}."
)

# The source's own currency, not its publication date: the data reflect landscape conditions as
# of the end of 2014 (LANDFIRE 2020, version 2.2.0).
TEMPORAL = ["2014-01-01T00:00:00Z", "2014-12-31T23:59:59Z"]

# ---------------------------------------------------------------------------
# Per-theme copy. Descriptions are USER-FACING: the geo-agent quotes them nearly
# verbatim to end users, so they say what the layer is, what it measures, at what
# resolution, and the one thing needed to use it correctly. No issue numbers, no
# shouted imperatives, no bare abbreviations.
# ---------------------------------------------------------------------------
THEMES = {
    "hurisk": dict(
        column="hurisk",
        label="Housing Unit Risk",
        webapp="Risk to Homes",
        units="unitless index",
        reducer="mean",
        dtype="int32",
        source_range="0 to 7,556,012 across the United States",
        what=(
            "Housing Unit Risk combines all four primary elements of wildfire risk at a "
            "location: how likely a fire is, how intense it would be, how susceptible housing "
            "units are, and how exposed they are. It is defined only where housing-unit density "
            "is greater than zero, so it describes risk where people actually live rather than "
            "risk to a hypothetical structure."
        ),
        interpretation=(
            "The value is a relative index with no physical unit, so it is meaningful for "
            "ranking and comparison rather than as a quantity. Combine cells by averaging; "
            "there is no meaningful total. Because the layer is undefined where nobody lives, "
            "an absence of data means no housing units, not an absence of wildfire risk."
        ),
    ),
    "huexposure": dict(
        column="huexposure",
        label="Housing Unit Exposure",
        webapp="Exposure",
        units="housing units per year",
        reducer="sum",
        dtype="float32",
        source_range="0 to 0.13 per 30 metre pixel across the United States",
        what=(
            "Housing Unit Exposure is the expected number of housing units potentially exposed "
            "to wildfire in a year at a given location. It is a long-term annual average from "
            "modelled fire likelihood, not a count of housing units exposed in any particular "
            "year."
        ),
        interpretation=(
            "This is an amount rather than an index: each cell holds the expected housing units "
            "within that cell, so cells add. Summing over an area gives the expected housing "
            "units exposed per year in that area, and the catalog total is meaningful. Values "
            "per cell are small because the quantity is an annual expectation."
        ),
    ),
}

DOMAINS = {
    "conus": dict(
        label="continental United States",
        # Carries its own article: "Coverage is the continental United States", "Coverage is Alaska".
        article="the ",
        short="CONUS",
        src_crs="EPSG:5070 (NAD83 / Conus Albers)",
        src_size="156,335 by 101,538 pixels",
        clip_note="",
    ),
    "ak": dict(
        label="Alaska",
        article="",
        short="Alaska",
        src_crs="EPSG:3338 (NAD83 / Alaska Albers)",
        src_size="124,603 by 66,861 pixels",
        clip_note=(
            " The Alaska raster is clipped to longitudes between 180 degrees west and 129 "
            "degrees west. The source grid crosses the antimeridian, and reprojecting it whole "
            "produces a raster about 360 degrees wide that is almost entirely empty. The "
            "excluded far-western Aleutian Islands contain no National Forest System land."
        ),
    ),
}


def http_head(url: str) -> dict:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=120) as r:
        return {k.lower(): v for k, v in r.headers.items()}


def http_get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=300) as r:
        return r.read()


def object_facts(url: str) -> dict:
    """Size and ETag of a published object, measured from the object itself."""
    h = http_head(url)
    return {"size": int(h["content-length"]), "etag": (h.get("etag") or "").strip('"')}


def hex_columns(theme: dict) -> list:
    """Per-column schema for the hex asset.

    Text for a given column name must be IDENTICAL everywhere it appears in the collection (the
    renderer folds duplicates and first-seen wins), and the H3 columns are kept grain-neutral so
    they stay reusable.
    """
    if theme["reducer"] == "sum":
        value_desc = (
            f"{theme['label']} ({theme['units']}) held by the cell, as the coverage-weighted sum "
            f"of the 30 metre source pixels falling in it. Cells add: summing this column over an "
            f"area gives that area's total. Source values span {theme['source_range']}."
        )
    else:
        value_desc = (
            f"{theme['label']} ({theme['units']}), as the area-weighted mean of the 30 metre "
            f"source pixels falling in the cell. Source values span {theme['source_range']}."
        )
    return [
        {"name": theme["column"], "type": "double", "description": value_desc},
        {
            "name": "h10",
            "type": "uint64",
            "description": "H3 cell identifier at resolution 10, the native resolution of this layer.",
        },
        {"name": "h9", "type": "uint64", "description": "H3 cell identifier at resolution 9."},
        {"name": "h8", "type": "uint64", "description": "H3 cell identifier at resolution 8."},
        {
            "name": "h0",
            "type": "int64",
            "description": (
                "H3 cell identifier at resolution 0, used as the partition key for "
                "hive-partitioned reads."
            ),
        },
    ]


def build_collection(dataset: str, facts: dict) -> dict:
    theme_key, domain_key = dataset.removeprefix("wrc-2-pa-").rsplit("-", 1)
    theme, domain = THEMES[theme_key], DOMAINS[domain_key]
    f = facts[dataset]
    is_sum = theme["reducer"] == "sum"

    cog_href = f"{S3}/{BUCKET}/{dataset}-cog.tif"
    hex_href = f"{S3}/{BUCKET}/{dataset}/hex/h0=*/data_0.parquet"
    raw_href = f"{S3}/{BUCKET}/raw/wrc-2-pa/{f['raw_name']}"

    cog = object_facts(cog_href)
    raw = object_facts(raw_href)

    webapp = (
        f" It is presented as {theme['webapp']} in the Wildfire Risk to Communities web "
        f"application."
        if theme.get("webapp") and theme["webapp"] not in theme["what"]
        else ""
    )

    if is_sum:
        reducer_para = (
            f"Coverage is {domain['article']}{domain['label']} at a 30 metre source pixel "
            f"size, from the "
            f"second edition of Wildfire Risk to Communities. Hexed to H3 resolution 10 using a "
            f"coverage-weighted sum of the source pixels in each cell, with rollup columns at "
            f"resolutions 9, 8 and 0. Resolution 10 cells are about 0.015 square kilometres, so "
            f"each cell gathers roughly 17 source pixels. Because the source value is an amount "
            f"held by each pixel rather than an intensity, both the reprojection and the hex "
            f"aggregation conserve the total, and the sum over any set of cells is the amount "
            f"within them.{domain['clip_note']}"
        )
    else:
        reducer_para = (
            f"Coverage is {domain['article']}{domain['label']} at a 30 metre source pixel "
            f"size, from the "
            f"second edition of Wildfire Risk to Communities. Hexed to H3 resolution 10 using an "
            f"area-weighted mean of the source pixels in each cell, with rollup columns at "
            f"resolutions 9, 8 and 0. Resolution 10 cells are about 0.015 square kilometres, so "
            f"each cell averages roughly 17 source pixels.{domain['clip_note']}"
        )

    sibling_para = (
        "Three related things are published separately in this bucket and answer different "
        "questions. Wildfire Hazard Potential, in the whp-2023 collections, measures the "
        "potential for a fire that would be difficult to control given fuels, terrain and "
        "weather, and its source metadata states that it does not account for what is exposed. "
        "Risk to Potential Structures, in the wrc-2-rps collections, measures what a fire would "
        "do to a home at a location whether or not one stands there. The populated-areas layers "
        "here, whose identifiers carry pa, are the ones that know where housing units actually "
        "are: they come from a separate publication that maps buildings, population and housing "
        "units, and they are defined in terms of real housing units rather than a hypothetical "
        "structure."
    )

    oversampling_para = (
        "The fire likelihood and intensity inputs behind these layers were modelled at 270 "
        "metres and upsampled to the 30 metre resolution of the LANDFIRE fuel and vegetation "
        "grid, so the 30 metre grid is finer than the independent information content of those "
        "inputs. The data reflect landscape conditions as of the end of 2014, from LANDFIRE 2020 "
        "version 2.2.0, which is why the temporal extent is 2014 rather than the 2024 "
        "publication date."
    )

    join_para = (
        "To compare this layer against inventoried roadless areas or the wildland-urban "
        "interface, join on h10 against public-usfs/roadless-areas-2001 or public-wui/wui-2020, "
        "both of which are published at H3 resolution 10 with the same rollup columns. Those two "
        "are derived from polygons, so their per-feature attributes repeat on every cell a "
        "feature covers and need de-duplicating by _cng_fid before being summed. This layer is "
        "derived from a raster and has one row per cell."
    )

    resampling = "the overlap-weighted sum of contributing source pixels" if is_sum else \
        "nearest-neighbour resampling"
    resampling_why = (
        "Nearest-neighbour resampling would not have preserved the total, because reprojection "
        "changes both the pixel count and the per-pixel ground area by an amount that varies "
        "with latitude."
        if is_sum else
        "Nearest neighbour is used so that the no-data value is not blended into valid data "
        "along boundaries."
    )

    provenance_para = (
        f"Provenance. Source archive RDS-2020-0060-2, accessed {ACCESS_DATE} from "
        f"{CATALOG_PAGE}. The staged source raster is {f['raw_name']} at {raw['size']:,} bytes "
        f"(S3 ETag {raw['etag']}), held at {BUCKET}/raw/wrc-2-pa/. Source grid "
        f"{domain['src_size']} in {domain['src_crs']} with a no-data value of "
        f"{f['src_nodata_text']}, reprojected to EPSG:4326 using {resampling} before hexing. "
        f"The no-data value in the published cloud-optimized GeoTIFF is -9999; every theme in "
        f"this publication is non-negative, so that value cannot collide with real data."
    )

    description = "\n\n".join([
        f"{theme['what']}{webapp}",
        theme["interpretation"],
        reducer_para,
        sibling_para,
        oversampling_para,
        join_para,
        provenance_para,
    ])

    if is_sum:
        hex_desc = (
            f"H3 resolution 10 hex cells carrying the {theme['label'].lower()} held by each "
            f"cell, as a coverage-weighted sum of the source pixels, with rollup columns at "
            f"resolutions 9, 8 and 0. One row per cell. The value is an amount rather than an "
            f"intensity, so cells add: sum the column to total an area, and roll up to a coarser "
            f"resolution with a sum rather than an average. A cell is present only where the "
            f"source raster holds data, so a cell whose value is zero is a measured zero, "
            f"meaning mapped ground with no expected exposure, while ground the mapping does "
            f"not cover has no row at all.\n\n"
            f"```sql\n"
            f"-- expected housing units exposed per year inside inventoried roadless areas\n"
            f"SELECT SUM(w.{theme['column']}) AS {theme['column']}_total\n"
            f"FROM read_parquet('{hex_href}') w\n"
            f"JOIN (\n"
            f"  SELECT DISTINCT h10\n"
            f"  FROM read_parquet('{S3}/public-usfs/roadless-areas-2001/hex/h0=*/data_0.parquet')\n"
            f") r USING (h10);\n"
            f"```"
        )
    else:
        hex_desc = (
            f"H3 resolution 10 hex cells carrying the area-weighted mean "
            f"{theme['label'].lower()} for each cell, with rollup columns at resolutions 9, 8 "
            f"and 0. One row per cell. Because the value is an index rather than an amount held "
            f"by each cell, there is no meaningful catalog total: combine cells by averaging, "
            f"and roll up to a coarser resolution with an area-weighted average rather than a "
            f"sum. The layer is defined only where housing-unit density is greater than zero, so "
            f"a cell with no row has no housing units rather than no risk.\n\n"
            f"```sql\n"
            f"-- mean {theme['column']} inside inventoried roadless areas, joined at resolution 10\n"
            f"SELECT AVG(w.{theme['column']}) AS mean_{theme['column']}\n"
            f"FROM read_parquet('{hex_href}') w\n"
            f"JOIN (\n"
            f"  SELECT DISTINCT h10\n"
            f"  FROM read_parquet('{S3}/public-usfs/roadless-areas-2001/hex/h0=*/data_0.parquet')\n"
            f") r USING (h10);\n"
            f"```"
        )

    cog_desc = (
        f"{theme['label']} reprojected to EPSG:4326 from {domain['src_crs']} using "
        f"{resampling}, at approximately the source 30 metre ground resolution. {resampling_why}"
    )
    if is_sum:
        cog_desc += (
            " Each pixel holds the amount within its own footprint, and reprojected pixels do "
            "not all cover the same ground area, so the per-pixel maximum here is not the "
            "per-pixel maximum of the source grid. The total across the raster is preserved."
        )

    coll = {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
        ],
        "id": dataset,
        "title": (
            f"Wildfire Risk to Communities v2 populated areas: {theme['label']} "
            f"({domain['short']}, 30 m)"
        ),
        "description": description,
        "license": "public-domain",
        "keywords": [
            "wildfire",
            "wildfire risk",
            "fire",
            "housing units",
            theme["label"].lower(),
            domain["short"].lower(),
            "h3",
            "hex",
        ],
        "sci:doi": "10.2737/RDS-2020-0060-2",
        "sci:citation": CITATION,
        "created": f["created"],
        "updated": f["created"],
        "extent": {
            "spatial": {"bbox": [f["bbox"]]},
            "temporal": {"interval": [TEMPORAL]},
        },
        "providers": [
            {
                "name": "USDA Forest Service, Rocky Mountain Research Station, Fire Modeling Institute",
                "roles": ["producer", "licensor"],
                "url": CATALOG_PAGE,
            },
            {
                "name": "USDA Forest Service Research Data Archive",
                "roles": ["host"],
                "url": DOI,
            },
            {
                "name": "Boettiger Lab",
                "roles": ["processor"],
                "url": "https://github.com/boettiger-lab/data-workflows",
            },
        ],
        "links": [
            {
                "rel": "self",
                "href": f"{S3}/{BUCKET}/{dataset}/stac-collection.json",
                "type": "application/json",
            },
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": PARENT, "type": "application/json"},
            {
                "rel": "license",
                "href": CATALOG_PAGE,
                "type": "text/html",
                "title": "US Government work, public domain -- see the archive's use constraints",
            },
            {"rel": "about", "href": CATALOG_PAGE, "type": "text/html"},
            {"rel": "cite-as", "href": DOI},
            {
                "rel": "related",
                "href": f"{S3}/{BUCKET}/wrc-2-rps-{domain_key}/stac-collection.json",
                "type": "application/json",
                "title": (
                    "Risk to Potential Structures, the landscape-wide counterpart from the "
                    "companion publication RDS-2020-0016-2"
                ),
            },
        ],
        "assets": {
            f"{dataset}-cog": {
                "href": cog_href,
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "title": f"{theme['label']} ({domain['short']}) cloud-optimized GeoTIFF",
                "description": cog_desc,
                "roles": ["data"],
                "created": f["created"],
                "file:size": cog["size"],
                "raster:bands": [
                    {
                        "name": theme["column"],
                        "data_type": theme["dtype"],
                        "nodata": -9999,
                        "unit": theme["units"],
                        "spatial_resolution": 30,
                        "statistics": {
                            "minimum": f["cog_min"],
                            "maximum": f["cog_max"],
                            "mean": f["cog_mean"],
                        },
                    }
                ],
            },
            f"{dataset}-hex": {
                "href": hex_href,
                "type": "application/x-parquet",
                "title": f"{theme['label']} ({domain['short']}) H3 resolution 10 hex cells",
                "description": hex_desc,
                "roles": ["data"],
                "created": f["created"],
                "h3:native_resolution": 10,
                "h3:parent_resolutions": [9, 8, 0],
                "table:row_count": f["rows"],
                "table:columns": hex_columns(theme),
            },
        },
    }
    return coll


# The `public-fire` description enumerates the kinds of layer the bucket holds, and this
# publication adds one it did not have: layers that know where housing units actually are. The
# sentence replaced below said "Three kinds of layer"; leaving it would make the bucket collection
# contradict its own children. Matched on an exact substring so a drifted description fails loudly
# rather than being silently half-patched.
BUCKET_DESC_OLD = (
    "Three kinds of layer live here and they answer different questions."
)
BUCKET_DESC_NEW = (
    "Four kinds of layer live here and they answer different questions."
)
BUCKET_DESC_INSERT_AFTER = (
    "a modelled surface, and hazard rather than risk, since it does not account for what is "
    "exposed to loss."
)
BUCKET_DESC_INSERT = (
    " Risk to Potential Structures asks what a fire would do to a home at a location, whether or "
    "not one stands there. The populated-areas layers, whose identifiers carry pa, are the ones "
    "that know where housing units actually are: they come from a separate Wildfire Risk to "
    "Communities publication that maps buildings, population and housing units, and they are "
    "defined in terms of real housing units rather than a hypothetical structure."
)


def patch_bucket_description(cur: dict) -> bool:
    """Widen the bucket description to cover the populated-areas layers. Idempotent."""
    d = cur.get("description", "")
    if BUCKET_DESC_INSERT.strip() in d:
        print("  description   : already widened, left alone")
        return False
    if BUCKET_DESC_OLD not in d or BUCKET_DESC_INSERT_AFTER not in d:
        raise SystemExit(
            "FATAL: the public-fire description has drifted from what this script was written "
            "against; re-read it and update BUCKET_DESC_* before publishing."
        )
    d = d.replace(BUCKET_DESC_OLD, BUCKET_DESC_NEW, 1)
    d = d.replace(
        BUCKET_DESC_INSERT_AFTER, BUCKET_DESC_INSERT_AFTER + BUCKET_DESC_INSERT, 1
    )
    cur["description"] = d
    print("  description   : widened to four kinds of layer")
    return True


def patch_bucket(datasets: list) -> None:
    """Add child links for the new collections, preserving everything else.

    Fetch -> edit -> re-upload, never regenerate: the bucket collection carries fields this
    script does not model, and pre-existing assets that must survive.
    """
    cur = json.loads(http_get(PARENT))
    before = len(cur.get("links", []))
    patch_bucket_description(cur)
    have = {l.get("href") for l in cur.get("links", []) if l.get("rel") == "child"}
    added = []
    for ds in datasets:
        href = f"{S3}/{BUCKET}/{ds}/stac-collection.json"
        if href in have:
            continue
        theme_key, domain_key = ds.removeprefix("wrc-2-pa-").rsplit("-", 1)
        cur["links"].append({
            "rel": "child",
            "href": href,
            "type": "application/json",
            "title": (
                f"Wildfire Risk to Communities v2 populated areas: "
                f"{THEMES[theme_key]['label']} ({DOMAINS[domain_key]['short']}, 30 m)"
            ),
        })
        added.append(ds)
    out = "/tmp/public-fire-stac-collection.json"
    with open(out, "w") as fh:
        json.dump(cur, fh, indent=2)
        fh.write("\n")
    print(f"  bucket collection: {before} -> {len(cur['links'])} links, added {added}")
    print(f"  assets preserved : {len(cur.get('assets', {}))}")
    print(f"  wrote {out}")
    print(f"  backup first:  rclone copyto nrp:{BUCKET}/stac-collection.json "
          f"/tmp/public-fire-stac-collection.backup.json")
    print(f"  then publish:   rclone copyto {out} nrp:{BUCKET}/stac-collection.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("datasets", nargs="*")
    ap.add_argument("--facts", default=os.path.join(HERE, "facts.json"))
    ap.add_argument("--bucket-patch", action="store_true")
    args = ap.parse_args()

    with open(args.facts) as fh:
        facts = json.load(fh)

    datasets = args.datasets or sorted(facts)
    missing = [d for d in datasets if d not in facts]
    if missing:
        print(f"FATAL: no measured facts for {missing}; populate {args.facts} first")
        return 1

    for ds in datasets:
        coll = build_collection(ds, facts)
        out = f"/tmp/{ds}-stac-collection.json"
        with open(out, "w") as fh:
            json.dump(coll, fh, indent=2)
            fh.write("\n")
        print(f"wrote {out}  ({coll['assets'][f'{ds}-hex']['table:row_count']:,} hex rows)")
        print(f"  verify:  python3 scripts/verify-stac.py --no-data {out}")
        print(f"  publish: rclone copyto {out} nrp:{BUCKET}/{ds}/stac-collection.json")

    if args.bucket_patch:
        patch_bucket(datasets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
