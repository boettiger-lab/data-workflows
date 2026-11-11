#!/usr/bin/env python3
"""Guard a STAC collection about to replace the live one on NRP.

A publish job that uploads a collection built from JSON kept outside the repo (a ConfigMap,
a gen_stac.py run) replaces whatever is live. Work done on the live collection since that
JSON was written is lost, and nothing in the job knows. Three such changes have been made
catalog-wide (#881 styles, #890 column dictionary and rel pmtiles links), plus asset-key
renames such as Kaiparowits. This guard runs between building the new file and the upload:

  stac-publish-guard.py NEW.json LIVE.json

It edits NEW.json in place to KEEP what the new file lacks:
  * style assets (`style` role), `renders`, and the render extension (#881)
  * `rel: pmtiles` links whose file is still a PMTiles asset of the new collection (#890)

and REFUSES (exit 3, NEW.json untouched) when the new file would undo a change:
  * `columns`: the live collection has a `table:columns` dictionary and the new one has none
    (regenerate it in the dictionary shape, skill stac-authoring)
  * `keys`: an asset file is live under one key and new under another (an asset-key rename
    reverted, e.g. Kaiparowits `m_adit-pmtiles` back to `kaiparowits-m-adit-pmtiles`)

A deliberate change of either kind sets STAC_GUARD_ALLOW=columns,keys (or one of them) in the
job, which records the decision where a reviewer sees it.

A missing or unreadable LIVE.json means a new collection: nothing to keep, nothing refused.
Exit 0 means NEW.json is safe to upload.

In a job (the image has no repo checkout, so fetch it; `curl -f` fails closed):

  curl -fsSL https://raw.githubusercontent.com/boettiger-lab/data-workflows/main/scripts/stac-publish-guard.py -o /tmp/stac-guard/guard.py --create-dirs
  guard_stac() {  # guard_stac <new.json> <nrp:path>; exits the job if the guard refuses
    case "$2" in *.json) ;; *) return 0 ;; esac
    rclone cat "$2" > /tmp/stac-guard/live.json 2>/dev/null || : > /tmp/stac-guard/live.json
    python3 /tmp/stac-guard/guard.py "$1" /tmp/stac-guard/live.json || exit 1
  }
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse

REFUSE = 3


def _base(doc: dict) -> str:
    return next((l.get("href", "") for l in doc.get("links", []) if l.get("rel") == "self"), "")


def _absolute(doc: dict, href: str) -> str:
    return urllib.parse.urljoin(_base(doc), href or "")


def _is_pmtiles(asset: dict) -> bool:
    return "pmtiles" in asset.get("type", "")


def guard(new: dict, live: dict, allow: set[str]) -> tuple[list[str], list[str]]:
    """Mutates `new`. Returns (kept, refused) human-readable lists."""
    kept, refused = [], []

    # refusals first: a refused file is not edited
    if live.get("table:columns") and not new.get("table:columns") and "columns" not in allow:
        refused.append("columns: the live collection has a table:columns dictionary and this "
                       "file has none; regenerate it in the dictionary shape (skill "
                       "stac-authoring), or set STAC_GUARD_ALLOW=columns")
    live_keys = {_absolute(live, a.get("href")): k for k, a in live.get("assets", {}).items()}
    for key, asset in new.get("assets", {}).items():
        was = live_keys.get(_absolute(new, asset.get("href")))
        if was and was != key and was not in new.get("assets", {}) and "keys" not in allow:
            refused.append(f"keys: asset '{key}' is live as '{was}'; this would revert an asset-"
                           f"key rename, or set STAC_GUARD_ALLOW=keys")
    if refused:
        return kept, refused

    assets = new.setdefault("assets", {})
    # Style keys name their PMTiles file: style-<stem>[-<variant>], style-fallback-<stem>.
    stems = sorted((k.removesuffix("-pmtiles") for k, a in assets.items() if _is_pmtiles(a)),
                   key=len, reverse=True)
    def stem_of(k):
        k = k.removeprefix("style-fallback-").removeprefix("style-")
        return next((s for s in stems if k == s or k.startswith(s + "-")), None)
    own = {k: a for k, a in assets.items() if "style" in (a.get("roles") or [])
           and not k.startswith("style-fallback-")}
    styled = {stem_of(k) for k in own}
    defaulted = {stem_of(k) for k, a in own.items() if "default" in a["roles"]}
    styles = {k: json.loads(json.dumps(a)) for k, a in live.get("assets", {}).items()
              if "style" in (a.get("roles") or []) and k not in assets
              and not (k.startswith("style-fallback-") and stem_of(k) in styled)}
    for k, a in styles.items():  # one default per PMTiles file
        if stem_of(k) in defaulted and "default" in a["roles"]:
            a["roles"] = [r for r in a["roles"] if r != "default"]
    assets.update(styles)
    if styles:
        kept.append(f"{len(styles)} style asset(s)")
    rendered = {a for r in new.get("renders", {}).values() for a in r.get("assets", [])}
    renders = {k: v for k, v in live.get("renders", {}).items() if k not in new.get("renders", {})
               and not (v.get("assets") and set(v["assets"]) <= rendered)}
    if renders:
        new.setdefault("renders", {}).update(renders)
        kept.append(f"{len(renders)} render(s)")
    for ext in live.get("stac_extensions", []):
        if "/render/" in ext and ext not in new.setdefault("stac_extensions", []):
            new["stac_extensions"].append(ext)

    tiles = {_absolute(new, a.get("href")) for a in assets.values() if _is_pmtiles(a)}
    have = {_absolute(new, l.get("href")) for l in new.get("links", []) if l.get("rel") == "pmtiles"}
    links = [l for l in live.get("links", []) if l.get("rel") == "pmtiles"
             and _absolute(live, l.get("href")) in tiles - have]
    if links:
        new.setdefault("links", []).extend(links)
        kept.append(f"{len(links)} rel pmtiles link(s)")
    return kept, refused


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    new_path, live_path = argv[1], argv[2]
    with open(new_path) as f:
        new = json.load(f)  # an unreadable NEW file is a broken job: let it fail loudly
    try:
        with open(live_path) as f:
            live = json.load(f)
    except (OSError, ValueError):
        print(f"stac-publish-guard: no live collection for {new_path}; publishing as new")
        return 0
    allow = {a.strip() for a in os.environ.get("STAC_GUARD_ALLOW", "").split(",") if a.strip()}
    kept, refused = guard(new, live, allow)
    if refused:
        for r in refused:
            print(f"stac-publish-guard: REFUSED {new_path}: {r}", file=sys.stderr)
        return REFUSE
    if kept:
        with open(new_path, "w") as f:
            json.dump(new, f, indent=2, ensure_ascii=False)
        print(f"stac-publish-guard: {new_path}: kept {', '.join(kept)} from the live collection")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
