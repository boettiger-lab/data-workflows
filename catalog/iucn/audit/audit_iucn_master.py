#!/usr/bin/env python3
"""
Pull the full IUCN Red List master list via the v4 API, then diff against
our coverage of `minio:public-iucn/` (from `iucn-coverage-species.parquet`).

Strategy:
  1. GET /api/v4/comprehensive_groups → all 51 groups (high + comp).
  2. For each group, page through /api/v4/comprehensive_groups/{name}?page=N
     collecting one record per assessment. Group name is kept as a coarse
     class proxy. We dedup at the end on (sis_taxon_id, latest=true) to keep
     only the current assessment.
  3. Diff against the local features parquet from the iucn-audit pipeline.

API key is read from env var IUCN_API_KEY (provided via the k8s secret
`iucn-api-key`). The key is never logged or written to disk.

Outputs (under $OUT_ROOT):
  iucn-master-assessments.parquet  — every (group × assessment) row IUCN returned
  iucn-master-species.parquet      — one row per unique sis_taxon_id (latest)
  iucn-have.csv                    — IUCN-master species we DO have on MinIO
  iucn-missing.csv                 — IUCN-master species we DO NOT have
  iucn-extras.csv                  — sis_taxon_id in our holdings, NOT in IUCN master
                                     (should be near-zero; non-zero flags renaming/sis-merges)
  iucn-coverage-summary.csv        — per-group: total / have / missing counts
"""
from __future__ import annotations

import os
import sys
import time
import json
from pathlib import Path

import requests
import polars as pl


API_BASE = os.environ.get("IUCN_API_BASE", "https://api.iucnredlist.org/api/v4")
API_KEY = os.environ.get("IUCN_API_KEY") or ""
PER_REQUEST_DELAY = float(os.environ.get("IUCN_REQUEST_DELAY", "0.2"))
PAGE_TIMEOUT = float(os.environ.get("IUCN_PAGE_TIMEOUT", "60"))
MAX_RETRIES = int(os.environ.get("IUCN_MAX_RETRIES", "5"))
FEATURES = Path(os.environ.get("FEATURES", "/scratch/iucn-audit/output/iucn-coverage-species.parquet"))
OUT_ROOT = Path(os.environ.get("OUT_ROOT", "/scratch/iucn-audit/output"))
CACHE_DIR = Path(os.environ.get("CACHE_DIR", "/scratch/iucn-audit/master-cache"))


def get(path: str) -> dict:
    """GET an API path with retries + backoff. Never logs the key."""
    if not API_KEY:
        raise RuntimeError("IUCN_API_KEY env var is empty")
    url = f"{API_BASE}{path}"
    headers = {"Authorization": API_KEY, "Accept": "application/json"}
    delay = 1.0
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, headers=headers, timeout=PAGE_TIMEOUT)
            if r.status_code == 429:  # rate-limited
                print(f"  429 on {path}; sleeping {delay:.1f}s", file=sys.stderr)
                time.sleep(delay)
                delay *= 2
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            print(f"  attempt {attempt + 1} failed for {path}: {e}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"giving up on {path}: {last_err}")


def fetch_groups() -> list[dict]:
    return get("/comprehensive_groups")["comprehensive_group"]


def fetch_group(name: str) -> list[dict]:
    """Page through every assessment in a comprehensive group."""
    cache = CACHE_DIR / f"{name}.json"
    if cache.exists():
        print(f"[cache] {name}")
        return json.loads(cache.read_text())
    rows: list[dict] = []
    page = 1
    while True:
        data = get(f"/comprehensive_groups/{name}?page={page}")
        page_rows = data.get("assessments", [])
        if not page_rows:
            break
        for a in page_rows:
            a["_group"] = name
            rows.append(a)
        print(f"  {name} page {page}: +{len(page_rows)} (total {len(rows)})")
        page += 1
        time.sleep(PER_REQUEST_DELAY)
    cache.write_text(json.dumps(rows))
    return rows


def flatten_scopes(rec: dict) -> str:
    return ",".join(s.get("code", "") for s in rec.get("scopes", []) or [])


def to_df(rows: list[dict]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame([
        {
            "sis_taxon_id": r.get("sis_taxon_id"),
            "taxon_scientific_name": r.get("taxon_scientific_name"),
            "red_list_category_code": r.get("red_list_category_code"),
            "assessment_id": r.get("assessment_id"),
            "year_published": r.get("year_published"),
            "latest": r.get("latest"),
            "possibly_extinct": r.get("possibly_extinct"),
            "possibly_extinct_in_the_wild": r.get("possibly_extinct_in_the_wild"),
            "scope_codes": flatten_scopes(r),
            "url": r.get("url"),
            "iucn_group": r.get("_group"),
        }
        for r in rows
    ])


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print("== fetching comprehensive_groups list")
    groups = fetch_groups()
    print(f"   {len(groups)} groups")
    high_groups = [g for g in groups if g.get("high")]
    print(f"   {len(high_groups)} high-level groups (preferred for enumeration)")

    # Walk every high-level group. Comprehensive (high:false, comp:true) subgroups
    # are subsets of these; we'd just dedup them later anyway.
    all_rows: list[dict] = []
    for g in high_groups:
        name = g["name"]
        try:
            rows = fetch_group(name)
            all_rows.extend(rows)
            print(f"   {name}: {len(rows)} assessments")
        except Exception as e:
            print(f"   {name}: FAILED ({e})", file=sys.stderr)

    df = to_df(all_rows)
    print(f"== fetched {df.height} total (group × assessment) rows")
    df.write_parquet(OUT_ROOT / "iucn-master-assessments.parquet")

    # Keep latest assessment per sis_taxon_id (a species can appear in
    # multiple groups when a high-level group contains a comp subgroup).
    if df.height:
        latest = (
            df.filter(pl.col("latest") == True)  # noqa: E712 — polars filter
            .sort(["sis_taxon_id", "iucn_group"])
            .group_by("sis_taxon_id")
            .agg(
                pl.col("taxon_scientific_name").first(),
                pl.col("red_list_category_code").first(),
                pl.col("year_published").first(),
                pl.col("assessment_id").first(),
                pl.col("url").first(),
                # implode → list[str], then join. .unique() on a group-by'd
                # series already yields a Series; we need an explicit list dtype
                # before .list.join.
                pl.col("iucn_group").unique().sort().implode().alias("iucn_groups"),
            )
            .with_columns(pl.col("iucn_groups").list.join(",").alias("iucn_groups"))
        )
    else:
        latest = pl.DataFrame()
    print(f"== unique species (latest assessment): {latest.height}")
    latest.write_parquet(OUT_ROOT / "iucn-master-species.parquet")

    # ---------- DIFF against our holdings ----------
    if not FEATURES.exists():
        print(f"!! features parquet missing: {FEATURES}; skipping diff", file=sys.stderr)
        return 0
    print(f"== reading our holdings: {FEATURES}")
    ours = pl.read_parquet(FEATURES)
    print(f"   {ours.height} unique (id_no, sci_name)")

    ours_ids = (
        ours.select(pl.col("id_no").cast(pl.Int64).alias("sis_taxon_id"))
        .drop_nulls()
        .unique()
    )

    # BOTW (BirdLife of the World) ships as a GeoPackage inside a zip.
    # The wrapper job unzips it to disk first; SQLite-backed GPKG reads
    # through /vsizip are too slow to be practical.
    botw_path = os.environ.get("BOTW_GPKG")
    if botw_path and Path(botw_path).exists():
        print(f"== reading BOTW birds: {botw_path}")
        import pyogrio
        botw = pyogrio.read_dataframe(botw_path, layer="all_species", read_geometry=False)
        botw_ids = (
            pl.from_pandas(botw[["sisid", "sci_name"]])
            .rename({"sisid": "sis_taxon_id"})
            .with_columns(pl.col("sis_taxon_id").cast(pl.Int64))
            .drop_nulls(subset=["sis_taxon_id"])
            .unique(subset=["sis_taxon_id"])
        )
        print(f"   BOTW unique sisid: {botw_ids.height}")
        ours_ids = ours_ids.join(botw_ids.select("sis_taxon_id"), on="sis_taxon_id", how="full", coalesce=True).unique()
        # Also enrich `ours` so the extras CSV has the bird names too
        ours = pl.concat([
            ours,
            botw_ids.rename({"sis_taxon_id": "id_no"})
                    .with_columns(pl.lit(["BOTW_2025.gpkg"]).alias("source_files")),
        ], how="diagonal_relaxed")
        print(f"   ours_ids after BOTW union: {ours_ids.height}")

    master_ids = latest.select(pl.col("sis_taxon_id").cast(pl.Int64)).unique()

    have = master_ids.join(ours_ids, on="sis_taxon_id", how="inner")
    missing = master_ids.join(ours_ids, on="sis_taxon_id", how="anti")
    extras = ours_ids.join(master_ids, on="sis_taxon_id", how="anti")
    print(f"== have:    {have.height}")
    print(f"== missing: {missing.height}")
    print(f"== extras:  {extras.height}  (in our holdings, not in IUCN master)")

    # Decorate diffs with sci_name + category + iucn_group
    have_full = have.join(latest, on="sis_taxon_id", how="left")
    missing_full = missing.join(latest, on="sis_taxon_id", how="left")
    have_full.write_csv(OUT_ROOT / "iucn-have.csv")
    missing_full.write_csv(OUT_ROOT / "iucn-missing.csv")
    extras.join(
        ours.with_columns(pl.col("id_no").cast(pl.Int64).alias("sis_taxon_id")),
        on="sis_taxon_id", how="left",
    ).select(["sis_taxon_id", "sci_name", "source_files"]) \
     .with_columns(pl.col("source_files").list.join(",")) \
     .write_csv(OUT_ROOT / "iucn-extras.csv")

    # Per-group summary
    have_per_group = (
        have_full.with_columns(pl.col("iucn_groups").str.split(","))
        .explode("iucn_groups").rename({"iucn_groups": "iucn_group"})
        .group_by("iucn_group").agg(pl.len().alias("have"))
    )
    miss_per_group = (
        missing_full.with_columns(pl.col("iucn_groups").str.split(","))
        .explode("iucn_groups").rename({"iucn_groups": "iucn_group"})
        .group_by("iucn_group").agg(pl.len().alias("missing"))
    )
    summary = have_per_group.join(miss_per_group, on="iucn_group", how="full", coalesce=True) \
        .fill_null(0) \
        .with_columns((pl.col("have") + pl.col("missing")).alias("total"),
                      (pl.col("have") / (pl.col("have") + pl.col("missing")) * 100)
                      .round(1).alias("pct_have")) \
        .sort("total", descending=True)
    summary.write_csv(OUT_ROOT / "iucn-coverage-summary.csv")
    print()
    print("== per-group coverage summary ==")
    with pl.Config(tbl_rows=60, tbl_width_chars=200, fmt_str_lengths=80):
        print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
