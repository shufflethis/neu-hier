#!/usr/bin/env python3
"""neu-hier — Umzugs-/Ankommens-Planer über dem "in meiner Nähe"-Netzwerk.

Aggregiert 80+ vertikale Verzeichnis-APIs (agentic-naehe-Netzwerk) zu einer
Grundversorgungs-Suche je Postleitzahl. Läuft standalone: auf dem Netzwerk-VPS
gegen 127.0.0.1:<port>, überall sonst gegen die öffentlichen https-APIs
(CORS ist offen, keine Keys nötig).

Start:  python3 server.py            (Port 8871, öffentliche APIs)
        NEUHIER_LOCAL=1 python3 server.py   (lokale Ports, nur auf dem VPS)
"""
import json
import os
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("NEUHIER_PORT", "8871"))
USE_LOCAL = os.environ.get("NEUHIER_LOCAL") == "1"

with open(os.path.join(HERE, "network.json"), encoding="utf-8") as f:
    NETWORK = json.load(f)
BY_SLUG = {v["slug"]: v for v in NETWORK}

with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
    INDEX_HTML = f.read()

# Grundversorgungs-Set für den Ein-Klick-Starterplan
ESSENTIALS = ["supermarkt", "baecker", "drogerie", "arztpraxis", "zahnarzt",
              "bank", "tankstelle", "friseur", "optiker", "physiotherapie",
              "restaurant", "cafe"]


def vertical_search(slug, plz, limit=3, timeout=12):
    """Fragt die Such-API einer Vertikale ab (lokal oder öffentlich)."""
    v = BY_SLUG.get(slug)
    if not v:
        return {"slug": slug, "error": "unknown category"}
    base = (f"http://127.0.0.1:{v['port']}" if USE_LOCAL
            else f"https://{v['domain']}")
    url = f"{base}/api/search?plz={urllib.parse.quote(plz)}&limit={int(limit)}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "neu-hier-aggregator/1.0 (+https://github.com/shufflethis/neu-hier)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
        recs = []
        for rec in data.get("records", []):
            recs.append({k: rec.get(k) for k in (
                "name", "city", "street", "housenumber", "postcode",
                "lat", "lon", "phone", "website", "distance_km",
                "gmaps_rating", "gmaps_reviews", "opening_hours")})
        return {"slug": slug, "label": v["label"], "emoji": v["emoji"],
                "domain": v["domain"], "records": recs}
    except Exception as exc:  # Vertikale nicht erreichbar -> weich degradieren
        return {"slug": slug, "label": v["label"], "emoji": v["emoji"],
                "domain": v["domain"], "records": [], "error": str(exc)[:120]}


class Handler(BaseHTTPRequestHandler):
    server_version = "neu-hier/1.0"

    def _send(self, body, ctype="application/json; charset=utf-8", status=200):
        if not isinstance(body, (str, bytes)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store" if "json" in ctype else "public, max-age=300")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        q = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self._send(INDEX_HTML, "text/html; charset=utf-8")
            return

        if path == "/api/categories":
            self._send({"count": len(NETWORK), "essentials": ESSENTIALS,
                        "categories": [{k: v[k] for k in ("slug", "label", "plural", "emoji", "domain")}
                                       for v in NETWORK]})
            return

        if path == "/api/search":
            slug = (q.get("cat") or [""])[0]
            plz = (q.get("plz") or [""])[0]
            limit = min(int((q.get("limit") or ["5"])[0]), 20)
            if not slug or not plz:
                self._send({"error": "cat und plz sind Pflicht"}, status=400)
                return
            self._send(vertical_search(slug, plz, limit))
            return

        if path == "/api/essentials":
            plz = (q.get("plz") or [""])[0]
            cats = (q.get("cats") or [",".join(ESSENTIALS)])[0].split(",")
            cats = [c.strip() for c in cats if c.strip() in BY_SLUG][:20]
            limit = min(int((q.get("limit") or ["3"])[0]), 5)
            if not plz:
                self._send({"error": "plz ist Pflicht"}, status=400)
                return
            with ThreadPoolExecutor(max_workers=10) as ex:
                results = list(ex.map(lambda s: vertical_search(s, plz, limit), cats))
            self._send({"plz": plz, "categories": results})
            return

        if path == "/llms.txt":
            body = (
                "# move to germany, lol — arrival planner (human + agent)\n\n"
                "> movetogermany.lol: Kollaborativer Umzugs-Planer über dem deutschlandweiten "
                "'in meiner Nähe'-Verzeichnisnetzwerk (80+ Branchen, OpenStreetMap/Overture-Daten). "
                "Mensch und KI-Agent bauen gemeinsam die Grundversorgung für eine neue Adresse auf.\n\n"
                "## WebMCP\n"
                "Die Seite registriert Tools via document.modelContext (Suche, Shortlist, "
                "Starterplan, Export) — Agent und Mensch teilen sich denselben Seiten-Zustand.\n\n"
                "## API\n"
                "- /api/categories: alle Branchen des Netzwerks\n"
                "- /api/search?cat=<slug>&plz=<plz>&limit=5: eine Branche\n"
                "- /api/essentials?plz=<plz>: Grundversorgung parallel über viele Branchen\n"
            )
            self._send(body, "text/markdown; charset=utf-8")
            return

        self._send({"error": "not found"}, status=404)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"neu-hier auf 127.0.0.1:{PORT} — {'lokale Ports' if USE_LOCAL else 'öffentliche APIs'}, "
          f"{len(NETWORK)} Vertikalen")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
