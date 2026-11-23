"""Give a collection exactly one host provider, listed last (Portolan PTL-PRV-002, #761).

The host is us: the NRP entry if the collection names one, else the Boettiger Lab entry.
Upstream distributors (PacIOOS, Zenodo, ScienceBase, ...) lose the `host` role and keep
their other roles. One left with no role keeps its name and url, without `roles`.
A collection that names no lab entry gets one, as host, with the bucket url.

Usage: fix_hosts.py <collection.json> <bucket>   (edits the file in place)
"""
import json
import sys

NRP = "https://s3-west.nrp-nautilus.io"


def ours(p):
    n = p.get("name", "").lower()
    return "boettiger" in n or n == "national research platform"


def fix(c, bucket):
    provs = c.get("providers", [])
    mine = [p for p in provs if ours(p)]
    nrp = [p for p in mine if p["name"].lower() == "national research platform"]
    if nrp:
        host = nrp[0]
    elif mine:
        host = mine[0]
    else:
        host = {"name": "Boettiger Lab, UC Berkeley", "roles": ["host"],
                "url": f"{NRP}/{bucket}/"}
        provs.append(host)
    for p in provs:
        roles = [r for r in p.get("roles", []) if r != "host"]
        if p is host:
            roles.append("host")
        if roles:
            p["roles"] = roles
        else:
            p.pop("roles", None)
    if not host.get("url") and not host.get("email"):
        host["url"] = f"{NRP}/{bucket}/"
    c["providers"] = [p for p in provs if p is not host] + [host]
    return c


def main(path, bucket):
    c = json.load(open(path))
    fix(c, bucket)
    with open(path, "w") as f:
        json.dump(c, f, indent=2, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    main(*sys.argv[1:3])
