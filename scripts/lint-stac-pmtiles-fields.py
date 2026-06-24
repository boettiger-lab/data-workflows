#!/usr/bin/env python3
"""
Lint a STAC collection JSON for PMTiles tile-field completeness.

Rationale (data-workflows #283): tippecanoe selects a *subset* of source columns
at tile-build time, so the PMTiles fields differ from the source GeoParquet schema.
A consumer (the geo-agent, or a human app author) can only learn which fields are
present — and therefore stylable / filterable in MapLibre — from the PMTiles asset
itself. When `table:columns` is empty the only recovery is byte-ranging the
`.pmtiles` footer's `vector_layers[].fields`. Nodata sentinels (e.g. SVI
`RPL_THEMES = -999`) are likewise invisible unless documented.

Checks enforced (per AGENTS.md "PMTiles assets" standard):

1. Every PMTiles asset (`type` contains "pmtiles") MUST declare `vector:layers`
   (non-empty list of source-layer ids).
2. Every PMTiles asset MUST have a non-empty `table:columns` listing the
   tile-accurate fields, each with a `name` and `type`.
3. Each PMTiles column SHOULD have a non-empty `description` (warning, not error,
   unless --strict).

Discover the real tile fields with:

    python3 -c 'import urllib.request,json,struct,gzip; \
        u="https://.../layer.pmtiles"; \
        r=lambda a,b: urllib.request.urlopen(urllib.request.Request(u,headers={"Range":f"bytes={a}-{b}"})).read(); \
        h=r(0,126); o=struct.unpack_from("<Q",h,24)[0]; n=struct.unpack_from("<Q",h,32)[0]; \
        m=json.loads(gzip.decompress(r(o,o+n-1)).decode()); \
        print([(L["id"],L.get("fields")) for L in m["vector_layers"]])'

Usage:
    python3 scripts/lint-stac-pmtiles-fields.py path/to/stac-collection.json [...]
    python3 scripts/lint-stac-pmtiles-fields.py --url https://s3-west.nrp-nautilus.io/...

Exit 0 = all checks pass. Exit 1 = one or more failures.
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path


def load_doc(source: str) -> dict:
    if source.startswith("http://") or source.startswith("https://"):
        with urllib.request.urlopen(source) as r:
            return json.load(r)
    return json.loads(Path(source).read_text())


def lint(source: str, strict: bool = False) -> list[str]:
    """Return a list of error strings (empty = pass)."""
    try:
        doc = load_doc(source)
    except Exception as e:
        return [f"[LOAD ERROR] {e}"]

    errors = []
    collection_id = doc.get("id", source)

    for asset_key, asset in doc.get("assets", {}).items():
        mime = asset.get("type", "")
        if "pmtiles" not in mime:
            continue

        # 1. vector:layers required
        vlayers = asset.get("vector:layers")
        if not vlayers:
            errors.append(
                f"[{collection_id}] asset '{asset_key}': PMTiles asset missing "
                f"'vector:layers' (the MapLibre source-layer id(s))."
            )

        # 2. table:columns required and non-empty
        columns = asset.get("table:columns")
        if not columns:
            errors.append(
                f"[{collection_id}] asset '{asset_key}': PMTiles asset has empty "
                f"'table:columns' — populate the tile-accurate fields from the "
                f".pmtiles footer (vector_layers[].fields). See data-workflows #283."
            )
            continue

        # 3. each column needs name + type (+ description, soft unless --strict)
        for col in columns:
            name = col.get("name", "")
            if not name:
                errors.append(
                    f"[{collection_id}] asset '{asset_key}': a table:columns entry "
                    f"is missing 'name'."
                )
                continue
            if not col.get("type"):
                errors.append(
                    f"[{collection_id}] asset '{asset_key}', column '{name}': "
                    f"missing 'type'."
                )
            if not col.get("description"):
                msg = (
                    f"[{collection_id}] asset '{asset_key}', column '{name}': "
                    f"missing 'description'."
                )
                if strict:
                    errors.append(msg)
                else:
                    print("[WARN] " + msg, file=sys.stderr)

    return errors


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("sources", nargs="+", help="Path(s) or URL(s) to stac-collection.json files")
    parser.add_argument(
        "--strict", action="store_true",
        help="Treat missing column descriptions as errors (default: warning).",
    )
    args = parser.parse_args()

    all_errors = []
    for src in args.sources:
        errs = lint(src, strict=args.strict)
        for e in errs:
            print(e, file=sys.stderr)
        all_errors.extend(errs)

    if all_errors:
        print(f"\n{len(all_errors)} issue(s) found.", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"All {len(args.sources)} collection(s) passed PMTiles-fields lint.")
        sys.exit(0)


if __name__ == "__main__":
    main()
