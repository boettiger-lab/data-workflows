#!/usr/bin/env python3
"""Emit STAC collections for the WRC v2 (RDS-2020-0016-2) hex + COG datasets.

Writes to /tmp only -- this repo never contains STAC JSON (AGENTS.md Hard Boundary 1).
Upload with:

    rclone copyto /tmp/<dataset>-stac-collection.json nrp:public-fire/<dataset>/stac-collection.json

Every number that describes the *ingested data* (row counts, value ranges, populated h0
partitions, footprints) is read from `facts.json`, which is populated from measured
duckdb-geo MCP results and committed alongside this script as evidence. Nothing here
invents a measurement. Object sizes and checksums are read live from S3.

    python3 gen_stac.py                # all datasets present in facts.json
    python3 gen_stac.py wrc-2-rps-conus wrc-2-rps-ak
    python3 gen_stac.py --bucket-patch # patch the public-fire bucket collection's child links
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request

S3 = "https://s3-west.nrp-nautilus.io"
BUCKET = "public-fire"
ROOT = f"{S3}/public-data/stac/catalog.json"
PARENT = f"{S3}/{BUCKET}/stac-collection.json"
HERE = os.path.dirname(os.path.abspath(__file__))

DOI = "https://doi.org/10.2737/RDS-2020-0016-2"
CATALOG_PAGE = "https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0016-2"
ACCESS_DATE = "2026-08-22"

CITATION = (
    "Scott, Joe H.; Brough, April M.; Gilbertson-Day, Julie W.; Dillon, Gregory K.; "
    "Moran, Christopher. 2024. Wildfire Risk to Communities: Spatial datasets of "
    "landscape-wide wildfire risk components for the United States, 2nd Edition. "
    "Fort Collins, CO: Forest Service Research Data Archive. "
    f"{DOI}. Accessed {ACCESS_DATE}."
)

# The source's own currency, not its publication date: the abstract states the data
# "reflect landscape conditions as of the end of 2014" (LANDFIRE 2020, version 2.2.0).
TEMPORAL = ["2014-01-01T00:00:00Z", "2014-12-31T23:59:59Z"]

# ---------------------------------------------------------------------------
# Per-theme copy. Descriptions are USER-FACING: the geo-agent quotes them nearly
# verbatim to end users, so they say what the layer is, what it measures, at what
# resolution, and the one thing needed to use it correctly. No issue numbers, no
# shouted imperatives, no bare abbreviations.
# ---------------------------------------------------------------------------
THEMES = {
    "rps": dict(
        column="rps",
        label="Risk to Potential Structures",
        webapp="Risk to Homes",
        units="unitless index",
        source_range="0 to 13.2 across the United States",
        what=(
            "Risk to Potential Structures is the expected effect of wildfire on a home at a "
            "given location: the expected change in value if a structure stood on that pixel, "
            "combining how likely fire is, how intense it would be, and how a building responds "
            "at each of six intensity classes. It is presented as Risk to Homes in the Wildfire "
            "Risk to Communities web application."
        ),
        interpretation=(
            "This is the layer that measures risk to communities, as distinct from wildfire "
            "hazard. Values are a relative index on a single national scale, so they are "
            "comparable between the continental United States and Alaska."
        ),
    ),
    "bp": dict(
        column="bp",
        label="Burn Probability",
        webapp="Wildfire Likelihood",
        units="annual probability",
        source_range="0 to 0.14 across the United States",
        what=(
            "Burn Probability is the modelled annual probability that wildfire burns a given "
            "location. It is presented as Wildfire Likelihood in the Wildfire Risk to "
            "Communities web application."
        ),
        interpretation=(
            "A value of 0.01 means a roughly 1 percent chance of burning in any given year "
            "under the modelled conditions. This describes likelihood only, and says nothing "
            "about what would be harmed."
        ),
    ),
    "cfl": dict(
        column="cfl",
        label="Conditional Flame Length",
        webapp=None,
        units="feet",
        source_range="0 to 861.7 feet across the United States",
        what=(
            "Conditional Flame Length is the mean flame length, in feet, for a fire burning in "
            "the direction of maximum spread at a given location, if a fire were to occur "
            "there. It is an average measure of wildfire intensity."
        ),
        interpretation=(
            "The value is conditional on a fire occurring, so it is not reduced by a location "
            "being unlikely to burn. Pair it with Burn Probability to reason about expected "
            "rather than conditional intensity."
        ),
    ),
    "exposure": dict(
        column="exposure",
        label="Exposure Type",
        webapp="Exposure Type",
        units="unitless, 0 to 1",
        source_range="0 to 1 across the United States",
        what=(
            "Exposure Type describes the kind of wildfire exposure a housing unit would "
            "experience at a given location. A value of 1 is direct exposure from adjacent "
            "burnable wildland vegetation. Values between 0 and 1 are indirect exposure, from "
            "sources such as embers and home-to-home ignition, with higher values meaning "
            "closer proximity to directly exposed areas. A value of 0 means non-exposed: "
            "non-burnable land cover more than 1,530 metres, about one mile, from burnable "
            "wildland vegetation."
        ),
        interpretation=(
            "This is a continuous surface, not a set of categories. The Wildfire Risk to "
            "Communities web application groups it into direct, indirect and non-exposed "
            "classes for display, but the published raster carries the underlying continuum "
            "and no class codes."
        ),
    ),
}

DOMAINS = {
    "conus": dict(
        label="continental United States",
        short="CONUS",
        src_crs="EPSG:5070 (NAD83 / Conus Albers)",
        src_size="156,335 by 101,538 pixels",
        clip_note="",
    ),
    "ak": dict(
        label="Alaska",
        short="Alaska",
        src_crs="EPSG:3338 (NAD83 / Alaska Albers)",
        src_size="124,603 by 66,861 pixels",
        clip_note=(
            " The Alaska raster is clipped to longitudes between 180 degrees west and 129 "
            "degrees west. The source grid crosses the antimeridian, and reprojecting it "
            "whole produces a raster about 360 degrees wide that is almost entirely empty. "
            "The excluded far-western Aleutian Islands contain no National Forest System "
            "land."
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
    etag = (h.get("etag") or "").strip('"')
    return {"size": int(h["content-length"]), "etag": etag}


def hex_columns(theme: dict) -> list:
    """Per-column schema for the hex asset.

    Text for a given column name must be IDENTICAL everywhere it appears in the
    collection (the renderer folds duplicates and first-seen wins), and the H3 columns
    are kept grain-neutral so they stay reusable.
    """
    return [
        {
            "name": theme["column"],
            "type": "double",
            "description": (
                f"{theme['label']} ({theme['units']}), as the area-weighted mean of the "
                f"30 metre source pixels falling in the cell. Source values span "
                f"{theme['source_range']}."
            ),
        },
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
    theme_key, domain_key = dataset.removeprefix("wrc-2-").rsplit("-", 1)
    theme, domain = THEMES[theme_key], DOMAINS[domain_key]
    f = facts[dataset]

    cog_href = f"{S3}/{BUCKET}/{dataset}-cog.tif"
    hex_href = f"{S3}/{BUCKET}/{dataset}/hex/h0=*/data_0.parquet"
    raw_href = f"{S3}/{BUCKET}/raw/wrc-2/{f['raw_name']}"

    cog = object_facts(cog_href)
    raw = object_facts(raw_href)

    webapp = (
        f" It is presented as {theme['webapp']} in the Wildfire Risk to Communities web "
        f"application."
        if theme.get("webapp") and theme["webapp"] not in theme["what"]
        else ""
    )

    description = "\n\n".join(
        [
            f"{theme['what']}{webapp}",
            theme["interpretation"],
            (
                f"Coverage is the {domain['label']} at a 30 metre source pixel size, from the "
                f"second edition of Wildfire Risk to Communities. Hexed to H3 resolution 10 "
                f"using an area-weighted mean of the source pixels in each cell, with rollup "
                f"columns at resolutions 9, 8 and 0. Resolution 10 cells are about 0.015 square "
                f"kilometres, so each cell averages roughly 17 source pixels."
                f"{domain['clip_note']}"
            ),
            (
                "Wildfire hazard and wildfire risk are different quantities and are published "
                "separately in this bucket. Wildfire Hazard Potential, in the whp-2023 "
                "collections, measures the potential for a fire that would be difficult to "
                "control given fuels, terrain and weather, and its source metadata states that "
                "it does not account for what is exposed. The Wildfire Risk to Communities "
                "layers here incorporate exposure and the susceptibility of structures. A "
                "question about risk to homes or communities should use these collections, not "
                "Wildfire Hazard Potential."
            ),
            (
                "The burn probability and fire intensity inputs were modelled at 270 metres and "
                "upsampled to the 30 metre resolution of the LANDFIRE fuel and vegetation grid, "
                "so the 30 metre grid is finer than the independent information content of "
                "those inputs. The data reflect landscape conditions as of the end of 2014, "
                "from LANDFIRE 2020 version 2.2.0, which is why the temporal extent is 2014 "
                "rather than the 2024 publication date."
            ),
            (
                f"To compare this layer against inventoried roadless areas or the "
                f"wildland-urban interface, join on h10 against "
                f"public-usfs/roadless-areas-2001 or public-wui/wui-2020, both of which are "
                f"published at H3 resolution 10 with the same rollup columns. Those two are "
                f"derived from polygons, so their per-feature attributes repeat on every cell a "
                f"feature covers and need de-duplicating by _cng_fid before being summed. This "
                f"layer is derived from a raster and has one row per cell."
            ),
            (
                f"Provenance. Source archive RDS-2020-0016-2, accessed {ACCESS_DATE} from "
                f"{CATALOG_PAGE}. The staged source raster is {f['raw_name']} at "
                f"{raw['size']:,} bytes (S3 ETag {raw['etag']}), held at "
                f"{BUCKET}/raw/wrc-2/. Source grid {domain['src_size']} in "
                f"{domain['src_crs']}, 32-bit float, no-data value -9999, reprojected to "
                f"EPSG:4326 with nearest-neighbour resampling before hexing."
            ),
        ]
    )

    hex_desc = (
        f"H3 resolution 10 hex cells carrying the area-weighted mean {theme['label'].lower()} "
        f"for each cell, with rollup columns at resolutions 9, 8 and 0. One row per cell. "
        f"Because the value is a mean rather than an amount held by each cell, there is no "
        f"meaningful catalog total: combine cells by averaging, and roll up to a coarser "
        f"resolution with an area-weighted average rather than a sum.\n\n"
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
            f"Wildfire Risk to Communities v2: {theme['label']} ({domain['short']}, 30 m)"
        ),
        "description": description,
        "license": "public-domain",
        "keywords": [
            "wildfire",
            "wildfire risk",
            "fire",
            theme["label"].lower(),
            domain["short"].lower(),
            "h3",
            "hex",
        ],
        "sci:doi": "10.2737/RDS-2020-0016-2",
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
        ],
        "assets": {
            f"{dataset}-cog": {
                "href": cog_href,
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "title": f"{theme['label']} ({domain['short']}) cloud-optimized GeoTIFF",
                "description": (
                    f"{theme['label']} reprojected to EPSG:4326 from {domain['src_crs']} with "
                    f"nearest-neighbour resampling, at the source 30 metre ground resolution. "
                    f"Nearest neighbour is used so that the no-data value is not blended into "
                    f"valid data along boundaries."
                ),
                "roles": ["data"],
                "created": f["created"],
                "file:size": cog["size"],
                "raster:bands": [
                    {
                        "name": theme["column"],
                        "data_type": "float32",
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
                "table:primary_geometry": None,
                "table:row_count": f["rows"],
                "table:columns": hex_columns(theme),
            },
        },
    }
    # table:primary_geometry has no meaning for a hex table; drop rather than emit null.
    del coll["assets"][f"{dataset}-hex"]["table:primary_geometry"]
    return coll


def patch_bucket(datasets: list) -> None:
    """Add child links for the new collections, preserving everything else.

    Fetch -> edit -> re-upload, never regenerate: the bucket collection carries fields
    this script does not model, and 15 pre-existing assets that must survive.
    """
    cur = json.loads(http_get(PARENT))
    before = len(cur.get("links", []))
    have = {l.get("href") for l in cur.get("links", []) if l.get("rel") == "child"}
    added = []
    for ds in datasets:
        href = f"{S3}/{BUCKET}/{ds}/stac-collection.json"
        if href in have:
            continue
        theme_key, domain_key = ds.removeprefix("wrc-2-").rsplit("-", 1)
        cur["links"].append(
            {
                "rel": "child",
                "href": href,
                "type": "application/json",
                "title": (
                    f"Wildfire Risk to Communities v2: {THEMES[theme_key]['label']} "
                    f"({DOMAINS[domain_key]['short']}, 30 m)"
                ),
            }
        )
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
    sys.exit(main())
