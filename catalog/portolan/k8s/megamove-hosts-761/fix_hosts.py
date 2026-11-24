"""The 5 megamove collections name Dryad as host; the files are served from NRP (#761, PTL-PRV-002).

    fix_hosts.py <in.json> <out.json>     # exits 3 when nothing changes

Dryad, where the source data was downloaded, loses the `host` role and keeps its name and url,
with a description saying what it is. The lab goes last as processor and host, in the form the
bucket's other collections use. Nothing else changes. Idempotent.
"""
import json
import sys

HOST = {"name": "Boettiger Lab, University of California, Berkeley", "roles": ["processor", "host"],
        "url": "https://s3-west.nrp-nautilus.io/public-high-seas/"}


def fix(doc):
    provs = doc.get("providers") or []
    if any(p.get("name") == HOST["name"] for p in provs):
        return doc
    for p in provs:
        if p.get("name") == "Dryad" and "host" in (p.get("roles") or []):
            roles = [r for r in p["roles"] if r != "host"]
            if roles:
                p["roles"] = roles
            else:
                p.pop("roles")
            p.setdefault("description", "Distributor of the source data.")
    if any("host" in (p.get("roles") or []) for p in provs):
        return doc
    doc["providers"] = provs + [dict(HOST)]
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
