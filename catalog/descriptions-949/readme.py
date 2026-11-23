#!/usr/bin/env python3
"""readme.py readme-fixes.json PATH FILE: correct a live README in place (#949).

A fix either carries `replace` ([old, new] pairs; an absent old is reported, never guessed at)
or `content`, the whole corrected README. A second run changes nothing.
"""
import json
import sys

f = next(x for x in json.load(open(sys.argv[1])) if x["path"] == sys.argv[2])
t = open(sys.argv[3]).read()
new = f.get("content")
if new is None:
    new = t
    for a, b in f["replace"]:
        if a in new:
            new = new.replace(a, b)
        elif b not in new:
            print(f"{sys.argv[2]}: lacks {a!r}; left as is")
open(sys.argv[3], "w").write(new)
print(f"{sys.argv[2]}: {'changed' if new != t else 'unchanged'}")
