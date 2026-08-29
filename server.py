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


def vertical_search(slug, plz, limit=3, timeout=12, lat=None, lon=None, booking_only=False):
    """Fragt die Such-API einer Vertikale ab (lokal oder öffentlich)."""
    v = BY_SLUG.get(slug)
    if not v:
        return {"slug": slug, "error": "unknown category"}
    base = (f"http://127.0.0.1:{v['port']}" if USE_LOCAL
            else f"https://{v['domain']}")
    params = {"limit": str(int(limit))}
    if lat is not None and lon is not None:
        params["lat"], params["lon"] = str(lat), str(lon)
    else:
        params["plz"] = plz
    if booking_only:
        params["booking"] = "only"
    url = f"{base}/api/search?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "neu-hier-aggregator/1.0 (+https://github.com/shufflethis/neu-hier)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
        recs = []
        for rec in data.get("records", []):
            recs.append({k: rec.get(k) for k in (
                "name", "city", "street", "housenumber", "postcode",
                "lat", "lon", "phone", "email", "website", "distance_km",
                "review_rating", "review_count", "opening_hours",
                "booking_capable", "booking_platform", "booking_url")})
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


GUIDE_MD = """# Moving to Germany: the complete arrival checklist (2026)

A practical, week-by-week checklist for relocating to Germany — what to do
before you land, in your first 14 days, and in your first two months. No
affiliate links; every link below goes to an official source.

## Before you land (4–2 weeks out)

- **Passport & visa**: non-EU citizens need the right residence purpose
  (work, study, family). Blue Card thresholds change yearly — check the
  official migration portal: https://www.make-it-in-germany.com/en/
- **Book temporary housing** for 4–8 weeks. You cannot rent most long-term
  flats without a German bank account and often not without an Anmeldung —
  plan for the overlap.
- **Scan your documents**: passport, birth certificate, marriage
  certificate, degree certificates, vaccination record. Germany loves paper.
- **Get a job first if you can**: most people move *for* a job. The federal
  job database is public: https://www.arbeitsagentur.de/jobsuche/

## Days 1–14 (the critical window)

1. **Anmeldung (address registration)** — the key that unlocks everything
   else. Register at the local Buergeramt within 14 days of moving in.
   Appointments are scarce in big cities: book the moment you know your
   address. https://www.bmi.bund.de/EN/topics/administrative-reform/register/register-node.html
2. **Steuer-ID (tax ID)** — arrives by post automatically ~2 weeks after
   Anmeldung. Your employer needs it; without it you pay maximum tax until
   corrected. https://www.bzst.de/EN/Private_individuals/Tax_identification_number/tax_identification_number_node.html
3. **Health insurance** — legally mandatory from day one of employment.
   Choose a public insurer (gesetzliche Krankenkasse); ~14.6% of gross
   salary plus surcharge, split with your employer.
   https://www.krankenkassen.de/gesetzliche-krankenkassen/krankenkassen-liste/
4. **Bank account** — needed for salary and rent. Bring passport +
   Anmeldung certificate. Every resident is entitled to a basic account
   (Basiskonto). https://www.bafin.de/EN/Verbraucher/Bank/Produkte/Basiskonto/basiskonto_node_en.html
5. **SIM/phone contract** — prepaid activates with passport; postpaid
   contracts usually want the Anmeldung and a German bank account.

## Weeks 3–8 (settling in)

- **Kindergeld (child benefit)** — about 255 EUR per child per month,
  via the Familienkasse: https://www.arbeitsagentur.de/en/family-and-children
- **Buergergeld** — if you're job hunting and eligible, apply at your local
  Jobcenter: https://www.jobcenter.digital/
- **Rundfunkbeitrag (broadcasting fee)** — 18.36 EUR/month per household.
  It will find you after Anmeldung; register once, avoid the back-payment.
  https://www.rundfunkbeitrag.de/
- **Liability insurance (Haftpflicht)** — not mandatory but socially
  expected; landlords often ask for it. A few euros a month.
- **Build your everyday map** — GP (Hausarzt), dentist, supermarket,
  hairdresser, pharmacy-level essentials. This is exactly what
  https://movetogermany.lol does: you and your AI agent build the shortlist
  together from 1.16M real businesses, sorted by distance from your
  postal code.

## The unwritten rules (learn these early)

- **Sundays are silent.** Shops close, drills stay off. Buy groceries on
  Saturday.
- **Cash still matters.** Many bakeries and restaurants are card-free;
  keep 50 EUR on you.
- **Punctuality is politeness.** "Quarter past" means 15 minutes past, not
  "whenever".
- **Recycling is a lifestyle.** Glass by color, Pfand bottles back to the
  store, paper separate. Your neighbors are watching. Lovingly.

---

*Maintained by [movetogermany.lol](https://movetogermany.lol/) — the arrival
planner you and your AI agent operate together (WebMCP inside). Machine
readers: this page is also available at /guide.md, and the interactive
planner exposes typed tools — see /llms.txt.*
"""


DEV_MD = """# One keyless API for 1.16M German local businesses

Stripe unified payments. Plaid unified banks. This unifies **German local
business data for AI agents**: 81 category directories, one endpoint, one
schema, **no API key**, no signup — plus official job data and a unified
booking lookup.

## Why this exists

Agent developers need local grounding data. Google Places is excellent but
costs money, needs a key, and its terms restrict caching and derivatives.
This API is OpenStreetMap/Overture-based: free, keyless, cache-friendly
(ODbL / CDLA-Permissive), built agent-first.

## MCP (recommended for agents)

Connect any MCP client to the streamable-HTTP endpoint:

    https://movetogermany.lol/mcp

Six tools: search_local, list_categories, search_essentials, find_bookable,
find_jobs (official Bundesagentur fuer Arbeit data), get_paperwork_checklist.
Server card: /.well-known/mcp.json

## REST

- GET /api/categories — all 81 categories (German + English labels)
- GET /api/search?cat=friseur&plz=10115&limit=5 — one category, distance-sorted
- GET /api/essentials?plz=10115&cats=supermarkt,zahnarzt — many categories in parallel
- GET /api/booking?plz=10115&category=friseur — unified booking lookup (deep links)
- GET /api/jobs?plz=10115&what=developer — official job openings
- GET /api/paperwork — the German bureaucracy starter pack

Full contract: /openapi.json — errors and rate limits are stated in /auth.md.

## The data

1.16M businesses across 81 categories, nationwide Germany, distance-sorted
per postal code or coordinates. Sources: OpenStreetMap (ODbL 1.0) and
Overture Maps (CDLA-Permissive-2.0). Each category also runs as its own
agent-readable directory with per-domain MCP — this endpoint is the unified
interface over all of them.

## Booking (honest status)

find_bookable returns online-bookable providers normalized across platforms
(google_booking, calendly, own booking forms) with one deep link each.
Today: lookup + deep link — the booking completes on the provider's
platform. Availability/slot APIs are the roadmap, not the promise.

## Terms

Free, keyless, read-only. Rate-limit headers on every response. Please send
a meaningful User-Agent. Data licenses: ODbL 1.0 / CDLA-Permissive-2.0 —
attribution required. Built by [Agentifizierung](https://www.agentifizierung.de/);
source: https://github.com/shufflethis/neu-hier
"""


def md_page_html(md, title, desc, path):
    """Eine Markdown-Quelle als gestylte HTML-Seite (Zwilling: /<path>.md)."""
    import html as _h
    import re as _re
    body = []
    for block in md.split("\n\n"):
        b = block.strip()
        if not b:
            continue
        if b.startswith("# "):
            body.append(f"<h1>{_h.escape(b[2:])}</h1>")
        elif b.startswith("## "):
            body.append(f"<h2>{_h.escape(b[3:])}</h2>")
        elif b == "---":
            body.append("<hr>")
        else:
            lines = b.split("\n")
            if all(l.lstrip().startswith(("- ", "* ")) or l[:3].rstrip(". ").isdigit() or l.startswith("  ") for l in lines):
                items, cur = [], None
                for l in lines:
                    if l.lstrip().startswith(("- ", "* ")) or (l.strip() and l.strip()[0].isdigit() and ". " in l[:4]):
                        if cur is not None:
                            items.append(cur)
                        cur = _re.sub(r"^\s*(?:[-*]|\d+\.)\s*", "", l)
                    else:
                        cur = (cur or "") + " " + l.strip()
                if cur:
                    items.append(cur)
                tag = "ol" if lines[0].strip()[0].isdigit() else "ul"
                body.append(f"<{tag}>" + "".join(f"<li>{md_inline(i)}</li>" for i in items) + f"</{tag}>")
            else:
                body.append(f"<p>{md_inline(' '.join(lines))}</p>")
    return ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{_h.escape(title)}</title>'
            f'<meta name="description" content="{_h.escape(desc)}">'
            f'<link rel="canonical" href="https://{DOMAIN}/{path}">'
            f'<link rel="alternate" type="text/markdown" href="/{path}.md">'
            '<link rel="icon" href="/favicon.svg" type="image/svg+xml">'
            '<style>body{margin:0;font-family:-apple-system,"Segoe UI",Roboto,Arial,sans-serif;'
            'background:#f6f7f9;color:#1a1d21;line-height:1.65}'
            '.wrap{max-width:720px;margin:0 auto;padding:40px 20px 64px}'
            'h1{font-size:1.7rem;letter-spacing:-.02em}h2{font-size:1.2rem;margin-top:30px}'
            'a{color:#0e7490;text-decoration:none}a:hover{text-decoration:underline}'
            'li{margin-bottom:8px}hr{border:0;border-top:1px solid #e3e6ea;margin:28px 0}'
            'p.back a{font-weight:600}</style></head><body><div class="wrap"><main>'
            '<p class="back"><a href="/">← movetogermany.lol</a></p>'
            + "".join(body) + "</main></div></body></html>")


def md_inline(s):
    import html as _h
    import re as _re
    s = _h.escape(s)
    s = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = _re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', s)
    s = _re.sub(r"(?<![\"=\w])(https://[^\s<]+)", r'<a href="\1">\1</a>', s)
    return s


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


def ba_jobs(plz, what="", limit=5, radius=25):
    """Offizielle Jobsuche-API der Bundesagentur fuer Arbeit
    (bund.dev / bundesAPI, oeffentlicher Key "jobboerse-jobsuche")."""
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
        return ({"error": "Bundesagentur-API nicht erreichbar: " + str(exc)[:120]}, 502)
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
    return ({"plz": plz, "what": what or None,
             "total": data.get("maxErgebnisse"), "jobs": jobs,
             "source": "Bundesagentur für Arbeit (official Jobsuche API)"}, 200)


# Dienstleistungs-Branchen mit nennenswerter Online-Buchbarkeit im Netzwerk
BOOKING_CATS = ["friseur", "massage", "kosmetikstudio", "nagelstudio",
                "physiotherapie", "tierklinik", "heilpraktiker", "tattoo",
                "yoga-studio", "pilates", "fahrschule", "nachhilfe"]


def booking_search(plz, category=None, limit=5):
    """Unified-Booking-Lookup: buchbare Anbieter (booking=only) ueber eine
    oder alle Service-Branchen, normalisiertes Schema mit Deep-Link.
    Ehrlich: Lookup + Deep-Link — Verfuegbarkeits-/Slot-APIs sind Roadmap."""
    cats = [category] if category else BOOKING_CATS
    cats = [c for c in cats if c in BY_SLUG]
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(
            lambda s: vertical_search(s, plz, limit, booking_only=True), cats))
    providers = []
    for cat in results:
        for r in cat.get("records", []):
            providers.append({
                "name": r.get("name"),
                "category": cat["slug"],
                "category_label": cat.get("label"),
                "city": r.get("city"),
                "distance_km": r.get("distance_km"),
                "phone": r.get("phone"),
                "email": r.get("email"),
                "website": r.get("website"),
                "booking": {
                    "provider": r.get("booking_platform"),
                    "url": r.get("booking_url") or r.get("website"),
                    "kind": "deeplink",
                },
            })
    providers.sort(key=lambda p: (p["distance_km"] is None, p["distance_km"]))
    return {"plz": plz, "category": category,
            "count": len(providers), "providers": providers,
            "note": ("Unified booking lookup across the network's bookable providers. "
                     "kind=deeplink: booking completes on the provider's own page/platform. "
                     "Availability/slot APIs are on the roadmap.")}


MCP_TOOLS = [
    {"name": "search_local",
     "description": ("Find the closest providers of ONE category of German local businesses "
                     "around a postal code (plz) or coordinates (lat/lon), distance-sorted. "
                     "1.16M businesses, 81 categories, OpenStreetMap/Overture data, no key. "
                     "Use list_categories first for valid category slugs."),
     "inputSchema": {"type": "object", "properties": {
         "category": {"type": "string", "description": "Category slug, e.g. friseur (hairdresser), zahnarzt (dentist)"},
         "plz": {"type": "string", "pattern": "^[0-9]{5}$", "description": "German postal code"},
         "lat": {"type": "number"}, "lon": {"type": "number"},
         "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
      "required": ["category"]}},
    {"name": "list_categories",
     "description": "All 81 categories of the network with German and English labels. Read-only.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "search_essentials",
     "description": ("Search MANY categories in parallel around a postal code — one call builds a "
                     "relocation starter set (supermarket, doctors, dentist, bank …). Returns the "
                     "closest providers per category."),
     "inputSchema": {"type": "object", "properties": {
         "plz": {"type": "string", "pattern": "^[0-9]{5}$"},
         "categories": {"type": "array", "items": {"type": "string"},
                        "description": "Category slugs; omit for the default 15 essentials"},
         "limit": {"type": "integer", "minimum": 1, "maximum": 5}},
      "required": ["plz"]}},
    {"name": "find_bookable",
     "description": ("Unified booking lookup: online-bookable service providers (hairdresser, massage, "
                     "physio …) around a postal code, normalized across booking platforms "
                     "(google_booking, calendly, own forms) with a deep link each. Booking completes "
                     "on the provider's platform — availability APIs are roadmap."),
     "inputSchema": {"type": "object", "properties": {
         "plz": {"type": "string", "pattern": "^[0-9]{5}$"},
         "category": {"type": "string", "description": "Optional single category slug"},
         "limit": {"type": "integer", "minimum": 1, "maximum": 10}},
      "required": ["plz"]}},
    {"name": "find_jobs",
     "description": ("Real job openings around a postal code via the OFFICIAL German Federal "
                     "Employment Agency (Bundesagentur fuer Arbeit) API — title, employer, salary "
                     "range, official application link."),
     "inputSchema": {"type": "object", "properties": {
         "plz": {"type": "string", "pattern": "^[0-9]{5}$"},
         "what": {"type": "string", "description": "Free-text role query"},
         "limit": {"type": "integer", "minimum": 1, "maximum": 20},
         "radius": {"type": "integer", "minimum": 5, "maximum": 200}},
      "required": ["plz"]}},
    {"name": "get_paperwork_checklist",
     "description": "The ordered official German bureaucracy steps after moving (Anmeldung, tax ID, health insurance, Kindergeld …) with government links only. Read-only, static.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def mcp_call(name, args):
    """Dispatch eines MCP-tools/call auf die vorhandenen Funktionen."""
    args = args or {}
    if name == "search_local":
        return vertical_search(args.get("category", ""), args.get("plz", ""),
                               min(int(args.get("limit", 5)), 20),
                               lat=args.get("lat"), lon=args.get("lon"))
    if name == "list_categories":
        return {"count": len(NETWORK), "essentials": ESSENTIALS,
                "categories": [{k: v[k] for k in ("slug", "label", "label_en", "emoji", "domain")}
                               for v in NETWORK]}
    if name == "search_essentials":
        cats = [c for c in (args.get("categories") or ESSENTIALS) if c in BY_SLUG][:20]
        limit = min(int(args.get("limit", 3)), 5)
        with ThreadPoolExecutor(max_workers=10) as ex:
            results = list(ex.map(lambda s: vertical_search(s, args.get("plz", ""), limit), cats))
        return {"plz": args.get("plz"), "categories": results}
    if name == "find_bookable":
        return booking_search(args.get("plz", ""), args.get("category"),
                              min(int(args.get("limit", 5)), 10))
    if name == "find_jobs":
        data, _status = ba_jobs(args.get("plz", ""), args.get("what", ""),
                                min(int(args.get("limit", 5)), 20),
                                min(int(args.get("radius", 25)), 200))
        return data
    if name == "get_paperwork_checklist":
        return PAPERWORK
    return {"error": f"unknown tool: {name}"}


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

    def _send_mcp(self, body):
        """MCP-JSON-RPC-Antwort; bei Accept: text/event-stream als SSE-Event
        (Streamable-HTTP-Standard), sonst als einfaches JSON."""
        accept = self.headers.get("Accept") or ""
        if "text/event-stream" in accept:
            payload = f"event: message\ndata: {body}\n\n".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("mcp-protocol-version", "2025-03-26")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("mcp-protocol-version", "2025-03-26")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "content-type, mcp-session-id, mcp-protocol-version")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        """Backend-MCP (Streamable HTTP, JSON-RPC): initialize / tools/list / tools/call."""
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/mcp":
            self._send({"error": "not found"}, status=404)
            return
        try:
            n = int(self.headers.get("content-length") or 0)
            req = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception:
            req = {}
        method = req.get("method")
        rid = req.get("id")
        if method == "initialize":
            self._send_mcp(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "movetogermany-local-api", "version": "1.0.0"},
                "instructions": ("One keyless API for 1.16M German local businesses (81 categories), "
                                 "official job data and a unified booking lookup. Start with "
                                 "list_categories or search_essentials."),
            }}, ensure_ascii=False))
            return
        if method == "tools/list":
            self._send_mcp(json.dumps({"jsonrpc": "2.0", "id": rid,
                                       "result": {"tools": MCP_TOOLS}}, ensure_ascii=False))
            return
        if method == "tools/call":
            params = req.get("params") or {}
            result = mcp_call(params.get("name", ""), params.get("arguments"))
            self._send_mcp(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                "isError": bool(isinstance(result, dict) and result.get("error")),
            }}, ensure_ascii=False))
            return
        # notifications/initialized u.ä.
        self.send_response(202)
        self.send_header("Content-Length", "0")
        self.end_headers()

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

        if path == "/guide":
            if wants_markdown(self.headers.get("Accept", "")):
                self._send(GUIDE_MD, "text/markdown; charset=utf-8")
            else:
                self._send(md_page_html(GUIDE_MD, "Moving to Germany: the complete arrival checklist",
                    "Week-by-week relocation checklist for Germany: Anmeldung, tax ID, health insurance, bank account, Kindergeld — official links only.",
                    "guide"), "text/html; charset=utf-8")
            return

        if path == "/developers":
            if wants_markdown(self.headers.get("Accept", "")):
                self._send(DEV_MD, "text/markdown; charset=utf-8")
            else:
                self._send(md_page_html(DEV_MD, "One keyless API for 1.16M German local businesses",
                    "Unified MCP + REST interface over 81 German local-business directories: search, essentials, booking lookup, official job data. No API key.",
                    "developers"), "text/html; charset=utf-8")
            return

        if path == "/developers.md":
            self._send(DEV_MD, "text/markdown; charset=utf-8")
            return

        if path == "/guide.md":
            self._send(GUIDE_MD, "text/markdown; charset=utf-8")
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
            urls = ["/", "/guide", "/developers", "/llms.txt", "/index.md", "/auth.md", "/openapi.json"]
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
                "description": "One keyless API for 1.16M German local businesses: MCP + REST over 81 "
                               "distance-sorted directories, unified booking lookup, official job data. "
                               "Read-only, no authentication. WebMCP in-page tools on the website itself.",
                "version": "1.0.0",
                "websiteUrl": f"https://{DOMAIN}/developers",
                "remotes": [{"type": "streamable-http", "url": f"https://{DOMAIN}/mcp"}],
                # Icons sind (noch) nicht Teil des Registry-Schemas — als
                # Web-Manifest-artige Zusatzinfo fuer Clients, die sie lesen.
                "icons": [
                    {"src": f"https://{DOMAIN}/icon-192.png", "sizes": "192x192", "type": "image/png"},
                    {"src": f"https://{DOMAIN}/icon-512.png", "sizes": "512x512", "type": "image/png"},
                ],
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
                    "/api/booking": {"get": {"operationId": "searchBookable",
                        "summary": "Unified booking lookup: online-bookable providers across categories/platforms",
                        "parameters": [
                            {"name": "plz", "in": "query", "required": True, "schema": {"type": "string", "pattern": "^[0-9]{5}$"}},
                            {"name": "category", "in": "query", "schema": {"type": "string"}},
                            {"name": "limit", "in": "query", "schema": {"type": "integer", "maximum": 10}}],
                        "responses": {"200": {"description": "Bookable providers with normalized platform + deep link"},
                                      "400": {"description": "Missing parameters"}}}},
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
                        "categories": [{k: v[k] for k in ("slug", "label", "label_en", "plural", "emoji", "domain")}
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

        if path == "/favicon.svg":
            svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                   '<circle cx="50" cy="62" r="30" fill="#f8c99c"/>'
                   '<circle cx="39" cy="60" r="3.5" fill="#2b2b2b"/>'
                   '<circle cx="61" cy="60" r="3.5" fill="#2b2b2b"/>'
                   '<path d="M35 74 q8 -7 15 0 q8 -7 15 0 q-6 9 -15 5 q-9 4 -15 -5z" fill="#6b4a2f"/>'
                   '<ellipse cx="50" cy="38" rx="34" ry="8" fill="#3f6b3a"/>'
                   '<path d="M25 38 q4 -24 25 -24 q21 0 25 24 z" fill="#4d7f46"/>'
                   '<rect x="25" y="32" width="50" height="7" rx="3.5" fill="#8a3033"/>'
                   '<path d="M70 15 q13 -11 17 -3 q-8 1 -11 7 z" fill="#e8e3d4"/></svg>')
            self._send(svg, "image/svg+xml")
            return

        if path == "/og-image.png":
            fp = os.path.join(HERE, "og-image.png")
            if os.path.exists(fp):
                with open(fp, "rb") as f:
                    self._send(f.read(), "image/png")
            else:
                self._send({"error": "not found"}, status=404)
            return

        if path in ("/icon-512.png", "/icon-192.png", "/icon-180.png", "/icon-32.png",
                    "/apple-touch-icon.png", "/favicon.ico"):
            name = {"/apple-touch-icon.png": "icon-180.png",
                    "/favicon.ico": "icon-32.png"}.get(path, path.lstrip("/"))
            fp = os.path.join(HERE, name)
            if os.path.exists(fp):
                with open(fp, "rb") as f:
                    self._send(f.read(), "image/png")
            else:
                self._send({"error": "not found"}, status=404)
            return

        if path == "/site.webmanifest":
            self._send({
                "name": "move to germany, lol",
                "short_name": "movetogermany",
                "description": "The arrival planner for you + your AI agent.",
                "start_url": "/",
                "display": "browser",
                "background_color": "#f6f7f9",
                "theme_color": "#0e7490",
                "icons": [
                    {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                    {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
                    {"src": "/favicon.svg", "sizes": "any", "type": "image/svg+xml"},
                ],
            }, "application/manifest+json; charset=utf-8")
            return

        if path == "/api/jobs":
            plz = (q.get("plz") or [""])[0]
            what = (q.get("what") or [""])[0]
            limit = min(int((q.get("limit") or ["5"])[0]), 20)
            radius = min(int((q.get("radius") or ["25"])[0]), 200)
            if not plz:
                self._send({"error": "plz ist Pflicht"}, status=400)
                return
            data, status = ba_jobs(plz, what, limit, radius)
            self._send(data, status=status)
            return

        if path == "/api/booking":
            plz = (q.get("plz") or [""])[0]
            cat = (q.get("category") or [""])[0]
            limit = min(int((q.get("limit") or ["5"])[0]), 10)
            if not plz:
                self._send({"error": "plz ist Pflicht"}, status=400)
                return
            self._send(booking_search(plz, cat or None, limit))
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
                f"- [Arrival guide](https://{DOMAIN}/guide): week-by-week relocation checklist for Germany, official links only\n"
                f"- [Developer API](https://{DOMAIN}/developers): one keyless MCP+REST API for 1.16M German local businesses\n"
                f"- [Markdown version](https://{DOMAIN}/index.md): this page as plain Markdown\n"
                f"- [OpenAPI schema](https://{DOMAIN}/openapi.json): full HTTP API contract\n"
                f"- [Auth notes](https://{DOMAIN}/auth.md): keyless, read-only, rate-limit headers\n\n"
                "## API\n"
                f"- [All categories](https://{DOMAIN}/api/categories): the 80+ categories of the network\n"
                f"- [Search one category](https://{DOMAIN}/api/search?cat=supermarkt&plz=10115&limit=5): distance-sorted providers\n"
                f"- [Essentials in parallel](https://{DOMAIN}/api/essentials?plz=10115): many categories at once\n"
                f"- [Job search](https://{DOMAIN}/api/jobs?plz=10115&what=developer): official Bundesagentur fuer Arbeit openings\n"
                f"- [Paperwork starter pack](https://{DOMAIN}/api/paperwork): ordered official bureaucracy steps\n"
                f"- [Unified booking lookup](https://{DOMAIN}/api/booking?plz=10115): bookable providers across platforms, deep links\n"
                f"- [Backend MCP](https://{DOMAIN}/mcp): streamable-HTTP MCP server, 6 tools, see /.well-known/mcp.json\n\n"
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
