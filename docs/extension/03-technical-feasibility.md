# 03 — Technical feasibility

The purpose of this doc is to de-risk the "can we even build it this way" questions *before*
committing. Each section ends with a verdict and, where relevant, a spike to run first.

## 1. Manifest V3 + side panel
- Chrome now only accepts **Manifest V3** extensions. Background logic runs as an ephemeral
  **service worker**, not a persistent page — so we keep no long-lived in-memory state there;
  state lives in `chrome.storage` and the side panel.
- The **Side Panel API** (`chrome.sidePanel`, Chrome 114+) gives us a persistent right-hand panel
  that survives tab navigation — ideal for "stay on the posting, optimize alongside it." This is
  the correct surface (vs. a popup, which closes on click-away).
- **Verdict:** feasible, standard. Side panel is the right primitive.

## 2. Reading the JD from the page
- A **content script** injected into ATS domains reads the **rendered DOM** in the user's own
  authenticated session. This is the key unlock: no server ever fetches the JD, so LinkedIn/Indeed
  bot-blocking and Workday auth walls are irrelevant — we see what the user sees.
- Extraction strategy: **per-site CSS selectors** for named ATS portals (title, company, JD body),
  with a **generic "largest text block" fallback** for unknown sites, plus `<title>`/OG-tag parsing
  for company/role.
- **Risk:** DOM drift — ATS vendors change markup and selectors break. **Mitigation:** ship the
  selector map as a **remote, versioned config** fetched from the repo, so we fix drift by editing a
  JSON file, *not* by shipping a new extension (no store review, instant fix). See architecture doc.
- **Verdict:** feasible; DOM drift is the main ongoing maintenance cost, and the remote-config
  design contains it. **Spike:** capture real DOM samples from Greenhouse, Lever, Workday, LinkedIn,
  Indeed and confirm selectors + fallback quality before locking the config schema.

## 3. The localhost bridge (extension → desktop engine)
This is the highest-uncertainty piece and deserves the most scrutiny.
- The side panel (origin `chrome-extension://<id>`) calls the desktop server at
  `http://127.0.0.1:47615`. Two browser mechanisms gate this:
  1. **Host permissions / CORS.** The extension must declare `http://127.0.0.1/*` in
     `host_permissions`, **and** the local FastAPI server must return
     `Access-Control-Allow-Origin: chrome-extension://<id>` (plus allowed methods/headers) or the
     browser hides the response. → This is the planned engine-side change.
  2. **Private Network Access (PNA).** Chrome treats requests from a public/secure context to a
     *local* address as sensitive and may send a **CORS preflight** (`OPTIONS`) carrying
     `Access-Control-Request-Private-Network: true`, expecting the server to reply
     `Access-Control-Allow-Private-Network: true`. The engine's OPTIONS handler must answer this.
- **Engine change required (small, well-scoped):** add CORS middleware to `desktop.py`'s FastAPI
  app that (a) allows the extension origin, (b) handles the `OPTIONS` preflight, (c) sets the
  PNA allow header, and (d) exposes `GET /api/ping` for the "engine live" check.
- **Unknown to nail in the spike:** the extension ID isn't final until packed/published. Handle by
  allowing the dev (unpacked) ID during development and reading the published ID at release; the
  engine can allow a small known set or match the `chrome-extension://` scheme for `/api/ping`.
- **Verdict:** feasible with a bounded server change. **Spike first:** stand up the CORS+PNA change
  locally, load an unpacked extension, and confirm a real `fetch` to `/api/ping` and `/api/qualify`
  succeeds end-to-end before building UI.

## 4. Detecting "engine not running" (State C)
- On panel open, `fetch('http://127.0.0.1:47615/api/ping')` with a short timeout.
  - 200 → engine live (States A/B available).
  - network error / timeout → State C (launch prompt + download funnel).
- **"Launch RESOPT" button:** a browser extension can't directly spawn a native app for free.
  Options, cheapest first: (a) a `resopt://` **custom URL scheme** registered by the desktop app on
  install (click → OS launches the app); (b) **native messaging** host (more setup, more power);
  (c) fallback link to the download page. v1: pursue the custom-scheme approach, degrade to the
  download link. **Spike:** confirm the desktop app can register `resopt://` on macOS + Windows.

## 5. Chrome Web Store review
- **Single purpose** must be crisp: "tailor your résumé to the job posting you're viewing."
- **Permission justification** required for each permission (see security doc). Keep the list
  minimal — broad `host_permissions` invite scrutiny; prefer an explicit ATS domain list +
  `activeTab` over `<all_urls>`.
- **Privacy:** a privacy policy is required. Ours is a strength — "data is processed locally by the
  user's own RESOPT app; the extension transmits nothing to us." No remote code (MV3 bans it) — the
  remote *selector config* is data (JSON), not executable code, which is compliant.
- **Review latency:** first review can take days; plan the timeline around it. The one-time $5
  developer registration is the user's call at submission time.
- **Verdict:** feasible; the local-first design is review-friendly. Minimize permissions.

## Feasibility summary
| Area | Verdict | Biggest risk | Mitigation |
|---|---|---|---|
| MV3 + side panel | Green | — | Standard APIs |
| JD capture | Green | DOM drift | Remote selector config |
| localhost bridge | Yellow → Green after spike | CORS + PNA on localhost | Scoped engine CORS/PNA change + `/api/ping` |
| Launch app (State C) | Yellow | can't spawn native app directly | `resopt://` scheme, degrade to download link |
| Store review | Green | permission scrutiny | Minimal perms, strong privacy story |

**Do the three spikes (JD selectors, localhost bridge, `resopt://` launch) before UI work.**
