#!/usr/bin/env python3
"""Turn a grouping collection into a STAC Catalog (#762, nested catalogs, flat collections).

    scripts/to-catalog.py IN.json OUT.json

A node with children and no data assets of its own is a Catalog, not a Collection. This keeps
id, title, description, links (self, parent, children, root and the rest), keywords, providers
and citations; it drops what only a Collection carries (license, extent, summaries, item_assets,
table:columns, renders, assets) and the extensions that described them. A README asset becomes a
`describedby` link. It refuses a node that still holds data assets: move them into a child
collection first. Publish through stac-publish-guard.py with STAC_GUARD_ALLOW=columns when the
live node had a column dictionary.
"""
import json
import sys

DROP = ("license", "extent", "summaries", "item_assets", "assets", "table:columns", "renders")
EXT_DROP = ("table", "render", "raster", "classification", "file")
NON_DATA = {"style", "thumbnail", "metadata", "overview"}


def to_catalog(d: dict) -> dict:
    assets = d.get("assets") or {}
    data = [k for k, a in assets.items() if not set(a.get("roles") or []) & NON_DATA
            and not (a.get("href") or "").endswith(".md")]
    if data:
        raise SystemExit(f"{d.get('id')}: still holds data assets {data}; move them to a child first")
    out = {k: v for k, v in d.items() if k not in DROP}
    for a in assets.values():
        if (a.get("href") or "").endswith(".md"):
            out.setdefault("links", []).append({"rel": "describedby", "href": a["href"],
                                                "type": "text/markdown", "title": a.get("title") or "README"})
    out["type"] = "Catalog"
    ext = [e for e in d.get("stac_extensions", []) if not any(x in e for x in EXT_DROP)]
    if ext:
        out["stac_extensions"] = ext
    else:
        out.pop("stac_extensions", None)
    return out


if __name__ == "__main__":
    src, dst = sys.argv[1:3]
    json.dump(to_catalog(json.load(open(src))), open(dst, "w"), indent=2)
