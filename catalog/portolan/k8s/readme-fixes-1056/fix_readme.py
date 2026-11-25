#!/usr/bin/env python3
"""Append the licence or source section a README lacks, from its node's STAC (#1056, FIL-005).

  fix_readme.py STAC.json README.md     # edits README.md in place; prints what it added

Only appends. A README that already mentions a licence (or a source) gets nothing for it, so a
re-run changes nothing. The markers are rashid's: license/licence/spdx, and
provenance/source/produced/derived/origin/collected.
"""
import json
import sys

LICENSE = ("license", "licence", "spdx")
SOURCE = ("provenance", "source", "produced", "derived", "origin", "collected")


def sections(d, text):
    low = text.casefold()
    links = d.get("links", [])
    add = []
    if not any(m in low for m in LICENSE):
        lic = next((l for l in links if l.get("rel") == "license"), None)
        if d.get("license"):
            line = f"`{d['license']}`." + (f" Terms: {lic['href']}" if lic else "")
        else:
            line = "Each dataset in this catalog states its own license in its STAC metadata."
        add.append(("license", ["## License", "", line]))
    if not any(m in low for m in SOURCE):
        body = [f"- {p['name']} ({', '.join(p.get('roles', []))})" + (f": {p['url']}" if p.get("url") else "")
                for p in d.get("providers", [])]
        body += [f"- {l['rel']}: {l['href']}" for l in links if l.get("rel") in ("about", "source", "cite-as")]
        if d.get("sci:citation"):
            body = [f"Cite as: {d['sci:citation']}", ""] + body
        if not body:
            body = ["Each dataset in this catalog names its own sources in its STAC metadata."]
        add.append(("source", ["## Source", ""] + body))
    return add


def main(stac_path, readme_path):
    d = json.load(open(stac_path))
    text = open(readme_path, encoding="utf-8").read()
    add = sections(d, text)
    if add:
        text = text.rstrip("\n") + "\n\n" + "\n\n".join("\n".join(s) for _, s in add) + "\n"
        open(readme_path, "w", encoding="utf-8").write(text)
    print("added:", ",".join(k for k, _ in add) or "nothing")


if __name__ == "__main__":
    main(*sys.argv[1:3])
