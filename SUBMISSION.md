# Devpost Submission — move to germany, lol

*(Copy-paste-Vorlage für das Devpost-Formular. Video-Skript ganz unten.)*

## Project name
move to germany, lol

## Elevator pitch (tagline)
The collaborative arrival planner for Germany: your AI agent searches 80+
business categories in parallel, you curate the shared shortlist — because
the paperwork is enough drama.

## Live URL
https://movetogermany.lol

## Repository
https://github.com/shufflethis/neu-hier (MIT)

---

## Why this use case is a strong fit for WebMCP

Relocating to a new German city means rebuilding your entire everyday
infrastructure — supermarket, GP, dentist, hairdresser, bank, pharmacy-level
essentials — in a place you don't know, often in a language you don't speak
yet. Neither side solves this well alone:

- A **human alone** needs thirty browser tabs and an afternoon.
- An **agent alone** (via scraping or a backend API) makes decisions about
  your daily life without you — and loses you the moment taste, gut feeling
  or a handwritten note matters.

WebMCP is exactly the missing piece: the page becomes a **shared workspace**.
The agent gets typed, honest tools instead of guessing at our DOM; the human
sees every agent action render live on the same page and stays in control.

## How it creates a better user experience

One sentence to your agent — "Set me up at 10115" — and
`generate_starter_plan` searches 12 essential categories **in parallel**
across our directory network and drops the closest provider per category
into the plan. What used to be an afternoon is now a starting point you
refine together:

- Agent entries render **purple**, human entries **blue** — provenance is
  visible in the UI itself.
- The human vetoes, swaps and **writes notes** directly into entries.
- The agent reads those notes back (`get_shortlist` — marked
  `untrustedContentHint`, because notes are human-authored content), reacts
  to them, and exports the finished plan as Markdown (`export_plan`).

## What people and agents can do together that was hard before

The plan is co-authored state, not a chat transcript. The agent can operate
on the human's manual edits (a note saying "too far, find closer" is an
instruction it can act on), and the human can override any agent decision
with one click — no copy-pasting between a chatbot and the real page. That
loop — agent acts on page, human edits page, agent reads edits — simply does
not exist without WebMCP.

## How we implemented WebMCP

- **17 imperative tools** via `document.modelContext.registerTool`:
  `list_categories`, `set_home_plz`, `find_nearby`, `generate_starter_plan`,
  `add_to_shortlist`, `remove_from_shortlist`, `get_shortlist`, `set_note`,
  `draft_outreach`, `find_jobs`, `get_paperwork_checklist`, plus two
  **conditional tools**
  (`export_plan`, `compare_candidates`) that register and unregister with
  page state via `AbortController` — the agent's tool list always mirrors
  what is actually possible right now, exactly the lifecycle the spec
  intends.
  `find_jobs` searches real openings via the **official Federal Employment
  Agency (Bundesagentur fuer Arbeit) API** — home, essentials AND a job in
  one shared session; `get_paperwork_checklist` hands the agent the ordered
  official bureaucracy steps (Anmeldung, tax ID, Kindergeld, Buergergeld …)
  with government links only. Every tool has a typed JSON schema with per-property
  descriptions and explicit `required` lists; read paths carry
  `readOnlyHint`, and `get_shortlist` carries `untrustedContentHint`
  because it returns human-written notes.
- **1 declarative tool**: the postal-code form is annotated with
  `toolname` / `tooldescription` / `toolautosubmit` /
  `toolparamdescription` per the current declarative-API explainer.
- Tools and click handlers call the **same functions** — the page is one
  state machine with two front doors (mouse and model).
- A live **activity feed** on the page shows who did what (🤖 agent /
  🧑 human), so the collaboration is visible, auditable and demo-able.
- **Appointments with a human in the loop**: `propose_appointment` lets the
  agent lay concrete slots onto a plan entry; the human confirms one with a
  single click, which opens a pre-written provider email and saves a
  tentative .ics. The write path always pauses for a person — the WebMCP
  security model, implemented as UX.
- We also **contribute back**: tool icons don't exist in the spec, so the
  repo contains an issue-ready proposal (mirroring MCP's `Icon` type) and
  every tool already ships the proposed `icons` member.
- A shared **arrival persona** (`get_profile`/`set_profile`) — and this is
  WebMCP's quiet superpower made visible: **the visitor's agent already
  knows its user**. It fills household, pet, language needs, mobility and
  profession from its own memory, confirms them on the page, and asks only
  for the gaps. The site never collects anything; the user's context stays
  in their agent, which shares exactly what is relevant here. A dog adds
  the vet to the plan, kids add tutoring, "English only" reshapes the
  outreach drafts, the profession prefills the job search —
  privacy-preserving personalization as shared state.
- **Share link**: the whole co-authored plan serializes into a URL — send it
  to your partner, and their agent continues where yours left off.
- Three **tap-to-copy example prompts** on the page get first-time visitors
  (and judges) from zero to a working agent conversation in seconds.
- Feature-detected (`document.modelContext`, `navigator.modelContext` as
  deprecated fallback) — the page is a normal website in any browser.

## Three doors for agents, one state machine

WebMCP in-page tools for the visitor's own agent, a **backend MCP server**
(`https://movetogermany.lol/mcp`, streamable HTTP, six tools incl. a
unified booking lookup across platforms) for agent platforms, and plain
REST (`/developers`) — all calling the same functions over the same data.

## The data layer (our unfair advantage)

The app sits on the "in meiner Nähe" network we operate: **80+ live,
agent-readable German business directories** (OpenStreetMap + Overture Maps
data, distance-sorted per postal code, each with its own JSON API, MCP
endpoint and llms.txt — independently scored 97/100 on webmcp-tool.com's
Agent Readiness Check). `server.py` (stdlib Python, zero dependencies)
aggregates them in parallel; judges can clone the repo and run it anywhere —
it falls back to the public APIs automatically.

The app itself is agent-readable too: markdown content negotiation,
JSON-LD, llms.txt, OpenAPI, `/.well-known/mcp.json`, an AI-crawler-welcoming
robots.txt.

---

# Video-Skript (<3 Min, Screenrecording + Stimme)

**0:00–0:20 — Hook.** Browser zeigt movetogermany.lol (EN). Voice: "Moving
to Germany means rebuilding your whole everyday life — supermarket, doctors,
dentist — in a city you don't know. This is 'move to germany, lol': a page
built for you AND your AI agent."

**0:20–0:50 — Agent-Magie.** ChatGPT-In-App-Browser (oder Chrome mit
WebMCP-Flag) öffnen, Agent fragen: *"I'm moving to Berlin, postal code
10115. Set me up with the essentials."* Zeigen, wie der Agent
`set_home_plz` + `generate_starter_plan` aufruft und die Seite sich LIVE
füllt: 12 Kategorien, Karte zoomt, violette Einträge erscheinen im Plan.
Voice: "One sentence. The agent calls our WebMCP tools and searches twelve
categories in parallel across 80 live German directories."

**0:50–1:30 — Kollaboration (der Kernmoment).** Mit der Maus: einen
Agent-Vorschlag löschen, bei einer Kategorie einen anderen Anbieter per
"+ save" wählen (wird blau), in einen Eintrag eine Notiz tippen: *"call
them — do they speak English?"*. Dann den Agenten fragen: *"Check my plan —
anything I should know?"* → Agent ruft `get_shortlist` auf, LIEST die
Notiz und reagiert darauf (z.B. Telefonnummer nennen / Alternativen
suchen). Voice: "My edits and notes are part of the shared state. The agent
reads them back. Purple is the agent's work, blue is mine — the plan
belongs to both of us."

**1:30–2:10 — Tiefe zeigen.** Agent fragen: *"Now find me python developer
jobs nearby"* → `find_jobs` zeigt echte Stellen (offizielle Bundesagentur-
für-Arbeit-API!) mit Gehaltsspannen und Bewerbungslinks auf der Seite.
Dann: *"What paperwork do I need?"* → `get_paperwork_checklist`.
Dann `export_plan`: Agent liefert den fertigen Markdown-Plan im Chat.
Voice: "Nine imperative tools with typed schemas and honest annotations,
plus a declarative form tool — and every tool shares its code with the
buttons you just saw me click."

**2:10–2:50 — Unterbau + Abschluss.** Kurz /llms.txt oder README zeigen,
eine Netzwerk-Domain (z.B. friseur-in-meiner-naehe.de) einblenden. Voice:
"It runs on our own network of 80+ agent-readable German directories —
real nationwide OpenStreetMap data, every directory scoring 97 out of 100
on the community agent-readiness check. Open source, MIT, zero
dependencies. move to germany — lol. Because the paperwork is enough
drama." Ende auf der Startseite mit sichtbarem Plan.

**Checkliste vor dem Dreh:** Chrome-Flag `chrome://flags/#enable-webmcp-testing`
oder ChatGPT-Desktop-Browser; localStorage vorher leeren (frische Demo);
Fenster auf 1080p; Englisch als Seitensprache (Default).
