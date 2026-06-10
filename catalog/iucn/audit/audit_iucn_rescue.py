#!/usr/bin/env python3
"""
One-shot rescue: extract every species that exists in `PLANTS.zip` but in
none of the numbered advanced-search plant chunks. Writes a small
GeoParquet so the corresponding range polygons survive deletion of the
redundant pre-packaged PLANTS.zip.

Reads:
  $FEATURES        — iucn-audit-features.parquet (audit output already on PVC)
  $PLANTS_ZIP      — local path to PLANTS.zip (already synced to PVC)

Writes:
  $OUT_ROOT/plants-zip-unique-species.parquet

The wrapper k8s Job uploads that parquet to
`minio:public-iucn/raw/ranges/plants-zip-unique-species.parquet`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import polars as pl

DATA_ROOT = Path(os.environ.get("DATA_ROOT", "/scratch/iucn-audit/data"))
OUT_ROOT = Path(os.environ.get("OUT_ROOT", "/scratch/iucn-audit/output"))
FEATURES = Path(os.environ.get("FEATURES", str(OUT_ROOT / "iucn-audit-features.parquet")))
PLANTS_ZIP = Path(os.environ.get("PLANTS_ZIP", str(DATA_ROOT / "raw" / "rangemaps" / "PLANTS.zip")))
MASTER = Path(os.environ.get("MASTER", str(OUT_ROOT / "iucn-master-species.parquet")))


def main() -> int:
    if not FEATURES.exists():
        print(f"FATAL: features parquet missing: {FEATURES}", file=sys.stderr)
        return 1
    if not PLANTS_ZIP.exists():
        print(f"FATAL: PLANTS.zip missing: {PLANTS_ZIP}", file=sys.stderr)
        return 1
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    feats = pl.read_parquet(FEATURES)
    plants_ids = set(
        feats.filter(pl.col("source_file") == "PLANTS.zip")
        .filter(pl.col("id_no").is_not_null())["id_no"]
        .cast(pl.Int64)
        .unique()
    )
    # Numbered advanced-search chunks: 0data_0.shp … 20data_0.shp (21data_0 = fungi)
    advanced_ids = set(
        feats.filter(pl.col("source_file").str.contains(r"^[0-9]+data_0\.shp$"))
        .filter(pl.col("id_no").is_not_null())["id_no"]
        .cast(pl.Int64)
        .unique()
    )
    unique_ids = sorted(plants_ids - advanced_ids)
    print(f"PLANTS.zip species:                       {len(plants_ids)}")
    print(f"Numbered advanced-search chunk species:   {len(advanced_ids)}")
    print(f"Unique to PLANTS.zip (to rescue):         {len(unique_ids)}")

    if MASTER.exists():
        m = pl.read_parquet(MASTER)
        master_ids = set(m["sis_taxon_id"].cast(pl.Int64))
        in_master = [i for i in unique_ids if i in master_ids]
        print(f"   of which currently in IUCN master:     {len(in_master)}")

    if not unique_ids:
        print("No unique species to rescue — nothing to do")
        return 0

    # Push the filter down to GDAL so we don't materialize the whole layer.
    # PLANTS_PART* DBFs use uppercase ID_NO (verified earlier).
    id_list = ",".join(str(i) for i in unique_ids)
    where = f"ID_NO IN ({id_list})"

    parts = []
    for layer in ["PLANTS_PART1", "PLANTS_PART2", "PLANTS_PART3"]:
        df = gpd.read_file(str(PLANTS_ZIP), layer=layer, engine="pyogrio", where=where)
        df.columns = [c.lower() if c.lower() != "geometry" else "geometry" for c in df.columns]
        print(f"  {layer}: {len(df)} matching rows")
        parts.append(df)

    result = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:4326")
    print(f"Total rows rescued: {len(result)} across {result['id_no'].nunique()} species")

    out = OUT_ROOT / "plants-zip-unique-species.parquet"
    result.to_parquet(out, compression="snappy", index=False)
    size_kb = out.stat().st_size / 1024
    print(f"Wrote {out} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
