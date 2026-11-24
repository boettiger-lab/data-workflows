"""Portolan fixes on live collections (#761): a thumbnail asset (PTL-VIZ-001) and a WGS84 bbox clamp (PTL-BBX-001).

Usage:
  fix_viz_bbox.py thumb <collection.json> <render-name>   add the thumbnail asset beside the collection
  fix_viz_bbox.py clamp <collection.json>                 clamp every extent bbox to [-180, -90, 180, 90]
The thumbnail PNGs were drawn by scripts/thumbnail.py from the named COG render.
"""
import json
import sys

NRP = "https://s3-west.nrp-nautilus.io"


def thumb(c, render):
    self_href = next(l["href"] for l in c["links"] if l.get("rel") == "self")
    c.setdefault("assets", {})["thumbnail"] = {
        "href": self_href.rsplit("/", 1)[0] + "/thumbnail.png",
        "type": "image/png",
        "roles": ["thumbnail"],
        "title": "Thumbnail",
        "description": f"Preview drawn from the collection's render {render}.",
    }


def clamp(c):
    for b in c["extent"]["spatial"]["bbox"]:
        n = len(b) // 2                      # 2 for [W,S,E,N], 3 for [W,S,zmin,E,N,zmax]
        b[0], b[1] = max(b[0], -180), max(b[1], -90)
        b[n], b[n + 1] = min(b[n], 180), min(b[n + 1], 90)


def main(op, path, *rest):
    c = json.load(open(path))
    if op == "thumb":
        thumb(c, rest[0])
    elif op == "clamp":
        clamp(c)
    else:
        sys.exit(f"unknown op {op}")
    with open(path, "w") as f:
        json.dump(c, f, indent=2, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
