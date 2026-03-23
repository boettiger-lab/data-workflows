#!/usr/bin/env python3
"""
S3 bucket audit for boettiger-lab data-workflows.

Discovers all public-* buckets and checks each for the standard cloud-native
geospatial output stack: GeoParquet, PMTiles, H3 hex partitions, STAC, README.

Outputs:
  audit-report.json  — machine-readable full audit
  audit-report.md    — human-readable markdown table

Usage (local, reads from external S3 endpoint):
  AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... python audit.py

Usage (k8s job):
  See catalog/audit/k8s/s3-audit-job.yaml
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

import boto3

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

S3_ENDPOINT = os.environ.get(
    "S3_ENDPOINT", "https://rook-ceph-rgw-nautiluss3.rook"
)
MAIN_CATALOG_BUCKET = "public-data"
MAIN_CATALOG_KEY = "stac/catalog.json"

# Buckets that exist but are pipeline infrastructure, not published datasets.
# They are listed separately in the audit report and skipped for dataset analysis.
INFRASTRUCTURE_BUCKETS = {
    "public-grids",   # H3 reference grids used internally by cng-datasets raster workflow
    "public-data",    # Houses the top-level STAC catalog only
    "public-output",  # Analysis outputs, not published datasets
    "public-test",    # Test bucket
}

# Directory names that hold intermediate/internal data, never dataset roots.
# A key component matching any of these means we skip or handle specially.
INTERNAL_DIRS = {"hex", "chunks", "raw", "temp_versions", "Preprocessing", "lookup", "stac"}

# Spatial file extensions: presence → bucket is "spatial"
SPATIAL_EXTS = {".parquet", ".pmtiles", ".tif", ".tiff", ".gpkg", ".gdb", ".geojson"}


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------

def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )


def list_public_buckets(s3):
    """Return (dataset_buckets, infra_buckets) — both matching public-* convention."""
    resp = s3.list_buckets()
    all_public = sorted(b["Name"] for b in resp["Buckets"] if b["Name"].startswith("public-"))
    infra = [b for b in all_public if b in INFRASTRUCTURE_BUCKETS]
    datasets = [b for b in all_public if b not in INFRASTRUCTURE_BUCKETS]
    return datasets, infra


def list_all_objects(s3, bucket):
    """Paginate through all objects in a bucket, returning a list of keys."""
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def fetch_main_catalog(s3):
    """Return the set of href strings in the main catalog's child links."""
    try:
        obj = s3.get_object(Bucket=MAIN_CATALOG_BUCKET, Key=MAIN_CATALOG_KEY)
        catalog = json.loads(obj["Body"].read())
        return {lk["href"] for lk in catalog.get("links", []) if lk.get("rel") == "child"}
    except Exception as e:
        print(f"Warning: could not fetch main catalog: {e}", file=sys.stderr)
        return set()


# ---------------------------------------------------------------------------
# Key classification
# ---------------------------------------------------------------------------

def classify_key(key):
    """
    Parse an S3 object key and return (dataset_path, attribute).

    dataset_path: the logical dataset identifier (relative path without
                  extension), or None for bucket-level / skipped keys.

    attribute: one of:
      'parquet'       - GeoParquet file (the dataset)
      'pmtiles'       - PMTiles file
      'hex'           - H3 hex partition (any h0=* key)
      'cog'           - Cloud-Optimized GeoTIFF (ends with -cog.tif/tiff)
      'stac'          - stac-collection.json at dataset level
      'readme'        - README.md at dataset level
      'bucket_stac'   - root stac-collection.json
      'bucket_readme' - root README.md
      'raw'           - anything under raw/
      'skip'          - pseudo-directory artifact or other internal path
      'other'         - doesn't match any tracked pattern
    """
    parts = key.split("/")

    # ---- Pseudo-directory artifacts (e.g. stac-collection.json/foo.json) ----
    # These happen when rclone copy is run incorrectly; skip them entirely.
    if any(p == "stac-collection.json" for p in parts[:-1]):
        return None, "skip"

    # ---- raw/ ----------------------------------------------------------------
    if parts[0] == "raw":
        return None, "raw"

    # ---- H3 hex partitions ---------------------------------------------------
    # Pattern: <dataset-path>/hex/h0=<cell>/data_0.parquet
    if "hex" in parts:
        hex_idx = parts.index("hex")
        # Confirm it's a real hex partition (next component starts with h0=)
        if hex_idx + 1 < len(parts) and parts[hex_idx + 1].startswith("h0="):
            dataset_prefix = "/".join(parts[:hex_idx]) or "__root__"
            return dataset_prefix, "hex"

    # ---- Skip other internal directories ------------------------------------
    for i, part in enumerate(parts[:-1]):
        if part in INTERNAL_DIRS:
            return None, "skip"

    name = parts[-1]
    parent = "/".join(parts[:-1])  # empty string for root-level keys

    # ---- Root-level special files -------------------------------------------
    if not parent:
        if name == "stac-collection.json":
            return None, "bucket_stac"
        if name == "README.md":
            return None, "bucket_readme"

    # ---- stac-collection.json and README.md at dataset level ----------------
    if name == "stac-collection.json":
        return parent, "stac"
    if name == "README.md":
        return parent, "readme"

    # ---- GeoParquet ----------------------------------------------------------
    # Exclude hex partition files (data_0.parquet inside h0= directories).
    # We already caught those above via the hex check, but guard here too.
    if name.endswith(".parquet") and name != "data_0.parquet":
        stem = name[: -len(".parquet")]
        dataset = f"{parent}/{stem}" if parent else stem
        return dataset, "parquet"

    # ---- PMTiles -------------------------------------------------------------
    if name.endswith(".pmtiles"):
        stem = name[: -len(".pmtiles")]
        dataset = f"{parent}/{stem}" if parent else stem
        return dataset, "pmtiles"

    # ---- Cloud-Optimized GeoTIFF --------------------------------------------
    # Identify COGs by the -cog.tif / -cog.tiff suffix convention.
    # Note: COG names often differ from the logical dataset name
    # (e.g. "sagebrush-cog.tif" belongs to dataset "sagebrush-design").
    # We record the COG path and match it to datasets separately.
    if name.endswith(("-cog.tif", "-cog.tiff")):
        ext = ".tiff" if name.endswith(".tiff") else ".tif"
        stem = name[: -len(ext)]
        dataset = f"{parent}/{stem}" if parent else stem
        return dataset, "cog"

    # ---- Anything else -------------------------------------------------------
    # Check if it's a spatial file (to flag bucket as spatial even without a
    # canonical dataset entry).
    _, ext = os.path.splitext(name)
    if ext.lower() in SPATIAL_EXTS:
        return None, "other_spatial"

    return None, "other"


# ---------------------------------------------------------------------------
# Bucket analysis
# ---------------------------------------------------------------------------

def analyze_bucket(s3, bucket, catalog_links):
    """
    Scan one bucket and return a structured audit dict.
    """
    log = lambda msg: print(f"  {msg}", file=sys.stderr)

    try:
        keys = list_all_objects(s3, bucket)
    except Exception as e:
        return {"bucket": bucket, "error": str(e)}

    if not keys:
        return {"bucket": bucket, "empty": True, "total_objects": 0, "datasets": []}

    # Aggregate per-dataset attributes
    datasets = defaultdict(lambda: {
        "parquet": False,
        "pmtiles": False,
        "hex": False,
        "cog": False,
        "stac": False,
        "readme": False,
    })

    # Bucket-level flags
    bucket_stac = False
    bucket_readme = False
    bucket_raw = False
    is_spatial = False

    # Collect COG paths for post-processing match
    cog_paths = {}  # dataset_path (from COG key) -> True

    for key in keys:
        dataset, attr = classify_key(key)

        if attr == "bucket_stac":
            bucket_stac = True
        elif attr == "bucket_readme":
            bucket_readme = True
        elif attr == "raw":
            bucket_raw = True
        elif attr in ("parquet", "pmtiles", "hex", "stac", "readme"):
            is_spatial = True
            if dataset:
                datasets[dataset][attr] = True
        elif attr == "cog":
            is_spatial = True
            if dataset:
                cog_paths[dataset] = True
                datasets[dataset]["cog"] = True
        elif attr == "other_spatial":
            is_spatial = True

    # COG matching: for datasets missing a COG, check if any cog_path shares
    # the same parent directory (covers "sagebrush-cog" → "sagebrush-design").
    for ds_path in list(datasets.keys()):
        if datasets[ds_path]["cog"]:
            continue
        parent = ds_path.rsplit("/", 1)[0] if "/" in ds_path else ""
        for cog_path in cog_paths:
            cog_parent = cog_path.rsplit("/", 1)[0] if "/" in cog_path else ""
            if cog_parent == parent:
                datasets[ds_path]["cog"] = True
                break

    in_catalog = any(bucket in lk for lk in catalog_links)

    dataset_list = [
        {"path": path, **attrs}
        for path, attrs in sorted(datasets.items())
    ]

    log(f"{len(dataset_list)} datasets, spatial={is_spatial}, in_catalog={in_catalog}")

    return {
        "bucket": bucket,
        "total_objects": len(keys),
        "is_spatial": is_spatial,
        "in_catalog": in_catalog,
        "bucket_stac": bucket_stac,
        "bucket_readme": bucket_readme,
        "bucket_raw": bucket_raw,
        "datasets": dataset_list,
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

T = "✅"
F = "❌"
NA = "➖"
UNK = "❓"


def _fmt(val, na=False):
    if na:
        return NA
    return T if val else F


def render_markdown(results, catalog_links, infra_buckets=None):
    lines = [
        "# S3 Bucket Audit Report",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"**Legend:** {T} Present · {F} Missing · {NA} N/A",
        "",
        "---",
        "",
        "## Bucket Summary",
        "",
        "| Bucket | Spatial? | Datasets | Bucket STAC | Bucket README | In Catalog |",
        "|--------|----------|----------|-------------|---------------|------------|",
    ]

    spatial_buckets = []
    other_buckets = []

    for r in results:
        bucket = r["bucket"]
        if r.get("error"):
            lines.append(f"| `{bucket}` | {UNK} | — | — | — | — | ⚠️ {r['error']} |")
            continue
        if r.get("empty"):
            lines.append(f"| `{bucket}` | — | 0 (empty) | {F} | {F} | {F} |")
            continue

        spatial = r.get("is_spatial", False)
        n = len(r.get("datasets", []))
        bs = _fmt(r.get("bucket_stac"))
        br = _fmt(r.get("bucket_readme"))
        ic = _fmt(r.get("in_catalog"))
        kind = "spatial" if spatial else "non-spatial"

        lines.append(f"| `{bucket}` | {kind} | {n} | {bs} | {br} | {ic} |")

        if spatial:
            spatial_buckets.append(r)
        else:
            other_buckets.append(r)

    # ---- Spatial dataset detail tables -------------------------------------
    lines += ["", "---", "", "## Spatial Dataset Detail", ""]

    for r in spatial_buckets:
        bucket = r["bucket"]
        datasets = r.get("datasets", [])
        lines += [
            f"### `{bucket}`",
            "",
            "| Dataset path | Parquet | PMTiles | Hex | COG | STAC | README |",
            "|--------------|---------|---------|-----|-----|------|--------|",
        ]
        if not datasets:
            lines.append("| *(no datasets detected)* | — | — | — | — | — | — |")
        for ds in datasets:
            p = ds["path"]
            lines.append(
                f"| `{p}` "
                f"| {_fmt(ds['parquet'])} "
                f"| {_fmt(ds['pmtiles'])} "
                f"| {_fmt(ds['hex'])} "
                f"| {_fmt(ds['cog'])} "
                f"| {_fmt(ds['stac'])} "
                f"| {_fmt(ds['readme'])} |"
            )
        lines.append("")

    # ---- Non-spatial / unknown buckets -------------------------------------
    if other_buckets:
        lines += [
            "---",
            "",
            "## Non-Spatial Buckets",
            "",
            "These buckets exist but contain no detected spatial formats "
            "(parquet, pmtiles, tif, gpkg). No action needed unless they "
            "should be converted to cloud-native formats.",
            "",
            "| Bucket | Objects | Notes |",
            "|--------|---------|-------|",
        ]
        for r in other_buckets:
            bucket = r["bucket"]
            n = r.get("total_objects", 0)
            lines.append(f"| `{bucket}` | {n} | |")
        lines.append("")

    if infra_buckets:
        infra_notes = {
            "public-grids": "H3 reference grids for cng-datasets raster workflow",
            "public-data": "Top-level STAC catalog only",
            "public-output": "Analysis outputs, not published datasets",
            "public-test": "Test bucket",
        }
        lines += [
            "---", "", "## Infrastructure Buckets", "",
            "Pipeline infrastructure excluded from dataset audit.", "",
            "| Bucket | Purpose |",
            "|--------|---------|",
        ]
        for b in infra_buckets:
            note = infra_notes.get(b, "infrastructure")
            lines.append(f"| `{b}` | {note} |")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log = lambda msg: print(msg, file=sys.stderr)

    s3 = get_s3_client()

    log("Discovering public-* buckets...")
    buckets, infra_buckets = list_public_buckets(s3)
    log(f"Found {len(buckets)} dataset buckets, {len(infra_buckets)} infrastructure buckets")

    log("Fetching main STAC catalog...")
    catalog_links = fetch_main_catalog(s3)
    log(f"Main catalog has {len(catalog_links)} child links")

    results = []
    for bucket in buckets:
        log(f"Auditing {bucket}...")
        result = analyze_bucket(s3, bucket, catalog_links)
        results.append(result)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bucket_count": len(buckets),
        "infrastructure_buckets": infra_buckets,
        "catalog_child_links": sorted(catalog_links),
        "buckets": results,
    }

    with open("audit-report.json", "w") as f:
        json.dump(report, f, indent=2)
    log("Written: audit-report.json")

    md = render_markdown(results, catalog_links, infra_buckets=infra_buckets)
    with open("audit-report.md", "w") as f:
        f.write(md)
    log("Written: audit-report.md")


if __name__ == "__main__":
    main()
