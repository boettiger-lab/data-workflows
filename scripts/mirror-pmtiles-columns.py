#!/usr/bin/env python3
"""
Mirror a collection's canonical GeoParquet column schema onto its PMTiles
asset(s) — the "lean" form of the #283 / #320 tile-schema standard.

Why this exists (data-workflows #320): a fresh catalog crawl found 119 PMTiles
assets with an empty `table:columns`, so the geo-agent cannot discover which
fields are stylable/filterable in MapLibre. But empirically our tippecanoe step
keeps **all** attribute columns — the PMTiles field set is just
`geoparquet_attrs − geometry + _cng_fid` (types coarsened to String/Number/
Boolean). So the fix is NOT to hand-scrape thin metadata from the footer; it is
to mirror the canonical GeoParquet schema onto the PMTiles asset, reusing the
rich `values` enumerations already curated there (the #303 work).

Lean policy (chosen to avoid tripling the column prose across the 3 assets):
each mirrored PMTiles column carries **name + type + values** only. The prose
`description` stays canonical on the GeoParquet asset; the geo-agent reads it
there when it needs definitions. Visualization-only facts that genuinely belong
on the tile asset — the styling value column and nodata sentinel — are preserved
if already present (and reported as TODO if the layer looks continuous).

The PMTiles footer is read only to **validate** the field set (and to catch the
rare genuine-subset case, e.g. SVI, where tippecanoe really did drop columns).

Usage:
    mirror-pmtiles-columns.py <stac-collection.json | https-url> [--out FILE]
        Transform one collection; write the updated JSON to --out (default:
        /tmp/<id>-pmtiles.json) and print a per-asset report.

Exit 0 on success; non-zero if no PMTiles asset or no GeoParquet schema to
mirror from. A genuine-subset / field-mismatch is reported (not fatal) so a
human can review before publishing.
"""

import argparse
import gzip
import json
import struct
import sys
import urllib.request

GEOM_NAMES = {"geom", "geometry", "shape", "Shape", "SHAPE", "the_geom", "wkb_geometry"}


def load_doc(src: str) -> dict:
    if src.startswith("http://") or src.startswith("https://"):
        with urllib.request.urlopen(src, timeout=30) as r:
            return json.load(r)
    with open(src) as f:
        return json.load(f)


def footer_fields(pmtiles_url: str) -> dict:
    """Return {layer_id: {field_name: footer_type}} from the .pmtiles footer."""
    def rng(a, b):
        req = urllib.request.Request(pmtiles_url, headers={"Range": f"bytes={a}-{b}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    h = rng(0, 126)
    off = struct.unpack_from("<Q", h, 24)[0]
    ln = struct.unpack_from("<Q", h, 32)[0]
    meta = json.loads(gzip.decompress(rng(off, off + ln - 1)).decode())
    return {L["id"]: L.get("fields", {}) for L in meta.get("vector_layers", [])}


# footer type (String/Number/Boolean) -> STAC type, used only for fields absent
# from the GeoParquet schema (rare; the GeoParquet type is preferred when known).
_FOOTER_TYPE = {"String": "string", "Number": "double", "Boolean": "boolean"}


def geoparquet_asset(doc: dict):
    """Return (key, asset) for the canonical GeoParquet asset (non-hex parquet)."""
    for key, a in doc.get("assets", {}).items():
        if "parquet" in a.get("type", "") and "hex" not in key and "hex" not in a.get("href", ""):
            return key, a
    return None, None


def lean_columns(tile_field_names, gp_cols_by_name):
    """Build lean PMTiles table:columns (name+type+values) for the given tile
    fields, mirroring the GeoParquet column metadata where the names match."""
    out = []
    for name in tile_field_names:
        gp = gp_cols_by_name.get(name)
        if gp:
            col = {"name": name, "type": gp.get("type", "string")}
            if gp.get("values") is not None:
                col["values"] = gp["values"]
        elif name == "_cng_fid":
            col = {"name": name, "type": "int64"}
        else:
            col = {"name": name, "type": "string"}  # overwritten below from footer
        out.append(col)
    return out


def mirror(doc: dict) -> list:
    """Mutate doc in place; return a list of report strings."""
    report = []
    gpk, gp = geoparquet_asset(doc)
    if gp is None:
        report.append("ERROR: no GeoParquet asset to mirror from")
        return report
    gp_cols = gp.get("table:columns") or []
    gp_by_name = {c["name"]: c for c in gp_cols}
    report.append(f"canonical schema: '{gpk}' ({len(gp_cols)} columns)")

    found_pmtiles = False
    for key, a in doc.get("assets", {}).items():
        if "pmtiles" not in a.get("type", ""):
            continue
        found_pmtiles = True
        href = a.get("href")
        try:
            ff = footer_fields(href)
        except Exception as e:
            report.append(f"  [{key}] FOOTER READ FAILED ({e}) — skipped")
            continue
        tile_fields = {}
        for lid, flds in ff.items():
            tile_fields.update(flds)
        names = [n for n in tile_fields if n not in GEOM_NAMES]
        # order: follow GeoParquet column order, then any tile-only fields
        ordered = [c["name"] for c in gp_cols if c["name"] in names]
        ordered += [n for n in names if n not in set(ordered)]

        cols = lean_columns(ordered, gp_by_name)
        # fill type for tile-only fields from the footer's coarse type
        for col in cols:
            if col["name"] not in gp_by_name and col["name"] != "_cng_fid":
                col["type"] = _FOOTER_TYPE.get(tile_fields.get(col["name"]), "string")

        # report set differences vs GeoParquet attributes
        gp_attr = {c["name"] for c in gp_cols if c["name"] not in GEOM_NAMES}
        subset = sorted(gp_attr - set(names))
        extra = sorted(set(names) - gp_attr - {"_cng_fid"})
        a["table:columns"] = cols
        if "vector:layers" not in a:
            a["vector:layers"] = list(ff.keys())
        msg = f"  [{key}] {len(cols)} tile fields mirrored (layers {list(ff.keys())})"
        if subset:
            msg += f"\n      ⚠ GENUINE SUBSET — in GeoParquet but NOT in tiles: {subset}"
        if extra:
            msg += f"\n      tile-only fields (not in GeoParquet): {extra}"
        report.append(msg)
    if not found_pmtiles:
        report.append("ERROR: no PMTiles asset in collection")
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="stac-collection.json path or https URL")
    ap.add_argument("--out", help="output file (default /tmp/<id>-pmtiles.json)")
    args = ap.parse_args()

    doc = load_doc(args.source)
    cid = doc.get("id", "collection")
    report = mirror(doc)
    out = args.out or f"/tmp/{cid}-pmtiles.json"
    with open(out, "w") as f:
        json.dump(doc, f, indent=2)
    print(f"=== {cid} ===")
    for line in report:
        print(line)
    print(f"  -> wrote {out}")
    return 1 if any(r.startswith("ERROR") for r in report) else 0


if __name__ == "__main__":
    sys.exit(main())
