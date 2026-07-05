# 05 — Functional spec

## The three states (approved mockups)

### State A — job detected
Shown when the engine is live and the current tab is a recognized posting.
- **Header:** RESOPT wordmark + engine status ("engine live", green dot).
- **Detected block:** ATS chip (e.g. "Greenhouse"), job title, company · location.
- **Captured from this page:** key requirements/keywords pulled from the JD (chips).
- **Use résumé:** picker over the user's saved résumés (role-labeled, from `chrome.storage`).
- **CTA:** "Optimize for this job" (single primary action).
- **Footer:** "Runs on your Mac · nothing is uploaded."
- **Edge:** unknown site but text present → offer generic capture + "confirm this is the JD".
- **Edge:** JD capture empty → let the user paste/select JD text manually (never dead-end).

### State B — optimization result
- **ATS match:** score /100 + delta from the pre-optimization baseline + progress bar.
- **Closed from your fit check:** what optimization legitimately improved (rephrased real content,
  confirmed tools). Ties to the existing fit→optimize gap loop (`fixable_by_optimization`).
- **Left out — no basis to claim:** honest gaps the engine refused to fabricate (the safe-ingestion
  / truthful stance made visible). This is a feature, not an apology.
- **Downloads:** DOCX + PDF (via `/api/render`), plus re-optimize.
- **Edge:** engine error mid-run → inline error + retry, panel state preserved.

### State C — desktop engine not running
- Status shows "engine offline".
- Message + "Launch RESOPT" (custom `resopt://` scheme; degrades to download link).
- "Don't have it yet? Download →" — doubles as the install funnel.
- On successful launch/ping, auto-advance to State A.

## Core flows
- **Open panel:** ping engine → live? detect ATS + capture JD → State A · not live → State C.
- **Optimize:** State A → `POST /api/qualify` (fit + fixable gaps) → `POST /api/jobs` with
  `fix_gaps_json` → poll job → on done `POST /api/render` for files → State B.
- **Tab change:** side panel persists; re-detect + re-capture for the new tab.
- **Engine drops mid-session:** next call fails → surface State C with retry.

## Local engine API contract (consumed by the panel)
All against `http://127.0.0.1:47615`, all local, none upload anything.

| Method | Endpoint | Purpose | Status |
|---|---|---|---|
| GET | `/api/ping` | liveness for State C vs A | **new (v1)** |
| GET | `/api/health` | health check | exists |
| GET | `/api/ats` | list supported portals | exists |
| POST | `/api/qualify` | fit verdict + `fixable_by_optimization` gaps | exists |
| POST | `/api/jobs` | run optimization (async; carries `fix_gaps_json`) | exists |
| GET | `/api/jobs/{id}` | poll job status/result | exists |
| POST | `/api/render` | DOCX/PDF bytes (`fmt: docx\|pdf`) | exists |
| POST | `/api/extract-resume` | file → text (if importing a new résumé) | exists |

**Request shape (illustrative, `/api/qualify` + `/api/jobs`):** `{ jd_text, resume_text,
confirmed_tools?, style?, fix_gaps_json? }`. The extension passes the captured `jdText` and the
chosen saved résumé's text. Contract mirrors what the web UI already sends — no new engine logic.

## Data schemas (extension-side)

### Selector config (`selectors.json`, remote-overridable)
```json
{
  "version": 3,
  "ats": {
    "greenhouse": { "match": ["boards.greenhouse.io","*.greenhouse.io"],
                    "title": ".app-title", "company": ".company-name", "jd": "#content" },
    "lever":      { "match": ["jobs.lever.co"], "title": ".posting-headline h2",
                    "company": ".main-header-logo img[alt]", "jd": ".section-wrapper .section" }
  },
  "fallback": { "strategy": "largest-text-block", "title": "document.title" }
}
```

### chrome.storage
```json
{
  "resopt_resumes": [ { "id": "...", "label": "Backend — master v3", "text": "..." } ],
  "resopt_engine_port": 47615,
  "resopt_selectors_cache": { "version": 3, "fetchedAt": "..." }
}
```
The AI key (if used) is kept in **session** memory only, never in `chrome.storage`.

## manifest.json (v1 shape)
```json
{
  "manifest_version": 3,
  "name": "RESOPT — optimize your résumé in place",
  "permissions": ["sidePanel", "activeTab", "storage", "scripting"],
  "host_permissions": [
    "http://127.0.0.1/*",
    "*://boards.greenhouse.io/*", "*://*.greenhouse.io/*",
    "*://jobs.lever.co/*", "*://*.myworkdayjobs.com/*",
    "*://*.icims.com/*", "*://*.smartrecruiters.com/*",
    "*://*.ashbyhq.com/*", "*://*.bamboohr.com/*",
    "*://www.linkedin.com/*", "*://*.indeed.com/*"
  ],
  "background": { "service_worker": "background.js" },
  "side_panel": { "default_path": "sidepanel.html" },
  "action": { "default_title": "RESOPT" }
}
```
ATS domain list mirrors the engine's supported portals (`app/ats/portals.py`) so the two stay
in sync. `activeTab` + explicit domains is deliberately narrower than `<all_urls>` (review-friendly).

## Accessibility & UX rules
- Keyboard-reachable controls; visible focus; the panel works at narrow widths (~360px).
- Never dead-end: engine down, unknown site, or empty capture each offer a next step.
- Honest-gaps list is always shown when non-empty — it is core to the product, not hidden.
