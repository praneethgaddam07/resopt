# 04 — Architecture

## Trust zones (the whole point)
Three zones, one hard boundary:

1. **The job page** — runs in the user's authenticated session (LinkedIn, Greenhouse, Workday…).
2. **The extension** — runs inside Chrome: background worker, content script, side panel.
3. **The user's Mac** — the RESOPT desktop engine on `127.0.0.1:47615`.

**Trust boundary:** the extension only ever talks to zone 1 (the current page) and zone 3
(localhost). It never contacts a RESOPT server. There is no RESOPT server in this path. That is
what makes "nothing leaves your machine" true.

## Components

### Background service worker (`background.js`)
- Listens to tab updates; runs `detect.js` (hostname → ATS) to know if the current tab is a
  supported posting; sets the toolbar badge accordingly.
- Opens the side panel on action click; brokers messages between content script and panel.
- Ephemeral (MV3) — holds no durable state; anything worth keeping goes to `chrome.storage`.

### Content script (`content.js` + `detect.js`)
- Injected on ATS domains + `activeTab`. Reads the rendered DOM.
- Uses the **selector config** for the detected ATS to extract `{ title, company, location,
  jdText }`; falls back to largest-text-block + `<title>`/OG tags on unknown sites.
- Sends the captured JD to the side panel via message passing. Reads only; never writes the page.

### Side panel (`sidepanel.html` + `sidepanel.js`)
- The UI (States A/B/C). Holds the saved résumés (in `chrome.storage`) and the current job.
- On open: pings the engine → decides State C vs. A. In State A: shows captured JD + résumé picker.
- On "Optimize": POSTs JD + chosen résumé to the local engine; renders score/gaps/downloads (State B).
- The user's AI key (if a generative step is offered) is **session-only**, never persisted.

### Selector config (remote, versioned)
- A JSON map `{ atsId: { titleSel, companySel, jdSel, … } }` fetched from the repo at runtime and
  cached. Lets us fix DOM drift **without a store release**. It is *data*, not code — MV3-compliant.

### The engine (unchanged except CORS + `/api/ping`)
- The existing desktop FastAPI app. Deterministic: scoring, ATS formatting, validators/guardrails,
  taxonomy, DOCX/PDF rendering. No LLM cost on our side. Endpoints already exist; v1 adds CORS/PNA
  headers and `GET /api/ping`.

## Data flow (numbered, matches the architecture diagram)
1. **detect** — background worker reads the tab URL, resolves the ATS, badges the icon.
2. **read** — content script extracts `{title, company, location, jdText}` from the rendered DOM
   (using the selector config; fallback if unknown).
3. **JD + résumé** — captured job + the user's chosen saved résumé are assembled in the side panel.
4. **POST** — side panel calls the local engine:
   - `POST /api/qualify` → fit verdict + `fixable_by_optimization` gaps.
   - `POST /api/jobs` (async) → run the optimization workflow (carrying the fixable gaps).
   - `POST /api/render` → DOCX/PDF bytes for download.
5. **score + files** — engine returns match score, what was closed, honest gaps, and files; the
   side panel renders State B. Nothing is uploaded anywhere.

## Key design decisions
- **Thin client, fat engine.** All optimization logic stays in the desktop engine. The extension is
  a capture + display shell. Consequence: we iterate on quality by shipping the *app*, not the
  extension → no store-review bottleneck on the important stuff. (Goal G5.)
- **Config-driven scraping.** Selectors are data fetched at runtime, not baked into a release.
- **Local-only transport.** Only `chrome-extension://` ↔ page and `chrome-extension://` ↔ localhost.
  No third origin exists, by design.
- **Fail to a funnel.** Every failure mode (engine down, unknown site, capture miss) degrades to a
  useful next step (launch/download, manual paste, generic capture) rather than a dead end.

## File layout (planned)
```
extension/
  manifest.json         MV3: sidePanel, activeTab, storage, scripting + host_permissions
  background.js         ATS detection, badge, panel + messaging
  content.js            DOM read + JD extraction
  detect.js             hostname → ATS (shared by background + content)
  selectors.json        default selector config (overridden by remote fetch)
  sidepanel.html
  sidepanel.js          the 3 states, engine calls, storage
  sidepanel.css         Paper Studio palette
  icons/
```
Engine side: CORS/PNA middleware + `GET /api/ping` added to `desktop.py`.
