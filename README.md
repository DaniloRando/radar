# Radar · il tuo Vinted uomo, filtrato e ordinato per cuori

Ogni mattina un job gratuito su GitHub scarica gli articoli da vinted.it nella tua taglia e pubblica un sito da usare sul telefono.

- **Home**: tutte le sezioni (Camicie, Jeans, Pantaloni, Maglioni e felpe, Giacche e cappotti), ognuna con 5 anteprime da scorrere.
- **Sezione**: tutti gli articoli, ordinati di default per numero di cuori, con l'opzione per ordinare per prezzo crescente o decrescente e una ricerca per marca o parola.
- **Ogni articolo** mostra foto, prezzo totale (articolo + protezione acquisti + spedizione stimata), cuori, nome, marca, taglia e condizioni. Toccandolo si apre su Vinted (sul telefono si apre direttamente l'app).

Costo: **0 €** (GitHub Actions + GitHub Pages, repository pubblico).

---

## Installazione (10 minuti, anche da telefono)

1. **Crea un account** su github.com, se non ce l'hai.
2. **Crea un repository nuovo**, *pubblico* (Pages gratis richiede il repository pubblico), ad esempio `radar`.
3. **Carica i file**: nella pagina del repository premi *Add file → Upload files* e trascina **tutto il contenuto** di questa cartella, comprese le cartelle `.github`, `docs` e `scraper`.
   > Se dal telefono la cartella `.github` non si carica, crea il file a mano: *Add file → Create new file*, nome `.github/workflows/aggiorna.yml`, e incolla il contenuto del file.
4. **Attiva il sito**: *Settings → Pages → Build and deployment → Source: Deploy from a branch*, branch `main`, cartella `/docs`, *Save*.
5. **Primo aggiornamento**: *Actions →* abilita i workflow se richiesto *→ Aggiorna dati Vinted → Run workflow*. Ci mette circa 2 minuti.
6. **Apri il sito**: `https://TUO-UTENTE.github.io/radar/`. Sul telefono usa *Condividi → Aggiungi alla schermata Home* e diventa un'icona come un'app.

Da quel momento si aggiorna da solo ogni giorno alle 06:17 (ora italiana, in inverno).

---

## Taglie e filtri (175 cm / 75 kg)

| Sezione | Taglia applicata | Come |
|---|---|---|
| Camicie, Maglioni e felpe, Giacche e cappotti | **M** (accetta anche "IT 48") | filtro sulla taglia dell'annuncio |
| Jeans | **W32** (su vinted.it "IT 42 \| W32"), e scarta gli annunci che nel titolo dichiarano una lunghezza diversa da **L32** (es. "W32 L30", "32/34") | Vinted non ha un filtro per la lunghezza, quindi la si legge dal titolo |
| Pantaloni | **W32** (su vinted.it appare come "IT 42 \| W32") oppure **M** | filtro sulla taglia dell'annuncio |

Filtri nell'app (icona in alto a destra; valgono per tutte le sezioni e restano salvati sul telefono):
- **Condizioni minime**: predefinito *Buone o meglio* (esclude "Discrete")
- **Prezzo totale massimo**: 15 / 25 / 40 / 60 / 100 €
- **Cuori minimi**: 5+ / 15+ / 30+
- **Spedizione stimata** inclusa o esclusa dal prezzo

### Cambiare taglie o categorie
Modifica `config.json` direttamente su GitHub (icona della matita):
- `size_profiles` → le taglie accettate (sono espressioni regolari sulla taglia dell'annuncio: `^M\\b` = "M").
- `categories` → aggiungi o togli sezioni. Esempio T-shirt: `{ "id": "tshirt", "name": "T-shirt e polo", "catalog_ids": [76], "size_profile": "top", "shipping_estimate": 3.49 }` (verifica l'ID come spiegato sotto).

### Filtri esatti di Vinted (consigliato dopo il primo giorno)
Il modo più preciso, e quello che fa meno richieste, è copiare una ricerca vera:
1. Su vinted.it, dal browser, apri la categoria e imposta i filtri che vuoi (taglia, condizioni, marche, prezzo).
2. Copia l'URL, che contiene ad esempio `catalog[]=257&size_ids[]=...&status_ids[]=...`.
3. In `config.json`, nella categoria, aggiungi `"vinted_url": "URL-COPIATO"`.

Se l'URL contiene `size_ids`, il filtro taglia locale viene disattivato e si usa quello di Vinted.

### Prezzo mostrato
`totale = prezzo articolo + protezione acquisti + spedizione stimata`
- **Protezione acquisti**: si usa quella che Vinted restituisce per ogni articolo. Se manca, si calcola come 0,70 € + 5% del prezzo.
- **Spedizione**: è una **stima** fissa per sezione (`shipping_estimate`: 3,49 € di base, 4,99 € per giacche e cappotti). Il costo reale dipende dal corriere e dal punto di ritiro che scegli al pagamento. Puoi modificarla in `config.json`.

---

## Se Vinted blocca (importante)

Vinted usa un sistema anti-bot (Datadome) e a volte blocca i server cloud, compresi quelli di GitHub. Lo scraper simula un browser Chrome (`curl_cffi`), rallenta tra una richiesta e l'altra e, se viene bloccato:
- tiene i dati del giorno prima per le sezioni bloccate (sul sito compare "dati del …");
- se blocca tutto, non tocca i dati e il workflow diventa rosso. Il sito resta online e mostra un avviso.

Se succede spesso, hai tre opzioni in ordine di costo:
1. **Rilanciarlo a mano** (*Actions → Run workflow*): spesso va al secondo tentativo.
2. **Farlo girare dal tuo PC** (gratis, IP di casa, quasi mai bloccato):
   ```bash
   git clone https://github.com/TUO-UTENTE/radar && cd radar
   pip install -r scraper/requirements.txt
   python scraper/scrape.py && git add docs/data && git commit -m "dati" && git push
   ```
   Programmalo ogni giorno con *Utilità di pianificazione* (Windows) oppure `cron` (Mac/Linux), e disattiva il workflow su GitHub.
3. **Proxy residenziale** (a pagamento, pochi euro al mese): aggiungi il secret `VINTED_PROXY` (*Settings → Secrets and variables → Actions*) nel formato `http://utente:password@host:porta`.

---

## Note
- Lo scraper legge circa 8 pagine da 96 articoli per sezione (5 per "rilevanza" e 3 per "più recenti") e tiene i 300 articoli con più cuori. Vinted non permette di ordinare per cuori, quindi l'ordinamento avviene dopo lo scaricamento.
- GitHub sospende i workflow pianificati dopo 60 giorni senza attività nel repository. Se succede, ti arriva un'email: basta riattivarli da *Actions*.
- Legge le pagine catalogo di www.vinted.it (in italiano e in euro). La nuova API di Vinted (`api.vinted.it/svc-catalogue/items`, da settembre 2026) dai server GitHub negli USA restituisce annunci americani in dollari, quindi non è usata. Se Vinted cambia l'aspetto delle pagine, va adattato `parse_catalog_html` in `scraper/scrape.py`. È pensato per uso personale e con poche richieste al giorno.

## Struttura
```
config.json                  categorie, taglie, spedizione stimata
scraper/scrape.py            scarica, filtra, calcola i prezzi
.github/workflows/aggiorna.yml   pianificazione giornaliera
docs/index.html              l'app (pagina unica, nessuna dipendenza)
docs/data/items.json         i dati (generato ogni giorno)
```
