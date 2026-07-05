"""Fast, grounded résumé-tailoring engine.

Pipeline (≈4 LLM calls vs. the old ~14, two of them in parallel):
  1. EXTRACT  — pull the candidate's real content + original bullets (résumé only).
  2. ANALYZE  — JD problem, keywords (required/preferred), tone, reframe map, bridge.
     (1 and 2 are independent and run concurrently.)
  3. TAILOR   — REPHRASE the real bullets to fit the JD, SELECT the strongest,
                CUT the rest. Never invents new achievements.
  4. FINISH   — skills + summary in one call.
Contact + education are kept verbatim (never rephrased). Scoring/format are local.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from ..ats.portals import PortalRules, get_portal
from ..llm.client import LLMClient
from ..llm import prompts as P
from . import scoring
from . import validators
from .taxonomy_resolver import resolve_coverage
from .extract import regex_contact

ProgressCb = Callable[[int, str], None]


@dataclass
class WorkflowResult:
    contact: dict
    data: dict
    analysis: dict
    report: dict
    usage: dict = field(default_factory=dict)


def _noop(_s: int, _l: str) -> None:
    pass


def run_workflow(
    resume_text: str,
    jd_text: str,
    *,
    client: LLMClient,
    ats: str = "generic",
    bullet_counts: list[int] | None = None,
    project_counts: list[int] | None = None,
    max_bullets: int = 20,
    target_title: str = "",
    company: str = "",
    confirmed_tools: list[str] | None = None,
    fix_gaps: list[str] | None = None,  # fixable gaps from the fit check, targeted here
    progress_cb: ProgressCb | None = None,
) -> WorkflowResult:
    cb = progress_cb or _noop
    portal: PortalRules = get_portal(ats)
    resume_ctx = f"MASTER RESUME:\n{resume_text}"
    full_ctx = f"{resume_ctx}\n\nJOB DESCRIPTION:\n{jd_text}"
    jd_keywords = scoring.extract_jd_keywords(jd_text, limit=18)

    # ---- Steps 1+2 in parallel: extract real content & analyze the JD ----
    cb(1, "Reading your résumé")
    with ThreadPoolExecutor(max_workers=2) as ex:
        # Phase: content extraction + JD dissection/gap analysis -> Tier 1 (light).
        f_content = ex.submit(
            client.complete_json, resume_ctx, P.EXTRACT_CONTENT,
            mock=_mock_content(resume_text), max_tokens=3000, task_tier="light")
        f_analysis = ex.submit(
            client.complete_json, full_ctx, P.ANALYZE_JD,
            mock=_mock_analysis(jd_keywords), max_tokens=1500, task_tier="light")
        content = f_content.result()
        analysis = f_analysis.result()
    cb(2, "Understanding the role")

    real_exps = [e for e in content.get("experiences", []) if e.get("title")]
    real_projs = [p for p in content.get("projects", []) if p.get("title")]
    if not real_exps:
        real_exps = [{"title": "Experience", "company": "", "duration": "",
                      "location": "", "bullets": []}]
    contact = {
        **(content.get("contact") or {}),
        "education": content.get("education") or [],
        "certifications": content.get("certifications") or [],
    }

    # How many bullets to KEEP per entry (selection target, not generation count).
    if bullet_counts:
        exp_counts = _fit_counts(bullet_counts, len(real_exps))
        proj_counts = _fit_counts(project_counts or [], len(real_projs)) if real_projs else []
        exp_counts, proj_counts = _cap_total(exp_counts, proj_counts, max_bullets)
    else:
        exp_counts, proj_counts = _auto_distribute(len(real_exps), len(real_projs), hi=max_bullets)

    # ---- Steps 3+4 in parallel: tailor bullets & build skills+summary ----
    # Both depend only on (extracted content + analysis), not on each other.
    cb(3, "Matching your experience")
    star = ("\n- Every kept bullet must be a full STAR statement (Situation, Task, Action, Result)."
            if portal.star_every_bullet else "")
    lp = ("\n- Tag every bullet with a Leadership Principle in parentheses at the very end, "
          "e.g. '(Deliver Results)'." if portal.leadership_principle_tags else "")
    # Candidate's real tools + any they attested to in the Confirm-Your-Tools step.
    real_skill_inventory = list(content.get("skills", [])) + list(confirmed_tools or [])
    jd_required_tools, _seen_t = [], set()
    for t in (analysis.get("required", []) + analysis.get("hard_skills", [])):
        tl = (t or "").lower().strip()
        if tl and tl not in _seen_t:
            _seen_t.add(tl)
            jd_required_tools.append(t)
    # Truthful tool coverage (Bucket 2): which JD tools the candidate genuinely has, or
    # has a same-category real tool for. Drives weaving tools INTO the bullets (not just
    # skills) without changing the work or its metric — the JPMC/GS pattern.
    coverage = resolve_coverage(real_skill_inventory, jd_required_tools)
    adj = "; ".join(f"{a.your_tools[0]} (as {a.category}; JD asked for {a.jd_tool})"
                    for a in coverage.adjacent if a.your_tools)
    tailor_input = (
        full_ctx
        + "\n\nCANDIDATE EXPERIENCES (rephrase these, do not invent):\n" + _entries_text(real_exps)
        + "\n\nCANDIDATE PROJECTS:\n" + _entries_text(real_projs)
        + "\n\nCANDIDATE'S FULL REAL SKILL INVENTORY:\n" + ", ".join(real_skill_inventory[:60])
        + "\n\nTOOL COVERAGE — weave these into the RELEVANT BULLETS (experience AND projects), "
          "NOT just the skills list. Keep each bullet's work and its EXACT metric unchanged; only "
          "name the tool/framework where the candidate truly used it:"
        + "\n  - SURFACE in the JD's exact words (candidate genuinely has these): "
        + (", ".join(coverage.matched) or "(none)")
        + "\n  - SURFACE the candidate's REAL tool + its category, NEVER the JD's tool: " + (adj or "(none)")
        + "\n  - DO NOT add these (genuine gaps, flagged for the candidate separately): "
        + (", ".join(coverage.missing) or "(none)")
        + "\n\nJD KEYWORDS TO MIRROR: " + ", ".join(analysis.get("priority_keywords", [])[:18])
        + "\nPROBLEM: " + analysis.get("problem_statement", "")
        + (("\n\nFIT-CHECK GAPS TO CLOSE (these were diagnosed as REPHRASING gaps — close each "
            "one ONLY by resurfacing or rewording experience the candidate already has above; "
            "if no true basis exists in their real bullets/skills, SKIP it — never invent):\n- "
            + "\n- ".join(g.strip() for g in fix_gaps[:6] if g and g.strip()))
           if fix_gaps else "")
    )
    job_title = target_title or analysis.get("job_title") or _infer_title(jd_keywords)
    real_bullets_text = "\n".join(b for e in real_exps for b in e.get("bullets", []))
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_tailored = ex.submit(
            client.complete_json, tailor_input,
            P.TAILOR.format(star_clause=star, lp_clause=lp,
                            plan=_plan(real_exps, exp_counts, real_projs, proj_counts)),
            mock=_mock_tailor(real_exps, exp_counts, real_projs, proj_counts, portal),
            max_tokens=4000, task_tier="heavy")  # Phase 3: bullet rewriting — quality-critical
        f_fin = ex.submit(
            client.complete_json,
            full_ctx + "\n\nCANDIDATE BULLETS:\n" + real_bullets_text
            + "\n\nCOMPANY PROBLEM: " + analysis.get("problem_statement", "")
            + "\nBRIDGE: " + analysis.get("bridge", ""),
            P.SKILLS_SUMMARY.format(job_title=job_title, tone=analysis.get("tone", "professional")),
            mock=_mock_skills_summary(jd_keywords, content.get("skills", []), job_title),
            max_tokens=2500, task_tier="heavy")  # Phase 3: skills + recruiter-facing summary
        tailored = f_tailored.result()
        fin = f_fin.result()
    cb(4, "Writing your résumé")
    experiences = _attach_meta(real_exps, tailored.get("experiences", []), exp_counts)
    projects = _clean_projects(tailored.get("projects", []), proj_counts)
    skills = fin.get("skills", [])
    summary = _trim_to_words(fin.get("summary", ""), 75)

    # ---- Deterministic guards (never name the company or candidate; unique verbs) ----
    cand_name = (contact.get("name") or "").strip()
    _dedupe_verbs(experiences, projects)
    _scrub_bridge_lines(experiences, company, cand_name)
    summary = _fix_summary(client, summary, full_ctx, job_title, company, cand_name)

    data = {
        "job_title": job_title, "summary": summary, "skills": skills,
        "experiences": experiences, "projects": projects,
        "education": contact["education"], "certifications": contact["certifications"],
    }
    _sanitize_data(data)

    # ---- Step 5: score, then TRUTHFULLY maximize coverage, then re-score ----
    cb(5, "Scoring against the ATS")
    gap = {"reframeable": analysis.get("reframeable", [])}
    report = scoring.build_report(data, jd_text, portal, jd_dissection=analysis, gap=gap)
    # (a) LLM exact-phrase alignment: rephrase content the candidate already has into the
    #     JD's exact wording (near-miss + Moderate adjacents) — the biggest honest lift.
    if _align_keywords(client, data, analysis, report):
        report = scoring.build_report(data, jd_text, portal, jd_dissection=analysis, gap=gap)
    # (b) Deterministic safety net: drop any still-uncovered exact phrases the candidate
    #     genuinely has into the skills section.
    if _maximize_coverage(data, report, analysis, content.get("skills", [])):
        report = scoring.build_report(data, jd_text, portal, jd_dissection=analysis, gap=gap)

    # (c) Integrity Guardrail (Phase 4): deterministic backstop before formatting —
    #     no unbacked metric and no AI-tell word may ship. Source = original bullets.
    src_exp = [b for e in real_exps for b in e.get("bullets", [])]
    src_proj = [b for p in real_projs for b in p.get("bullets", [])]
    integrity = validators.enforce(data, src_exp, src_proj)
    if not integrity.ok:
        _sanitize_data(data)
        report = scoring.build_report(data, jd_text, portal, jd_dissection=analysis, gap=gap)
    analysis_out = {
        "problem": {"problem_statement": analysis.get("problem_statement", "")},
        "bridge": analysis.get("bridge", ""),
        "jd_dissection": analysis,
        "gap_analysis": {"reframeable": analysis.get("reframeable", [])},
        "portal": {"key": portal.key, "name": portal.name, "category": portal.category},
    }
    cb(6, "Done")
    return WorkflowResult(contact=contact, data=data, analysis=analysis_out,
                          report=report, usage=client.usage.as_dict())


# --------------------------- text helpers ---------------------------

def _entries_text(entries: list[dict]) -> str:
    out = []
    for i, e in enumerate(entries, 1):
        head = e.get("title", "")
        if e.get("company"):
            head += f" — {e['company']}"
        out.append(f"[{i}] {head}")
        for b in e.get("bullets", []):
            out.append(f"  - {b}")
    return "\n".join(out) or "(none)"


def _plan(exps, exp_counts, projs, proj_counts) -> str:
    lines = [f"Experience {i+1} ({e.get('title','')}): up to {n} bullets"
             for i, (e, n) in enumerate(zip(exps, exp_counts))]
    lines += [f"Project {i+1} ({p.get('title','')}): up to {n} bullets"
              for i, (p, n) in enumerate(zip(projs, proj_counts))]
    return "\n".join(lines)


def _attach_meta(real_exps, tailored_exps, exp_counts) -> list[dict]:
    """Keep real job metadata; take rephrased bullets + bridge line from the tailor step."""
    out = []
    for i, real in enumerate(real_exps):
        t = tailored_exps[i] if i < len(tailored_exps) else {}
        cap = exp_counts[i] if i < len(exp_counts) else 5
        out.append({
            "title": real.get("title", ""), "company": real.get("company", ""),
            "duration": real.get("duration", ""), "location": real.get("location", ""),
            "bridge_line": t.get("bridge_line", ""),
            "bullets": (t.get("bullets") or real.get("bullets", []))[:cap],
        })
    return out


def _clean_projects(tailored_projs, proj_counts) -> list[dict]:
    cap = max(proj_counts) if proj_counts else 3
    out = []
    for p in tailored_projs:
        if p.get("title"):
            out.append({"title": p["title"], "bullets": (p.get("bullets") or [])[:cap]})
    return out


# --------------------------- bullet-budget helpers ---------------------------

def _fit_counts(counts: list[int], n: int, default: int = 2) -> list[int]:
    counts = counts or []
    return [(counts[i] if i < len(counts) else default) for i in range(n)]


def _cap_total(exp_counts, proj_counts, hi):
    exp_counts, proj_counts = list(exp_counts), list(proj_counts)

    def total():
        return sum(exp_counts) + sum(proj_counts)

    while total() > hi:
        if proj_counts and proj_counts[-1] > 1:
            proj_counts[-1] -= 1
        elif len(proj_counts) > 1:
            proj_counts.pop()
        elif any(c > 2 for c in exp_counts):
            for i in range(len(exp_counts) - 1, -1, -1):
                if exp_counts[i] > 2:
                    exp_counts[i] -= 1
                    break
        elif proj_counts:
            proj_counts.pop()
        elif len(exp_counts) > 1:
            exp_counts.pop()
        else:
            exp_counts[-1] = max(1, exp_counts[-1] - 1)
            if exp_counts[-1] <= 1:
                break
    return exp_counts, proj_counts


def _auto_distribute(n_exp, n_proj, hi=20):
    if n_exp == 0:
        return [], [2] * min(n_proj, hi // 2)
    exp_counts = [max(2, 6 - i) for i in range(n_exp)]  # 6, 5, 4, 3, 2, ...
    proj_counts = [2] * n_proj
    return _cap_total(exp_counts, proj_counts, hi)


# --------------------------- quality / sanitize helpers ---------------------------

_SYMBOL_FIXES = [("---", "-"), ("#", ""), ("_", " "), ("*", "")]


def _sanitize_symbols(s: str) -> str:
    if not s:
        return s
    for bad, good in _SYMBOL_FIXES:
        s = s.replace(bad, good)
    s = s.replace(";", ",")
    return re.sub(r"\s{2,}", " ", s).strip()


_SKILL_QUALIFIER_RE = re.compile(
    r"\s*[-–—]\s*(advanced|intermediate|expert|proficient|proficiency|basic|beginner|experienced)\s*$",
    re.I)
_SKILL_PAREN_RE = re.compile(r"^\s*([^()]+?)\s*\(([^)]+)\)")


def _compact_skill(s: str) -> str:
    """Keep a skill as a concise keyword. Strips space-bloating descriptive glosses
    ('Tableau (interactive dashboard development)') and proficiency qualifiers
    ('- advanced'), but PRESERVES true acronym expansions ('SQL (Structured Query
    Language)') that help ATS match either form. Deterministic backstop so the section
    stays compact even if the model over-explains."""
    s = (s or "").strip()
    s = _SKILL_QUALIFIER_RE.sub("", s)
    m = _SKILL_PAREN_RE.match(s)
    if not m:
        return s
    term, paren = m.group(1).strip(), m.group(2).strip()
    letters = [c for c in term if c.isalpha()]
    is_acronym = bool(re.fullmatch(r"[A-Z][A-Z0-9.\-/]{1,7}", term)) and len(letters) >= 2
    words = [w for w in re.split(r"[\s,]+", paren) if w]
    keep_expansion = (
        is_acronym and words
        and words[0][:1].upper() == term[:1].upper()
        and (len(letters) - 1) <= len(words) <= (len(letters) + 1)
    )
    return f"{term} ({paren})" if keep_expansion else term


def _sanitize_data(data: dict) -> None:
    data["summary"] = _sanitize_symbols(data.get("summary", ""))
    for exp in data.get("experiences", []):
        exp["bullets"] = [_sanitize_symbols(b) for b in exp.get("bullets", [])]
        if exp.get("bridge_line"):
            exp["bridge_line"] = _sanitize_symbols(exp["bridge_line"])
    for proj in data.get("projects", []):
        proj["bullets"] = [_sanitize_symbols(b) for b in proj.get("bullets", [])]
    for cat in data.get("skills", []):
        cat["skills"] = [_compact_skill(_sanitize_symbols(s)) for s in cat.get("skills", [])]


def _trim_to_words(text: str, n: int) -> str:
    words = text.split()
    if len(words) <= n:
        return text
    return " ".join(words[:n]).rstrip(",.;: ") + "."


def _maximize_coverage(data: dict, report: dict, analysis: dict, real_skills: list[str]) -> bool:
    """Lift the ATS score TRUTHFULLY: add the JD's exact phrasing for keywords the
    candidate genuinely has a basis for, into the skills section (where ATS weights
    keywords most). Returns True if anything was added (caller re-scores).

    A keyword qualifies only if:
      * it's a near-miss (the candidate already demonstrates the concept, just worded
        differently), OR
      * it has a reframeable analogue from the gap analysis, OR
      * it literally appears in the candidate's real listed skills.
    Genuinely-absent requirements are NEVER injected — they stay flagged for the user.
    """
    real_lower = {s.lower() for s in (real_skills or [])}
    reframe_jd = {rf.get("jd_skill", "").lower() for rf in analysis.get("reframeable", [])}
    near = {k.lower() for k in report.get("near_miss_keywords", [])}
    missing = {m.lower() for m in report.get("missing_keywords", [])}
    not_matched = near | missing  # keywords the JD wants that aren't an exact match yet

    candidates, seen = [], set()
    # Keep original casing/order from the report's keyword lists.
    for kw in report.get("near_miss_keywords", []) + report.get("missing_keywords", []):
        kl = kw.lower()
        if kl in seen or kl not in not_matched:
            continue
        seen.add(kl)
        has_basis = (kl in near or kl in reframe_jd or kl in real_lower
                     or any(kl in s or s in kl for s in real_lower))
        if has_basis:
            candidates.append(kw)

    if not candidates:
        return False

    # Append to the smallest category to keep them balanced; avoid duplicates.
    existing = {s.lower() for c in data.get("skills", []) for s in c.get("skills", [])}
    cats = data.get("skills", [])
    if not cats:
        cats = [{"name": "Key Skills", "skills": []}]
        data["skills"] = cats
    added = False
    for kw in candidates:
        if kw.lower() in existing:
            continue
        target = min(cats, key=lambda c: len(c.get("skills", [])))
        target.setdefault("skills", []).append(kw)
        existing.add(kw.lower())
        added = True
    return added


def _align_keywords(client, data: dict, analysis: dict, report: dict) -> bool:
    """Moderate ATS alignment (the big honest lever). Rephrase EXISTING bullets/skills
    to use the JD's EXACT wording for keywords the candidate already has a basis for —
    near-misses (concept present, worded differently) and adjacent skills (MySQL↔
    PostgreSQL). Never inserts a skill with no basis. Returns True if anything changed.

    Skipped in mock mode (deterministic tests use _maximize_coverage instead).
    """
    if getattr(client, "mock", False):
        return False
    targets, seen = [], set()
    for kw in report.get("near_miss_keywords", []) + report.get("missing_keywords", []):
        kl = (kw or "").lower().strip()
        if kl and kl not in seen:
            seen.add(kl)
            targets.append(kw)
    exps = data.get("experiences", [])
    if not targets or not exps:
        return False

    payload = {
        "experiences": [{"bullets": list(e.get("bullets", []))} for e in exps],
        "skills": data.get("skills", []),
        "target_phrases": targets[:24],
        "reframeable": analysis.get("reframeable", []),
    }
    try:
        out = client.complete_json(
            "ATS keyword alignment — truthful rephrasing only.",
            P.ALIGN_KEYWORDS + "\n\nCURRENT CONTENT + TARGET PHRASES (JSON):\n"
            + json.dumps(payload, ensure_ascii=False),
            mock={}, max_tokens=2500, task_tier="light",
        )
    except Exception:  # noqa: BLE001 -- alignment is best-effort; keep the original on failure
        return False

    changed = False
    new_exps = out.get("experiences")
    if isinstance(new_exps, list) and len(new_exps) == len(exps):
        for e, ne in zip(exps, new_exps):
            nb = ne.get("bullets") if isinstance(ne, dict) else None
            if isinstance(nb, list) and nb:
                cap = len(e.get("bullets", [])) or len(nb)  # never let it add bullets
                e["bullets"] = [str(b) for b in nb if str(b).strip()][:cap]
                changed = True
    new_skills = out.get("skills")
    if (isinstance(new_skills, list) and new_skills
            and all(isinstance(c, dict) and c.get("skills") for c in new_skills)):
        data["skills"] = new_skills
        changed = True
    if changed:
        _sanitize_data(data)
    return changed


# NOTE: keep this free of the AI-tell ban-list in prompts.py (no "Spearheaded",
# "Orchestrated", etc.) so the dedupe guard never reintroduces a banned verb.
_VERB_POOL = ["Built", "Engineered", "Designed", "Implemented", "Analyzed", "Automated",
              "Deployed", "Optimized", "Delivered", "Streamlined", "Led", "Architected",
              "Reduced", "Accelerated", "Standardized", "Drove", "Established",
              "Produced", "Modeled", "Validated", "Consolidated", "Translated", "Directed",
              "Overhauled", "Devised", "Formulated", "Pioneered", "Revamped", "Rebuilt"]


def _dedupe_verbs(experiences: list[dict], projects: list[dict]) -> None:
    """Guarantee every bullet starts with a UNIQUE action verb (Resume-Worded rule)."""
    used: set[str] = set()
    pool = [v for v in _VERB_POOL]

    def fix(bullets: list[str]) -> None:
        for i, b in enumerate(bullets):
            words = b.split()
            if not words:
                continue
            head = words[0].strip(",.").lower()
            if head in used:
                repl = next((v for v in pool if v.lower() not in used), None)
                if repl:
                    words[0] = repl
                    bullets[i] = " ".join(words)
                    used.add(repl.lower())
            else:
                used.add(head)

    for e in experiences:
        fix(e.get("bullets", []))
    for p in projects:
        fix(p.get("bullets", []))


def _names(*vals: str) -> list[str]:
    """Lowercased name/company tokens worth scrubbing (full string + each long word)."""
    out: list[str] = []
    for v in vals:
        v = (v or "").strip()
        if len(v) >= 3:
            out.append(v.lower())
            out += [w.lower() for w in v.split() if len(w) >= 4]
    return out


def _scrub_bridge_lines(experiences: list[dict], company: str, cand_name: str) -> None:
    """Blank any bridge line that names the company/candidate or is over-long."""
    bad = set(_names(company, cand_name))
    for e in experiences:
        bl = (e.get("bridge_line") or "").strip()
        if not bl:
            continue
        low = bl.lower()
        if len(bl.split()) > 24 or any(b in low for b in bad):
            e["bridge_line"] = ""


def _fix_summary(client, summary: str, ctx: str, job_title: str,
                 company: str, cand_name: str) -> str:
    """If the summary names the company or candidate, rewrite it impersonally."""
    low = summary.lower()
    offenders = set(_names(company, cand_name))
    if not summary or not any(o in low for o in offenders):
        return _trim_to_words(summary, 75)
    if getattr(client, "mock", False):  # mock summaries are already clean
        return _trim_to_words(summary, 75)
    fixed = client.complete_json(
        ctx + f"\n\nDRAFT SUMMARY (fix it):\n{summary}",
        f"Rewrite this résumé summary. STRICT: never mention any company name, never "
        f"mention any person's name, no he/she/they. Impersonal. Open with the candidate's "
        f"best-fit defensible title (anchor: '{job_title}') without inflating seniority, and "
        f"claim a domain only if the résumé actually shows it. Exactly 4 sentences, max 75 "
        f"words total, max 20 words per sentence. JSON: {{\"summary\": \"...\"}}",
        mock={"summary": summary}, max_tokens=300, task_tier="light",  # Phase 4 quality repair
    ).get("summary", summary)
    return _trim_to_words(fixed, 75)


def _metricless_indices(experiences: list[dict]) -> list[tuple[int, int]]:
    out = []
    for ei, exp in enumerate(experiences):
        for bi, b in enumerate(exp.get("bullets", [])):
            if not scoring.has_metric_or_artifact(b):
                out.append((ei, bi))
    return out


def _infer_title(jd_keywords: list[str]) -> str:
    for k in jd_keywords:
        if any(t in k for t in ("analyst", "engineer", "manager", "developer", "scientist")):
            return k.title()
    return "Analyst"


# --------------------------- mock builders (no-key dev/tests) ---------------------------

_SAMPLE_BULLETS = [
    "Reduced manual processing time by 34% across the reporting workflow",
    "Improved data accuracy to 98% through automated validation checks",
    "Cut report turnaround from 5 days to under 1 day for 12 stakeholders",
    "Increased pipeline throughput by 40% while maintaining a 99% SLA",
    "Saved an estimated 200 hours per quarter via process automation",
    "Built a reusable dashboard adopted by 6 regional managers",
]


def _mock_content(resume_text: str) -> dict:
    c = regex_contact(resume_text)
    def role(title, dur):
        return {"title": title, "company": "Confidential", "duration": dur,
                "location": "Remote", "bullets": list(_SAMPLE_BULLETS)}
    return {
        "contact": {k: c.get(k, "") for k in ("name", "phone", "email", "linkedin", "location")},
        "education": c.get("education", []),
        "certifications": c.get("certifications", []),
        "skills": ["SQL", "Python", "Tableau", "Excel", "data validation", "reporting",
                   "ETL", "dashboards", "stakeholder communication"],
        "experiences": [role("Most Recent Role", "May 2022 - Present"),
                        role("Prior Role 1", "Jun 2020 - Apr 2022"),
                        role("Prior Role 2", "Jan 2018 - May 2020")],
        "projects": [{"title": "Project 1", "bullets": list(_SAMPLE_BULLETS[:4])},
                     {"title": "Project 2", "bullets": list(_SAMPLE_BULLETS[:4])}],
    }


def _mock_analysis(jd_keywords: list[str]) -> dict:
    kw = jd_keywords or ["data analysis", "reporting", "automation"]
    return {
        "problem_statement": "The team needs someone who can immediately own the core work "
                             "and close the gap between current output and target outcomes.",
        "job_title": _infer_title(kw),
        "tone": "technical",
        "required": kw[:6],
        "preferred": kw[6:10],
        "priority_keywords": kw[:14],
        "hard_skills": kw,  # mock: treat all extracted JD terms as the hard-skill universe
        "reframeable": [{"candidate_skill": k, "jd_skill": k} for k in kw[:3]],
        "bridge": "The candidate has solved this exact class of problem using the tools the JD names.",
    }


def _mock_tailor(real_exps, exp_counts, real_projs, proj_counts, portal) -> dict:
    lps = ["Deliver Results", "Dive Deep", "Bias for Action", "Invent and Simplify"]

    def take(bullets, n, lp_offset=0):
        out = []
        for j, b in enumerate(bullets[:n]):
            t = b if b.endswith(".") else b + "."
            if portal.leadership_principle_tags:
                t = t[:-1] + f" ({lps[(j + lp_offset) % len(lps)]})"
            out.append(t)
        return out

    exps = []
    for i, e in enumerate(real_exps):
        n = exp_counts[i] if i < len(exp_counts) else 3
        exps.append({"bridge_line": "This work maps directly to the role's core problem.",
                     "bullets": take(e.get("bullets", _SAMPLE_BULLETS), n, i)})
    projs = []
    for i, p in enumerate(real_projs):
        n = proj_counts[i] if i < len(proj_counts) else 2
        projs.append({"title": p.get("title", f"Project {i+1}"),
                      "bullets": take(p.get("bullets", _SAMPLE_BULLETS), n)})
    return {"experiences": exps, "projects": projs}


def _mock_skills_summary(jd_keywords, real_skills, job_title) -> dict:
    pool, seen = [], set()
    for s in (jd_keywords + list(real_skills) + ["SQL (Structured Query Language)",
              "Python (Programming Language)", "Excel", "Tableau", "Power BI",
              "ETL (Extract Transform Load)", "data validation", "dashboards",
              "process automation", "A/B testing", "statistical analysis", "reporting"]):
        if s.lower() not in seen:
            seen.add(s.lower())
            pool.append(s)
    while len(pool) < 28:
        pool.append(f"Tool {len(pool)}")
    pool = pool[:32]
    names = ["Core Technical Skills", "Data & Analytics", "Tools & Platforms", "Process & Delivery"]
    cats = [{"name": names[i], "skills": pool[i::4]} for i in range(4)]
    a, b = (jd_keywords + ["data analysis", "reporting"])[:2]
    summary = (f"{job_title} who turns operational data into decisions teams act on. "
               f"Builds {a} and {b} pipelines with validation checks that hold up under audit. "
               f"Recent work cut report turnaround by 80 percent and lifted data accuracy to 98 percent. "
               f"Pairs hands-on analysis with clear handoffs that keep stakeholders moving.")
    return {"skills": cats, "summary": summary}
