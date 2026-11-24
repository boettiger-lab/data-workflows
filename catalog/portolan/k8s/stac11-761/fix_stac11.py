"""Move a LIVE catalog or collection to STAC 1.1.0 (Portolan PTL-STR-001, #761).

    fix_stac11.py <in.json> <out.json>     # exits 3 when nothing changes

- `stac_version` becomes "1.1.0".
- A `summaries` entry that is neither an array nor an object (a feature count, a version label,
  a note) is not a summary in STAC 1.1, which requires an array, a range or a JSON schema. It
  moves to a top-level field of the same name, which STAC allows, unless that name is taken.
- A provider role outside the STAC enum (producer, licensor, processor, host) is dropped; the
  provider keeps its name and url, and its `description` says what the role was.
Nothing else changes. Idempotent.
"""
import json
import sys

ROLES = {"producer", "licensor", "processor", "host"}
ROLE_TEXT = {"funder": "Funder.", "distributor": "Distributor of the source data."}


def fix(doc):
    if doc.get("type") not in ("Catalog", "Collection"):
        return doc
    doc["stac_version"] = "1.1.0"
    summ = doc.get("summaries")
    if isinstance(summ, dict):
        for k in [k for k, v in summ.items() if not isinstance(v, (list, dict))]:
            if k in doc:
                raise ValueError(f"summaries.{k} cannot move: top-level {k} exists")
            doc[k] = summ.pop(k)
        if not summ:
            doc.pop("summaries")
    for p in doc.get("providers") or []:
        roles = p.get("roles")
        if not isinstance(roles, list):
            continue
        odd = [r for r in roles if r not in ROLES]
        if not odd:
            continue
        keep = [r for r in roles if r in ROLES]
        if keep:
            p["roles"] = keep
        else:
            p.pop("roles")
        if not p.get("description"):
            p["description"] = " ".join(ROLE_TEXT.get(r, f"{r.capitalize()}.") for r in odd)
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
