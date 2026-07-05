# 01 — Product brief

## The problem
A serious job seeker applies to 50–150 roles. For each one the honest, effective loop is:

1. Open the posting, read the JD.
2. Switch to RESOPT (web or desktop), paste the JD, pick/upload the résumé.
3. Optimize, download, switch back to the ATS, upload, fill the form.

Steps 1–2 are pure friction — copy, paste, tab-switch — repeated dozens of times. It is the
single biggest reason people stop tailoring their résumé and start blasting one generic PDF,
which is exactly what tanks their ATS match score. The tool works; the *workflow around it*
is where candidates give up.

## The insight
The job description is already rendered on the page the user is looking at — behind their own
login on LinkedIn, Indeed, Workday, Greenhouse, etc. If the tool lives *in the browser*, it can
read that page directly. No paste. No scraping servers. No fighting bot-detection, because it is
the user's own authenticated session.

And RESOPT already ships a desktop app that runs the full deterministic engine locally on
`127.0.0.1:47615`. So the extension needs no backend of its own — it calls the engine on the
user's machine.

## The vision
**Optimize in place.** Land on a posting → the extension detects the ATS and captures the JD →
one click optimizes against a saved résumé → score, honest gaps, and a downloadable DOCX/PDF
appear in a side panel, without ever leaving the page.

## Why this is the right bet for RESOPT specifically
- **The privacy pitch becomes literally true.** "The engine is on your machine, nothing is
  uploaded" is a headline feature, not marketing spin — the extension talks to `localhost`.
- **Zero marginal cost.** No server, no scraping infra, no LLM spend on our side (the desktop
  engine is deterministic; any LLM use is the user's own key/subscription).
- **It compounds the existing moat.** Truthful optimization + the "confirm your tools / safe
  ingestion" stance is *more* valuable in-context, where the real JD and the real résumé meet.
- **Distribution flywheel.** State C (engine not running) doubles as an install funnel for the
  desktop app — the extension markets the app and vice versa.

## Goals (v1)
- G1 — Detect the ATS and capture the JD automatically on the top ATS domains.
- G2 — Optimize a saved résumé against that JD via the local engine, in the side panel.
- G3 — Show ATS match score, what was closed, honest gaps, and DOCX/PDF downloads.
- G4 — Graceful, funnel-friendly handling when the desktop engine isn't running (State C).
- G5 — Keep the extension *thin* — logic stays in the engine so we can iterate without store review.

## Non-goals (v1 — explicitly deferred)
- No auto-apply / auto-fill of application forms (that's v2).
- No job tracker / saved-applications database (v2).
- No hosted/cloud fallback engine for users without the desktop app (v3, opt-in).
- No server-side JD fetching or scraping — the extension only reads the page the user is on.
- No new résumé authoring UI — the side panel picks from existing saved résumés.

## Success metrics
Because the engine is local and we store nothing, instrument lightly and locally (opt-in):
- **Activation:** % of installs that complete ≥1 optimization within 7 days.
- **Detection quality:** JD-capture success rate per ATS domain (target ≥90% on named portals).
- **Loop compression:** self-reported time-per-application before/after (qualitative v1).
- **Funnel:** State C → desktop-app download clicks.
- **Retention proxy:** optimizations per active user per week.
