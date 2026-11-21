#!/usr/bin/env python3
"""
Vinted Radar – scraper giornaliero.

Legge config.json, interroga l'endpoint interno di Vinted /api/v2/catalog/items
per ogni categoria, filtra per taglia, calcola il prezzo finale
(articolo + protezione acquisti + spedizione stimata) e scrive docs/data/items.json.

Se Vinted blocca una categoria, si tengono i dati del giorno prima per quella
categoria (marcati come "stale"). Se le blocca tutte, il file non viene toccato
e lo script esce con codice 1 (il workflow risulta rosso, il sito resta online).
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("VR_CONFIG", ROOT / "config.json"))
OUT_PATH = Path(os.environ.get("VR_OUT", ROOT / "docs" / "data" / "items.json"))

CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
BASE = f"https://www.{CONFIG['domain']}"
API = f"{BASE}/api/v2/catalog/items"

LANG = "it-IT,it;q=0.9,en-US;q=0.6,en;q=0.5"
API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": LANG,
    "Referer": f"{BASE}/catalog",
    "Origin": BASE,
}

# status_id Vinted -> grado (5 = nuovo con cartellino ... 1 = discrete)
STATUS_ID_RANK = {6: 5, 1: 4, 2: 3, 3: 2, 4: 1}
STATUS_TEXT_RANK = [
    ("con cartellino", 5), ("with tags", 5),
    ("senza cartellino", 4), ("without tags", 4),
    ("ottim", 3), ("very good", 3),
    ("buon", 2), ("good", 2),
    ("discret", 1), ("satisf", 1),
]

# chiavi dell'URL di ricerca vinted.it -> parametri API
URL_PARAM_MAP = {
    "catalog": "catalog_ids", "catalog_ids": "catalog_ids",
    "size_ids": "size_ids", "brand_ids": "brand_ids", "status_ids": "status_ids",
    "color_ids": "color_ids", "material_ids": "material_ids",
    "price_from": "price_from", "price_to": "price_to", "currency": "currency",
    "search_text": "search_text",
}


class Blocked(Exception):
    pass


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- HTTP

class VintedClient:
    def __init__(self):
        from curl_cffi import requests  # import qui: i test possono sostituire il client

        self._requests = requests
        self.session = None
        self.new_session()

    def new_session(self):
        s = self._requests.Session(impersonate="chrome")
        proxy = os.environ.get("VINTED_PROXY", "").strip()
        if proxy:
            s.proxies = {"http": proxy, "https": proxy}
        # la home imposta il cookie anonimo access_token_web
        for path in ("/", "/catalog"):
            try:
                r = s.get(BASE + path, headers={"Accept-Language": LANG}, timeout=30)
                log(f"  bootstrap {path}: HTTP {r.status_code}")
            except Exception as e:  # rete, TLS…
                log(f"  bootstrap {path}: errore {e}")
                continue
            if s.cookies.get("access_token_web"):
                break
        if not s.cookies.get("access_token_web"):
            log("  attenzione: cookie access_token_web assente, provo comunque")
        self.session = s

    def get_items(self, params: dict) -> list[dict]:
        wait = 5
        for attempt in range(1, 5):
            try:
                r = self.session.get(API, params=params, headers=API_HEADERS, timeout=30)
                code = r.status_code
            except Exception as e:
                log(f"    errore rete ({e}), tentativo {attempt}")
                code = None
            if code == 200:
                try:
                    return r.json().get("items", []) or []
                except ValueError:
                    log("    risposta non JSON (probabile challenge anti-bot)")
                    code = 403
            if code == 401:
                log("    401: rinnovo sessione")
                self.new_session()
            elif code in (403, 429, None) or (code and code >= 500):
                log(f"    HTTP {code}: attendo {wait}s")
                time.sleep(wait)
                wait *= 2
                if code == 403 and attempt >= 2:
                    self.new_session()
            else:
                log(f"    HTTP {code} inatteso")
                break
        raise Blocked(f"bloccato su {params}")


# ---------------------------------------------------------------- utilità

def money(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, dict):
        v = v.get("amount")
    try:
        return round(float(str(v).replace(",", ".")), 2)
    except (TypeError, ValueError):
        return None


def condition(item) -> tuple[str, int]:
    raw = item.get("status")
    sid = item.get("status_id")
    if isinstance(raw, dict):
        sid = raw.get("id", sid)
        raw = raw.get("title")
    text = str(raw or "").strip()
    try:
        rank = STATUS_ID_RANK.get(int(sid), 0) if sid is not None else 0
    except (TypeError, ValueError):
        rank = 0
    if not rank:
        low = text.lower()
        rank = next((r for k, r in STATUS_TEXT_RANK if k in low), 0)
    return text, rank


def photo_url(item) -> str | None:
    p = item.get("photo") or (item.get("photos") or [None])[0]
    if not isinstance(p, dict):
        return None
    for t in p.get("thumbnails") or []:
        if t.get("type") in ("thumb310x430", "thumb428x624", "thumb364x428") and t.get("url"):
            return t["url"]
    return p.get("url") or p.get("full_size_url")


def item_url(item) -> str:
    u = item.get("url") or ""
    if u.startswith("http"):
        return u
    if u.startswith("/"):
        return BASE + u
    return f"{BASE}/items/{item.get('id')}"


LEN_PATTERNS = [
    re.compile(r"\bL\s?(\d{2})\b", re.I),                                # L32
    re.compile(r"\bW\s?\d{2}\s?[/xX×-]?\s?L\s?(\d{2})\b", re.I),          # W32L30, W32/L30
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
    size = str(item.get("size_title") or item.get("size") or "").strip()
    if not any(re.search(p, size, re.I) for p in profile.get("match", [])):
        return False
    allowed = profile.get("allowed_lengths")
    if allowed:
        lens = detected_lengths(f"{item.get('title', '')} {item.get('description', '')}")
        if lens and not (lens & set(allowed)):
            return False
    return True


def base_params(cat: dict) -> tuple[dict, bool]:
    """Parametri API per la categoria. Ritorna (params, size_lato_server)."""
    params: dict[str, str] = {}
    if cat.get("vinted_url"):
        qs = parse_qs(urlparse(cat["vinted_url"]).query)
        for key, values in qs.items():
            name = URL_PARAM_MAP.get(key.replace("[]", ""))
            if name:
                params[name] = ",".join(values)
    if "catalog_ids" not in params and cat.get("catalog_ids"):
        params["catalog_ids"] = ",".join(map(str, cat["catalog_ids"]))
    if cat.get("size_ids") and "size_ids" not in params:
        params["size_ids"] = ",".join(map(str, cat["size_ids"]))
    return params, "size_ids" in params


def normalize(item, cat: dict) -> dict | None:
    price = money(item.get("price"))
    if price is None:
        return None
    total = money(item.get("total_item_price"))
    fee = money(item.get("service_fee"))
    if total is None or total < price:
        bp = CONFIG["buyer_protection"]
        pct = bp["percent"] if price <= 500 else 2
        fee = fee if fee is not None else round(price * pct / 100 + bp["fixed"], 2)
        total = round(price + fee, 2)
    else:
        fee = round(total - price, 2)
    ship = float(cat.get("shipping_estimate", 0))
    cond_text, cond_rank = condition(item)
    return {
        "id": item.get("id"),
        "t": (item.get("title") or "").strip(),
        "b": (item.get("brand_title") or "").strip(),
        "s": (item.get("size_title") or "").strip(),
        "c": cond_text,
        "cr": cond_rank,
        "p": price,
        "f": fee,
        "sh": ship,
        "tot": round(total + ship, 2),
        "h": int(item.get("favourite_count") or 0),
        "img": photo_url(item),
        "u": item_url(item),
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
            q = dict(params, order=order, page=page, per_page=CONFIG.get("per_page", 96))
            try:
                items = client.get_items(q)
            except Blocked:
                if not seen:
                    raise
                log(f"  bloccato a metà: tengo i {len(seen)} articoli già letti")
                blocked = True
                break
            raw_count += len(items)
            for it in items:
                if it.get("is_reserved") or it.get("is_closed"):
                    continue
                if not size_ok(it, local_profile):
                    continue
                norm = normalize(it, cat)
                if norm and norm["id"] not in seen and norm["img"]:
                    seen[norm["id"]] = norm
            time.sleep(random.uniform(*CONFIG["delay_seconds"]))
            if len(items) < int(q["per_page"]) * 0.5:
                break  # pagine finite
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
                raise Blocked("nessun articolo")
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
        log("Nessuna categoria aggiornata: Vinted ha bloccato le richieste. File invariato.")
        return 1

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": now, "domain": CONFIG["domain"], "categories": out_cats}
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"Scritto {OUT_PATH} ({fresh}/{len(CONFIG['categories'])} categorie aggiornate)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
