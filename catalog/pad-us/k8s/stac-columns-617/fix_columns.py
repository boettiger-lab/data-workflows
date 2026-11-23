#!/usr/bin/env python3
"""Match a PAD-US 4.1 collection's table:columns to the cng-datasets 0.12.0 rebuild (#617).

    fix_columns.py <collection.json>          # edits the file in place

The rebuild no longer writes the `bbox` struct column and now keeps the geodatabase's
OBJECTID in the parquet, hex and PMTiles. This drops `bbox` and adds `OBJECTID` after
`_cng_fid` in the collection's column dictionary and in every asset that lists columns.
Running it twice is a no-op.
"""
import json
import sys

OBJECTID = {
    "name": "OBJECTID",
    "type": "int64",
    "description": "Feature ID in the PAD-US 4.1 geodatabase layer. It is not stable across "
                   "PAD-US editions; use _cng_fid to join this collection's files.",
}


def fix(cols, describe):
    cols = [c for c in cols if c["name"] != "bbox"]
    if not any(c["name"] == "OBJECTID" for c in cols):
        entry = OBJECTID if describe else {k: OBJECTID[k] for k in ("name", "type")}
        at = next((i + 1 for i, c in enumerate(cols) if c["name"] == "_cng_fid"), 0)
        cols.insert(at, dict(entry))
    return cols


def main(path):
    doc = json.load(open(path))
    if "table:columns" in doc:
        doc["table:columns"] = fix(doc["table:columns"], True)
    for asset in doc.get("assets", {}).values():
        if "table:columns" in asset:
            asset["table:columns"] = fix(asset["table:columns"], False)
    json.dump(doc, open(path, "w"), indent=2, ensure_ascii=False)
    print(f"{doc['id']}: columns updated")


if __name__ == "__main__":
    main(sys.argv[1])
