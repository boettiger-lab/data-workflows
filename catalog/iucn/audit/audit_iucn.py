#!/usr/bin/env python3
"""
IUCN raw-data coverage audit.

Reads every shapefile (loose + zipped) and GDB under DATA_ROOT, extracts the
attribute table (no geometry), and writes:

  iucn-audit-features.parquet  — one row per feature with id_no, sci_name,
                                  presence/origin/seasonal, and whatever
                                  taxonomy columns the source provides.
                                  Tagged with source_file + source_layer.
  iucn-audit-summary.csv       — per-(file, layer) feature/species counts,
                                  DBF_DATE_LAST_UPDATE, first/middle/last
                                  sci_name samples for taxon ID at a glance.
  iucn-audit-overlaps.csv      — id_no values that appear in more than one
                                  source file (the dedup matrix).
  iucn-audit-taxonomy.csv      — id_no → kingdom/class/order/family derived
                                  from the pre-packaged sources (which carry
                                  taxonomy columns) so that advanced-search
                                  shapefiles (which carry only id_no +
                                  sci_name) can be looked up.

Run via catalog/iucn/audit/k8s/iucn-audit-job.yaml; the manifest does
rclone sync minio:public-iucn → PVC, then invokes this script.
"""

from __future__ import annotations

import os
import sys
import traceback
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pyogrio

DATA_ROOT = Path(os.environ.get("DATA_ROOT", "/scratch/iucn-audit/data"))
OUT_ROOT = Path(os.environ.get("OUT_ROOT", "/scratch/iucn-audit/output"))

# Columns we keep (lowercased). All optional — sources vary.
ATTR_COLS = [
    "id_no",
    "sci_name",
    "presence",
    "origin",
    "seasonal",
    "category",
    "kingdom",
    "phylum",
    "class",
    "order_",
    "family",
    "genus",
    "marine",
    "terrestria",
    "freshwater",
    "yrcompiled",
]


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.lower() for c in df.columns]
    # Some exports use "order" without underscore; standardize to order_
    if "order" in df.columns and "order_" not in df.columns:
        df = df.rename(columns={"order": "order_"})
    keep = [c for c in ATTR_COLS if c in df.columns]
    return df[keep].copy()


def list_sources(root: Path) -> list[tuple[str, Path]]:
    sources: list[tuple[str, Path]] = []
    for shp in sorted(root.rglob("*.shp")):
        sources.append(("shapefile", shp))
    for z in sorted(root.rglob("*.zip")):
        sources.append(("zip", z))
    for gdb in sorted(root.rglob("*.gdb")):
        sources.append(("gdb", gdb))
    return sources


def read_one(kind: str, path: Path) -> list[tuple[dict, pd.DataFrame]]:
    """Read one source. Returns [(meta, df)] — one per layer for zips/gdbs."""
    out = []
    if kind == "shapefile":
        ds = str(path)
        layers = [(path.stem, None)]
    elif kind == "zip":
        ds = f"/vsizip/{path}"
        try:
            layers = pyogrio.list_layers(ds).tolist()
        except Exception as e:
            print(f"  list_layers failed: {e}", file=sys.stderr)
            return []
    elif kind == "gdb":
        ds = str(path)
        layers = pyogrio.list_layers(ds).tolist()
    else:
        return []

    for layer_name, _geom in layers:
        try:
            info = pyogrio.read_info(ds, layer=layer_name)
            df = pyogrio.read_dataframe(ds, layer=layer_name, read_geometry=False)
            df = normalize(df)
            df["source_file"] = path.name
            df["source_layer"] = layer_name
            df["source_path"] = str(path.relative_to(DATA_ROOT))
            out.append((info, df))
        except Exception as e:
            print(f"  read failed for layer {layer_name}: {e}", file=sys.stderr)
            traceback.print_exc()
    return out


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    if not DATA_ROOT.exists():
        print(f"DATA_ROOT does not exist: {DATA_ROOT}", file=sys.stderr)
        return 1

    sources = list_sources(DATA_ROOT)
    print(f"Found {len(sources)} sources under {DATA_ROOT}")

    all_dfs: list[pd.DataFrame] = []
    summary_rows: list[dict] = []

    for kind, path in sources:
        print(f"[{kind}] {path}")
        for info, df in read_one(kind, path):
            all_dfs.append(df)
            sci = df.get("sci_name")
            n = len(df)
            mid = n // 2
            summary_rows.append(
                {
                    "source_path": df["source_path"].iloc[0],
                    "source_file": df["source_file"].iloc[0],
                    "source_layer": df["source_layer"].iloc[0],
                    "feature_count": n,
                    "unique_species": int(sci.nunique()) if sci is not None else 0,
                    "dbf_date": (info.get("layer_metadata") or {}).get(
                        "DBF_DATE_LAST_UPDATE"
                    ),
                    "has_taxonomy_cols": "class" in df.columns or "kingdom" in df.columns,
                    "sample_first": sci.iloc[0] if sci is not None and n else None,
                    "sample_mid": sci.iloc[mid] if sci is not None and n else None,
                    "sample_last": sci.iloc[-1] if sci is not None and n else None,
                }
            )

    if not all_dfs:
        print("No sources read.", file=sys.stderr)
        return 1

    # Features parquet — union with NaN-filled missing columns
    features = pd.concat(all_dfs, ignore_index=True, sort=False)
    features.to_parquet(OUT_ROOT / "iucn-audit-features.parquet", index=False)

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT_ROOT / "iucn-audit-summary.csv", index=False)

    # Overlap matrix on id_no
    if "id_no" in features.columns:
        overlaps = (
            features.dropna(subset=["id_no"])
            .groupby("id_no")["source_file"]
            .agg(lambda s: sorted(set(s)))
            .reset_index()
        )
        overlaps["n_files"] = overlaps["source_file"].map(len)
        overlaps = overlaps[overlaps["n_files"] > 1].copy()
        overlaps["source_files"] = overlaps["source_file"].map(lambda x: ",".join(x))
        overlaps[["id_no", "n_files", "source_files"]].to_csv(
            OUT_ROOT / "iucn-audit-overlaps.csv", index=False
        )

    # Taxonomy lookup — best available row per id_no for files that carry
    # kingdom/class/order_/family columns. Lets us back-fill the
    # advanced-search shapefiles that only carry id_no + sci_name.
    tax_cols = [c for c in ["kingdom", "phylum", "class", "order_", "family", "genus"]
                if c in features.columns]
    if tax_cols and "id_no" in features.columns:
        tax = (
            features.dropna(subset=["id_no"])
            .dropna(subset=tax_cols, how="all")
            .drop_duplicates(subset=["id_no"])
            [["id_no", "sci_name", *tax_cols]]
        )
        tax.to_csv(OUT_ROOT / "iucn-audit-taxonomy.csv", index=False)
        print(f"Taxonomy lookup: {len(tax)} id_no rows with at least one taxonomy column")

    print(f"Done. Outputs in {OUT_ROOT}")
    print(f"  features: {len(features)} rows across {len(summary)} layers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
