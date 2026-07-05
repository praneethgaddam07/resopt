# RESOPT browser extension (v1 · Manifest V3)

A thin Chrome extension: on a job posting it detects the ATS, captures the description,
and tailors your résumé in a side panel — with the engine being your **local** RESOPT
desktop app (`127.0.0.1:47615`). There is no RESOPT server in the path; nothing leaves
your machine. See the full spec in [`../docs/extension/`](../docs/extension/README.md).

## Load it (unpacked, for development)
1. Run the engine locally — the desktop app, or from source:
   `FORCE_MOCK=1 python -m uvicorn app.main:app --host 127.0.0.1 --port 47615`
2. Chrome → `chrome://extensions` → enable **Developer mode** → **Load unpacked** → select this `extension/` folder.
3. Open a posting (Greenhouse, Lever, Workday, iCIMS, SmartRecruiters, Ashby, BambooHR, LinkedIn `/jobs/`, Indeed). The toolbar icon shows a **JD** badge → click it to open the side panel.

## Files
| File | Role |
|------|------|
| `manifest.json` | MV3 config: permissions, ATS host matches, side panel, content scripts |
| `detect.js` | hostname → ATS (shared by the worker + content script) |
| `selectors.json` | per-ATS JD selectors — bundled default; overridden at runtime from the public `resopt` repo |
| `background.js` | badges the icon on job pages; opens the side panel on click |
| `content.js` | reads the rendered DOM → `{ title, company, jdText }` (read-only) |
| `sidepanel.*` | the 3-state UI + local-engine calls · **built in layer 2** |

## Requires the engine change
The desktop server must expose `GET /api/ping` and allow `chrome-extension://` origins
(CORS + Private Network Access) — added in [`../app/main.py`](../app/main.py). Ship a desktop
build that includes it before the extension can reach the engine.

## Decisions (locked)
See [`../docs/extension/07-risks-roadmap-gtm.md`](../docs/extension/07-risks-roadmap-gtm.md#decisions-locked-2026-07-03).
State C uses a download/open link for v1 (`resopt://` one-click comes in v1.1); optimize-only scope.
