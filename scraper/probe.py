"""Diagnostica temporanea (3): la pagina catalogo renderizzata dal server è italiana?"""
import re
from curl_cffi import requests

WWW = "https://www.vinted.it"
s = requests.Session(impersonate="chrome")
s.get(WWW + "/", headers={"Accept-Language": "it-IT,it;q=0.9"}, timeout=30)
for q in ("catalog[]=257&order=relevance", "catalog[]=257&order=relevance&page=2", "catalog[]=257&order=newest_first&page=3"):
    c = s.get(f"{WWW}/catalog?{q}", headers={"Accept-Language": "it-IT,it;q=0.9"}, timeout=30)
    t = c.text
    u = t.replace('\\"', '"')
    print(f"\n== {q} -> {c.status_code} len={len(t)}")
    print(" favourite_count:", u.count('"favourite_count"'), " EUR:", u.count('"currency_code":"EUR"'), " USD:", u.count('"currency_code":"USD"'),
          " next_f:", "self.__next_f" in t, " NEXT_DATA:", "__NEXT_DATA__" in t, " data-testid items:", t.count('data-testid="grid-item"'))
    ids = re.findall(r'"id":(\d{9,12}),"title":"([^"]{0,60})"', u)
    print(" items:", len(ids), ids[:4])
    i = u.find('"favourite_count"')
    if i >= 0:
        print(" SNIPPET:", u[max(0, i - 1500): i + 900].replace("\n", " "))
    else:
        j = t.find("€")
        print(" EURO SNIPPET:", t[max(0, j - 600): j + 300].replace("\n", " ") if j >= 0 else "nessun €")
