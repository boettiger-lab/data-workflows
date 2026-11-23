#!/usr/bin/env python3
"""Small Portolan metadata fixes from the #761 catalog-wide rashid run, applied to a LIVE collection.

    fix_small.py <collection.json> <bucket>/<path>     # edits the file in place

Each edit is idempotent and touches only the field rashid flagged:
  PTL-LNK-003  rel:root link with no `type`        -> add application/json
  PTL-PRV-001  no providers / no producer role     -> providers from the collection's own citation and licence
  PTL-PRV-003  host provider with neither url nor email -> its bucket URL
"""
import json, sys

NRP = "https://s3-west.nrp-nautilus.io"

PROVIDERS = {
    # Description, licence link and sci:citation all name TPL's LandVote database.
    "public-tpl/landvote": [
        {"name": "Trust for Public Land", "roles": ["producer", "licensor"], "url": "https://www.landvote.org"},
        {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"], "url": f"{NRP}/public-tpl/"},
    ],
    # sci:citation and the cite-as DOI name ESA as publisher; the licence link is ESA's CSCDA annex.
    "public-dem/copernicus-glo90": [
        {"name": "European Space Agency (Copernicus)", "roles": ["producer", "licensor"],
         "url": "https://doi.org/10.5270/ESA-c5d3d65"},
        {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"], "url": f"{NRP}/public-dem/"},
    ],
}


def main(path, key):
    doc = json.load(open(path))
    key = key.removesuffix("/stac-collection.json")
    bucket = key.split("/")[0]
    changed = []
    for l in doc.get("links", []):
        if l.get("rel") == "root" and not l.get("type"):
            l["type"] = "application/json"; changed.append("root link type")
    if key in PROVIDERS and not doc.get("providers"):
        doc["providers"] = PROVIDERS[key]; changed.append("providers")
    provs = doc.get("providers") or []
    # The lab built this derived product and its sci:citation names the lab as author.
    if key == "public-coastal/meow-coastal-band" and not any("producer" in p.get("roles", []) for p in provs):
        for p in provs:
            if "host" in p.get("roles", []) and "Boettiger" in p.get("name", ""):
                p["roles"] = ["producer"] + p["roles"]; changed.append("producer role")
    for p in provs:
        if "host" in p.get("roles", []) and not p.get("url") and not p.get("email"):
            p["url"] = f"{NRP}/{bucket}/"; changed.append(f"host url ({p['name']})")
    json.dump(doc, open(path, "w"), indent=2, ensure_ascii=False)
    print(key, "->", ", ".join(changed) or "no change")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
