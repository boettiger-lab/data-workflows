#!/usr/bin/env python3
"""Point the WorldCover Peru provenance at the kept tile manifest, not at raw/ (AGENTS.md Step 1b).

    set_provenance.py COLLECTION.json README.md

The staged tiles under raw/worldcover-2021/ are deleted after the build. The tile manifest
(size, sha256, AWS ETag, URL, download time per tile) is kept beside the collection as
source-manifest.tsv. This rewrites the two provenance sentences in the collection description
and the README, and adds the manifest as a `metadata` asset. Idempotent.
"""
import json
import sys

stac_path, readme_path = sys.argv[1:3]
doc = json.load(open(stac_path))
before = json.loads(json.dumps(doc))

OLD = ("downloaded 2026-11-18 and kept unchanged under raw/worldcover-2021/map/ (806,493,731 bytes "
       "in total). The size, sha256 and AWS ETag of each tile, with its source URL and download time, "
       "are in raw/worldcover-2021/manifest.tsv.")
NEW = ("downloaded 2026-11-18 (806,493,731 bytes in total); the staged copies were deleted after the "
       "build. The size, sha256 and AWS ETag of each tile, with its source URL and download time, are "
       "in source-manifest.tsv beside this collection.")
d = doc["description"]
assert OLD in d or NEW in d, "provenance sentence not found"
doc["description"] = d.replace(OLD, NEW)
doc["assets"]["source-manifest"] = {
    "href": "https://s3-west.nrp-nautilus.io/public-land-cover/worldcover-2021/peru/source-manifest.tsv",
    "type": "text/tab-separated-values",
    "title": "Source tile manifest",
    "description": ("One row per WorldCover 2021 v200 source tile used: size, sha256, AWS ETag, "
                    "source URL and download time (2026-11-18)."),
    "roles": ["metadata"],
}
changed = {k for k in set(before) | set(doc) if before.get(k) != doc.get(k)}
assert changed <= {"description", "assets"}, changed
json.dump(doc, open(stac_path, "w"), indent=2, ensure_ascii=False)
print("collection:", sorted(changed))

md = open(readme_path).read()
OLD_MD = ("The 26 source tiles are kept unchanged under `raw/worldcover-2021/map/` (806,493,731 bytes). Each\n"
          "tile's size, sha256, AWS ETag, URL and download time are in `raw/worldcover-2021/manifest.tsv`.")
NEW_MD = ("The 26 source tiles (806,493,731 bytes) were downloaded 2026-11-18; the staged copies were deleted\n"
          "after the build. Each tile's size, sha256, AWS ETag, URL and download time are in\n"
          "`source-manifest.tsv` beside this README.")
assert OLD_MD in md or NEW_MD in md, "README provenance not found"
md = md.replace(OLD_MD, NEW_MD)
assert "raw/worldcover-2021" not in md
open(readme_path, "w").write(md)
print("README: provenance rewritten")
