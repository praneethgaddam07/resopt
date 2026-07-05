"""Integrity Guardrail — post-generation, pre-formatter validation (stateless).

Runs after the writer (Phase 3) and before formatting. Two deterministic checks,
both backed by Pydantic models for typed data exchange:

  * Metric preservation — no number may appear in a generated bullet unless it
    exists in the candidate's source bullets (no rounding / inflating / inventing).
  * Anti-AI-tell — no banned word ("spearheaded", "synergy", "leverage", …) ships.

Deterministic repair is the GUARANTEE: rather than an LLM regeneration loop that
can still fail, offending bullets are repaired in place so a violation can never
reach the formatter. The full diff is returned for transparency.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from . import anti_ai, metrics


class BulletIssue(BaseModel):
    section: str            # "experience" | "projects"
    index: int
    original: str
    repaired: str
    bad_metrics: list[str] = Field(default_factory=list)   # numbers not in the source
    ai_tells: list[str] = Field(default_factory=list)       # banned words found
    weak_opener: str | None = None


class IntegrityReport(BaseModel):
    ok: bool                       # True if nothing needed repair
    checked: int = 0
    repaired: int = 0
    issues: list[BulletIssue] = Field(default_factory=list)


def enforce(data: dict, source_exp_bullets: list[str],
            source_proj_bullets: list[str]) -> IntegrityReport:
    """Validate + deterministically repair generated bullets in place. Returns the report.

    `source_*_bullets` are the candidate's ORIGINAL (pre-tailoring) bullets — the
    only place a truthful metric can come from.
    """
    allowed = metrics.source_numbers(source_exp_bullets, source_proj_bullets)
    issues: list[BulletIssue] = []
    checked = 0

    def fix(container: list[str], kind: str) -> None:
        nonlocal checked
        for i, b in enumerate(container):
            checked += 1
            bad = metrics.bad_numbers(b, allowed)
            tells = anti_ai.ai_tell_hits(b)
            wk = anti_ai.weak_opener(b)
            if not (bad or tells or wk):
                continue
            fixed = anti_ai.scrub(b)                       # remove banned words / weak opener
            if bad:
                fixed = metrics.strip_unbacked(fixed, allowed)  # drop unbacked numbers
            container[i] = fixed
            issues.append(BulletIssue(section=kind, index=i, original=b, repaired=fixed,
                                      bad_metrics=bad, ai_tells=tells, weak_opener=wk))

    for e in data.get("experiences", []):
        fix(e.setdefault("bullets", []), "experience")
    for p in data.get("projects", []):
        fix(p.setdefault("bullets", []), "projects")

    return IntegrityReport(ok=not issues, checked=checked, repaired=len(issues), issues=issues)
