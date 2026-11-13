#!/usr/bin/env python3
"""Repoint the three STAC assets that were published from a raw/ prefix (#721, #545, #656).

    move_hrefs.py <collection.json>          # edits the file in place

The collection is recognised by its `id`. Every string in it that names the old object
(https or s3:// form) is rewritten to the new location, so the asset href and any prose that
quotes the path move together. Strings naming other raw/ objects, such as the OBIS staged
source and its MANIFEST, are left alone: those are genuine upstream input. Running it twice
is a no-op. It exits non-zero if the collection still points into raw/ afterwards.
"""
import json
import sys

PUBLIC = "https://s3-west.nrp-nautilus.io/"

# collection id -> (old key, new key, old asset key, new asset key)
MOVES = {
    "ghs-pop-2020": ("public-population/raw/ghs-pop-2020-cog.tif",
                     "public-population/ghs-pop-2020-cog.tif", None, None),
    "landvote": ("public-tpl/landvote/raw/Measures.csv",
                 "public-tpl/landvote/Measures.csv", "landvote-raw-csv", "landvote-measures-csv"),
    "obis-derived": ("public-obis/raw/licenses.tsv",
                     "public-obis/2026-09-09/licenses.tsv", None, None),
}


def rewrite(node, old, new):
    if isinstance(node, str):
        for a, b in ((PUBLIC + old, PUBLIC + new), ("s3://" + old, "s3://" + new),
                     ("staged alongside the data at s3://" + new,
                      "published alongside the data at s3://" + new)):
            node = node.replace(a, b)
        return node
    if isinstance(node, list):
        return [rewrite(v, old, new) for v in node]
    if isinstance(node, dict):
        return {k: rewrite(v, old, new) for k, v in node.items()}
    return node


def main(path):
    doc = json.load(open(path))
    old, new, old_key, new_key = MOVES[doc["id"]]
    doc = rewrite(doc, old, new)
    if old_key and old_key in doc["assets"]:
        doc["assets"] = {(new_key if k == old_key else k): v for k, v in doc["assets"].items()}
    left = [k for k, a in doc["assets"].items() if "/raw/" in a["href"]]
    if left:
        sys.exit(f"{doc['id']}: still published from raw/: {left}")
    json.dump(doc, open(path, "w"), indent=2, ensure_ascii=False)
    print(f"{doc['id']}: {old} -> {new}")


if __name__ == "__main__":
    main(sys.argv[1])
