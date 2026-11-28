"""Replace the pre-0.8.1 line-hexing wording in a LIVE collection (#728).

  set_line_wording.py <collection.json>

Every string anywhere in the collection is checked against the exact sentences below; each match
is replaced, and nothing else changes. `updated` is set to now. Apply only after the collection's
hex is rebuilt on cng-datasets 0.8.1 or later, since the new wording describes that build.
Exits non-zero if the collection still mentions a circumradius afterwards (an unmapped variant).
"""
import datetime
import json
import sys

PASS8 = "Each line was indexed to every H3 cell it passes through at resolution 8."
SENTENCES = {
    "Line features were hexed to H3 resolution 8 by buffering each segment by the H3 cell circumradius before polyfill, so the cells trace a corridor along the line rather than its exact path.":
        "Each line was indexed to every H3 cell it passes through at resolution 8, so the cells trace the line's own path.",
    "Line features were hexed to H3 resolution 8 by buffering each segment by the H3 cell circumradius before polyfill.": PASS8,
    "Line features were hexed to H3 resolution 10 by buffering each segment by the H3 cell circumradius before polyfill.":
        "Each line was indexed to every H3 cell it passes through at resolution 10.",
    "Line features hexed to H3 resolution 8 by buffering each segment by the H3 circumradius before polyfill.": PASS8,
    "Line features hexed to H3 resolution 8 by buffering each segment by the H3 cell circumradius before polyfill.": PASS8,
    "Line features were hexed to H3 res 8 by buffering each segment by the H3 cell circumradius before polyfill.": PASS8,
    "Lines were hexed by buffering each segment by the H3 res-8 cell circumradius before polyfill.": PASS8,
    "Lines hexed by buffering each segment by the H3 res-8 cell circumradius before polyfill.": PASS8,
    "Each barrier line was buffered by the H3 cell circumradius before polyfill, so one row = one (barrier, h8 cell) pair.":
        "Each barrier line was indexed to every resolution 8 cell it passes through, so one row = one (barrier, h8 cell) pair.",
    "Each river-reach line was buffered by the H3 resolution-8 cell circumradius before polyfill, so one reach maps to the set of cells its buffered corridor covers.":
        "Each river reach was indexed to every resolution 8 cell it passes through, so one reach maps to the set of cells along its path.",
    "Line geometries are converted to H3 hex via segment buffering by the H3 circumradius at the native resolution (cng-datasets line support, PR #69).":
        "Each line was indexed to every H3 cell it passes through at the native resolution.",
}
# Longest first, so a sentence that extends another is matched whole.
ORDER = sorted(SENTENCES, key=len, reverse=True)
count = 0


def fix(v):
    global count
    if isinstance(v, str):
        for old in ORDER:
            if old in v:
                v = v.replace(old, SENTENCES[old])
                count += 1
        return v
    if isinstance(v, list):
        return [fix(x) for x in v]
    if isinstance(v, dict):
        return {k: fix(x) for k, x in v.items()}
    return v


path = sys.argv[1]
c = fix(json.load(open(path)))
left = "circumradius" in json.dumps(c).lower()
c["updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
json.dump(c, open(path, "w"), indent=2, ensure_ascii=False)
print(f"{c['id']}: {count} sentences replaced{'; CIRCUMRADIUS STILL PRESENT' if left else ''}")
sys.exit(1 if left else 0)
