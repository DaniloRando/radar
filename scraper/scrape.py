#!/usr/bin/env python3
"""
Radar – scraper giornaliero di vinted.it.

Da settembre 2026 Vinted ha ritirato la vecchia API /api/v2/catalog/items, e la
nuova (api.vinted.<tld>/svc-catalogue/items) sceglie il mercato in base all'IP:
dai server GitHub (USA) restituisce annunci americani in dollari.
La pagina catalogo di www.vinted.it, invece, è generata dal server in italiano
e in euro, e contiene per ogni articolo: titolo, marca, condizioni, taglia,
prezzo, totale con protezione acquisti, foto e numero di cuori.
Questo script legge quelle pagine.

Per ogni categoria in config.json: scarica alcune pagine (rilevanza + più recenti),
filtra per taglia, calcola il prezzo finale (articolo + protezione + spedizione
stimata) e scrive docs/data/items.json.

Se una categoria non risponde, si tengono i dati del giorno prima (marcati
"stale"). Se non risponde nessuna, il file non viene toccato e lo script esce
con codice 1 (workflow rosso, sito online con i dati precedenti).
"""
from __future__ import annotations

import html
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("VR_CONFIG", ROOT / "config.json"))
OUT_PATH = Path(os.environ.get("VR_OUT", ROOT / "docs" / "data" / "items.json"))

CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
BASE = f"https://www.{CONFIG['domain']}"
LANG = "it-IT,it;q=0.9,en;q=0.5"

STATUS_TEXT_RANK = [
    ("con cartellino", 5), ("senza cartellino", 4),
    ("ottim", 3), ("buon", 2), ("discret", 1),
]


class Blocked(Exception):
    pass


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- parsing HTML

CARD_RE = re.compile(r'data-testid="product-item-id-(\d+)"')
IMG_RE = re.compile(r'<img\b[^>]*?\bsrc="([^"]+)"[^>]*?\balt="([^"]*)"|<img\b[^>]*?\balt="([^"]*)"[^>]*?\bsrc="([^"]+)"')
HREF_RE = re.compile(r'href="(/items/[^"?]+)')
FAV_RE = re.compile(r'preferiti da (\d+)')
PRICE = r'([\d.,]+)\s*€'
ALT_RE = re.compile(
    r'^(?P<title>.*?)'
    r'(?:, Brand: (?P<brand>.*?))?'
    r'(?:, Condizioni: (?P<cond>.*?))?'
    r'(?:, Taglia: (?P<size>.*?))?'
    r', ' + PRICE + r'(?:, ' + PRICE + r')?\s*$'
)


def to_float(s: str | None) -> float | None:
    if not s:
        return None
    s = s.strip()
    if "," in s and "." in s:          # 1,234.50 oppure 1.234,50
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def parse_catalog_html(text: str) -> list[dict]:
    """Estrae gli articoli dalla pagina catalogo. Ritorna dict 'grezzi'."""
    marks = [(m.start(), m.group(1)) for m in CARD_RE.finditer(text)]
    out, seen = [], set()
    for idx, (pos, iid) in enumerate(marks):
        if iid in seen:
            continue
        end = marks[idx + 1][0] if idx + 1 < len(marks) else pos + 20000
        block = text[pos:end]
        m = IMG_RE.search(block)
        if not m:
            continue
        src = m.group(1) or m.group(4)
        alt = html.unescape(m.group(2) if m.group(1) else m.group(3))
        a = ALT_RE.match(alt)
        if not a:
            continue
        seen.add(iid)
        href = HREF_RE.search(block)
        fav = FAV_RE.search(block)
        out.append({
            "id": int(iid),
            "title": (a.group("title") or "").strip(),
            "brand_title": (a.group("brand") or "").strip(),
            "status": (a.group("cond") or "").strip(),
            "size_title": (a.group("size") or "").strip(),
            "price": to_float(a.group(5)),
            "total_item_price": to_float(a.group(6)),
            "favourite_count": int(fav.group(1)) if fav else 0,
            "photo": html.unescape(src),
            "url": BASE + href.group(1) if href else f"{BASE}/items/{iid}",
        })
    return out


# ---------------------------------------------------------------- HTTP

class VintedClient:
    def __init__(self):
        from curl_cffi import requests  # import qui: i test possono sostituire il client

        self._requests = requests
        self.new_session()

    def new_session(self):
        s = self._requests.Session(impersonate="chrome")
        proxy = os.environ.get("VINTED_PROXY", "").strip()
        if proxy:
            s.proxies = {"http": proxy, "https": proxy}
        try:
            r = s.get(BASE + "/", headers={"Accept-Language": LANG}, timeout=30)
            log(f"  sessione: home HTTP {r.status_code}")
        except Exception as e:
            log(f"  sessione: errore {e}")
        self.session = s

    def get_items(self, params: list[tuple[str, str]]) -> list[dict]:
        wait = 5
        for attempt in range(1, 5):
            try:
                r = self.session.get(f"{BASE}/catalog", params=params,
                                     headers={"Accept-Language": LANG, "Referer": BASE + "/"}, timeout=45)
                code = r.status_code
            except Exception as e:
                log(f"    errore rete ({e}), tentativo {attempt}")
                code = None
            if code == 200:
                items = parse_catalog_html(r.text)
                if items:
                    return items
                if "captcha-delivery" in r.text or len(r.text) < 50_000:
                    log("    pagina anti-bot invece del catalogo")
                    code = 403
                else:
                    return []  # pagina vera ma senza risultati
            if code in (403, 429, None) or (code and code >= 500):
                log(f"    HTTP {code}: attendo {wait}s")
                time.sleep(wait)
                wait *= 2
                if attempt >= 2:
                    self.new_session()
            else:
                log(f"    HTTP {code} inatteso")
                break
        raise Blocked(f"nessuna risposta valida per {params}")


# ---------------------------------------------------------------- utilità

def condition(item) -> tuple[str, int]:
    text = str(item.get("status") or "").strip()
    low = text.lower()
    return text, next((r for k, r in STATUS_TEXT_RANK if k in low), 0)


LEN_PATTERNS = [
    re.compile(r"\bL\s?(\d{2})\b", re.I),                                         # L32
    re.compile(r"\bW\s?\d{2}\s?[/xX×-]?\s?L\s?(\d{2})\b", re.I),                   # W32L30, W32/L30
    re.compile(r"(?<![\d.,])(?:2[6-9]|3\d|4[0-4])\s?[/xX×]\s?(\d{2})(?![\d.,])"),  # 32/30, 32x34
]


def detected_lengths(text: str) -> set[int]:
    found = set()
    for pat in LEN_PATTERNS:
        for m in pat.finditer(text or ""):
            n = int(m.group(1))
            if 26 <= n <= 38:
                found.add(n)
    return found


def size_ok(item, profile: dict | None) -> bool:
    if not profile:
        return True
    size = str(item.get("size_title") or "").strip()
    if not any(re.search(p, size, re.I) for p in profile.get("match", [])):
        return False
    allowed = profile.get("allowed_lengths")
    if allowed:
        lens = detected_lengths(item.get("title", ""))
        if lens and not (lens & set(allowed)):
            return False
    return True


def base_params(cat: dict) -> tuple[list[tuple[str, str]], bool]:
    """Parametri della pagina catalogo. Ritorna (params, taglie_filtrate_da_vinted)."""
    params: list[tuple[str, str]] = []
    if cat.get("vinted_url"):
        params = [(k, v) for k, v in parse_qsl(urlparse(cat["vinted_url"]).query)
                  if k not in ("order", "page", "time", "search_id")]
    if not any(k.startswith("catalog") for k, _ in params):
        params += [("catalog[]", str(c)) for c in cat.get("catalog_ids", [])]
    if cat.get("size_ids") and not any(k.startswith("size_ids") for k, _ in params):
        params += [("size_ids[]", str(s)) for s in cat["size_ids"]]
    return params, any(k.startswith("size_ids") for k, _ in params)


def normalize(item, cat: dict) -> dict | None:
    price = item.get("price")
    if price is None:
        return None
    total = item.get("total_item_price")
    if total is None or total < price:
        bp = CONFIG["buyer_protection"]
        pct = bp["percent"] if price <= 500 else 2
        total = round(price + price * pct / 100 + bp["fixed"], 2)
    fee = round(total - price, 2)
    ship = float(cat.get("shipping_estimate", 0))
    cond_text, cond_rank = condition(item)
    return {
        "id": item.get("id"),
        "t": item.get("title", ""),
        "b": item.get("brand_title", ""),
        "s": item.get("size_title", ""),
        "c": cond_text,
        "cr": cond_rank,
        "p": price,
        "f": fee,
        "sh": ship,
        "tot": round(total + ship, 2),
        "h": int(item.get("favourite_count") or 0),
        "img": item.get("photo"),
        "u": item.get("url"),
    }


# ---------------------------------------------------------------- main

def scrape_category(client, cat: dict, profile: dict | None) -> list[dict]:
    params, server_sizes = base_params(cat)
    local_profile = None if server_sizes else profile
    seen: dict = {}
    raw_count = 0
    blocked = False
    for order, n_pages in CONFIG["pages"].items():
        if blocked:
            break
        for page in range(1, int(n_pages) + 1):
            q = params + [("order", order), ("page", str(page))]
            try:
                items = client.get_items(q)
            except Blocked:
                if not seen:
                    raise
                log(f"  interrotto a metà: tengo i {len(seen)} articoli già letti")
                blocked = True
                break
            raw_count += len(items)
            for it in items:
                if not size_ok(it, local_profile):
                    continue
                norm = normalize(it, cat)
                if norm and norm["id"] not in seen and norm["img"]:
                    seen[norm["id"]] = norm
            time.sleep(random.uniform(*CONFIG["delay_seconds"]))
            if len(items) < 30:
                break  # risultati finiti
    items = sorted(seen.values(), key=lambda x: (-x["h"], x["tot"]))
    log(f"  {cat['name']}: {raw_count} letti, {len(items)} nella tua taglia")
    return items[: CONFIG.get("max_items_per_category", 300)]


def main(client=None) -> int:
    previous = {}
    if OUT_PATH.exists():
        try:
            for c in json.loads(OUT_PATH.read_text(encoding="utf-8")).get("categories", []):
                previous[c["id"]] = c
        except Exception:
            pass

    client = client or VintedClient()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out_cats, fresh = [], 0
    for cat in CONFIG["categories"]:
        profile = CONFIG["size_profiles"].get(cat.get("size_profile", ""))
        log(f"> {cat['name']}")
        entry = {
            "id": cat["id"],
            "name": cat["name"],
            "size_label": (profile or {}).get("label", ""),
            "shipping_estimate": cat.get("shipping_estimate", 0),
        }
        try:
            items = scrape_category(client, cat, profile)
            if not items:
                raise Blocked("nessun articolo nella tua taglia")
            entry.update(items=items, updated_at=now, stale=False)
            fresh += 1
        except Blocked as e:
            log(f"  {cat['name']}: {e}")
            old = previous.get(cat["id"])
            if not old:
                continue
            entry.update(items=old.get("items", []), updated_at=old.get("updated_at"), stale=True)
        out_cats.append(entry)

    if fresh == 0:
        log("Nessuna categoria aggiornata. File invariato.")
        return 1

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": now, "domain": CONFIG["domain"], "categories": out_cats}
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"Scritto {OUT_PATH} ({fresh}/{len(CONFIG['categories'])} categorie aggiornate)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
