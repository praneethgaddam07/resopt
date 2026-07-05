"""Confirm-Your-Tools — the human-attestation layer over the taxonomy resolver.

One light LLM call pulls the tool lists from résumé + JD; the resolver maps them to
an honest coverage report (matched / your-tool+category / missing). The UI shows it
and the CANDIDATE ticks any borderline tool they've genuinely used. Those confirmed
tools are then treated as real and fed to the writer — the model never claims a tool
the candidate didn't confirm.
"""
from __future__ import annotations

from ..llm.client import LLMClient
from ..llm import prompts as P
from .scoring import extract_jd_keywords
from .taxonomy_resolver import resolve_coverage, CoverageReport


def tool_coverage(resume_text: str, jd_text: str, *, client: LLMClient,
                  confirmed: list[str] | None = None) -> CoverageReport:
    """Return an honest tool-coverage map. `confirmed` tools (candidate-attested) are
    treated as ones the candidate genuinely has."""
    ctx = f"MASTER RESUME:\n{resume_text}\n\nJOB DESCRIPTION:\n{jd_text}"
    out = client.complete_json(
        ctx, P.EXTRACT_TOOLS, mock=_mock(jd_text), max_tokens=1200, task_tier="light")
    candidate = [t for t in out.get("candidate_tools", []) if t] + list(confirmed or [])
    jd_tools = [t for t in out.get("jd_tools", []) if t]
    return resolve_coverage(candidate, jd_tools)


def _mock(jd_text: str) -> dict:
    jd = extract_jd_keywords(jd_text, limit=10) or ["Salesforce", "Power BI", "SQL", "SAS"]
    return {"candidate_tools": ["Python", "SQL", "Tableau", "HubSpot", "SAS"], "jd_tools": jd}
