#!/usr/bin/env python3
"""Correct dead links, missing citations and default styles on LIVE collections, in place (#949).

    apply.py fixes.json COLLECTION_PATH COLLECTION.json

Each fix (keyed by `collection`, the path inside the bucket host) may carry:
  title, description          set outright
  set                         {top-level field: value}, set outright (e.g. sci:citation)
  license, license_links      the SPDX id, and the links that replace every rel: license link
  description_replace         [old, new] pairs on the description
  description_append          appended once
  providers                   {old name: replacement provider object}
  links_replace               {old href: replacement link object}
  links_add                   links appended when no link has that href
  columns                     {column name: new description} in table:columns
  asset_text_replace          {asset key: [[old, new], ...]} on that asset's title and description
  assets_set                  {asset key: asset object}, set outright
  asset_roles                 {asset key: roles}, set on an existing asset (e.g. to drop `default`)
and the `evidence` its text came from. A replacement whose old text is absent is reported,
never guessed at. Touches nothing else; a second run changes nothing.
"""
import json
import sys

fixes, coll, path = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
f = next((x for x in fixes if x["collection"] == coll), None)
if f is None:
    sys.exit(f"{coll}: no fix listed")
doc = json.load(open(path))
did = []


def replace(text, pairs, where):
    for a, b in pairs:
        if a in text:
            text = text.replace(a, b)
            did.append(where)
        elif b not in text:
            print(f"{coll}: {where} lacks {a!r}; left as is")
    return text


for key in ("title", "description"):
    if key in f and doc.get(key) != f[key]:
        doc[key] = f[key]
        did.append(key)
for key, val in f.get("set", {}).items():
    if doc.get(key) != val:
        doc[key] = val
        did.append(key)
if "license" in f:
    if doc.get("license") != f["license"]:
        doc["license"] = f["license"]
        did.append("license")
    old = [l for l in doc.get("links", []) if l.get("rel") == "license"]
    if old != f["license_links"]:
        doc["links"] = [l for l in doc.get("links", []) if l.get("rel") != "license"] + f["license_links"]
        did.append("license link")
doc["description"] = replace(doc.get("description", ""), f.get("description_replace", []), "description")
add = f.get("description_append")
if add and add not in doc["description"]:
    doc["description"] = doc["description"].rstrip() + "\n\n" + add
    did.append("description note")
for i, p in enumerate(doc.get("providers", [])):
    new = f.get("providers", {}).get(p.get("name"))
    if new and p != new:
        doc["providers"][i] = new
        did.append("provider")
for i, l in enumerate(doc.get("links", [])):
    new = f.get("links_replace", {}).get(l.get("href"))
    if new and l != new:
        doc["links"][i] = new
        did.append("link")
hrefs = {l.get("href") for l in doc.get("links", [])}
for l in f.get("links_add", []):
    if l["href"] not in hrefs:
        doc["links"].append(l)
        did.append("link")
cols = {c["name"]: c for c in doc.get("table:columns", [])}
for name, text in f.get("columns", {}).items():
    if name not in cols:
        print(f"{coll}: no column {name}; left as is")
    elif cols[name].get("description") != text:
        cols[name]["description"] = text
        did.append(f"column {name}")
for key, pairs in f.get("asset_text_replace", {}).items():
    a = doc.get("assets", {}).get(key)
    if a is None:
        print(f"{coll}: no asset {key}; left as is")
        continue
    for field in ("title", "description"):
        hits = [p for p in pairs if p[0] in a.get(field, "")]
        if hits:
            a[field] = replace(a[field], hits, f"asset {key}")
for key, a in f.get("assets_set", {}).items():
    if doc.setdefault("assets", {}).get(key) != a:
        doc["assets"][key] = a
        did.append(f"asset {key}")
for key, roles in f.get("asset_roles", {}).items():
    a = doc.get("assets", {}).get(key)
    if a is None:
        print(f"{coll}: no asset {key}; left as is")
    elif a.get("roles") != roles:
        a["roles"] = roles
        did.append(f"asset {key} roles")
with open(path, "w") as fh:
    fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
print(f"{coll}: {', '.join(dict.fromkeys(did)) or 'unchanged'}")
