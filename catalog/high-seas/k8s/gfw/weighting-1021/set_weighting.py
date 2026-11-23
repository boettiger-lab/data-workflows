#!/usr/bin/env python3
"""Say how to total GFW fishing effort inside a polygon, on the live hex asset (#1021).

    set_weighting.py COLLECTION.json

The hex is h6 (~36 km²) from a 0.1° grid, so it is already finer than the source; a polygon
smaller than a few hundred km² still has many boundary cells partly outside it. Appends one
paragraph to the `fishing-effort-hex` description. Idempotent.
"""
import json
import sys

path = sys.argv[1]
doc = json.load(open(path))
a = doc["assets"]["fishing-effort-hex"]
MARK = "To total effort inside a polygon"
PARA = ("To total effort inside a polygon (an EBSA, an MPA), weight each cell by the share of its "
        "area that lies inside the polygon. Cells on the polygon's edge are partly outside it, so "
        "summing every cell the polygon touches overstates the total. For the 'Slopes of the "
        "Flemish Cap and Grand Bank' EBSA in 2024, touched cells sum to 36,187 fishing hours, cells "
        "weighted by their inside share to 29,416, and the source grid clipped to the polygon to "
        "28,949. A finer hex would not help: the source is a 0.1 degree grid, coarser than these "
        "cells.")
d = a["description"]
if MARK in d:
    d = d[:d.index(MARK)].rstrip()
a["description"] = d + " " + PARA
json.dump(doc, open(path, "w"), indent=2, ensure_ascii=False)
print("fishing-effort-hex description updated")
