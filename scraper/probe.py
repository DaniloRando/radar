"""Diagnostica temporanea (2): valuta, lingua e campi prezzo della nuova API."""
import json
from curl_cffi import requests

WWW, API = "https://www.vinted.it", "https://api.vinted.it/svc-catalogue/items"
L = "it-IT,it;q=0.9"
s = requests.Session(impersonate="chrome")
r = s.get(WWW + "/", headers={"Accept-Language": L}, timeout=30)
print("locale cookie", s.cookies.get("anonymous-iso-locale"), "| x-user-iso-locale", r.headers.get("x-user-iso-locale"))
tok, anon = s.cookies.get("access_token_web"), r.headers.get("x-anon-id")
H = {"Accept": "application/json", "Accept-Language": L, "Origin": WWW, "Referer": WWW + "/catalog",
     "Authorization": "Bearer " + tok, "X-Anon-Id": anon}

def show(label, params, extra=None):
    x = s.get(API, params=params, headers={**H, **(extra or {})}, timeout=30)
    print(f"\n== {label} -> {x.status_code}")
    if x.status_code != 200: print(x.text[:200]); return
    it = x.json()["items"]
    for i in it[:3]:
        print(" ", json.dumps({k: i.get(k) for k in ("price", "service_fee", "total_item_price", "url")}, ensure_ascii=False))
        print("   box:", i["item_box"].get("second_line"), "|", i["item_box"].get("accessibility_label", "")[:140])
    print("  user keys:", sorted((it[0].get("user") or {}).keys()))
    print("  currencies:", sorted({(i.get("price") or {}).get("currency_code") for i in it if isinstance(i.get("price"), dict)}))

b = {"attribute_ids[catalog]": "257", "page": 1, "per_page": 10, "order": "relevance"}
show("base", b)
show("currency=EUR", dict(b, currency="EUR"))
show("currency+locale", dict(b, currency="EUR", locale="it-IT"))
show("header locale", dict(b, currency="EUR"), {"X-Locale": "it-IT", "X-User-Iso-Locale": "it-IT"})
s.cookies.set("anonymous-iso-locale", "it-IT", domain=".vinted.it")
show("cookie locale it", dict(b, currency="EUR"))
