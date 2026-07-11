import sys, re, json, time, hashlib, http.cookiejar, urllib.request, urllib.parse
FILE_ID = sys.argv[1]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
stream_url = f"https://datadryad.org/downloads/file_stream/{FILE_ID}"
captured = {}
class Catch(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if "amazonaws.com" in newurl or "assetstore" in newurl:
            captured["url"] = newurl
            return None   # stop — don't fetch the 8.5 GB body
        return super().redirect_request(req, fp, code, msg, headers, newurl)
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(Catch(), urllib.request.HTTPCookieProcessor(cj))
opener.addheaders = [("User-Agent", UA)]
html = opener.open(stream_url, timeout=60).read().decode("utf-8","replace")
m = re.search(r'<script id="anubis_challenge"[^>]*>(.*?)</script>', html, re.S)
ch = json.loads(m.group(1))
rnd = ch["challenge"]["randomData"]; cid = ch["challenge"]["id"]; diff = ch["rules"]["difficulty"]
t0=time.time(); n=0; pre="0"*diff
while True:
    h=hashlib.sha256((rnd+str(n)).encode()).hexdigest()
    if h.startswith(pre): break
    n+=1
ms=int((time.time()-t0)*1000)
qs=urllib.parse.urlencode({"id":cid,"response":h,"nonce":n,"redir":f"/downloads/file_stream/{FILE_ID}","elapsedTime":ms})
try:
    opener.open(f"https://datadryad.org/.within.website/x/cmd/anubis/api/pass-challenge?{qs}", timeout=60).read(2048)
except Exception:
    pass
print(captured.get("url",""))
