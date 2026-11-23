#!/usr/bin/env python3
"""Record the WD-OECM source provenance before the staged raw is deleted (AGENTS.md Step 1b).

    set_source_provenance.py COLLECTION.json FILES BYTES

Adds one sentence to the description (source GDB, staged date, file count and size, where the
per-file sha256 manifest is) and a `metadata` asset for source-manifest.tsv. Idempotent.
"""
import json
import re
import sys

path, files, nbytes = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
doc = json.load(open(path))
before = json.loads(json.dumps(doc))
MARK = "Source: the file geodatabase WDOECM_May2026_Public.gdb"
para = (f"{MARK} from Protected Planet (May 2026 release), staged here on 2026-05-22 "
        f"({files} files, {nbytes:,} bytes); the staged copy was deleted after the build. Each "
        f"file's size and sha256 are in source-manifest.tsv beside this collection.")
d = doc["description"]
d = re.sub(re.escape(MARK) + r".*?source-manifest\.tsv beside this collection\.", para, d, flags=re.S) if MARK in d \
    else d.rstrip() + "\n\n" + para
doc["description"] = d
doc["assets"]["source-manifest"] = {
    "href": "https://s3-west.nrp-nautilus.io/public-wdpa/wdoecm-may-2026/source-manifest.tsv",
    "type": "text/tab-separated-values",
    "title": "Source file manifest",
    "description": "Size and sha256 of each file of the source WDOECM_May2026_Public.gdb, staged 2026-05-22.",
    "roles": ["metadata"],
}
changed = {k for k in set(before) | set(doc) if before.get(k) != doc.get(k)}
assert changed <= {"description", "assets"}, changed
assert "/raw/" not in json.dumps(doc)
json.dump(doc, open(path, "w"), indent=2, ensure_ascii=False)
print("collection:", sorted(changed))
