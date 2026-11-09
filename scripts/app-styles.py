#!/usr/bin/env python3
"""Derive Portolan default styles for catalog collections from the GLEN apps' layer configs.

Portolan (PORTO-CORE-069/070, PORTO-FMT-014/015) requires every collection with PMTiles to
carry at least one MapLibre GL style as a STAC asset with the `style` role, and exactly one
`default` when there are several. Rasters have no style file yet (portolan-spec#41); a COG is
display-ready when the collection says how to colorize it, which the STAC `render` extension
does with the same colormap and rescale the apps already pass to titiler.

The deployed GLEN apps' `layers-input.json` files hold hand-tuned paint for most of our
assets. This script reads them all, picks one style per (collection, asset, attribute) when
apps disagree, and writes for each collection:

  <out>/<collection dir>/styles/<variant>.json   complete MapLibre style v8 files
  <out>/<collection dir>/stac-collection.json    the live collection with style assets,
                                                  `renders` and the render extension merged in
  <out>/report.md                                 every choice made, and every conflict

It reads the live STAC (for `vector:layers` and asset hrefs) but publishes nothing. Upload
with `rclone copy <out>/<bucket>/ nrp:<bucket>/` after review (see skill `stac-authoring`).

Conflict rule, in order: the style used by the most distinct apps wins; ties go to the app
whose name matches the collection's bucket (the domain app, e.g. `calenviroscreen` for
`public-calenviroscreen`), then to the config with the most legend detail, then by app name.
Within a collection the default style is the variant used by the most apps, then a variant
an app shows on load (`visible: true`).

Usage:
  scripts/app-styles.py --fetch --out /tmp/styles                 # app list from glen-ops APPS.md
  scripts/app-styles.py --configs DIR --out /tmp/styles           # pre-fetched layers-input*.json
  scripts/app-styles.py ... --only public-census                  # limit to collections in a bucket
"""
from __future__ import annotations

import argparse
import collections
import json
import posixpath
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

PUBLIC = "https://s3-west.nrp-nautilus.io/"
STYLE_TYPE = "application/vnd.mapbox.style+json"
RENDER_EXT = "https://stac-extensions.github.io/render/v2.0.0/schema.json"
VECTOR_KEYS = ("layer_type", "default_style", "outline_style")
RASTER_KEYS = ("colormap", "rescale")
LEGEND_KEYS = ("legend_type", "legend_classes", "legend_label")


# ── inputs ──────────────────────────────────────────────────────────────────────

def gh_raw(repo: str, path: str) -> str | None:
    r = subprocess.run(["gh", "api", f"repos/{repo}/contents/{path}",
                        "-H", "Accept: application/vnd.github.raw"],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def fetch_configs(dest: Path) -> None:
    """Download every app's layers-input*.json, using the repo list in glen-ops APPS.md."""
    apps_md = gh_raw("boettiger-lab/glen-ops", "APPS.md") or ""
    repos = sorted(set(re.findall(r"^\|[^|]+\|\s*\[?([\w-]+/[\w.-]+)", apps_md, re.M)))
    dest.mkdir(parents=True, exist_ok=True)
    for repo in repos:
        r = subprocess.run(["gh", "api", f"repos/{repo}/contents", "--jq", ".[].name"],
                           capture_output=True, text=True)
        for name in r.stdout.split():
            if re.fullmatch(r"layers-input.*\.json", name):
                body = gh_raw(repo, name)
                if body:
                    (dest / f"{repo.split('/')[1]}__{name}").write_text(body)
                    print(f"fetched {repo}/{name}", file=sys.stderr)


def app_name(fname: str) -> tuple[str, str]:
    """('bosl-high-seas', 'bosl-high-seas:private') — the family votes once."""
    repo, rest = fname.split("__", 1)
    variant = rest[len("layers-input"):-len(".json")].lstrip(".")
    return repo, f"{repo}:{variant}" if variant else repo


def collection_path(url: str) -> str:
    """Bucket-relative path of a collection, whatever host the app reads it from."""
    p = re.sub(r"^https?://[^/]+/", "", url or "")
    return re.sub(r"^cboettig/", "", p)  # source.coop prefix


def flatten(config_dir: Path) -> list[dict]:
    rows = []
    for f in sorted(config_dir.glob("*__layers-input*.json")):
        family, app = app_name(f.name)
        doc = json.loads(f.read_text())
        for c in doc.get("collections", []):
            if not isinstance(c, dict):
                continue
            for a in c.get("assets") or []:
                if not isinstance(a, dict):
                    continue
                variants = [a] + [{**a, **v, "id": v.get("asset_id", v.get("id", a["id"]))}
                                  for v in a.get("versions") or [] if isinstance(v, dict)]
                for v in variants:
                    if not any(v.get(k) for k in VECTOR_KEYS + RASTER_KEYS):
                        continue
                    rows.append({"family": family, "app": app,
                                 "coll": collection_path(c["collection_url"]),
                                 "asset": v["id"], "name": v.get("display_name"),
                                 "visible": bool(v.get("visible")), "cfg": v})
    return rows


# ── choosing ────────────────────────────────────────────────────────────────────

def attrs(expr) -> list[str]:
    """Attributes a paint expression reads with ["get", name]."""
    out = []
    if isinstance(expr, list):
        if len(expr) == 2 and expr[0] == "get" and isinstance(expr[1], str):
            return [expr[1]]
        for e in expr:
            out += attrs(e)
    elif isinstance(expr, dict):
        for e in expr.values():
            out += attrs(e)
    return out


def variant_key(cfg: dict) -> str:
    paint = {**(cfg.get("default_style") or {}), **(cfg.get("outline_style") or {})}
    names = sorted(set(attrs(paint)))
    return "-".join(names) if names else "single"


def signature(cfg: dict, keys) -> str:
    return json.dumps({k: cfg.get(k) for k in keys}, sort_keys=True)


def bucket_tokens(coll: str) -> set[str]:
    b = coll.split("/", 1)[0].removeprefix("public-").removeprefix("private-")
    return {b, b.replace("-", "")}


def pick(rows: list[dict], keys) -> tuple[dict, list[dict]]:
    """Choose one config among rows that style the same thing. Returns (winner, options)."""
    groups = collections.defaultdict(list)
    for r in rows:
        groups[signature(r["cfg"], keys)].append(r)
    toks = bucket_tokens(rows[0]["coll"])
    options = []
    for sig, rs in groups.items():
        fams = sorted({r["family"] for r in rs})
        options.append({
            "rows": rs, "apps": fams, "votes": len(fams),
            "domain": any(f in toks or f.replace("-", "") in toks for f in fams),
            "detail": max(sum(1 for k in LEGEND_KEYS + ("outline_style", "tooltip_fields")
                              if r["cfg"].get(k)) for r in rs),
        })
    options.sort(key=lambda o: (-o["votes"], not o["domain"], -o["detail"], o["apps"]))
    return options[0], options


# ── building ────────────────────────────────────────────────────────────────────

def fetch_json(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except Exception as e:  # noqa: BLE001 — report and skip
        print(f"  ! cannot read {url}: {e}", file=sys.stderr)
        return None


def asset_path(href: str) -> str:
    return re.sub(r"^(https?://[^/]+/|s3://)", "", href)


def layer_type(cfg: dict) -> str:
    if cfg.get("layer_type"):
        return cfg["layer_type"]
    prefixes = {k.split("-")[0] for k in (cfg.get("default_style") or {})}
    for t in ("fill", "line", "circle"):
        if t in prefixes:
            return t
    return "fill"


def maplibre_style(cfg: dict, name: str, pmtiles_rel: str, source_layer: str,
                   description: str) -> dict:
    t = layer_type(cfg)
    paint = {k: v for k, v in (cfg.get("default_style") or {}).items() if k.startswith(t + "-")}
    layers = [{"id": f"{source_layer}-{t}", "type": t, "source": "data",
               "source-layer": source_layer, "paint": paint}]
    if t == "fill" and cfg.get("outline_style"):
        layers.append({"id": f"{source_layer}-outline", "type": "line", "source": "data",
                       "source-layer": source_layer,
                       "paint": {k: v for k, v in cfg["outline_style"].items()
                                 if k.startswith("line-")}})
    meta = {"description": description}
    legend = {k.removeprefix("legend_"): cfg[k] for k in LEGEND_KEYS if cfg.get(k)}
    if cfg.get("default_filter"):
        # The app hides some classes on load and its legend lists only the rest. A catalog
        # default shows every feature, so a partial class list would mislabel the map.
        legend.pop("classes", None)
    if legend:
        meta["glen:legend"] = legend
    if cfg.get("tooltip_fields"):
        meta["glen:tooltip_fields"] = cfg["tooltip_fields"]
    return {"version": 8, "name": name,
            "sources": {"data": {"type": "vector", "url": f"pmtiles://{pmtiles_rel}"}},
            "layers": layers, "metadata": meta}


def describe(cfg: dict, var: str) -> str:
    """One plain sentence on what the colours mean, from the paint itself."""
    paint = cfg.get("default_style") or {}
    color = next((v for k, v in paint.items() if k.endswith("-color")), None)
    if isinstance(color, list) and color and color[0] == "match":
        return f"Features coloured by category of {var}."
    if isinstance(color, list) and color and color[0] in ("interpolate", "step"):
        return f"Features shaded by the value of {var}."
    return "All features in one colour."


def render_entry(cfg: dict, asset: str, title: str) -> dict:
    e = {"title": title, "assets": [asset]}
    if cfg.get("colormap"):
        e["colormap_name"] = cfg["colormap"]
    if cfg.get("rescale"):
        lo, hi = (float(x) for x in str(cfg["rescale"]).split(","))
        e["rescale"] = [[lo, hi]]
    if cfg.get("nodata") is not None:
        e["nodata"] = cfg["nodata"]
    return e


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def build(rows: list[dict], out: Path, only: str | None) -> None:
    by_coll = collections.defaultdict(list)
    for r in rows:
        if not only or r["coll"].startswith(only.rstrip("/") + "/"):
            by_coll[r["coll"]].append(r)
    report = ["# Default styles derived from GLEN app configs", "",
              f"{len(rows)} styled layer configs, {len(by_coll)} collections.", ""]
    conflicts = []
    for coll, crow in sorted(by_coll.items()):
        doc = fetch_json(PUBLIC + coll)
        if not doc:
            report.append(f"- `{coll}`: collection unreadable, skipped")
            continue
        coll_dir = posixpath.dirname(coll)
        styles, renders = [], {}
        per_asset = collections.defaultdict(list)
        for r in crow:
            per_asset[r["asset"]].append(r)
        for asset_key, arows in sorted(per_asset.items()):
            asset = doc.get("assets", {}).get(asset_key)
            if not asset:
                report.append(f"- `{coll}` / `{asset_key}`: apps name an asset the STAC lacks")
                continue
            vrows = [r for r in arows if any(r["cfg"].get(k) for k in VECTOR_KEYS)]
            rrows = [r for r in arows if any(r["cfg"].get(k) for k in RASTER_KEYS)]
            if vrows and "pmtiles" in asset.get("type", "") + asset.get("href", ""):
                layers = asset.get("vector:layers") or []
                if not layers:
                    report.append(f"- `{coll}` / `{asset_key}`: no `vector:layers`, skipped")
                    continue
                pm_rel = posixpath.relpath(asset_path(asset["href"]),
                                           posixpath.join(coll_dir, "styles"))
                by_var = collections.defaultdict(list)
                for r in vrows:
                    by_var[variant_key(r["cfg"])].append(r)
                for var, vr in by_var.items():
                    win, opts = pick(vr, VECTOR_KEYS)
                    cfg = win["rows"][0]["cfg"]
                    stem = asset_key.removesuffix("-pmtiles")
                    key = f"style-{stem}" + ("" if var == "single" else f"-{slug(var)}")
                    title = win["rows"][0]["name"] or asset.get("title") or stem
                    if var != "single" and len(by_var) > 1:
                        title = f"{title} by {var}"
                    desc = describe(cfg, var)
                    sty = maplibre_style(cfg, title, pm_rel, layers[0], desc)
                    fname = key.removeprefix("style-") + ".json"
                    styles.append({"key": key, "file": fname, "style": sty, "title": title,
                                   "desc": desc, "votes": win["votes"],
                                   "visible": any(r["visible"] for r in vr)})
                    if len(opts) > 1:
                        conflicts.append((coll, key, opts))
            if rrows and asset.get("type", "").startswith("image/tiff"):
                win, opts = pick(rrows, RASTER_KEYS)
                cfg = win["rows"][0]["cfg"]
                renders[asset_key.removesuffix("-cog")] = render_entry(
                    cfg, asset_key, win["rows"][0]["name"] or asset.get("title") or asset_key)
                if len(opts) > 1:
                    conflicts.append((coll, f"renders.{asset_key}", opts))
        if not styles and not renders:
            continue
        styles.sort(key=lambda s: (-s["votes"], not s["visible"], s["key"]))
        cdir = out / coll_dir
        new = json.loads(json.dumps(doc))
        for i, s in enumerate(styles):
            (cdir / "styles").mkdir(parents=True, exist_ok=True)
            (cdir / "styles" / s["file"]).write_text(json.dumps(s["style"], indent=2) + "\n")
            new["assets"][s["key"]] = {
                "href": f"{PUBLIC}{coll_dir}/styles/{s['file']}", "type": STYLE_TYPE,
                "title": s["title"], "description": s["desc"],
                "roles": ["style", "default"] if i == 0 else ["style"]}
        if renders:
            new.setdefault("renders", {}).update(renders)
            ext = new.setdefault("stac_extensions", [])
            if RENDER_EXT not in ext:
                ext.append(RENDER_EXT)
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / posixpath.basename(coll)).write_text(json.dumps(new, indent=2) + "\n")
        report.append(f"- `{coll}`: {len(styles)} style(s)"
                      + (f", default `{styles[0]['key']}`" if styles else "")
                      + (f", {len(renders)} render(s)" if renders else ""))
    report += ["", f"## Conflicts ({len(conflicts)})", "",
               "First option listed is the one chosen.", ""]
    for coll, key, opts in conflicts:
        report.append(f"### `{coll}` → `{key}`")
        for o in opts:
            cfg = o["rows"][0]["cfg"]
            brief = json.dumps({k: cfg.get(k) for k in VECTOR_KEYS + RASTER_KEYS if cfg.get(k)})
            report.append(f"- {', '.join(o['apps'])}"
                          + (" (domain app)" if o["domain"] else "") + f": `{brief[:400]}`")
        report.append("")
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text("\n".join(report) + "\n")
    print(f"wrote {out}/report.md ({len(conflicts)} conflicts)", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--fetch", action="store_true", help="fetch configs from GitHub")
    src.add_argument("--configs", type=Path, help="dir of <repo>__layers-input*.json files")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only", help="bucket (or bucket/prefix) to limit output to")
    a = ap.parse_args()
    cfg_dir = a.configs or a.out / "_configs"
    if a.fetch:
        fetch_configs(cfg_dir)
    build(flatten(cfg_dir), a.out, a.only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
