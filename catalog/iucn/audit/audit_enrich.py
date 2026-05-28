#!/usr/bin/env python3
"""
Enrich the IUCN coverage features parquet with GBIF backbone taxonomy.

Reads:
  $FEATURES        — iucn-audit-features.parquet (output of audit_iucn.py)
  $GBIF_TAXA       — nrp:public-gbif/taxa.parquet (GBIF backbone, ~8M rows)

Writes (under $OUT_ROOT):
  iucn-coverage-species.parquet     — per-species, all sources + GBIF taxonomy
  iucn-coverage-by-class.csv        — per kingdom/class: species count, file list
  iucn-coverage-by-order.csv        — per kingdom/class/order: species count
  iucn-coverage-by-family.csv       — per kingdom/class/order/family: species count
  iucn-coverage-unmatched.csv       — IUCN sci_names not found in GBIF

Match strategy (case-insensitive):
  1. `sci_name` == GBIF `verbatimscientificname` (exact)
  2. fallback: `sci_name` == GBIF `species` (binomial form)
  3. fallback: first two words of `sci_name` == GBIF `species` (drop subspecies/var.)
GBIF rows have many duplicates per name (different taxonomic interpretations).
We pick the highest-`n` row per matched name to favour the GBIF-preferred ID.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import polars as pl

FEATURES = Path(os.environ.get("FEATURES", "/scratch/iucn-audit/output/iucn-audit-features.parquet"))
GBIF_TAXA = os.environ.get("GBIF_TAXA", "s3://public-gbif/taxa.parquet")
OUT_ROOT = Path(os.environ.get("OUT_ROOT", "/scratch/iucn-audit/output"))


def norm(col: str) -> pl.Expr:
    return (pl.col(col).cast(pl.Utf8).str.strip_chars().str.to_lowercase()).alias(col + "_norm")


def first_two_words(col: str) -> pl.Expr:
    return (
        pl.col(col)
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.to_lowercase()
        .str.split(" ")
        .list.slice(0, 2)
        .list.join(" ")
        .alias(col + "_binomial")
    )


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    print(f"== reading features parquet: {FEATURES}")
    feats = pl.read_parquet(FEATURES)
    print(f"   {feats.height} rows, {feats.width} cols")

    # Collapse to one row per (id_no, sci_name) with the list of source files.
    if "id_no" not in feats.columns:
        print("FATAL: id_no column missing", file=sys.stderr)
        return 1
    species = (
        feats.lazy()
        .filter(pl.col("id_no").is_not_null())
        .group_by(["id_no", "sci_name"])
        .agg(
            pl.col("source_file").unique().sort().alias("source_files"),
            # Capture any pre-existing taxonomy columns from the pre-packaged zips
            *[pl.col(c).drop_nulls().first().alias(c + "_iucn") for c in
              ["kingdom", "phylum", "class", "order_", "family", "genus"]
              if c in feats.columns],
        )
        .with_columns(
            pl.col("source_files").list.len().alias("n_source_files"),
        )
        .collect()
    )
    print(f"   {species.height} unique (id_no, sci_name)")

    # Prep normalized join keys.
    species = species.with_columns(
        pl.col("sci_name").cast(pl.Utf8).str.strip_chars().str.to_lowercase().alias("sci_lc"),
        pl.col("sci_name").cast(pl.Utf8).str.strip_chars().str.to_lowercase()
            .str.split(" ").list.slice(0, 2).list.join(" ").alias("sci_binomial"),
        # genus = first whitespace-separated word
        pl.col("sci_name").cast(pl.Utf8).str.strip_chars().str.to_lowercase()
            .str.split(" ").list.first().alias("sci_genus"),
    )

    print(f"== reading GBIF backbone: {GBIF_TAXA}")
    cols = ["kingdom", "phylum", "class", "order", "family", "genus", "species",
            "scientificname", "verbatimscientificname", "n"]
    gbif = pl.scan_parquet(GBIF_TAXA, storage_options={
        "aws_endpoint_url": "https://s3-west.nrp-nautilus.io",
        "aws_region": "us-west-2",
        "aws_skip_signature": "true",
    }).select(cols)

    # Build two normalized lookup tables (verbatim, species) — pick best (largest n) per key.
    print("== preparing GBIF lookup tables")
    g_verbatim = (
        gbif.filter(pl.col("verbatimscientificname").is_not_null())
        .with_columns(pl.col("verbatimscientificname").cast(pl.Utf8).str.strip_chars().str.to_lowercase().alias("k"))
        .sort("n", descending=True, nulls_last=True)
        .unique(subset=["k"], keep="first")
        .select(["k", "kingdom", "phylum", "class", "order", "family", "genus", "species", "n"])
        .collect()
    )
    print(f"   verbatim lookup: {g_verbatim.height}")

    g_species = (
        gbif.filter(pl.col("species").is_not_null())
        .with_columns(pl.col("species").cast(pl.Utf8).str.strip_chars().str.to_lowercase().alias("k"))
        .sort("n", descending=True, nulls_last=True)
        .unique(subset=["k"], keep="first")
        .select(["k", "kingdom", "phylum", "class", "order", "family", "genus", "species", "n"])
        .collect()
    )
    print(f"   species lookup:  {g_species.height}")

    # Genus-level lookup — picks the most-occurrences row per genus to disambiguate
    # homonyms. Acceptable for class/order/family resolution; do NOT propagate the
    # GBIF `species` column from here.
    g_genus = (
        gbif.filter(pl.col("genus").is_not_null() & pl.col("class").is_not_null())
        .with_columns(pl.col("genus").cast(pl.Utf8).str.strip_chars().str.to_lowercase().alias("k"))
        .sort("n", descending=True, nulls_last=True)
        .unique(subset=["k"], keep="first")
        .select(["k", "kingdom", "phylum", "class", "order", "family", "genus"])
        .collect()
    )
    print(f"   genus lookup:    {g_genus.height}")

    # Join: first try verbatim, then species, then binomial-against-species.
    enriched = species.join(g_verbatim, left_on="sci_lc", right_on="k", how="left", suffix="_v")
    miss1 = enriched["kingdom"].is_null()
    print(f"   matched via verbatim: {(~miss1).sum()} / {enriched.height}")

    enriched = enriched.join(
        g_species.rename({c: c + "_s" for c in g_species.columns if c != "k"}),
        left_on="sci_lc", right_on="k", how="left",
    )
    enriched = enriched.with_columns(
        *[pl.coalesce([pl.col(c), pl.col(c + "_s")]).alias(c)
          for c in ["kingdom", "phylum", "class", "order", "family", "genus", "species", "n"]]
    ).drop([c + "_s" for c in ["kingdom", "phylum", "class", "order", "family", "genus", "species", "n"]])
    miss2 = enriched["kingdom"].is_null()
    print(f"   matched after species fallback: {(~miss2).sum()} / {enriched.height}")

    enriched = enriched.join(
        g_species.rename({c: c + "_b" for c in g_species.columns if c != "k"}),
        left_on="sci_binomial", right_on="k", how="left",
    )
    enriched = enriched.with_columns(
        *[pl.coalesce([pl.col(c), pl.col(c + "_b")]).alias(c)
          for c in ["kingdom", "phylum", "class", "order", "family", "genus", "species", "n"]]
    ).drop([c + "_b" for c in ["kingdom", "phylum", "class", "order", "family", "genus", "species", "n"]])
    miss3 = enriched["class"].is_null()
    print(f"   class set after binomial fallback: {(~miss3).sum()} / {enriched.height}")

    # Genus fallback DISABLED — introduced homonym false positives (fish genus
    # names matched plant/insect homonyms with higher occurrence counts).

    # Track match confidence so the caller can filter if needed.
    enriched = enriched.with_columns(
        pl.when(pl.col("class").is_not_null()).then(pl.lit("gbif_exact"))
          .otherwise(pl.lit("unmatched"))
          .alias("match_confidence")
    )

    # Pick best taxonomy: prefer IUCN-derived columns (more authoritative for IUCN context),
    # fall back to GBIF. Normalize case to upper so we don't double-count
    # Mammalia / MAMMALIA across rows that came from different sources.
    final_cols = []
    for src, dst in [("kingdom", "kingdom"), ("phylum", "phylum"), ("class", "class"),
                     ("order_", "order"), ("family", "family"), ("genus", "genus")]:
        iucn_col = src + "_iucn"
        if iucn_col in enriched.columns:
            picked = pl.coalesce([pl.col(iucn_col), pl.col(dst)])
        else:
            picked = pl.col(dst)
        enriched = enriched.with_columns(picked.str.to_uppercase().alias("tx_" + dst))
        final_cols.append("tx_" + dst)

    # File-context fallback: for source files where ≥ 70 % of matched species
    # agree on a single class, propagate that class (with order/family/etc
    # left null) to the file's unmatched species. Mark them with a distinct
    # match_confidence so downstream queries can filter.
    file_modal = (
        enriched.filter(pl.col("tx_class").is_not_null())
        .explode("source_files")
        .group_by("source_files")
        .agg(
            pl.col("tx_kingdom").mode().first().alias("modal_kingdom"),
            pl.col("tx_phylum").mode().first().alias("modal_phylum"),
            pl.col("tx_class").mode().first().alias("modal_class"),
            pl.col("tx_class").count().alias("n_matched"),
            (pl.col("tx_class") == pl.col("tx_class").mode().first()).mean().alias("modal_fraction"),
        )
        .filter(pl.col("modal_fraction") >= 0.70)
        .select(["source_files", "modal_kingdom", "modal_phylum", "modal_class",
                 "n_matched", "modal_fraction"])
    )
    print(f"== file-context modal table for {file_modal.height} files (≥70% agreement)")

    # For unmatched species, look up their (single) source_files entry against
    # the modal table. If exactly one source file and that file qualifies,
    # fill tx_kingdom/tx_phylum/tx_class from the modal.
    enriched = enriched.with_columns(
        pl.col("source_files").list.first().alias("first_source"),
        pl.col("source_files").list.len().alias("n_source_files_unwrapped"),
    )
    enriched = enriched.join(
        file_modal, left_on="first_source", right_on="source_files", how="left"
    )
    fill_mask = pl.col("tx_class").is_null() & pl.col("modal_class").is_not_null() \
                & (pl.col("n_source_files_unwrapped") == 1)
    enriched = enriched.with_columns(
        pl.when(fill_mask).then(pl.col("modal_kingdom"))
          .otherwise(pl.col("tx_kingdom")).alias("tx_kingdom"),
        pl.when(fill_mask).then(pl.col("modal_phylum"))
          .otherwise(pl.col("tx_phylum")).alias("tx_phylum"),
        pl.when(fill_mask).then(pl.col("modal_class"))
          .otherwise(pl.col("tx_class")).alias("tx_class"),
        pl.when(fill_mask).then(pl.lit("file_context"))
          .otherwise(pl.col("match_confidence")).alias("match_confidence"),
    ).drop(["modal_kingdom", "modal_phylum", "modal_class", "n_matched", "modal_fraction",
            "first_source", "n_source_files_unwrapped"])
    filled = (enriched["match_confidence"] == "file_context").sum()
    print(f"   file-context filled: {filled} previously-unmatched species")

    enriched.write_parquet(OUT_ROOT / "iucn-coverage-species.parquet")
    print(f"== wrote {OUT_ROOT / 'iucn-coverage-species.parquet'} ({enriched.height} rows)")

    # Aggregates
    matched = enriched.filter(pl.col("tx_class").is_not_null())
    unmatched = enriched.filter(pl.col("tx_class").is_null())

    print(f"== matched (have class/order/family): {matched.height}")
    print(f"== unmatched: {unmatched.height}")

    by_class = (
        matched.group_by(["tx_kingdom", "tx_class"])
        .agg(
            pl.col("id_no").n_unique().alias("n_species"),
            pl.col("source_files").explode().unique().sort().alias("source_files"),
        )
        .with_columns(pl.col("source_files").list.join(",").alias("source_files"))
        .sort("n_species", descending=True)
    )
    by_class.write_csv(OUT_ROOT / "iucn-coverage-by-class.csv")
    print(f"   by_class rows: {by_class.height}")

    by_order = (
        matched.group_by(["tx_kingdom", "tx_class", "tx_order"])
        .agg(pl.col("id_no").n_unique().alias("n_species"))
        .sort(["tx_kingdom", "tx_class", "n_species"], descending=[False, False, True])
    )
    by_order.write_csv(OUT_ROOT / "iucn-coverage-by-order.csv")

    by_family = (
        matched.group_by(["tx_kingdom", "tx_class", "tx_order", "tx_family"])
        .agg(pl.col("id_no").n_unique().alias("n_species"))
        .sort(["tx_kingdom", "tx_class", "tx_order", "n_species"],
              descending=[False, False, False, True])
    )
    by_family.write_csv(OUT_ROOT / "iucn-coverage-by-family.csv")

    unmatched.select(["id_no", "sci_name", "source_files"]).with_columns(
        pl.col("source_files").list.join(",")
    ).write_csv(OUT_ROOT / "iucn-coverage-unmatched.csv")

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
