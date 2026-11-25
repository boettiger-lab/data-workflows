#!/usr/bin/env python3
"""Write a README.md for one STAC node from its own fields, and link it (Portolan FIL-003, #1056).

  gen_readme.py readme STAC.json OUT.md    # draft the README from the node's STAC
  gen_readme.py link STAC.json             # add rel:describedby ./README.md, in place

Only for nodes with no README.md beside their STAC file; the job checks that before writing.
Everything in the README comes from the node's STAC: title, description, files, a usage example,
licence, citation and sources. Other `describedby` links on the node are left as they are.
"""
import json
import posixpath
import sys

NRP = "https://s3-west.nrp-nautilus.io"
LINK = {"rel": "describedby", "href": "./README.md", "type": "text/markdown", "title": "README"}


def s3(href):
    return "s3://" + href[len(NRP) + 1:] if href.startswith(NRP + "/") else href


def usage(d, assets):
    out = []
    flat = next((a for a in assets.values() if a["href"].endswith(".parquet") and "*" not in a["href"]), None)
    hexa = next((a for a in assets.values() if "*" in a["href"] and a["href"].endswith(".parquet")), None)
    pm = next(((k, a) for k, a in assets.items() if a["href"].endswith(".pmtiles")), None)
    cog = next((a for a in assets.values() if a["href"].endswith(".tif")), None)
    if flat:
        out += ["DuckDB:", "", "```sql", "INSTALL httpfs; LOAD httpfs;",
                f"SELECT * FROM read_parquet('{flat['href']}') LIMIT 10;", "```", ""]
    elif hexa:  # a glob needs S3 listing, which https does not offer
        out += ["DuckDB, reading the hex partitions over S3 (anonymous, path-style):", "", "```sql",
                "INSTALL httpfs; LOAD httpfs;",
                "CREATE SECRET nrp (TYPE s3, ENDPOINT 's3-west.nrp-nautilus.io', URL_STYLE 'path');",
                f"SELECT * FROM read_parquet('{s3(hexa['href'])}', hive_partitioning = true) LIMIT 10;",
                "```", ""]
    if pm:
        k, a = pm
        layer = (a.get("vector:layers") or [posixpath.splitext(posixpath.basename(a["href"]))[0]])[0]
        style = next((s for s in assets.values() if "style" in s.get("roles", [])
                      and "default" in s.get("roles", [])), None)
        out += ["MapLibre GL JS, with the `pmtiles` protocol registered:", "", "```js",
                f"map.addSource('{d['id']}', {{ type: 'vector', url: 'pmtiles://{a['href']}' }});",
                f"map.addLayer({{ id: '{d['id']}', type: 'fill', source: '{d['id']}', "
                f"'source-layer': '{layer}' }});  // 'line' or 'circle' for lines and points",
                "```", ""]
        if style:
            out += [f"A default MapLibre style for this layer: {style['href']}", ""]
    if cog and not pm:
        out += ["The COG can be drawn as map tiles by any COG tiler, for example TiTiler:", "", "```",
                f"https://titiler.nrp-nautilus.io/cog/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}?url={cog['href']}",
                "```", ""]
    return out


def readme(d, url):
    links = d.get("links", [])
    out = [f"# {d.get('title') or d['id']}", "", d.get("description", "").strip(), ""]
    kids = [l for l in links if l.get("rel") == "child"]
    if kids:
        out += ["## Datasets", ""]
        out += [f"- [{l.get('title') or posixpath.basename(posixpath.dirname(l['href']))}]({l['href']})"
                for l in kids]
        out.append("")
    assets = {k: a for k, a in d.get("assets", {}).items()
              if not set(a.get("roles", [])) & {"thumbnail", "style"} and "href" in a}
    if assets:
        out += ["## Files", "", "| Asset | Format | Location |", "|---|---|---|"]
        for k, a in assets.items():
            title = (a.get("title") or k).replace("|", "/")
            out.append(f"| {title} | {a.get('type', '').split(';')[0]} | `{s3(a['href'])}` |")
        out.append("")
        u = usage(d, assets)
        if u:
            out += ["## Usage", ""] + u
    out += ["## License", ""]
    lic = next((l for l in links if l.get("rel") == "license"), None)
    if d.get("license"):
        out.append(f"`{d['license']}`." + (f" Terms: {lic['href']}" if lic else ""))
    else:
        out.append("Each dataset listed above states its own license.")
    out += ["", "## Source", ""]
    if d.get("sci:citation"):
        out += [f"Cite as: {d['sci:citation']}", ""]
    for p in d.get("providers", []):
        out.append(f"- {p['name']} ({', '.join(p.get('roles', []))})" + (f": {p['url']}" if p.get("url") else ""))
    out += [f"- {l['rel']}: {l['href']}" for l in links if l.get("rel") in ("about", "source", "cite-as")]
    if out[-1] == "":
        out.append("Each dataset listed above names its own sources." if kids else
                   "See the STAC metadata below.")
    out += ["", "## Metadata", "", f"STAC: {url}", ""]
    return "\n".join(out)


def main(argv):
    cmd, path = argv[1], argv[2]
    d = json.load(open(path))
    self_ = next(l["href"] for l in d["links"] if l.get("rel") == "self")
    if cmd == "readme":
        open(argv[3], "w").write(readme(d, self_))
    elif cmd == "link":
        base = posixpath.dirname(self_) + "/"
        have = any(l.get("rel") == "describedby" and l.get("href") in ("./README.md", "README.md", base + "README.md")
                   for l in d["links"])
        if not have:
            d["links"].append(dict(LINK))
            json.dump(d, open(path, "w"), indent=2, ensure_ascii=False)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
