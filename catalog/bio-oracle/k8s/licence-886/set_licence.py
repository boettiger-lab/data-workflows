#!/usr/bin/env python3
"""Record Bio-ORACLE's GPL grant on one collection, in place (#886).

    set_licence.py COLLECTION.json

Bio-ORACLE's download page (https://bio-oracle.org/downloads-to-email.php) says the data
"is released under the GNU General Public License" and names no version. The GPL's own
terms let a work that names no version be used under any version the FSF has published,
which is SPDX `GPL-1.0-or-later`. The collections carried `license: other` with a link to
that page; this sets the SPDX id and states the terms in the description.

Changes `license` and `description` only, and is idempotent: a collection already carrying
the id and the sentence is written back unchanged.
"""
import json
import sys

SPDX = "GPL-1.0-or-later"
SENTENCE = (
    "Licence: Bio-ORACLE releases its data under the GNU General Public License without "
    "naming a version, which the GPL treats as permission to use any version (SPDX "
    "GPL-1.0-or-later). The data may be used and redistributed under those terms."
)

path = sys.argv[1]
doc = json.load(open(path))
before = dict(doc)

if doc.get("license") not in ("other", SPDX):
    sys.exit(f"{path}: unexpected license {doc.get('license')!r}, refusing to change it")
doc["license"] = SPDX
if "GNU General Public License" not in doc.get("description", ""):
    doc["description"] = doc.get("description", "").rstrip() + "\n\n" + SENTENCE

changed = {k for k in set(before) | set(doc) if before.get(k) != doc.get(k)}
assert changed <= {"license", "description"}, changed
json.dump(doc, open(path, "w"), indent=2, ensure_ascii=False)
print(f"{doc['id']}: {', '.join(sorted(changed)) or 'unchanged'}")
