#!/usr/bin/env python3
"""Render a collection's thumbnail from its default style or render (#889, PORTO-CORE-067).

    scripts/thumbnail.py <collection-url> --out DIR [--size 512]

Writes DIR/<bucket>/<path>/thumbnail.png and DIR/<bucket>/<path>/stac-collection.json, the
collection with a `thumbnail` asset (role `thumbnail`, image/png) pointing at it. A collection
file not named stac-collection.json gets <stem>-thumbnail.png, so neighbours do not collide. Publish both
with the usual guard (AGENTS.md Step 5); the guard keeps a live thumbnail the new file lacks.

What it draws, in order of preference:
  * PMTiles: the collection's first default style (by asset key), drawn by MapLibre GL JS in
    headless Chromium (Playwright) over the collection's bounding box, or a crop at the
    tiles' minimum zoom when the box would fit below it. Symbol layers are
    dropped, so a thumbnail needs no glyphs or sprites.
  * COG: the collection's last render by name whose asset is a GeoTIFF (the newest year of a
    series keyed by year), drawn by TiTiler's
    /cog/preview.png with the render's colormap, rescale and nodata. A band with a scale or
    offset is unscaled first, as the map apps do, so the rescale is in real units.
A collection with neither gets no thumbnail; the script says so and exits 2.

Needs Playwright with Chromium for PMTiles (`pip install playwright; playwright install
chromium`). MapLibre and pmtiles load from unpkg at pinned versions.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request

TITILER = os.environ.get("TITILER_URL", "https://titiler.nrp-nautilus.io")
MAPLIBRE = "https://unpkg.com/maplibre-gl@5.23.0/dist"
PMTILES = "https://unpkg.com/pmtiles@3.2.1/dist/pmtiles.js"
BACKGROUND = "#f4f4f2"
UA = {"User-Agent": "data-workflows-thumbnail"}


def fetch(url: str) -> bytes:
    for attempt in range(3):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def self_href(doc: dict, fallback: str) -> str:
    return next((l["href"] for l in doc.get("links", []) if l.get("rel") == "self"), fallback)


def absolute(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href)


def thumb_name(collection_url: str) -> str:
    """thumbnail.png beside stac-collection.json; <stem>-thumbnail.png beside any other collection
    file, so collections sharing a directory (public-cpad) do not overwrite each other's."""
    name = urllib.parse.urlparse(collection_url).path.rsplit("/", 1)[-1]
    if name == "stac-collection.json":
        return "thumbnail.png"
    return name.removesuffix(".json").removesuffix("-stac-collection").removesuffix("-stac") + "-thumbnail.png"


def coll_path(url: str) -> str:
    """public-x/a/b/stac-collection.json from any https URL of the collection."""
    return urllib.parse.urlparse(url).path.lstrip("/")


def pmtiles_header(url: str) -> tuple[list[float], int] | None:
    """([w, s, e, n], min zoom) from a PMTiles v3 header (bounds at bytes 102-117 as int32
    degrees x 1e7, min zoom at byte 100)."""
    import struct
    try:
        req = urllib.request.Request(url, headers={**UA, "Range": "bytes=0-126"})
        h = urllib.request.urlopen(req, timeout=60).read()
        if h[:7] != b"PMTiles":
            return None
        return [v / 1e7 for v in struct.unpack_from("<iiii", h, 102)], h[100]
    except Exception:
        return None


def bbox(doc: dict, fallback: list[float] | None = None) -> list[float]:
    b = doc.get("extent", {}).get("spatial", {}).get("bbox") or [[-180, -85, 180, 85]]
    b = b if isinstance(b[0], (int, float)) else b[0]  # tolerate a flat (malformed) bbox
    if len(b) not in (4, 6) or not all(isinstance(v, (int, float)) for v in b):
        where = "the tile bounds" if fallback else "the whole world"
        print(f"  unusable bbox {b!r}; using {where}", file=sys.stderr)
        b = fallback or [-180, -85, 180, 85]
    w, s, e, n = (b[0], b[1], b[3], b[4]) if len(b) == 6 else b[:4]
    if e < w:  # crosses the antimeridian: show the whole width
        w, e = -180, 180
    return [max(w, -180), max(s, -85), min(e, 180), min(n, 85)]


def default_style(doc: dict) -> tuple[str, dict] | None:
    for k in sorted(doc.get("assets", {})):
        a = doc["assets"][k]
        if "style" in (a.get("roles") or []) and "default" in a["roles"]:
            return k, a
    return None


def cog_render(doc: dict) -> tuple[str, dict, dict] | None:
    assets = doc.get("assets", {})
    # Last by name: a series keyed by year (CRW annual `*-cog-1985` … `-2025`) shows its newest.
    for name, r in sorted((doc.get("renders") or {}).items(), reverse=True):
        for k in r.get("assets", []):
            a = assets.get(k, {})
            if "geotiff" in (a.get("type") or "") or (a.get("href") or "").endswith((".tif", ".tiff")):
                return name, r, a
    return None


# ---------------------------------------------------------------------------- COG

def cog_preview_url(base: str, render: dict, asset: dict, size: int) -> str:
    q = [("url", absolute(base, asset["href"])), ("max_size", str(size))]
    for rng in render.get("rescale") or []:
        q.append(("rescale", ",".join(str(v) for v in rng)))
    if render.get("colormap_name"):
        q.append(("colormap_name", render["colormap_name"]))
    if render.get("colormap"):
        q.append(("colormap", json.dumps(render["colormap"])))
    if render.get("nodata") is not None:
        q.append(("nodata", str(render["nodata"])))
    for b in render.get("bidx") or []:
        q.append(("bidx", str(b)))
    if render.get("expression"):
        q.append(("expression", render["expression"]))
    if render.get("resampling"):
        q.append(("resampling", render["resampling"]))
    bands = asset.get("raster:bands") or []
    if any(b.get("scale") not in (None, 1) or b.get("offset") not in (None, 0) for b in bands):
        q.append(("unscale", "true"))
    return f"{TITILER}/cog/preview.png?" + urllib.parse.urlencode(q)


def colormap_locally(base: str, render: dict, asset: dict, size: int) -> bytes:
    """Fetch the raw band as .npy and apply a categorical colormap here, for a colormap too
    long to send in a URL (LANDFIRE vegetation types have hundreds of classes)."""
    import io
    import numpy as np
    from PIL import Image
    bare = {k: v for k, v in render.items() if k not in ("colormap", "rescale", "colormap_name")}
    url = cog_preview_url(base, bare, asset, size).replace("/preview.png?", "/preview.npy?")
    arr = np.load(io.BytesIO(fetch(url)))
    data, mask = arr[0], arr[-1]
    rgba = np.zeros(data.shape + (4,), dtype=np.uint8)
    for code, colour in render["colormap"].items():
        c = colour.lstrip("#") if isinstance(colour, str) else None
        rgb = [int(c[i:i + 2], 16) for i in (0, 2, 4)] if c else list(colour)[:3]
        rgba[data == float(code)] = rgb + [255]
    rgba[mask == 0] = 0
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------- PMTiles

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="{ml}/maplibre-gl.css">
<script src="{ml}/maplibre-gl.js"></script><script src="{pm}"></script>
<style>html,body{{margin:0}}#map{{width:{w}px;height:{h}px}}</style></head>
<body><div id="map"></div><script>
const protocol = new pmtiles.Protocol();
maplibregl.addProtocol("pmtiles", protocol.tile);
const map = new maplibregl.Map({{container: "map", style: {style}, bounds: {bounds},
  fitBoundsOptions: {{padding: 12}}, attributionControl: false, interactive: false,
  canvasContextAttributes: {{preserveDrawingBuffer: true}}, fadeDuration: 0}});
map.on("error", e => {{ window.mapErrors = (window.mapErrors || []).concat(String(e.error && e.error.message)); }});
// Below the tiles' minimum zoom nothing is drawn: show a crop at that zoom instead.
if (map.getZoom() < {minzoom}) map.jumpTo({{zoom: {minzoom}}});
map.once("idle", () => {{ window.done = true; }});
</script></body></html>"""


def style_for_thumbnail(style: dict, style_url: str) -> dict:
    s = json.loads(json.dumps(style))
    for src in s.get("sources", {}).values():
        url = src.get("url", "")
        if url.startswith("pmtiles://") and not url.startswith("pmtiles://http"):
            src["url"] = "pmtiles://" + absolute(style_url, url[len("pmtiles://"):])
        elif url and not url.startswith(("http", "pmtiles://")):
            src["url"] = absolute(style_url, url)
    s["layers"] = [l for l in s.get("layers", []) if l.get("type") != "symbol"]
    if not any(l.get("type") == "background" for l in s["layers"]):
        s["layers"].insert(0, {"id": "thumbnail-background", "type": "background",
                               "paint": {"background-color": BACKGROUND}})
    s.pop("sprite", None)
    s.pop("glyphs", None)
    return s


def render_pmtiles(style: dict, bounds: list[float], w: int, h: int, min_zoom: int = 0) -> bytes:
    from playwright.sync_api import sync_playwright
    w_, s_, e_, n_ = bounds
    html = PAGE.format(ml=MAPLIBRE, pm=PMTILES, w=w, h=h, style=json.dumps(style), minzoom=min_zoom,
                       bounds=json.dumps([[w_, s_], [e_, n_]]))
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": w, "height": h})
        page.set_content(html)
        page.wait_for_function("window.done === true", timeout=120_000)
        errors = page.evaluate("window.mapErrors || []")
        png = page.locator("#map").screenshot()
        browser.close()
    if errors:
        print("  map errors:", "; ".join(sorted(set(errors)))[:300], file=sys.stderr)
    return png


# ---------------------------------------------------------------------------- main

def thumbnail(url: str, size: int) -> tuple[dict, bytes, str] | None:
    doc = json.loads(fetch(url))
    base = self_href(doc, url)
    st = default_style(doc)
    if st:
        key, asset = st
        style_url = absolute(base, asset["href"])
        style = style_for_thumbnail(json.loads(fetch(style_url)), style_url)
        tiles = next((src["url"][len("pmtiles://"):] for src in style.get("sources", {}).values()
                      if str(src.get("url", "")).startswith("pmtiles://")), None)
        head = pmtiles_header(tiles) if tiles else None
        png = render_pmtiles(style, bbox(doc, head and head[0]), size, round(size * 3 / 4),
                             min_zoom=head[1] if head else 0)
        how = f"default style {key}"
    else:
        cr = cog_render(doc)
        if not cr:
            return None
        name, render, asset = cr
        url = cog_preview_url(base, render, asset, size)
        if len(url) > 6000 and render.get("colormap"):  # hundreds of classes: too long a URL
            png = colormap_locally(base, render, asset, size)
        else:
            png = fetch(url)
        how = f"render {name}"
    new = json.loads(json.dumps(doc))
    new.setdefault("assets", {})["thumbnail"] = {
        "href": absolute(base, thumb_name(base)), "type": "image/png", "roles": ["thumbnail"],
        "title": "Thumbnail", "description": f"Preview drawn from the collection's {how}."}
    return new, png, how


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("url")
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--size", type=int, default=512)
    a = ap.parse_args()
    r = thumbnail(a.url, a.size)
    if r is None:
        print(f"{a.url}: no default style or COG render; no thumbnail")
        return 2
    new, png, how = r
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        print(f"{a.url}: renderer returned no PNG", file=sys.stderr)
        return 1
    out = a.out / coll_path(self_href(new, a.url))
    out.parent.mkdir(parents=True, exist_ok=True)
    (out.parent / thumb_name(self_href(new, a.url))).write_bytes(png)
    out.write_text(json.dumps(new, indent=2) + "\n")
    print(f"{coll_path(self_href(new, a.url))}: thumbnail from {how}, {len(png)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
