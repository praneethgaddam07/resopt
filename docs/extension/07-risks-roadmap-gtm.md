# 07 — Risks, roadmap & go-to-market

## Risk register

| # | Risk | Likelihood | Impact | Mitigation / owner action |
|---|---|---|---|---|
| R1 | localhost bridge blocked by CORS/PNA quirks | Med | High | Spike the engine CORS+PNA change first; prove `fetch` before any UI |
| R2 | ATS DOM drift breaks JD capture | High (over time) | Med | Remote selector config — fix without a release; generic fallback |
| R3 | Users don't keep the desktop engine running | Med | Med | State C funnel + `resopt://` one-click launch; v3 hosted lite as backstop |
| R4 | "Launch app" from a browser is limited | Med | Med | `resopt://` scheme, degrade to download link; native messaging later |
| R5 | Store review delays / permission pushback | Med | Med | Minimal permissions, crisp single purpose, strong privacy policy |
| R6 | LinkedIn/Indeed markup hostile or ToS-sensitive | Med | Med | Reading the user's own page (not scraping); keep capture read-only; monitor |
| R7 | Extension ID unknown until publish (CORS allowlist) | Low | Low | Allow dev ID in dev; match `chrome-extension://` scheme for `/api/ping` |
| R8 | Scope creep into tracker/autofill in v1 | Med | Med | Hard non-goals (see brief); autofill is v2 |

## Roadmap

### v1 — optimize in place (~2–3 sessions)
Build order (each step is verifiable before the next):
1. **Engine change** — CORS + PNA middleware + `GET /api/ping` in `desktop.py`. Verify with an
   unpacked extension `fetch`.
2. **MV3 scaffold** — `manifest.json`, `background.js` (detect + badge + panel), `detect.js`.
3. **Capture** — `content.js` + `selectors.json`; validate on real Greenhouse/Lever/Workday/
   LinkedIn/Indeed pages.
4. **Panel** — `sidepanel.html/js/css`, the three states, résumé storage, engine calls.
5. **State C** — `resopt://` launch + download funnel.
6. **Remote config** — load selectors from the repo with a bundled fallback.
7. **Tests + live walkthrough** with screenshots before shipping.
8. **(User's call)** Web Store submission — $5 registration, review wait.

### v2 — retention hooks
- **Job tracker** — saved postings + statuses (kanban), still local-first.
- **Form autofill** — pre-fill application fields from the profile (the Simplify/Teal table-stakes
  feature, but privacy-first).

### v3 — reach beyond the desktop app
- **Optional hosted "lite" engine** for users without the desktop app — local-first by default,
  hosted only as an explicit opt-in, so the privacy default holds.

## Go-to-market
- **Funnel loop:** extension State C markets the desktop app; the desktop app's docs market the
  extension. Each install grows the other.
- **Listing angle:** lead with the differentiator — "runs on your machine, reads the job you're on,
  won't lie for you." The privacy policy is a selling point.
- **Distribution:** Chrome Web Store first (largest surface). Edge accepts Chromium extensions with
  minimal changes as a fast follow.
- **Proof content:** a 30-second screen recording of the in-page loop (posting → optimize →
  download) is the single most persuasive asset; capture it during the v1 walkthrough.

## Decisions (locked 2026-07-03)
1. **State C launch** — ship v1 with a download / "open RESOPT" link (no auto-launch).
   Add the `resopt://` one-click launch in v1.1 (it needs a desktop-app change on mac + Windows
   and a re-release, and State C needs the download link regardless).
2. **CORS allowlist** — the engine reflects **any `chrome-extension://` origin** (works for
   unpacked dev + the published build without knowing the ID; only extensions, never websites,
   can reach `127.0.0.1`).
3. **ATS coverage at launch** — the 7 the engine already supports (Greenhouse, Lever, Workday,
   iCIMS, SmartRecruiters, Ashby, BambooHR) **+ LinkedIn + Indeed**, with a generic
   "largest text block" fallback on every other site.
4. **Selector config** — bundle a default `selectors.json` in the extension **and** fetch an
   override from the **public `resopt` repo** at runtime (fall back to the bundled copy on any
   fetch failure). Fixes DOM drift by editing one file — no store re-review.
5. **Scope** — **optimize-only** for v1. No job tracker, no form autofill (those are v2).
