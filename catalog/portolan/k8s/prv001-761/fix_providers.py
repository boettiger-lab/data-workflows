"""Providers for the 5 public-high-seas collections that have none (Portolan PTL-PRV-001, #761).

    fix_providers.py <in.json> <out.json>     # exits 3 when nothing changes

Each gets its producer, as its own citation names it, then the lab as processor and host,
listed last, in the form the bucket's other collections use. mpa-candidates is a direct
contribution whose owner is deliberately not named (#579), so it gets the host only.
A collection that already has providers is left alone.
"""
import json
import sys

HOST = {"name": "Boettiger Lab, University of California, Berkeley", "roles": ["processor", "host"],
        "url": "https://s3-west.nrp-nautilus.io/public-high-seas/"}
VLIZ = {"name": "Marine Regions / Flanders Marine Institute (VLIZ)", "roles": ["producer", "licensor"],
        "url": "https://www.marineregions.org/"}
CBD = {"name": "Secretariat of the Convention on Biological Diversity", "roles": ["producer", "licensor"],
       "url": "https://www.cbd.int/ebsa/"}
PRODUCER = {"longhurst-provinces": VLIZ, "ecs-extended-continental-shelf": VLIZ,
            "ebsa": CBD, "ebsa-2023": CBD, "mpa-candidates": None}


def fix(doc):
    if doc.get("providers") or doc.get("id") not in PRODUCER:
        return doc
    p = PRODUCER[doc["id"]]
    doc["providers"] = ([dict(p)] if p else []) + [dict(HOST)]
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
