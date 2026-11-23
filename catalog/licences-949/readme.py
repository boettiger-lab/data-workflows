#!/usr/bin/env python3
"""readme.py readme-fixes.json PATH FILE: replace one licence line in a live README (#949)."""
import json, sys
f = next(x for x in json.load(open(sys.argv[1])) if x["path"] == sys.argv[2])
t = open(sys.argv[3]).read()
if f["new"] in t:
    print(f"{sys.argv[2]}: unchanged"); sys.exit(0)
if f["old"] not in t:
    sys.exit(f"{sys.argv[2]}: licence line not found; left as is")
open(sys.argv[3], "w").write(t.replace(f["old"], f["new"]))
print(f"{sys.argv[2]}: licence line")
