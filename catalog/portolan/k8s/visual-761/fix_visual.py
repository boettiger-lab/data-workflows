"""Give every PMTiles asset the `visual` role (Portolan PTL-AST-009, #761).

    fix_visual.py <in.json> <out.json>     # exits 3 when nothing changes

A PMTiles asset (media type application/vnd.pmtiles, or an href ending .pmtiles) that is
not a `source` asset and lacks `visual` gets it appended; its other roles stay. Nothing
else changes. Idempotent.
"""
import json
import re
import sys

PM = re.compile(r"\.pmtiles([?#]|$)", re.I)


def fix(doc):
    for a in (doc.get("assets") or {}).values():
        if not isinstance(a, dict):
            continue
        if a.get("type") != "application/vnd.pmtiles" and not PM.search(str(a.get("href", ""))):
            continue
        roles = a.get("roles") or []
        if "source" in roles or "visual" in roles:
            continue
        a["roles"] = list(roles) + ["visual"]
    return doc


def main(src, dst):
    raw = open(src).read()
    doc = fix(json.loads(raw))
    if json.loads(raw) == doc:
        sys.exit(3)
    with open(dst, "w") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    main(*sys.argv[1:3])
