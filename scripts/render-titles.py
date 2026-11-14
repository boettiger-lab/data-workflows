#!/usr/bin/env python3
"""Render titles that name the map, not the file.

    render-titles.py COLLECTION.json [...]     # rewrite in place; prints each change

The fallback renders (#881) took their titles from the COG asset title and prefixed
"Fallback:", so a map app's layer list read "Fallback: MTBS burn severity 1984 (CONUS, 30 m COG)".
A render is a way to draw the data, so its title names what is drawn: the prefix and the file
format ("COG", "cloud-optimized GeoTIFF", "WGS84", "EPSG:4326") come out, and the region,
year and resolution stay. A title left with nothing but format words takes the collection's
title. Only titles starting "Fallback:" are touched, and a second run changes nothing.
"""
import json
import re
import sys

FMT = r"(?:WGS84\s+)?(?:categorical\s+)?(?:cloud[- ]optimi[sz]ed\s+geotiff|COG)"


def render_title(title: str, collection_title: str = "") -> str:
    t = re.sub(r"^Fallback:\s*", "", title)
    t = re.sub(r"\s*[—-]\s*" + FMT + r"(\s*\([^)]*\))?\s*$", "", t, flags=re.I)  # "— WGS84 COG"
    t = re.sub(r",\s*" + FMT + r"(?=,|$)", "", t, flags=re.I)  # ", cloud-optimized GeoTIFF, 30 m"
    t = re.sub(r"\s*\(\s*" + FMT + r"(?:,\s*([^)]*))?\)",  # "(COG)", "(cloud-optimized GeoTIFF, 30 m)"
               lambda m: f" ({m.group(1)})" if m.group(1) else "", t, flags=re.I)
    t = re.sub(r"\(([^)]*?),?\s*" + FMT + r"\)", r"(\1)", t, flags=re.I)  # "(CONUS, 30 m COG)"
    t = re.sub(r"\s+" + FMT + r"(?=\s*(\(|$))", "", t, flags=re.I)  # "(CONUS) cloud-optimized GeoTIFF"
    t = re.sub(r",?\s*(?:EPSG:\d+|WGS84)\s*,?\s*", lambda m: ", " if m.group(0).count(",") == 2 else "", t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"\s*[—-]\s*$", "", t).strip(" ,")
    if not t or re.fullmatch(r"(?i)" + FMT, t):
        return collection_title or title
    return t


def retitle(doc: dict) -> list[tuple[str, str, str]]:
    changes = []
    for key, r in (doc.get("renders") or {}).items():
        old = r.get("title") or ""
        if old.startswith("Fallback:"):
            r["title"] = render_title(old, doc.get("title", ""))
            changes.append((key, old, r["title"]))
    return changes


if __name__ == "__main__":
    for path in sys.argv[1:]:
        doc = json.load(open(path))
        changes = retitle(doc)
        if changes:
            with open(path, "w") as f:
                f.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        for key, old, new in changes:
            print(f"{path} {key}: {old!r} -> {new!r}")
