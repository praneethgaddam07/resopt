# RESOPT Browser Extension — pre-project dossier

This folder is the "before we write code" package for the RESOPT Chrome extension v1:
the research, the spec, the architecture, and the risks — everything a team would settle
before opening an editor.

**One-line vision:** on any job posting, RESOPT reads *that* page, detects the ATS, captures
the JD, and optimizes the résumé in a side panel — with the engine being the user's own
desktop app running locally. Zero server cost, zero scraping infrastructure, and a privacy
story that is literally true ("the engine is on your machine").

## Status
- Concept, 3-state side-panel mockups, and prototype spec **approved** (2026-07-03).
- No code written yet. This dossier is the approval/kickoff gate.
- Effort estimate for v1: **~2–3 build sessions.**

## Read in this order
1. [01 — Product brief](01-product-brief.md) — problem, vision, goals, non-goals, success metrics
2. [02 — Market, competitive & user research](02-research-market-users.md) — landscape, positioning, personas, journeys
3. [03 — Technical feasibility](03-technical-feasibility.md) — MV3, side panel, localhost bridge, scraping, store review
4. [04 — Architecture](04-architecture.md) — components, data flow, trust boundary, config-driven selectors
5. [05 — Functional spec](05-functional-spec.md) — states, flows, edge cases, API contracts, permissions
6. [06 — Security & privacy](06-security-privacy.md) — threat model, permission justifications, data handling
7. [07 — Risks, roadmap & go-to-market](07-risks-roadmap-gtm.md) — risk register, milestones, v2/v3, distribution

## The one engine-side change v1 needs
The desktop local server (`desktop.py`, FastAPI on `127.0.0.1:47615`) adds:
- CORS headers allowing `Origin: chrome-extension://<id>`
- a lightweight `GET /api/ping` (used by the side panel to detect "engine live" vs. State C)

Everything else the extension calls already exists: `/api/qualify`, `/api/jobs`, `/api/render`,
`/api/health`, `/api/ats`, `/api/extract-resume`.

## Open decisions (need your call before build)
See the end of [07 — Risks, roadmap & go-to-market](07-risks-roadmap-gtm.md#open-decisions).
