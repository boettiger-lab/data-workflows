"""Crawl bondaccountability.resources.ca.gov/Project/Details/{ProjectNo_FK} for one slice of the
ABCRS project IDs (#866). The published spreadsheets key projects by 'Project Ref Num'; the map
service keys features by the internal ProjectNo_FK. The detail page is the only public place that
shows both, so it is the crosswalk. Output: one JSON line per ID, every label/value on the page."""
import html, json, os, re, sys, time, requests
from concurrent.futures import ThreadPoolExecutor
idx, n = int(os.environ["JOB_COMPLETION_INDEX"]), int(os.environ["N_SLICES"])
ids = sorted({f["properties"]["ProjectNo_FK"] for name in ("points", "lines", "polygons")
              for f in json.load(open(f"/tmp/raw/abcrs-{name}.geojson"))["features"]})
mine = ids[idx::n]
print(f"slice {idx}/{n}: {len(mine)} of {len(ids)} ids", flush=True)
S = requests.Session(); S.headers["User-Agent"] = "boettiger-lab data-workflows (#866) dataset ingest"
def parse(t):
    m = t.find('id="main-content"'); t = t[m:t.find("Back to top", m)]
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)
    toks = [html.unescape(x).replace("\xa0", " ").strip() for x in re.split(r"<[^>]+>", t)]
    toks = [x for x in toks if x]
    out, i = {}, 0
    for i, x in enumerate(toks):
        if x.startswith("Project:") and "title" not in out: out["title"] = x[len("Project:"):].strip()
        elif x.endswith(":") and i + 1 < len(toks) and not toks[i + 1].endswith(":"): out[x[:-1].strip()] = toks[i + 1]
        elif x.endswith(":"): out.setdefault(x[:-1].strip(), None)
    return out
def fetch(fk):
    for a in range(6):
        try:
            r = S.get(f"https://bondaccountability.resources.ca.gov/Project/Details/{fk}/?PropositionPK=1", timeout=60)
            time.sleep(0.5)
            if r.status_code == 200: return {"ProjectNo_FK": fk, "status": 200, **parse(r.text)}
            if r.status_code == 404: return {"ProjectNo_FK": fk, "status": 404}
        except Exception as e: print("err", fk, e, flush=True)
        time.sleep(5 * (a + 1))
    return {"ProjectNo_FK": fk, "status": r.status_code if 'r' in dir() else -1}
with ThreadPoolExecutor(2) as ex, open(f"/tmp/part-{idx:02d}.jsonl", "w") as fh:
    for k, rec in enumerate(ex.map(fetch, mine)):
        fh.write(json.dumps(rec) + "\n")
        if k % 500 == 0: print(k, rec, flush=True)
