"""Diagnostica temporanea: struttura della nuova API catalogo di Vinted."""
import json, re
from curl_cffi import requests

WWW, API = "https://www.vinted.it", "https://api.vinted.it/svc-catalogue/items"
L = "it-IT,it;q=0.9,en;q=0.5"
s = requests.Session(impersonate="chrome")
r = s.get(WWW + "/", headers={"Accept-Language": L}, timeout=30)
print("HOME", r.status_code)
print("COOKIES", sorted(s.cookies.keys()))
print("RESP HEADERS", sorted(k.lower() for k in r.headers.keys()))
anon = r.headers.get("x-anon-id") or s.cookies.get("anon_id")
m = re.search(r'csrf[_-]?token["\']?\s*[:=,]\s*(?:content=)?["\']([^"\']{10,})', r.text, re.I) or re.search(r'CSRF_TOKEN\\?":\\?"([^"\\]+)', r.text)
csrf = m.group(1) if m else None
tok = s.cookies.get("access_token_web")
print("anon", bool(anon), "csrf", bool(csrf), "token", bool(tok))

def call(label, params, auth=True):
    h = {"Accept": "application/json, text/plain, */*", "Accept-Language": L, "Origin": WWW, "Referer": WWW + "/catalog"}
    if auth:
        if tok: h["Authorization"] = "Bearer " + tok
        if anon: h["X-Anon-Id"] = anon
        if csrf: h["X-Csrf-Token"] = csrf
    x = s.get(API, params=params, headers=h, timeout=30)
    print(f"\n== {label} -> {x.status_code} {x.headers.get('content-type')}")
    try:
        j = x.json()
    except Exception:
        print(x.text[:300]); return None
    print("TOP KEYS", list(j.keys()) if isinstance(j, dict) else type(j))
    for k in ("pagination", "meta"):
        if isinstance(j, dict) and k in j: print(k.upper(), json.dumps(j[k])[:400])
    items = j.get("items") if isinstance(j, dict) else None
    if items:
        print("N", len(items), "ITEM KEYS", sorted(items[0].keys()))
    return items

base = {"attribute_ids[catalog]": "536", "page": 1, "per_page": 5, "order": "relevance"}
it = call("auth relevance", base)
if it: print("FIRST ITEM", json.dumps(it[0], ensure_ascii=False)[:3500])
call("no auth", base, auth=False)
it2 = call("newest", dict(base, order="newest_first", per_page=96))
if it2: print("favourite_count present:", sum(1 for i in it2 if "favourite_count" in i), "/", len(it2))
call("catalog_ids old name", {"catalog_ids": "536", "page": 1, "per_page": 5})
c = s.get(WWW + "/catalog?catalog[]=536", headers={"Accept-Language": L}, timeout=30)
sizes = sorted(set(re.findall(r'\{\\?"id\\?":(\d+),\\?"title\\?":\\?"(M|W32[^"\\]*|IT 48|48)\\?"', c.text)))[:30]
print("\nCATALOG PAGE", c.status_code, "size ids:", sizes)
