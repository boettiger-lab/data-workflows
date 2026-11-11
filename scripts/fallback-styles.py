#!/usr/bin/env python3
"""Fallback default styles and renders for collections no GLEN app styles (#881).

Fills gaps only: a PMTiles asset gets a one-colour MapLibre style when the collection has no
default style; a COG gets a render when it has none and its metadata says how to draw it:

  * `classification:classes` with `color_hint` -> a per-class colormap
  * `raster:bands[0].statistics` min/max      -> viridis stretched over that range
  * `--stats` file (overview statistics)       -> viridis over mean ± 2 sd, clipped to min/max

`--stats` takes the JSON lines the overview-statistics Job prints ({"path": "/vsis3/...",
"min", "max", "mean", "std"}); they shape the render only and are not written to the STAC.
COGs with none of these are listed in the report and skipped. Fallback styles are keyed
`style-fallback-<stem>`; `scripts/app-styles.py` drops them when an app supplies real paint.

  scripts/fallback-styles.py --out /tmp/fb URL [URL ...]
  scripts/fallback-styles.py --out /tmp/fb --crawl https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json
"""

import argparse
import gzip
import importlib.util
import json
import posixpath
import struct
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


apps = _load("app_styles", "app-styles.py")
pc = _load("portolan_columns", "portolan-columns.py")

FALLBACK_PREFIX = "style-fallback-"
PAINT = {
    "fill": ({"fill-color": "#4a7bb7", "fill-opacity": 0.5},
             {"line-color": "#2b4c7e", "line-width": 0.5}),
    "line": ({"line-color": "#2b4c7e", "line-width": 1.2}, None),
    "circle": ({"circle-color": "#2b4c7e", "circle-radius": 3,
                "circle-stroke-color": "#ffffff", "circle-stroke-width": 0.5}, None),
}
GEOM = {"polygon": "fill", "multipolygon": "fill", "linestring": "line",
        "multilinestring": "line", "point": "circle", "multipoint": "circle"}


def _range(url, start, length):
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{start + length - 1}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def pmtiles_layer_types(url: str) -> dict:
    """{layer: fill|line|circle} from a PMTiles v3 file's tilestats (header + metadata only)."""
    head = _range(url, 0, 127)
    if head[:7] != b"PMTiles" or head[7] != 3:
        raise ValueError("not a PMTiles v3 file")
    off, ln = struct.unpack_from("<QQ", head, 24)
    raw = _range(url, off, ln)
    meta = json.loads(gzip.decompress(raw) if head[97] == 2 else raw)
    out = {}
    for lay in (meta.get("tilestats") or {}).get("layers", []):
        g = (lay.get("geometry") or "").lower()
        if g in GEOM:
            out[lay["layer"]] = GEOM[g]
    return out


def cog_render(asset_key: str, asset: dict, measured: dict | None = None) -> tuple[dict | None, str]:
    band = (asset.get("raster:bands") or [{}])[0]
    title = f"Fallback: {asset.get('title') or asset_key}"
    nodata = band.get("nodata", asset.get("nodata"))
    classes = band.get("classification:classes") or asset.get("classification:classes")
    if classes and all(c.get("color_hint") for c in classes):
        e = {"title": title, "assets": [asset_key], "resampling": "nearest",
             "colormap": {str(c["value"]): "#" + c["color_hint"].lstrip("#") for c in classes}}
    elif (st := band.get("statistics")) and st.get("minimum") is not None \
            and st.get("maximum") is not None and st["maximum"] > st["minimum"]:
        e = {"title": title, "assets": [asset_key], "colormap_name": "viridis",
             "rescale": [[st["minimum"], st["maximum"]]]}
    elif measured and measured.get("min") is not None and measured.get("max") is not None \
            and measured["max"] > measured["min"]:
        lo, hi = measured["min"], measured["max"]
        if measured.get("std"):
            lo = max(lo, measured["mean"] - 2 * measured["std"])
            hi = min(hi, measured["mean"] + 2 * measured["std"])
        e = {"title": title, "assets": [asset_key], "colormap_name": "viridis",
             "rescale": [[round(lo, 6), round(hi, 6)]]}
    else:
        return None, "no classes with color_hint and no statistics"
    if nodata is not None:
        e["nodata"] = nodata
    return e, ""


def key_has_stats(asset: dict) -> bool:
    return bool(((asset.get("raster:bands") or [{}])[0]).get("statistics"))


def load_stats(path: Path) -> dict:
    """{asset href: stats} from the Job's JSON lines; lines with an error are dropped."""
    out, text, i, dec = {}, path.read_text(), 0, json.JSONDecoder()
    while (i := text.find("{", i)) >= 0:  # parallel writers can share a line
        r, i = dec.raw_decode(text, i)
        if "error" not in r and r.get("path", "").startswith("/vsis3/"):
            out[apps.PUBLIC + r["path"].removeprefix("/vsis3/")] = r
    return out


def style_targets(doc: dict) -> dict:
    """{style asset key: set of absolute PMTiles hrefs its sources name, or None if none}."""
    out = {}
    for k, a in doc.get("assets", {}).items():
        if "style" not in (a.get("roles") or []):
            continue
        sty = apps.fetch_json(a["href"]) or {}
        urls = {urllib.parse.urljoin(a["href"], src["url"].removeprefix("pmtiles://"))
                for src in (sty.get("sources") or {}).values()
                if str(src.get("url", "")).startswith("pmtiles://")}
        out[k] = urls or None
    return out


def fallback(doc: dict, coll: str, stats: dict | None = None, targets: dict | None = None
             ) -> tuple[dict | None, list[tuple[str, dict]], list[str]]:
    """Return (new doc or None, [(style filename, style)], report lines).

    Every PMTiles file gets a default style naming it (glen matches style to file): an
    existing style for the file is promoted to default, else a fallback style is added."""
    assets = doc.get("assets", {})
    renders = doc.get("renders", {})
    rendered = {a for r in renders.values() for a in r.get("assets", [])}
    coll_dir = posixpath.dirname(coll)
    new = json.loads(json.dumps(doc))
    files, notes, promoted = [], [], False
    base = next((l.get("href") for l in doc.get("links", []) if l.get("rel") == "self"), "")
    tiles = {k: dict(a, href=urllib.parse.urljoin(base, a["href"]))
             for k, a in sorted(assets.items()) if pc.is_pmtiles(a)}
    if tiles and targets is None:
        targets = style_targets(doc)
    targets = targets or {}
    generic_default = any(t is None and "default" in assets[k].get("roles", [])
                          for k, t in targets.items())

    for key, a in ({} if generic_default else tiles).items():
        mine = sorted(k for k, t in targets.items() if t and a["href"] in t)
        if any("default" in assets[k].get("roles", []) for k in mine):
            continue
        if mine:
            new["assets"][mine[0]]["roles"] = ["style", "default"]
            promoted = True
            notes.append(f"`{key}`: `{mine[0]}` made its default")
            continue
        layers = a.get("vector:layers") or []
        if not layers:
            notes.append(f"`{key}`: no `vector:layers`, skipped")
            continue
        try:
            types = pmtiles_layer_types(a["href"])
        except Exception as e:  # noqa: BLE001 — report and skip
            notes.append(f"`{key}`: cannot read PMTiles metadata ({e}), skipped")
            continue
        layer = layers[0]
        t = types.get(layer)
        if not t:
            notes.append(f"`{key}`: no geometry type for layer `{layer}`, skipped")
            continue
        stem = key.removesuffix("-pmtiles")
        paint, outline = PAINT[t]
        cfg = {"layer_type": t, "default_style": paint}
        if outline:
            cfg["outline_style"] = outline
        title = f"Fallback: {a.get('title') or stem}"
        desc = "All features in one colour. No GLEN app styles this layer yet."
        pm_rel = posixpath.relpath(apps.asset_path(a["href"]),
                                   posixpath.join(coll_dir, "styles"))
        fname = f"fallback-{stem}.json"
        files.append((fname, apps.maplibre_style(cfg, title, pm_rel, layer, desc)))
        new["assets"][FALLBACK_PREFIX + stem] = {
            "href": f"{apps.PUBLIC}{coll_dir}/styles/{fname}", "type": apps.STYLE_TYPE,
            "title": title, "description": desc, "roles": ["style", "default"]}
        notes.append(f"`{key}`: {t} style")

    added = {}
    for key, a in sorted(assets.items()):
        if not (a.get("type") or "").startswith("image/tiff") or key in rendered:
            continue
        e, why = cog_render(key, a, (stats or {}).get(a.get("href")))
        if e:
            rkey = key.removesuffix("-cog")
            if rkey in renders or rkey in added:
                rkey = key
            added[rkey] = e
            kind = "classes" if "colormap" in e else "statistics" if key_has_stats(a) else "overview statistics"
            notes.append(f"`{key}`: render ({kind})")
        else:
            notes.append(f"`{key}`: no render, {why}")
    if added:
        new.setdefault("renders", {}).update(added)
        ext = new.setdefault("stac_extensions", [])
        if apps.RENDER_EXT not in ext:
            ext.append(apps.RENDER_EXT)

    changed = bool(files or added or promoted)
    return (new if changed else None), files, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--crawl")
    ap.add_argument("--stats", type=Path, help="JSON lines from the overview-statistics Job")
    ap.add_argument("urls", nargs="*")
    args = ap.parse_args()
    urls = list(args.urls) + (pc.crawl(args.crawl) if args.crawl else [])
    stats = load_stats(args.stats) if args.stats else None
    report = ["# Fallback styles and renders", ""]
    n = 0
    for url in urls:
        doc = apps.fetch_json(url)
        if not doc:
            report.append(f"- {url}: unreadable, skipped")
            continue
        coll = apps.asset_path(url)
        new, files, notes = fallback(doc, coll, stats)
        if notes:
            report.append(f"- `{coll}`" + ("" if new else " (unchanged)"))
            report += [f"  - {x}" for x in notes]
        if not new:
            continue
        n += 1
        cdir = args.out / posixpath.dirname(coll)
        for fname, sty in files:
            (cdir / "styles").mkdir(parents=True, exist_ok=True)
            (cdir / "styles" / fname).write_text(json.dumps(sty, indent=2) + "\n")
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / posixpath.basename(coll)).write_text(json.dumps(new, indent=2) + "\n")
    report.insert(2, f"{n} of {len(urls)} collections changed.\n")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.md").write_text("\n".join(report) + "\n")
    print(f"{n} collections changed; wrote {args.out}/report.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
