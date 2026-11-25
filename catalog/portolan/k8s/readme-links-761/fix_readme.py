"""Link the README.md beside a catalog or collection (Portolan PTL-FIL-003, #761).

    fix_readme.py <in.json> <out.json> <url-of-in.json>     # exits 3 when nothing changes

The node gets {"rel": "describedby", "href": "./README.md", "type": "text/markdown"}.
A describedby link that already points at that README by another href is rewritten to
this form rather than duplicated; other describedby links (upstream metadata, papers)
stay. The README is checked to exist and to describe this node before the job runs
(stac-files.txt lists only those). Idempotent.
"""
import json
import sys
from urllib.parse import urljoin

LINK = {"rel": "describedby", "href": "./README.md", "type": "text/markdown", "title": "README"}


def fix(doc, url):
    readme = urljoin(url, "README.md")
    links = doc.setdefault("links", [])
    own = [l for l in links if l.get("rel") == "describedby" and urljoin(url, l.get("href", "")) == readme]
    if own:
        for l in own:
            l["href"], l["type"] = LINK["href"], LINK["type"]
            l.setdefault("title", LINK["title"])
    else:
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
