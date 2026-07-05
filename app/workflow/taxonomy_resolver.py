"""Tier-1 (static) taxonomy resolver — truthful 'safe ingestion'.

Maps tools -> functional categories from master_taxonomy.json (shipped in repo).
Given the candidate's REAL tool inventory and the JD's tools, it produces an
honest coverage map so the engine can:

  * MATCHED   — JD tool the candidate genuinely has -> surface it (fixes under-claiming).
  * ADJACENT  — JD tool the candidate lacks but has a same-category real tool
                (JD wants Salesforce, candidate has HubSpot -> category "CRM").
                The engine surfaces the candidate's REAL tool + the category keyword;
                the specific JD tool is offered to the CANDIDATE to confirm, never
                written autonomously.
  * MISSING   — no tool in that category at all -> flagged as a genuine gap.

Deliberately Tier-1 only: NO sentence-transformers (avoids ~400MB of torch in the
desktop app) and NO disk 'self-healing' file (that would break the stateless rule).
All state is in-memory; everything crosses boundaries as Pydantic models.
"""
from __future__ import annotations

import json
import os
import sys
from functools import lru_cache

from pydantic import BaseModel, Field


def _candidate_paths() -> list[str]:
    """Every place master_taxonomy.json might live — source tree AND PyInstaller
    bundles (Windows onefile/onedir, macOS .app puts data under Contents/Resources
    while code is in a bytecode archive, so dirname(__file__) is not enough)."""
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [os.path.join(here, "master_taxonomy.json")]
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        cands += [
            os.path.join(meipass, "app", "workflow", "master_taxonomy.json"),
            os.path.join(meipass, "master_taxonomy.json"),
            os.path.join(meipass, "..", "Resources", "app", "workflow", "master_taxonomy.json"),
        ]
    try:
        exe = os.path.dirname(os.path.abspath(sys.executable))
        cands += [
            os.path.join(exe, "..", "Resources", "app", "workflow", "master_taxonomy.json"),  # mac .app
            os.path.join(exe, "_internal", "app", "workflow", "master_taxonomy.json"),         # win onedir
        ]
    except Exception:
        pass
    return cands


@lru_cache(maxsize=1)
def _load_taxonomy() -> dict[str, list[str]]:
    for p in _candidate_paths():
        try:
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:  # noqa: BLE001
            continue
    return {}  # graceful: resolver degrades to no category-assist rather than crashing


@lru_cache(maxsize=1)
def _tool_to_categories() -> dict[str, set[str]]:
    """Reverse index: lowercased tool name -> set of categories it belongs to."""
    idx: dict[str, set[str]] = {}
    for cat, tools in _load_taxonomy().items():
        for t in tools:
            idx.setdefault(t.lower(), set()).add(cat)
    return idx


def categories_of(tool: str) -> set[str]:
    return _tool_to_categories().get((tool or "").strip().lower(), set())


class AdjacentTool(BaseModel):
    jd_tool: str                       # what the JD asks for (candidate lacks it)
    category: str                      # the shared functional category
    your_tools: list[str] = Field(default_factory=list)  # the candidate's REAL tools in it


class CoverageReport(BaseModel):
    """Honest tool-coverage map for one résumé against one JD."""
    matched: list[str] = Field(default_factory=list)        # surface these (real + JD wants them)
    adjacent: list[AdjacentTool] = Field(default_factory=list)  # surface YOUR tool + category
    missing: list[str] = Field(default_factory=list)        # genuine gaps (confirm or address)

    @property
    def category_keywords(self) -> list[str]:
        """Functional-category keywords the candidate can truthfully claim (from adjacents)."""
        seen, out = set(), []
        for a in self.adjacent:
            if a.category not in seen:
                seen.add(a.category)
                out.append(a.category)
        return out


def resolve_coverage(candidate_tools: list[str], jd_tools: list[str]) -> CoverageReport:
    """Truthful coverage: never invents a tool the candidate doesn't have.

    candidate_tools — the candidate's REAL listed/used tools.
    jd_tools        — tools/skills the JD names.
    """
    cand_lower = {t.strip().lower() for t in candidate_tools if t and t.strip()}
    cand_cats: dict[str, list[str]] = {}  # category -> candidate's real tools in it
    for t in candidate_tools:
        for c in categories_of(t):
            cand_cats.setdefault(c, []).append(t)

    matched, adjacent, missing = [], [], []
    seen = set()
    for jd in jd_tools:
        key = (jd or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        if key in cand_lower:
            matched.append(jd)                       # candidate genuinely has it
            continue
        jd_cats = categories_of(jd)
        real_in_cat = sorted({t for c in jd_cats for t in cand_cats.get(c, [])})
        if jd_cats and real_in_cat:
            cat = next(iter(jd_cats & set(cand_cats)), next(iter(jd_cats)))
            adjacent.append(AdjacentTool(jd_tool=jd, category=cat, your_tools=real_in_cat))
        else:
            missing.append(jd)                       # no honest basis — a real gap
    return CoverageReport(matched=matched, adjacent=adjacent, missing=missing)
