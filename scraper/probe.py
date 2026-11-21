"""Diagnostica temporanea (4): dove sono i cuori nella pagina catalogo."""
import re
from curl_cffi import requests

WWW = "https://www.vinted.it"
s = requests.Session(impersonate="chrome")
s.get(WWW + "/", headers={"Accept-Language": "it-IT,it;q=0.9"}, timeout=30)
t = s.get(f"{WWW}/catalog?catalog[]=536&order=relevance", headers={"Accept-Language": "it-IT,it;q=0.9"}, timeout=30).text
u = t.replace('\\"', '"')
for k in ("avourite", "favorite", "Favourite", "heart", "like_count", "likes"):
    print(k, u.count(k))
m = re.search(r'data-testid="product-item-id-(\d+)"', t)
iid = m.group(1)
a = t.find(f'product-item-id-{iid}')
block = t[a: a + 9000]
end = block.find('data-testid="product-item-id-', 200)
print("\nHTML ITEM BLOCK:\n", re.sub(r'class="[^"]*"', '', block[: end if end > 0 else 6000])[:5000])
print("\nJSON MENTIONS OF ID:")
for mm in list(re.finditer(iid, u))[:8]:
    seg = u[max(0, mm.start() - 200): mm.start() + 700]
    if "avourite" in seg or "price" in seg:
        print("---", seg.replace("\n", " "))
