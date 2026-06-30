import sys, re, json, time, hashlib, http.cookiejar, urllib.request, urllib.parse

FILE_ID = sys.argv[1]
OUT = sys.argv[2]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
stream_url = f"https://datadryad.org/downloads/file_stream/{FILE_ID}"

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.addheaders = [("User-Agent", UA)]

# 1. GET challenge page
r = opener.open(stream_url, timeout=60)
html = r.read().decode("utf-8", "replace")
m = re.search(r'<script id="anubis_challenge"[^>]*>(.*?)</script>', html, re.S)
if not m:
    # maybe already redirected to the file (no challenge)
    open(OUT, "wb").write(html.encode() if isinstance(html, str) else html)
    print("NO_CHALLENGE: wrote", len(html), "bytes"); sys.exit(0)
ch = json.loads(m.group(1))
rnd = ch["challenge"]["randomData"] if isinstance(ch["challenge"], dict) else ch["challenge"]
cid = ch["challenge"]["id"] if isinstance(ch["challenge"], dict) else ch["id"]
diff = ch["rules"]["difficulty"]
print("challenge id", cid, "difficulty", diff)

# 2. proof of work
t0 = time.time(); nonce = 0; prefix = "0"*diff
while True:
    h = hashlib.sha256((rnd+str(nonce)).encode()).hexdigest()
    if h.startswith(prefix): break
    nonce += 1
ms = int((time.time()-t0)*1000)
print("solved nonce", nonce, "in", ms, "ms ->", h[:diff+4])

# 3. pass-challenge -> 302 to presigned S3
qs = urllib.parse.urlencode({"id": cid, "response": h, "nonce": nonce,
       "redir": f"/downloads/file_stream/{FILE_ID}", "elapsedTime": ms})
pass_url = f"https://datadryad.org/.within.website/x/cmd/anubis/api/pass-challenge?{qs}"
r2 = opener.open(pass_url, timeout=120)
data = r2.read()
open(OUT, "wb").write(data)
print("wrote", len(data), "bytes to", OUT, "final url:", r2.geturl()[:90])
