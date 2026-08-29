# neu hier — Ankommens-Planer für Mensch + Agent 📦➡️🏙️

**WebMCP-Challenge-Einreichung.** Neue Adresse? Du und dein KI-Agent baut
**gemeinsam** die Grundversorgung auf: Supermarkt, Zahnarzt, Friseur, Bank &
80 weitere Branchen — echte deutschlandweite Daten (OpenStreetMap / Overture
Maps), nach Entfernung sortiert, auf einer gemeinsam editierbaren Karte + Plan.

## Warum WebMCP hier wirklich trägt

Ein Umzug ist genau die Aufgabe, die weder Mensch noch Agent allein gut löst:

- Der **Agent** kann in Sekunden 12+ Branchen parallel durchsuchen und einen
  Startplan bauen (`generate_starter_plan`) — für einen Menschen 30 Tabs.
- Der **Mensch** kennt seine Präferenzen: er wirft Vorschläge raus, merkt
  eigene Favoriten, schreibt Notizen an die Einträge.
- Der Agent **liest den gemeinsamen Zustand zurück** (`get_shortlist` inkl.
  handgeschriebener Notizen, markiert wer was angelegt hat) und arbeitet
  darauf weiter: tauschen, ergänzen, als Markdown exportieren.

Seiten-Zustand = geteilter Arbeitsbereich. Violette Einträge kommen vom
Agenten, blaue vom Menschen — beide bearbeiten denselben Plan.

## WebMCP-Tools (document.modelContext)

| Tool | Art | Zweck |
|---|---|---|
| `list_categories` | read-only | 80+ Branchen-Slugs entdecken |
| `set_home_plz` | write | Neue Wohn-PLZ setzen |
| `find_nearby` | write (UI) | Eine Branche suchen + anzeigen |
| `generate_starter_plan` | write | 12 Branchen parallel → nächstgelegener Anbieter je Branche in den Plan |
| `add_to_shortlist` / `remove_from_shortlist` | write | Plan gemeinsam kuratieren |
| `get_shortlist` | read-only (`untrustedContentHint`) | Plan inkl. Nutzer-Notizen lesen |
| `set_note` | write | Notiz an Eintrag schreiben |
| `export_plan` | read-only | Fertiges Markdown |

Dazu ein **deklaratives WebMCP-Formular** (`toolname`/`tooldescription`/
`toolautosubmit`/`toolparamdescription`) am PLZ-Feld.

## Datenschicht

Das [„in meiner Nähe“-Netzwerk](https://friseur-in-meiner-naehe.de/llms.txt):
80+ live agentenlesbare Branchenverzeichnisse (je Domain eigene JSON-API,
MCP-Server, llms.txt; Agent-Readiness-Score 97/100 auf webmcp-tool.com).
`network.json` ist der Katalog-Snapshot. Der Aggregator (`server.py`, reine
Python-Stdlib) fragt die Branchen parallel ab — öffentlich über HTTPS (CORS
offen, keine Keys) oder auf dem Netzwerk-VPS direkt über localhost.

## Starten

```bash
python3 server.py           # http://127.0.0.1:8871 — nutzt die öffentlichen APIs
NEUHIER_LOCAL=1 python3 server.py   # nur auf dem Netzwerk-VPS
```

Keine Dependencies, kein Build. WebMCP testen: ChatGPT-In-App-Browser oder
Chrome mit `chrome://flags/#enable-webmcp-testing`.

## Lizenz

MIT. Daten: OpenStreetMap (ODbL 1.0, © OpenStreetMap contributors) & Overture
Maps Foundation (CDLA-Permissive-2.0).
