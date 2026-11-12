#!/usr/bin/env python3
"""Build a considered default MapLibre style for one PMTiles file from its data.

Every PMTiles file gets a default style that shows its primary variable, chosen the way the
STAC is written: read the columns, their types, their distinct values or ranges, and what the
dataset is about. Two steps:

  default-style.py profile COLLECTION_URL [--asset KEY]
      Lists each PMTiles file's drawable attributes (from the file's own tilestats: type,
      distinct count, range or sample values) beside the collection's column descriptions.
      Pick the primary variable from this.

  default-style.py build COLLECTION_URL --asset KEY --column COL --kind categorical|continuous
                   [--why "one sentence"] [--palette NAME] [--colors JSON] [--labels JSON]
                   [--breaks a,b,c] [--max-classes 10] [--tooltip A,B] --out DIR
  default-style.py build COLLECTION_URL --asset KEY --single-colour "why no variable is worth showing" --out DIR

`categorical` colours the most frequent values (measured in the GeoParquet through the duckdb-geo
MCP server; the PMTiles tilestats when there is no GeoParquet), up to --max-classes, with the rest
as Other. Labels come from the column's `CODE=Definition` description, or --labels. `continuous`
shades graduated classes at quantile breaks of the real values (rounded), with a no-data grey for
missing or non-numeric values. Both write `glen:legend` classes. `--single-colour` is for a file
with no variable worth showing; the reason becomes the style's description and
`glen:single_colour_reason`, and is the only way a one-colour default passes the checks.

Writes <out>/<collection dir>/styles/<stem>-<column>.json and the patched collection JSON, with
the new style as the file's default and any fallback style for the file removed. Publishes
nothing; upload with rclone after review (skill stac-authoring, Step 5b).

The MCP endpoint is MCP_ENDPOINT (default http://localhost:8000/mcp, the port-forward), with the
token from MCP_AUTH_TOKEN or GEO_WORKFLOWS_MCP_TOKEN.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import posixpath
import re
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


apps = _load("app_styles", "app-styles.py")
fb = _load("fallback_styles", "fallback-styles.py")

NO_DATA = apps.NO_DATA
OTHER = "#bdbdbd"
CATEGORICAL = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948",
               "#b07aa1", "#ff9da7", "#9c755f", "#86bcb6", "#d4a6c8", "#a0cbe8"]
SEQUENTIAL = {
    "viridis": ["#440154", "#414487", "#2a788e", "#22a884", "#7ad151", "#fde725"],
    "ylorrd": ["#ffffb2", "#fed976", "#feb24c", "#fd8d3c", "#f03b20", "#bd0026"],
    "blues": ["#eff3ff", "#c6dbef", "#9ecae1", "#6baed6", "#3182bd", "#08519c"],
    "greens": ["#edf8e9", "#c7e9c0", "#a1d99b", "#74c476", "#31a354", "#006d2c"],
    "purples": ["#f2f0f7", "#dadaeb", "#bcbddc", "#9e9ac8", "#756bb1", "#54278f"],
    "oranges": ["#feedde", "#fdd0a2", "#fdae6b", "#fd8d3c", "#e6550d", "#a63603"],
}
SINGLE = {"fill": "#4a7bb7", "line": "#2b4c7e", "circle": "#2b4c7e"}
SKIP = re.compile(r"^(_cng_fid|ogc_fid|objectid|fid|shape_(area|len|length)|shape_leng|h\d+)$", re.I)


# --------------------------------------------------------------------------- inputs

def pmtiles_meta(url: str) -> dict:
    """{layer: tilestats layer} from a PMTiles v3 file's metadata."""
    import gzip
    import struct
    head = fb._range(url, 0, 127)
    if head[:7] != b"PMTiles" or head[7] != 3:
        raise ValueError("not a PMTiles v3 file")
    off, ln = struct.unpack_from("<QQ", head, 24)
    raw = fb._range(url, off, ln)
    meta = json.loads(gzip.decompress(raw) if head[97] == 2 else raw)
    return {l["layer"]: l for l in (meta.get("tilestats") or {}).get("layers", [])}


def tiles(doc: dict) -> dict:
    base = next((l.get("href") for l in doc.get("links", []) if l.get("rel") == "self"), "")
    return {k: dict(a, href=urllib.parse.urljoin(base, a["href"]))
            for k, a in sorted(doc.get("assets", {}).items()) if fb.pc.is_pmtiles(a)}


def columns(doc: dict, asset_key: str | None = None) -> dict:
    """{name: column} from the collection dictionary, overlaid by an asset's own entries."""
    out = {c["name"]: c for c in doc.get("table:columns") or [] if isinstance(c, dict)}
    for k, a in doc.get("assets", {}).items():
        if asset_key is None or k == asset_key:
            for c in a.get("table:columns") or []:
                out.setdefault(c["name"], {}).update({x: y for x, y in c.items() if y})
    return out


def parquet_for(doc: dict, stem: str) -> str | None:
    """s3:// path of the GeoParquet that holds the same features as the PMTiles file."""
    cands = [(k, a) for k, a in doc.get("assets", {}).items()
             if "parquet" in (a.get("type") or "") and "/hex" not in a.get("href", "")
             and not k.endswith("-hex")]
    pick = next((a for k, a in cands if k == f"{stem}-parquet"), None) or \
        (cands[0][1] if len(cands) == 1 else None)
    if not pick:
        return None
    m = re.match(r"https?://s3-west\.nrp-nautilus\.io/(.+)$", pick["href"])
    return "s3://" + m.group(1) if m else (pick["href"] if pick["href"].startswith("s3://") else None)


def mcp():
    vs = _load("verify_stac", "verify-stac.py")
    tok = os.environ.get("MCP_AUTH_TOKEN") or os.environ.get("GEO_WORKFLOWS_MCP_TOKEN")
    return vs.MCPClient(os.environ.get("MCP_ENDPOINT", "http://localhost:8000/mcp"), tok)


def q(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'


def sql_value(column: str) -> str:
    """SQL for a column, or for a ratio `A/B` of two numeric columns."""
    if "/" in column:
        a, b = column.split("/", 1)
        return f"TRY_CAST({q(a)} AS DOUBLE) / NULLIF(TRY_CAST({q(b)} AS DOUBLE), 0)"
    return f"TRY_CAST({q(column)} AS DOUBLE)"


def style_value(column: str) -> tuple[list, list]:
    """(numeric MapLibre expression, guard that it is defined) for a column or a ratio `A/B`."""
    if "/" in column:
        a, b = column.split("/", 1)
        return (["/", ["to-number", ["get", a], 0], ["to-number", ["get", b], 1]],
                ["all", ["==", ["typeof", ["get", a]], "number"],
                 [">", ["to-number", ["get", b], 0], 0]])
    return ["to-number", ["get", column]], ["==", ["typeof", ["get", column]], "number"]


# --------------------------------------------------------------------------- profile

def profile(doc: dict, url: str, only: str | None) -> str:
    cols = columns(doc)
    lines = [f"# {doc.get('title', '')}", f"{url}", "",
             re.sub(r"\s+", " ", doc.get("description", ""))[:600], ""]
    for key, a in tiles(doc).items():
        if only and key != only:
            continue
        try:
            meta = pmtiles_meta(a["href"])
        except Exception as e:  # noqa: BLE001
            lines.append(f"## {key}: cannot read PMTiles metadata ({e})")
            continue
        for layer, st in meta.items():
            lines.append(f"## {key} layer `{layer}`: {st.get('count')} {st.get('geometry')} features")
            if (st.get("attributeCount") or 0) > len(st.get("attributes", [])):
                lines.append(f"(tilestats lists {len(st['attributes'])} of {st['attributeCount']} "
                             "attributes; the rest are in the collection's column dictionary)")
            for at in st.get("attributes", []):
                name = at["attribute"]
                if SKIP.match(name):
                    continue
                desc = re.sub(r"\s+", " ", (cols.get(name) or {}).get("description", ""))[:220]
                if at.get("type") == "number" and at.get("min") is not None:
                    rng = f"{at['min']} .. {at['max']}"
                else:
                    rng = "; ".join(str(v) for v in (at.get("values") or [])[:8])
                vals = " [values]" if (cols.get(name) or {}).get("values") else ""
                lines.append(f"- `{name}` {at.get('type')} n={at.get('count')}{vals}: {rng}"
                             + (f" — {desc}" if desc else ""))
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- classes

def code_labels(col: dict, codes=()) -> dict:
    """{str(code): definition} from a `Values: A=Alpha, B=Beta.` description, for the declared
    `values` and any other codes given (the classes actually drawn)."""
    desc = col.get("description") or ""
    pos = []
    for v in dict.fromkeys([str(x) for x in (col.get("values") or [])] + [str(x) for x in codes]):
        m = re.search(r"(?:^|[:;,]\s*|\(\s*)" + re.escape(v) + r"\s*=\s*", desc)
        if m:
            pos.append((m.end(), m.start(), v))
    pos.sort()
    out = {}
    for i, (end, _, v) in enumerate(pos):
        stop = pos[i + 1][1] if i + 1 < len(pos) else len(desc)
        text = re.split(r"\.\s+(?=[A-Z])", desc[end:stop])[0]  # the definition, not what follows
        out[v] = text.strip().rstrip(".;,").strip()
    return out


def nice_breaks(qs: list[float], lo: float, hi: float) -> list[float]:
    """Round quantile breaks to the fewest significant figures that keeps them distinct."""
    raw = sorted({x for x in qs if lo < x < hi})
    for sig in range(1, 7):
        out = sorted({float(f"{x:.{sig}g}") for x in raw})
        out = [x for x in out if lo < x < hi]
        if len(out) == len(raw):
            return out
    return raw


def fmt(x: float) -> str:
    if abs(x) >= 10000:
        return f"{x:,.0f}"
    return f"{x:g}"


def categorical_classes(doc, stem, layer_stats, column, max_classes):
    """[(value str, count or None)] most frequent first, plus total distinct count."""
    pq = parquet_for(doc, stem)
    if pq:
        rows = mcp().query(
            f"SELECT CAST({q(column)} AS VARCHAR) AS v, count(*) AS n, "
            f"count(*) OVER () AS k FROM read_parquet('{pq}') "
            f"WHERE {q(column)} IS NOT NULL GROUP BY 1 ORDER BY n DESC, v LIMIT {max_classes + 1}")
        k = int(rows[0]["k"]) if rows else 0
        return [(r["v"], int(r["n"])) for r in rows], k, pq
    at = next(a for a in layer_stats["attributes"] if a["attribute"] == column)
    vals = [str(v) for v in at.get("values") or []]
    return [(v, None) for v in sorted(vals)[:max_classes + 1]], at.get("count", len(vals)), None


def continuous_breaks(doc, stem, layer_stats, column, n, nodata=None):
    pq = parquet_for(doc, stem)
    probs = [i / n for i in range(1, n)]
    if pq:
        x = sql_value(column)
        where = f" WHERE {x} IS DISTINCT FROM {nodata}" if nodata is not None else ""
        sel = ", ".join(f"quantile_cont({x}, {p}) AS q{i}" for i, p in enumerate(probs))
        r = mcp().query(f"SELECT {sel}, min({x}) AS lo, max({x}) AS hi FROM read_parquet('{pq}'){where}")[0]
        return [float(r[f"q{i}"]) for i in range(len(probs))], float(r["lo"]), float(r["hi"]), pq
    at = next(a for a in layer_stats["attributes"] if a["attribute"] == column)
    vs = sorted(float(v) for v in at.get("values") or []
                if isinstance(v, (int, float)) and v != nodata)
    qs = [vs[min(len(vs) - 1, int(p * len(vs)))] for p in probs]
    return qs, float(at["min"]), float(at["max"]), None


# --------------------------------------------------------------------------- style

def paint_for(t: str, color) -> tuple[dict, dict | None]:
    if t == "fill":
        return ({"fill-color": color, "fill-opacity": 0.7},
                {"line-color": "#4d4d4d", "line-width": 0.4, "line-opacity": 0.6})
    if t == "line":
        return ({"line-color": color, "line-width": 1.5}, None)
    return ({"circle-color": color, "circle-radius": 4, "circle-stroke-color": "#ffffff",
             "circle-stroke-width": 0.6}, None)


def build(doc: dict, coll: str, key: str, args) -> tuple[dict, str, dict, list[str]]:
    a = tiles(doc)[key]
    stem = key.removesuffix("-pmtiles")
    layer = (a.get("vector:layers") or [None])[0]
    meta = pmtiles_meta(a["href"])
    layer = layer if layer in meta else next(iter(meta))
    st = meta[layer]
    t = fb.GEOM.get((st.get("geometry") or "").lower())
    if not t:
        raise SystemExit(f"{key}: unknown geometry {st.get('geometry')!r}")
    attrs = {x["attribute"]: x for x in st.get("attributes", [])}
    cols = columns(doc, key)
    name = a.get("title") or stem
    report = []
    legend, tooltip = None, [c for c in (args.tooltip or "").split(",") if c]

    if args.single_colour:
        color = args.color or SINGLE[t]
        title, desc = f"{name}", args.single_colour.strip()
        slugc = None
    else:
        column = args.column
        truncated = (st.get("attributeCount") or 0) > len(attrs)
        for c in column.split("/"):
            if c not in attrs and not (truncated and c in cols):
                raise SystemExit(f"{key}: `{c}` is not an attribute of the PMTiles layer "
                                 f"`{layer}` (has: {', '.join(attrs)})")
        label = args.label or column
        slugc = apps.slug(column.replace("/", "-per-"))
        if args.kind == "categorical":
            colors = json.loads(args.colors) if args.colors else {}
            limit = 500 if colors else args.max_classes + len(args.nodata or [])
            classes, k, src = categorical_classes(doc, stem, st, column, limit)
            skip = {str(x) for x in (args.nodata or [])}
            k -= sum(1 for v, _ in classes if v in skip)
            classes = [(v, n) for v, n in classes if v not in skip]
            labels = code_labels(cols.get(column) or {}, [v for v, _ in classes])
            labels.update(json.loads(args.labels) if args.labels else {})
            shown = classes[:args.max_classes] if k > args.max_classes else classes
            if colors:  # an explicit palette names the classes to show, in legend order
                present = dict(classes)
                shown = [(v, present[v]) for v in colors if v in present]
            if not colors and all(re.fullmatch(r"-?\d+(\.\d+)?", v) for v, _ in shown):
                shown = sorted(shown, key=lambda vn: float(vn[0]))  # codes read in order
            if args.palette and not colors:  # ordered classes: spread a sequential ramp
                ramp = SEQUENTIAL[args.palette][::-1 if args.reverse else 1]
                k1 = max(1, len(shown) - 1)
                pal = iter(ramp[round(i * (len(ramp) - 1) / k1)] for i in range(len(shown)))
            else:
                pal = iter(CATEGORICAL)
            need = sum(1 for v, _ in shown if v not in colors)
            if not (args.palette and not colors) and need > len(CATEGORICAL):
                sys.exit(f"{need} classes but the categorical palette has {len(CATEGORICAL)} colours; "
                         f"pass --colors, or lower --max-classes")
            pairs = [(v, colors.get(v) or next(pal)) for v, _ in shown]
            other = k > len(pairs)
            expr = ["match", ["to-string", ["get", column]]]
            for v, c in pairs:
                expr += [v, c]
            expr.append(OTHER if other else NO_DATA)
            nd = [str(x) for x in (args.nodata or [])]
            color = ["case", ["!", ["has", column]], NO_DATA] + \
                sum(([["==", ["to-string", ["get", column]], x], NO_DATA] for x in nd), []) + [expr]
            legend = {"type": "categorical", "label": label,
                      "classes": [{"label": labels.get(v, v), "color": c} for v, c in pairs]
                      + ([{"label": "Other", "color": OTHER}] if other else [])}
            desc = (f"Features coloured by {label}" +
                    (f", the {len(pairs)} most common of {k} values, the rest grey" if other
                     else f", {k} values") + ".")
            report.append(f"{key}: categorical `{column}` {len(pairs)}/{k} classes "
                          f"({'GeoParquet' if src else 'tilestats'}): "
                          + ", ".join(f"{v}={n}" for v, n in shown))
        else:
            ramp = list(SEQUENTIAL[args.palette or "viridis"])
            if args.reverse:
                ramp.reverse()
            n = len(ramp)
            if args.breaks:
                bks = [float(x) for x in args.breaks.split(",")]
                lo = hi = None
                src = "given"
            else:
                nd = args.nodata[0] if args.nodata else None
                qs, lo, hi, src = continuous_breaks(doc, stem, st, column, n, nd)
                bks = nice_breaks(qs, lo, hi)
            if not bks:
                raise SystemExit(f"{key}: `{column}` has no spread to class ({lo}..{hi})")
            k = len(bks) + 1  # spread the ramp's colours over however many classes there are
            ramp = [ramp[round(i * (n - 1) / (k - 1))] for i in range(k)]
            num, guard = style_value(column)
            step = ["step", num, ramp[0]]
            for b, c in zip(bks, ramp[1:]):
                step += [b, c]
            if args.nodata:
                guard = ["all", guard] + [["!=", num, float(x)] for x in args.nodata]
            color = ["case", guard, step, NO_DATA]
            unit = f" {args.unit}" if args.unit else ""
            labs = [f"under {fmt(bks[0])}{unit}"] + \
                [f"{fmt(x)} – {fmt(y)}{unit}" for x, y in zip(bks, bks[1:])] + \
                [f"{fmt(bks[-1])}{unit} and over"]
            legend = {"type": "categorical", "label": label,
                      "classes": [{"label": l, "color": c} for l, c in zip(labs, ramp)]
                      + [{"label": "No data", "color": NO_DATA}]}
            desc = f"Features shaded by {label}, in {len(ramp)} classes at quantile breaks of the data."
            report.append(f"{key}: continuous `{column}` range {lo}..{hi}, breaks {bks} "
                          f"({'GeoParquet' if src else 'tilestats' if src is None else src})")
        title = f"{name} by {label}"
        for c in reversed(column.split("/")):
            if c not in tooltip:
                tooltip.insert(0, c)
    if args.why:
        desc = f"{desc} {args.why.strip()}"

    paint, outline = paint_for(t, color)
    cfg = {"layer_type": t, "default_style": paint}
    if outline:
        cfg["outline_style"] = outline
    coll_dir = posixpath.dirname(coll)
    pm_rel = posixpath.relpath(apps.asset_path(a["href"]), posixpath.join(coll_dir, "styles"))
    sty = apps.maplibre_style(cfg, title, pm_rel, layer, desc)
    if legend:
        sty["metadata"]["glen:legend"] = legend
    if args.single_colour:
        sty["metadata"]["glen:single_colour_reason"] = desc
    if tooltip:
        sty["metadata"]["glen:tooltip_fields"] = tooltip

    fname = f"{stem}-{slugc}.json" if slugc else f"{stem}.json"
    skey = f"style-{stem}-{slugc}" if slugc else f"style-{stem}"
    new = json.loads(json.dumps(doc))
    assets = new["assets"]
    for k in [k for k in assets if k == fb.FALLBACK_PREFIX + stem]:
        del assets[k]
    stems = sorted((k.removesuffix("-pmtiles") for k, x in assets.items() if fb.pc.is_pmtiles(x)),
                   key=len, reverse=True)

    def stem_of(k):  # style-<stem>[-<variant>] names its file; longest stem wins
        k = k.removeprefix(fb.FALLBACK_PREFIX).removeprefix("style-")
        return next((s for s in stems if k == s or k.startswith(s + "-")), None)

    for k, x in assets.items():  # one default per PMTiles file
        if "default" in (x.get("roles") or []) and stem_of(k) == stem:
            x["roles"] = ["style"]
    assets[skey] = {"href": f"{apps.PUBLIC}{coll_dir}/styles/{fname}", "type": apps.STYLE_TYPE,
                    "title": title, "description": desc, "roles": ["style", "default"]}
    return new, fname, sty, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("profile")
    p.add_argument("url")
    p.add_argument("--asset")
    b = sub.add_parser("build")
    b.add_argument("url")
    b.add_argument("--asset", required=True)
    b.add_argument("--column")
    b.add_argument("--kind", choices=["categorical", "continuous"])
    b.add_argument("--single-colour")
    b.add_argument("--label", help="human name of the column for title and legend")
    b.add_argument("--why", help="one sentence on why this is the primary variable")
    b.add_argument("--palette", choices=sorted(SEQUENTIAL))
    b.add_argument("--reverse", action="store_true")
    b.add_argument("--colors", help='JSON {"value": "#hex"}: exactly these classes, these colours')
    b.add_argument("--labels", help='JSON {"value": "legend label"}')
    b.add_argument("--breaks", help="explicit class breaks, comma-separated")
    b.add_argument("--unit")
    b.add_argument("--nodata", action="append", help="a sentinel value drawn as no data (repeatable)")
    b.add_argument("--color", help="the colour of a --single-colour style")
    b.add_argument("--max-classes", type=int, default=10)
    b.add_argument("--tooltip")
    b.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    doc = apps.fetch_json(args.url)
    if not doc:
        return 1
    if args.cmd == "profile":
        print(profile(doc, args.url, args.asset))
        return 0
    if not args.single_colour and not (args.column and args.kind):
        ap.error("build needs --column and --kind, or --single-colour REASON")
    coll = apps.asset_path(args.url)
    out_json = args.out / coll
    if out_json.exists():  # several files in one collection: build on the earlier result
        doc = json.loads(out_json.read_text())
    new, fname, sty, report = build(doc, coll, args.asset, args)
    sdir = out_json.parent / "styles"
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / fname).write_text(json.dumps(sty, indent=2) + "\n")
    out_json.write_text(json.dumps(new, indent=2) + "\n")
    print("\n".join(report) or f"{args.asset}: single colour", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
