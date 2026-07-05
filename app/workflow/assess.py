"""Standalone "Am I qualified?" pre-check — one light LLM call on résumé + JD.

Stateless and BYO-key: inputs live only for the request. It is OPTIONAL and never
blocks optimization — the candidate can read the honest verdict and still choose to
optimize, or skip the check and optimize directly. The verdict distinguishes gaps
résumé optimization CAN fix (wording, exact keywords, surfacing buried experience)
from gaps it CANNOT (genuinely missing years, degree, or core skills).
"""
from __future__ import annotations

from ..llm.client import LLMClient
from ..llm import prompts as P
from .scoring import extract_jd_keywords

_VERDICTS = ("strong_fit", "qualified", "stretch", "not_a_match")
_VERDICT_LABELS = {
    "strong_fit": "Strong fit",
    "qualified": "Qualified",
    "stretch": "Stretch",
    "not_a_match": "Not a match",
}


def assess_qualification(resume_text: str, jd_text: str, *, client: LLMClient) -> dict:
    """Return an honest qualification verdict for this résumé against this JD."""
    ctx = f"MASTER RESUME:\n{resume_text}\n\nJOB DESCRIPTION:\n{jd_text}"
    out = client.complete_json(
        ctx, P.QUALIFY, mock=_mock(jd_text), max_tokens=1800, task_tier="light")
    return _normalize(out)


def _as_int(v, default: int = 0) -> int:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


def _normalize(out: dict) -> dict:
    out = dict(out or {})
    score = max(0, min(100, _as_int(out.get("fit_score"))))
    verdict = str(out.get("verdict") or "").strip().lower()
    if verdict not in _VERDICTS:  # derive from score if the model returned an odd label
        verdict = ("strong_fit" if score >= 80 else "qualified" if score >= 60
                   else "stretch" if score >= 40 else "not_a_match")
    gaps = out.get("gaps") if isinstance(out.get("gaps"), list) else []
    blockers = [g for g in gaps if isinstance(g, dict) and g.get("severity") == "blocker"]
    # Optimization is worth offering unless the only thing standing in the way is a hard,
    # un-fixable blocker (missing years/degree/cert) — in which case we say so plainly.
    optimization_helps = bool(
        any(isinstance(g, dict) and g.get("fixable_by_optimization") for g in gaps)
        or verdict in ("strong_fit", "qualified", "stretch"))
    out.update({
        "verdict": verdict,
        "verdict_label": _VERDICT_LABELS[verdict],
        "fit_score": score,
        "gaps": gaps,
        "has_hard_blocker": bool(blockers),
        "optimization_helps": optimization_helps,
    })
    return out


# --------------------------- mock (no-key dev/tests) ---------------------------

def _mock(jd_text: str) -> dict:
    kw = extract_jd_keywords(jd_text, limit=8) or ["data analysis", "SQL", "reporting"]
    matched = kw[:5]
    missing = kw[5:7]
    return {
        "verdict": "qualified",
        "fit_score": 72,
        "headline": "You meet the core requirements and cover most must-have skills — "
                    "a solid application with a few gaps worth addressing.",
        "experience_years": {"required": "", "candidate": "~3 years", "meets": True},
        "education": {"required": "", "candidate": "Bachelor's degree", "meets": True},
        "hard_requirements": [
            {"requirement": f"Experience with {kw[0]}", "status": "met",
             "evidence": "Demonstrated across recent roles.", "blocker": True},
        ],
        "must_have_skills": {"matched": matched, "missing": missing,
                             "coverage_pct": round(100 * len(matched) / max(1, len(matched) + len(missing)))},
        "nice_to_have_skills": {"matched": kw[5:8], "missing": []},
        "strengths": ["Directly relevant recent experience",
                      "Quantified, results-oriented background"],
        "gaps": [{"gap": f"'{m}' not shown as an exact match", "severity": "minor",
                  "fixable_by_optimization": True} for m in missing],
        "recommendation": "Worth applying. Résumé optimization will help here — it can "
                          "surface and exact-match the keywords you already have a basis "
                          "for. It cannot manufacture skills you don't have, but none of "
                          "your gaps are hard blockers.",
    }
