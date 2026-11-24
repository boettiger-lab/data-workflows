"""Classification v2 class names (Portolan PTL-EXT-001 / PTL-CLS-002, #761), applied to a LIVE collection.

    fix_classes.py <collection.json>     # edits the file in place

In classification v2, `name` is a machine identifier (^[0-9A-Za-z-_]+$) and `title` the label.
Our classes carry the label in `name` and have no `title`. For every `classification:classes`
list in the collection (asset, raster band or anywhere else), a class with no `title`:
  - gets `title` = its current `name`, unchanged (a class with no `name` -- the two WHP hex
    assets keep the label in `description` -- takes its `description`, which stays too);
  - gets `name` = a lowercase slug of that label, with `-<value>` appended when two classes in
    the list would share a slug (or the label has no letters or digits).
`value`, `description`, `color_hint` and every other key stay as they are. A classification
v1.1.0 schema URI moves to v2.0.0, which defines `title`. Idempotent: a class that already
has a `title` is left alone. Legends read `title` first from glen v4.2.1 (SchmidtDSE/glen#528).
"""
import json
import re
import sys
import unicodedata

V1 = "https://stac-extensions.github.io/classification/v1.1.0/schema.json"
V2 = "https://stac-extensions.github.io/classification/v2.0.0/schema.json"


def slug(label):
    s = unicodedata.normalize("NFKD", str(label)).encode("ascii", "ignore").decode()
    return re.sub(r"[^0-9a-z]+", "-", s.lower()).strip("-")


def value_tag(v):
    return re.sub(r"[^0-9A-Za-z_-]", "-", str(v))


def fix_list(classes):
    todo = [c for c in classes if isinstance(c, dict) and "title" not in c
            and (c.get("name") or c.get("description"))]
    if not todo:
        return 0
    taken = {c["name"] for c in classes if isinstance(c, dict) and "title" in c and c.get("name")}
    labels = [c.get("name") or c["description"] for c in todo]
    slugs = [slug(x) for x in labels]
    for c, label, s in zip(todo, labels, slugs):
        if not s or slugs.count(s) > 1 or s in taken:
            s = f"{s}-{value_tag(c.get('value'))}".strip("-")
        if s in taken:  # still clashes; should not happen with distinct values
            raise ValueError(f"slug collision: {s!r}")
        taken.add(s)
        c["title"] = label
        c["name"] = s
    return len(todo)


def walk(o):
    n = 0
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "classification:classes" and isinstance(v, list):
                n += fix_list(v)
            else:
                n += walk(v)
    elif isinstance(o, list):
        for v in o:
            n += walk(v)
    return n


def fix(doc):
    n = walk(doc)
    exts = doc.get("stac_extensions", [])
    if V1 in exts:
        doc["stac_extensions"] = [V2 if e == V1 else e for e in exts]
        doc["stac_extensions"] = list(dict.fromkeys(doc["stac_extensions"]))
    return n


def main(path):
    doc = json.load(open(path))
    n = fix(doc)
    with open(path, "w") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"{path}: {n} classes")


if __name__ == "__main__":
    main(sys.argv[1])
