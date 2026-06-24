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

            # Skip pure index/geometry columns up front
            if col_type in ("uint64", "int64", "geometry") and col_name.startswith("h"):
                continue
            if col_name in ("h0", "h1", "h2", "h3", "h4", "h5", "h6", "h7", "h8", "h9", "h10",
                            "geometry", "geom", "shape", "_cng_fid", "bbox"):
                continue

            # The exclusions below only decide whether to *demand* a values array for a
            # column that lacks one. A column that already declares `values` is an
            # explicit opt-in to categorical validation and is never skipped here.
            if values_arr is None:
                desc_l = desc.lower()

                # Skip date columns — a date is never a categorical class, even when its
                # description names the "code" it dates (e.g. "Date the GAP Status Code
                # was assigned in YYYYMMDD"). Signals: name ends in dt/date, or a date-ish
                # description.
                is_date = (
                    bool(re.fullmatch(r"(?i).*(dt|date)", col_name))
                    or (bool(re.search(r"\bdate\b", desc_l)) and "yyyy" in desc_l)
                )
                if is_date:
                    continue

                # Skip source/provenance columns — free-text "source document used to
                # assign the X code" fields, not codes themselves. Signals: name ends in
                # src/source, or a source-provenance phrase in the description.
                is_source = (
                    bool(re.fullmatch(r"(?i).*(src|source)", col_name))
                    or bool(re.search(r"\bsource (document|used|data)\b|used to assign", desc_l))
                )
                if is_source:
                    continue

                # Skip FIPS / fixed-width geographic identifier codes — GEOID-component
                # keys (STATEFP/COUNTYFP/TRACTCE/SLDLST/SLDUST…) and FIPS/STCNTY/iso3.
                # These are identifier components, not enumerable classes (#303). The
                # discriminator is a "FIPS code" or "<thing> code (N digits)" description
                # (a fixed-width numeric key) or a known identifier name; genuine small
                # enums (MTFCC, CLASSFP, FUNCSTAT) carry neither signal and still flag.
                is_geo_identifier = (
                    bool(re.search(r"\bfips code\b|\bcode \(\d+\s*digits?\)", desc_l))
                    or bool(re.fullmatch(r"(?i)(fips|stcnty|iso3|geoid\w*)", col_name))
                )
                if is_geo_identifier:
                    continue

                # Skip identifier columns — unique keys / external record codes, not
                # categorical classes, even though their names often end in "num"/"id"/"cd"
                # or their types are integer. Discriminator: the description calls it a
                # number/identifier/site-or-record code, NOT a class/categorical. A strong
                # identifier phrase ("site code") wins even when the word "code" is present.
                mentions_class = bool(re.search(r"\bclass\b|categor", desc, re.I))
                strong_identifier = bool(
                    re.search(r"\b(site code|record code|unique (id|identifier)|object\s*id)\b", desc_l)
                )
                if strong_identifier:
                    continue
                looks_like_identifier = (
                    bool(re.search(r"\b(number|identifier|unique id|object\s*id)\b", desc, re.I))
                    or bool(re.fullmatch(r"(?i).*(_id|objectid|fid|guid|uuid)", col_name))
                )
                if looks_like_identifier and not mentions_class:
                    continue

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

            # Check for an inline CODE=Definition list in the description.
            # Accepts numeric codes (1=Lightning) and alphanumeric/string codes
            # (USF=US Forest Service, OGC:CRS84-style excluded). A single TOKEN=word
            # pair is a strong signal once the column is already known to be coded.
            has_inline_codes = bool(re.search(r"[A-Za-z0-9][\w/.-]*\s*=\s*\w", desc))
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

            # Cross-check hex values ⊆ COG classification:classes.
            # Only meaningful for numeric codes that line up with raster class values.
            numeric_vals = None
            if values_arr is not None:
                try:
                    numeric_vals = set(int(v) for v in values_arr)
                except (ValueError, TypeError):
                    numeric_vals = None  # string-coded enum (e.g. AGENCY) — no COG to cross-check
            if numeric_vals is not None and cog_classes:
                hex_set = numeric_vals
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
