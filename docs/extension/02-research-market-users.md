# 02 — Market, competitive & user research

## Market context
Résumé-optimization and job-application tooling is a crowded, well-funded consumer space
(Jobscan, Teal, Simplify, Rezi, Careerflow, Huntr, and a long tail of auto-appliers). Demand is
structurally high: cold job markets push more applications per seeker, and ATS filtering makes
keyword-matched, tailored résumés materially outperform generic ones. The browser-extension form
factor is already validated — Teal and Simplify have hundreds of thousands of installs — which
de-risks "will people install a job-search extension" (they will).

## Competitive landscape

| Product | Form factor | What it does | Data model | Gap RESOPT exploits |
|---|---|---|---|---|
| **Jobscan** | Web app | Paste JD + résumé → ATS match score | Server-side, paid | Still paste-driven; no in-page capture; subscription |
| **Teal** | Extension + web | Save jobs, résumé builder, tracker | Cloud account, freemium | Cloud-stored data; optimization is manual/generic |
| **Simplify** | Extension | Autofill applications, track jobs | Cloud profile | Autofill-first, not optimization; data lives on their servers |
| **Careerflow** | Extension + web | LinkedIn optimization, tracker, AI | Cloud, freemium | Broad but shallow tailoring; cloud data |
| **Rezi** | Web app | AI résumé builder, ATS templates | Cloud, paid | Builder, not in-context optimizer; no page capture |
| **Huntr** | Extension + web | Job tracker / kanban | Cloud | Tracking only; no optimization engine |
| **LazyApply / Sonara / LoopCV** | Extension / service | Mass auto-apply | Cloud, paid | Volume over quality; the opposite of honest tailoring |

## RESOPT's differentiated position
1. **Local-first / zero-retention, provably.** Everyone else runs optimization on their servers.
   RESOPT's extension calls the user's own machine — the privacy claim is verifiable, not a policy.
2. **Truthful optimization ("safe ingestion").** The category quietly rewards keyword-stuffing and
   fabricated metrics. RESOPT deliberately *won't* invent experience — it closes gaps only by
   rephrasing real content and shows an honest "left out — no basis" list (see State B). This is a
   trust wedge no auto-applier can copy without contradicting their own pitch.
3. **In-page, one-click, on the real JD.** No paste, no re-typing — lower friction than paste-based
   tools, and it reads the JD exactly as shown behind the user's login (LinkedIn/Workday included,
   which server scrapers can't reliably reach).
4. **No double-pay.** No forced subscription and no second AI bill — the engine is deterministic;
   any generative step uses the user's own key/subscription.

**Positioning statement:** *The only résumé optimizer that runs on your machine, reads the job
you're actually looking at, and refuses to lie on your behalf.*

## User research

### Primary persona — "Applying Alex"
- Early-to-mid career, technical or business, applying to 30–100 roles over a few months.
- Comfortable installing a browser extension; already has 5+ tabs of postings open.
- Pain: tailoring each résumé is tedious, so quality decays as volume rises.
- Wants: fast, honest tailoring that visibly improves ATS match without lying.

### Secondary persona — "Career-switch Casey"
- Changing industries; genuinely worried about honesty and "am I even qualified."
- Values the fit-check + honest-gaps framing over a vanity score — the truthful stance is the draw.

### Jobs to be done
- *When I'm on a posting I want to apply to, help me tailor my résumé to it without leaving the page.*
- *When I tailor, tell me honestly what I can and can't claim, so I don't get caught out in interviews.*
- *When I'm done, give me an ATS-ready file I can upload right here.*

### Current journey (painful) vs. proposed
- **Today:** posting → copy JD → open RESOPT → paste → pick résumé → optimize → download → back to ATS → upload. ~8 context switches.
- **Proposed:** posting → open side panel (JD already captured) → pick résumé → optimize → download. ~2 context switches.

### What we're assuming and must validate
- Users will keep the desktop engine running (or accept launching it). — Mitigated by State C funnel.
- JD capture is reliable enough across ATS DOM structures. — Mitigated by per-site selectors + fallback + remote config.
- The honest-gaps framing is a *draw*, not a downer. — Validate in the first walkthrough with real users.
