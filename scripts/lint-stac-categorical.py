#!/usr/bin/env python3
"""
Lint a STAC collection JSON for categorical-metadata completeness.

Checks enforced (per AGENTS.md standards):

1. Coded categorical columns on parquet assets must have:
   - An inline CODE=Definition list in the column description
   - A "values" array

2. COG raster:bands classification:classes must have:
   - Each entry with value, name, description, color_hint
   - name must not look like a code/abbreviation (all-caps ≤4 chars, or equals value)

3. If both a hex asset and a COG asset exist for the same dataset, the set of
   codes in the hex "values" array must be a subset of the COG
   classification:classes values.

Usage:
    python3 scripts/lint-stac-categorical.py path/to/stac-collection.json [...]
    python3 scripts/lint-stac-categorical.py --url https://s3-west.nrp-nautilus.io/...

Exit 0 = all checks pass. Exit 1 = one or more failures.
"""

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path


def load_doc(source: str) -> dict:
    if source.startswith("http://") or source.startswith("https://"):
        with urllib.request.urlopen(source) as r:
            return json.load(r)
    return json.loads(Path(source).read_text())


def is_abbrev_name(name: str, value) -> bool:
    """Return True if name looks like a code/abbreviation rather than a human-readable label."""
    if name == str(value):
        return True
    # All-caps word of ≤4 chars, possibly with slash/dash between all-caps segments
    if re.fullmatch(r"[A-Z]{1,4}([/\-][A-Z]{1,4})*", name):
        return True
    return False


def lint(source: str) -> list[str]:
    """Return a list of error strings (empty = pass)."""
    try:
        doc = load_doc(source)
    except Exception as e:
        return [f"[LOAD ERROR] {e}"]

    errors = []
    collection_id = doc.get("id", source)

    # Gather classification:classes from all COG assets (value → name)
    cog_classes: dict[str, dict[int, str]] = {}  # asset_key -> {value: name}
    for asset_key, asset in doc.get("assets", {}).items():
        bands = asset.get("raster:bands", [])
        for band in bands:
            classes = band.get("classification:classes")
            if classes is None:
                continue
            cog_classes[asset_key] = {}
            for cls in classes:
                v = cls.get("value")
                n = cls.get("name", "")
                d = cls.get("description", "")
                ch = cls.get("color_hint", "")

                # Check required fields
                if v is None:
                    errors.append(
                        f"[{collection_id}] asset '{asset_key}': classification:classes entry missing 'value'"
                    )
                if not n:
                    errors.append(
                        f"[{collection_id}] asset '{asset_key}': classification:classes value={v} missing 'name'"
                    )
                if not d:
                    errors.append(
                        f"[{collection_id}] asset '{asset_key}': classification:classes value={v} missing 'description'"
                    )
                if not ch:
                    errors.append(
                        f"[{collection_id}] asset '{asset_key}': classification:classes value={v} missing 'color_hint'"
                    )

                # Check name is human-readable
                if n and v is not None and is_abbrev_name(n, v):
                    errors.append(
                        f"[{collection_id}] asset '{asset_key}': classification:classes value={v} "
                        f"has abbreviation-style name='{n}' — use the full human-readable name "
                        f"(keep the abbreviation in 'description')"
                    )

                if v is not None:
                    cog_classes[asset_key][int(v)] = n

    # Check parquet assets for categorical column completeness
    for asset_key, asset in doc.get("assets", {}).items():
        mime = asset.get("type", "")
        if "parquet" not in mime:
            continue

        columns = asset.get("table:columns", [])
        for col in columns:
            col_name = col.get("name", "")
            col_type = col.get("type", "")
            desc = col.get("description", "")
            values_arr = col.get("values")

            # Detect coded categorical columns:
            # - has a "values" array already (opt-in explicit)
            # - or the description mentions "categorical", "code", or "class code"
            # - or the column name ends in "num" / "code" / "class"
            is_coded = (
                values_arr is not None
                or bool(re.search(r"\bcategor|class code\b|code\b", desc, re.I))
                or bool(re.search(r"(num|code|class)$", col_name, re.I))
            )

            if not is_coded:
                continue

            # Skip pure index/geometry columns
            if col_type in ("uint64", "int64", "geometry") and col_name.startswith("h"):
                continue
            if col_name in ("h0", "h1", "h2", "h3", "h4", "h5", "h6", "h7", "h8", "h9", "h10",
                            "geometry", "geom", "shape", "_cng_fid", "bbox"):
                continue

            # Check for inline CODE=Definition list in description
            # Pattern: one or more "digits=Word" tokens separated by commas
            has_inline_codes = bool(re.search(r"\d+=\w", desc))
            if not has_inline_codes:
                errors.append(
                    f"[{collection_id}] asset '{asset_key}', column '{col_name}': "
                    f"coded categorical column missing inline CODE=Definition list in description. "
                    f"Add e.g. 'Valid values: 10=Agriculture, 20=Barren/Other, ...'"
                )

            # Check for values array
            if values_arr is None:
                errors.append(
                    f"[{collection_id}] asset '{asset_key}', column '{col_name}': "
                    f"coded categorical column missing 'values' array."
                )

            # Cross-check hex values ⊆ COG classification:classes
            if values_arr is not None and cog_classes:
                hex_set = set(int(v) for v in values_arr)
                for cog_key, cog_map in cog_classes.items():
                    cog_set = set(cog_map.keys())
                    extra = hex_set - cog_set
                    if extra:
                        errors.append(
                            f"[{collection_id}] asset '{asset_key}', column '{col_name}': "
                            f"values {sorted(extra)} present in hex but not in '{cog_key}' "
                            f"classification:classes — cross-check failed."
                        )

    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="+", help="Path(s) or URL(s) to stac-collection.json files")
    args = parser.parse_args()

    all_errors = []
    for src in args.sources:
        errs = lint(src)
        for e in errs:
            print(e, file=sys.stderr)
        all_errors.extend(errs)

    if all_errors:
        print(f"\n{len(all_errors)} issue(s) found.", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"All {len(args.sources)} collection(s) passed categorical lint.")
        sys.exit(0)


if __name__ == "__main__":
    main()
