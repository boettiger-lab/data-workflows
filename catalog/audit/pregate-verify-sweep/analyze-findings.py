#!/usr/bin/env python3
"""Summarise a pre-gate sweep: HARD findings by category and by collection.

Usage:  python3 analyze-findings.py /path/to/all-results.txt
"""
import re, sys
from collections import Counter, defaultdict

lines = open(sys.argv[1]).read().splitlines()
cur, per_coll = None, defaultdict(Counter)
for ln in lines:
    m = re.match(r'^HARD\(\d+\)\t\d+s\t(\S+)', ln)
    if m:
        cur = m.group(1).split('/public-')[-1].rsplit('/stac', 1)[0]
        per_coll.setdefault(cur, Counter())
        continue
    m = re.match(r'^\s+\[HARD\]\[([a-z0-9-]+)\]', ln)
    if m and cur:
        per_coll[cur][m.group(1)] += 1

total = lambda c: sum(per_coll[c].values())
print(f"{'COLLECTION':48} {'N':>3}  categories")
for c in sorted(per_coll, key=lambda c: -total(c)):
    cats = ", ".join(f"{k}×{v}" if v > 1 else k for k, v in per_coll[c].most_common())
    print(f"{c:48} {total(c):>3}  {cats}")

cat_colls = defaultdict(set)
for c, cnt in per_coll.items():
    for k in cnt:
        cat_colls[k].add(c)
print(f"\n# {len(per_coll)} collections with HARD findings\n# by category (collections affected):")
for k in sorted(cat_colls, key=lambda k: -len(cat_colls[k])):
    print(f"  {len(cat_colls[k]):>3}  {k}")
