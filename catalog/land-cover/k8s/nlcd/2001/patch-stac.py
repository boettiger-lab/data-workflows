#!/usr/bin/env python3
"""Apply the #739 map-year-2001 edits to the live nlcd collection and write it to /tmp.

Idempotent: run against a collection that already has the edits, it writes it unchanged.
Edits: add the nlcd-cog-2001 asset, 19 -> 20 map years, the 2001 provenance paragraph,
and drop the 250 NoData entry from classification:classes on every COG (#630).

  python3 patch-stac.py
  -> /tmp/nlcd-stac-collection.json
"""
import argparse
import copy
import json
import urllib.request

URL = "https://s3-west.nrp-nautilus.io/public-land-cover/nlcd/stac-collection.json"
OUT = "/tmp/nlcd-stac-collection.json"

PROVENANCE = (
    "**Map year 2001 provenance (#739):** added after the original 19-year build. Accessed "
    "2026-10-01 from MRLC (`Annual_NLCD_LndCov_2001_CU_C1V2.zip`, Last-Modified 2026-04-20); "
    "upstream publishes no edition label beyond the collection version C1V2. Staged raw: "
    "`s3://public-land-cover/raw/Annual_NLCD_LndCov_2001_CU_C1V2.tif`, 1,367,828,587 bytes, "
    "SHA256 `0872ceddd4fa68351654f75cf06572a4ff34f64bb5f0c685f798796efda48900`. Processed with "
    "the same COG and hex parameters as the other map years."
)
LICENSE_LINK = {
    "rel": "license",
    "href": "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits",
    "type": "text/html",
    "title": "USGS copyrights and credits (public domain)",
}


def main():
    ap = argparse.ArgumentParser()
    args = ap.parse_args()

    with urllib.request.urlopen(URL) as r:
        doc = json.load(r)

    d = doc["description"]
    d = d.replace("across 19 map years", "across 20 map years")
    d = d.replace("1998, 2000, 2005,", "1998, 2000, 2001, 2005,")
    if "Map year 2001 provenance" not in d:
        d = d.rstrip() + "\n\n" + PROVENANCE
    doc["description"] = d

    for k in ("nlcd-hex", "nlcd-hex-fractions"):
        a = doc["assets"][k]
        a["description"] = a["description"].replace("ALL 19 years", "ALL 20 years")

    assets = doc["assets"]
    if "nlcd-cog-2001" not in assets:
        new = copy.deepcopy(assets["nlcd-cog-2000"])
        new["href"] = new["href"].replace("nlcd-2000-cog", "nlcd-2001-cog")
        new["title"] = new["title"].replace("NLCD 2000", "NLCD 2001")
        assets["nlcd-cog-2001"] = new
        cogs = sorted(k for k in assets if k.startswith("nlcd-cog-"))
        doc["assets"] = {k: assets[k] for k in cogs} | {
            k: v for k, v in assets.items() if k not in cogs}

    for k, a in doc["assets"].items():
        if k.startswith("nlcd-cog-"):
            for b in a.get("raster:bands", []):
                if "classification:classes" in b:
                    b["classification:classes"] = [
                        c for c in b["classification:classes"] if c.get("value") != 250]

    if not any(l.get("rel") == "license" for l in doc["links"]):
        doc["links"].append(LICENSE_LINK)

    with open(OUT, "w") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(OUT)


if __name__ == "__main__":
    main()
