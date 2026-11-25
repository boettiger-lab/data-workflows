"""Link the AGENTS.md beside a catalog or collection (Portolan PTL-FIL-001/002, #1057).

    fix_agents.py <in.json> <out.json> <url-of-in.json>     # exits 3 when nothing changes

The node gets {"rel": "agents", "href": "./AGENTS.md", "type": "text/markdown"}, unless a
link to that file is already there. Nothing else changes. Idempotent.
"""
import json
import sys
from urllib.parse import urljoin

LINK = {"rel": "agents", "href": "./AGENTS.md", "type": "text/markdown", "title": "Agent guide"}


def fix(doc, url):
    target = urljoin(url, "AGENTS.md")
    links = doc.setdefault("links", [])
    if not any(l.get("rel") == "agents" and urljoin(url, l.get("href", "")) == target for l in links):
        links.append(dict(LINK))
    return doc


def main(src, dst, url):
    raw = open(src).read()
    doc = fix(json.loads(raw), url)
    if json.loads(raw) == doc:
        sys.exit(3)
    with open(dst, "w") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    main(*sys.argv[1:4])
