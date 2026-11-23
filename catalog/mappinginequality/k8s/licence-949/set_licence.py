"""Mapping Inequality licence: CC-BY-NC-SA-4.0 -> CC-BY-NC-2.5, per the project FAQ (#949).

usage: set_licence.py collection <path> | readme <path>
"""
import json, sys

OLD_URL = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
NEW_URL = "https://creativecommons.org/licenses/by-nc/2.5/"
NEW_TITLE = "Creative Commons Attribution-NonCommercial 2.5 Generic"
OLD_MD = ("[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International]"
          "(https://creativecommons.org/licenses/by-nc-sa/4.0/)")
NEW_MD = f"[{NEW_TITLE}]({NEW_URL})"

mode, path = sys.argv[1], sys.argv[2]
if mode == "collection":
    d = json.load(open(path))
    d["license"] = "CC-BY-NC-2.5"
    lic = [l for l in d["links"] if l["rel"] == "license"]
    assert len(lic) == 1 and lic[0]["href"] in (OLD_URL, NEW_URL), lic
    lic[0].update(href=NEW_URL, title=NEW_TITLE, type="text/html")
    s = json.dumps(d, indent=2, ensure_ascii=False)
    assert "by-nc-sa" not in s.lower() and "sharealike" not in s.lower()
    open(path, "w").write(s)
elif mode == "readme":
    s = open(path).read()
    if NEW_MD not in s:
        assert s.count(OLD_MD) == 1
        s = s.replace(OLD_MD, NEW_MD)
    open(path, "w").write(s)
else:
    sys.exit(f"unknown mode {mode}")
