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
# Offizieller Papierkram nach dem Umzug — Links auf die echten Behoerdenwege.
PAPERWORK = {
    "title": "German paperwork starter pack (in rough order)",
    "steps": [
        {"step": 1, "name": "Anmeldung (address registration)",
         "note": "Register your address at the local Buergeramt within 14 days of moving in. Book the appointment EARLY.",
         "url": "https://www.bmi.bund.de/EN/topics/administrative-reform/register/register-node.html"},
        {"step": 2, "name": "Steuer-ID (tax ID)",
         "note": "Arrives by post automatically after Anmeldung. Your employer needs it.",
         "url": "https://www.bzst.de/EN/Private_individuals/Tax_identification_number/tax_identification_number_node.html"},
        {"step": 3, "name": "Health insurance (Krankenversicherung)",
         "note": "Mandatory. Pick a public insurer (gesetzliche Kasse) before your first working day.",
         "url": "https://www.krankenkassen.de/gesetzliche-krankenkassen/krankenkassen-liste/"},
        {"step": 4, "name": "Bank account",
         "note": "Needed for salary and rent. Many banks accept passport + Anmeldung certificate.",
         "url": "https://www.bafin.de/EN/Verbraucher/Bank/Produkte/Basiskonto/basiskonto_node_en.html"},
        {"step": 5, "name": "Kindergeld (child benefit)",
         "note": "About 255 EUR per child per month via the Familienkasse — apply online.",
         "url": "https://www.arbeitsagentur.de/en/family-and-children"},
        {"step": 6, "name": "Buergergeld (citizen's benefit)",
         "note": "If you need support while job hunting — apply at your local Jobcenter (jobcenter.digital).",
         "url": "https://www.jobcenter.digital/"},
        {"step": 7, "name": "Rundfunkbeitrag (broadcasting fee)",
         "note": "Yes, it finds you automatically. 18.36 EUR/month per household. Resistance is futile.",
         "url": "https://www.rundfunkbeitrag.de/"},
    ],
    "source": "Official links only (bund.de ecosystem). No affiliate, no middlemen.",
}


# Expat-getestet: erst wohnen (hotel/immobilienmakler/umzug/moebel), dann
# Alltag (supermarkt..friseur), dann der deutsche Endgegner (steuerberater).
ESSENTIALS = ["hotel", "immobilienmakler", "umzugsunternehmen", "moebelhaus",
              "supermarkt", "baecker", "drogerie", "arztpraxis", "zahnarzt",
              "bank", "friseur", "optiker", "restaurant", "cafe",
              "steuerberater"]


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


DOMAIN = "movetogermany.lol"


def _accept_quality(accept, target):
    """RFC-9110-q-Wert für einen Medientyp im Accept-Header (exakter Match)."""
    best = None
    for part in (accept or "").split(","):
        bits = part.strip().split(";")
        mt = bits[0].strip().lower()
        if mt != target:
            continue
        q = 1.0
        for p in bits[1:]:
            p = p.strip()
            if p.startswith("q="):
                try: q = float(p[2:])
                except ValueError: q = 0.0
        best = max(best or 0.0, q)
    return best


def wants_markdown(accept):
    q_md = _accept_quality(accept, "text/markdown")
    if q_md is None:
        return False
    q_html = _accept_quality(accept, "text/html")
    if q_html is None:
        q_html = _accept_quality(accept, "text/*") or _accept_quality(accept, "*/*") or 0.0
    return q_md > 0 and q_md >= q_html


def index_markdown():
    cats = ", ".join(v["label"] for v in NETWORK[:15]) + f" … ({len(NETWORK)} categories total)"
    return (
        "# move to germany, lol — the arrival planner for you + your AI agent\n\n"
        "Because the paperwork is enough drama. Human and AI agent build the everyday\n"
        "essentials for a new German address together: the agent searches 80+ business\n"
        "categories in parallel, the human curates the shared shortlist and writes notes,\n"
        "the agent reads them back and refines the plan.\n\n"
        "## WebMCP tools on this page\n"
        "list_categories, set_home_plz, find_nearby, generate_starter_plan,\n"
        "add_to_shortlist, remove_from_shortlist, get_shortlist, set_note, export_plan —\n"
        "registered via document.modelContext, typed JSON schemas, readOnlyHint where honest.\n\n"
        "## HTTP API\n"
        "- GET /api/categories — all categories of the network\n"
        "- GET /api/search?cat=<slug>&plz=<plz>&limit=5 — one category, distance-sorted\n"
        "- GET /api/essentials?plz=<plz>&cats=a,b,c — many categories in parallel\n\n"
        f"Categories include: {cats}\n\n"
        "Data: the 'in meiner Naehe' network — 80+ agent-readable German directories\n"
        "(OpenStreetMap ODbL 1.0, Overture Maps CDLA-Permissive-2.0). Open source (MIT):\n"
        "https://github.com/shufflethis/neu-hier\n"
    )


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
        self.send_header("Vary", "Accept")
        self.send_header("ratelimit-limit", "1000")
        self.send_header("ratelimit-remaining", "999")
        self.send_header("ratelimit-reset", "60")
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
            if wants_markdown(self.headers.get("Accept", "")):
                self._send(index_markdown(), "text/markdown; charset=utf-8")
            else:
                self._send(INDEX_HTML, "text/html; charset=utf-8")
            return

        if path == "/index.md":
            self._send(index_markdown(), "text/markdown; charset=utf-8")
            return

        if path == "/robots.txt":
            agents = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot",
                      "Claude-User", "Claude-SearchBot", "PerplexityBot",
                      "Perplexity-User", "Google-Extended", "GoogleOther",
                      "CCBot", "meta-externalagent", "Applebot-Extended",
                      "Bytespider", "MistralAI-User"]
            body = "# Explicitly welcomed AI agents/crawlers (deliberate choice)\n"
            for a in agents:
                body += f"User-agent: {a}\nAllow: /\n\n"
            body += ("User-agent: *\nAllow: /\n"
                     "Content-Signal: search=yes, ai-input=yes, ai-train=yes\n\n"
                     f"Sitemap: https://{DOMAIN}/sitemap.xml\n")
            self._send(body, "text/plain; charset=utf-8")
            return

        if path == "/sitemap.xml":
            import datetime as _dt
            today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
            urls = ["/", "/llms.txt", "/index.md", "/auth.md", "/openapi.json"]
            body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
            for u in urls:
                body += f"  <url><loc>https://{DOMAIN}{u}</loc><lastmod>{today}</lastmod></url>\n"
            body += "</urlset>"
            self._send(body, "application/xml; charset=utf-8")
            return

        if path == "/.well-known/mcp.json":
            self._send({
                "$schema": "https://static.modelcontextprotocol.io/schemas/2025-07-09/server.schema.json",
                "name": "lol.movetogermany/arrival-planner",
                "description": "Collaborative arrival planner for Germany: WebMCP in-page tools plus an "
                               "HTTP aggregation API over 80+ distance-sorted German business directories. "
                               "Read-only, no authentication.",
                "version": "1.0.0",
                "websiteUrl": f"https://{DOMAIN}/",
            }, "application/json; charset=utf-8")
            return

        if path == "/auth.md":
            self._send(
                f"# Authentication — {DOMAIN}\n\n"
                "This public API is **read-only and requires no authentication** — no key,\n"
                "token or session. Please send a meaningful User-Agent (name + contact URL).\n\n"
                "There is deliberately no OAuth: no user accounts, no write endpoints.\n"
                "For bulk access use the underlying network APIs (see /llms.txt).\n",
                "text/markdown; charset=utf-8")
            return

        if path == "/openapi.json":
            self._send({
                "openapi": "3.0.3",
                "info": {"title": "move to germany, lol — aggregation API", "version": "1.0.0",
                         "description": "Distance-sorted essentials search across 80+ German business directories."},
                "servers": [{"url": f"https://{DOMAIN}"}],
                "paths": {
                    "/api/categories": {"get": {"operationId": "listCategories",
                        "summary": "All categories of the network",
                        "responses": {"200": {"description": "Category catalog"}}}},
                    "/api/search": {"get": {"operationId": "searchCategory",
                        "summary": "Closest providers of one category around a PLZ",
                        "parameters": [
                            {"name": "cat", "in": "query", "required": True, "schema": {"type": "string"}},
                            {"name": "plz", "in": "query", "required": True, "schema": {"type": "string", "pattern": "^[0-9]{5}$"}},
                            {"name": "limit", "in": "query", "schema": {"type": "integer", "maximum": 20}}],
                        "responses": {"200": {"description": "Distance-sorted providers"},
                                      "400": {"description": "Missing parameters"}}}},
                    "/api/jobs": {"get": {"operationId": "searchJobs",
                        "summary": "Job openings around a PLZ (official Bundesagentur fuer Arbeit data)",
                        "parameters": [
                            {"name": "plz", "in": "query", "required": True, "schema": {"type": "string", "pattern": "^[0-9]{5}$"}},
                            {"name": "what", "in": "query", "schema": {"type": "string", "description": "free-text job query, e.g. 'python developer'"}},
                            {"name": "limit", "in": "query", "schema": {"type": "integer", "maximum": 20}},
                            {"name": "radius", "in": "query", "schema": {"type": "integer", "maximum": 200, "description": "km, default 25"}}],
                        "responses": {"200": {"description": "Job openings with salary ranges and official detail links"},
                                      "400": {"description": "Missing parameters"},
                                      "502": {"description": "Upstream API unavailable"}}}},
                    "/api/paperwork": {"get": {"operationId": "getPaperwork",
                        "summary": "German paperwork starter pack with official links",
                        "responses": {"200": {"description": "Ordered checklist"}}}},
                    "/api/essentials": {"get": {"operationId": "searchEssentials",
                        "summary": "Many categories in parallel around a PLZ",
                        "parameters": [
                            {"name": "plz", "in": "query", "required": True, "schema": {"type": "string", "pattern": "^[0-9]{5}$"}},
                            {"name": "cats", "in": "query", "schema": {"type": "string", "description": "comma-separated slugs"}},
                            {"name": "limit", "in": "query", "schema": {"type": "integer", "maximum": 5}}],
                        "responses": {"200": {"description": "Per-category distance-sorted providers"},
                                      "400": {"description": "Missing parameters"}}}},
                },
            }, "application/json; charset=utf-8")
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

        if path == "/api/jobs":
            plz = (q.get("plz") or [""])[0]
            what = (q.get("what") or [""])[0]
            limit = min(int((q.get("limit") or ["5"])[0]), 20)
            radius = min(int((q.get("radius") or ["25"])[0]), 200)
            if not plz:
                self._send({"error": "plz ist Pflicht"}, status=400)
                return
            # Offizielle Jobsuche-API der Bundesagentur fuer Arbeit
            # (bund.dev / bundesAPI, oeffentlicher Key "jobboerse-jobsuche")
            params = {"wo": plz, "umkreis": str(radius), "size": str(limit)}
            if what:
                params["was"] = what
            url = ("https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
                   "/pc/v6/jobs?" + urllib.parse.urlencode(params))
            try:
                req = urllib.request.Request(url, headers={
                    "X-API-Key": "jobboerse-jobsuche",
                    "User-Agent": "movetogermany.lol/1.0"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = json.load(r)
            except Exception as exc:
                self._send({"error": "Bundesagentur-API nicht erreichbar: " + str(exc)[:120]},
                           status=502)
                return
            jobs = []
            for s in data.get("ergebnisliste", [])[:limit]:
                lok = (s.get("stellenlokationen") or [{}])[0]
                adr = lok.get("adresse") or {}
                salary = None
                if s.get("gehaltsspanneVon"):
                    salary = (f"{int(s['gehaltsspanneVon']):,} – "
                              f"{int(s.get('gehaltsspanneBis') or s['gehaltsspanneVon']):,} EUR/Jahr")
                jobs.append({
                    "title": s.get("stellenangebotsTitel"),
                    "employer": s.get("firma"),
                    "city": adr.get("ort"), "plz": adr.get("plz"),
                    "lat": lok.get("breite"), "lon": lok.get("laenge"),
                    "salary": salary,
                    "homeoffice": s.get("homeofficemoeglich"),
                    "career_changer_ok": s.get("quereinstiegGeeignet"),
                    "url": ("https://www.arbeitsagentur.de/jobsuche/jobdetail/"
                            + urllib.parse.quote(s.get("referenznummer") or "")),
                })
            self._send({"plz": plz, "what": what or None,
                        "total": data.get("maxErgebnisse"), "jobs": jobs,
                        "source": "Bundesagentur für Arbeit (official Jobsuche API)"})
            return

        if path == "/api/paperwork":
            self._send(PAPERWORK)
            return

        if path == "/llms.txt":
            body = (
                "# move to germany, lol — collaborative arrival planner\n\n"
                "> Human and AI agent build the everyday essentials for a new German address "
                "together: the agent searches 80+ business categories in parallel via WebMCP "
                "tools, the human curates the shared shortlist and writes notes, the agent "
                "reads them back. Data: the 'in meiner Naehe' network (OpenStreetMap/Overture).\n\n"
                "## Core pages\n"
                f"- [App](https://{DOMAIN}/): the collaborative planner (WebMCP tools register on load)\n"
                f"- [Markdown version](https://{DOMAIN}/index.md): this page as plain Markdown\n"
                f"- [OpenAPI schema](https://{DOMAIN}/openapi.json): full HTTP API contract\n"
                f"- [Auth notes](https://{DOMAIN}/auth.md): keyless, read-only, rate-limit headers\n\n"
                "## API\n"
                f"- [All categories](https://{DOMAIN}/api/categories): the 80+ categories of the network\n"
                f"- [Search one category](https://{DOMAIN}/api/search?cat=supermarkt&plz=10115&limit=5): distance-sorted providers\n"
                f"- [Essentials in parallel](https://{DOMAIN}/api/essentials?plz=10115): many categories at once\n"
                f"- [Job search](https://{DOMAIN}/api/jobs?plz=10115&what=developer): official Bundesagentur fuer Arbeit openings\n"
                f"- [Paperwork starter pack](https://{DOMAIN}/api/paperwork): ordered official bureaucracy steps\n\n"
                "## WebMCP tools on the page\n"
                "list_categories, set_home_plz, find_nearby, generate_starter_plan, add_to_shortlist, "
                "remove_from_shortlist, get_shortlist, set_note, find_jobs, get_paperwork_checklist, "
                "export_plan — registered via "
                "document.modelContext with typed JSON schemas and honest annotations.\n\n"
                "## Source\n"
                "- [GitHub (MIT)](https://github.com/shufflethis/neu-hier): full source, zero dependencies\n"
                "- [Network example](https://friseur-in-meiner-naehe.de/llms.txt): one of the 80+ underlying directories\n"
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
