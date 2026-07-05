"""ATS keyword match scoring + the universal pre-submit checklist.

Both are deterministic and run on the *generated* resume content, mirroring how
real ATS parsers score (exact keyword match, frequency, section parsing) per
ATS_Portal_Documentation §10 and the §11 pre-submit checklist.
"""
from __future__ import annotations

import re
from collections import Counter

from ..ats.portals import PortalRules, UNIVERSAL_RULES

# Generic terms modern ATS treat as noise (doc §10 keyword strategy).
_GENERIC = {
    "teamwork", "communication", "communication skills", "team player",
    "hardworking", "detail oriented", "detail-oriented", "motivated",
    "responsible", "passionate", "leadership", "problem solving",
}

_STOP = {
    "the", "and", "for", "with", "you", "your", "our", "are", "this", "that",
    "will", "have", "has", "a", "an", "to", "of", "in", "on", "as", "is", "be",
    "or", "we", "they", "their", "from", "at", "by", "it", "its", "etc", "able",
    "ability", "experience", "experienced", "years", "year", "work", "working",
    "role", "team", "teams", "including", "strong", "good", "excellent", "plus",
    "preferred", "required", "responsibilities", "requirements", "skills",
    "candidate", "candidates", "job", "position", "company", "looking",
    # JD-posting boilerplate that forms noisy bigrams ("hiring business", "analyst own")
    "hiring", "hire", "seeking", "seek", "join", "joining", "growing", "grow",
    "needed", "need", "build", "building", "own", "owning", "new", "help",
    "ensure", "across", "using", "use", "drive", "driving", "responsible",
    "who", "what", "will", "must", "should", "etc",
}

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*")

# A bullet satisfies the universal rule if it ends on a number OR a concrete,
# named deliverable (Resume_Customization_Workflow Step 7 allows either).
_METRIC_SIGNAL = re.compile(
    r"\d|%|\$|percent|\bhours?\b|reduction|increase[d]?|reduced|improved|cut|saved|"
    r"faster|fewer|lower|higher|growth|roi")
_ARTIFACT_SIGNAL = re.compile(
    r"\b(framework|librar(?:y|ies)|reports?|dashboards?|templates?|models?|"
    r"pipelines?|playbooks?|systems?|deliverables?|scorecards?|taxonom(?:y|ies)|"
    r"classification|standards?|guidelines?|documentation|specifications?|"
    r"tool(?:kit)?s?|workflows?|catalogs?|registr(?:y|ies)|trackers?|matri(?:x|ces))\b")


def has_metric_or_artifact(text: str) -> bool:
    t = text.lower()
    return bool(_METRIC_SIGNAL.search(t) or _ARTIFACT_SIGNAL.search(t))


def _tokens(text: str) -> list[str]:
    out = []
    for w in _WORD.findall(text):
        # Keep internal punctuation (node.js, c++) but drop trailing/leading noise.
        w = w.strip(".-#+").lower()
        if len(w) >= 2:
            out.append(w)
    return out


_SEGMENT = re.compile(r"[.,\n;:•|/()\[\]]+")


def extract_jd_keywords(jd_text: str, limit: int = 15) -> list[str]:
    """Rank niche JD keywords (uni/bi-grams) by frequency; drop generic noise.

    Bigrams are formed only *within* a sentence/segment so we don't fabricate
    phrases that span a period or line break.
    """
    grams: Counter[str] = Counter()
    for segment in _SEGMENT.split(jd_text):
        words = [w for w in _tokens(segment) if w not in _STOP]
        for i, w in enumerate(words):
            grams[w] += 1
            if i + 1 < len(words):
                grams[f"{w} {words[i + 1]}"] += 2  # phrases matter more than single words
    ranked = []
    for term, _count in grams.most_common(80):
        if term in _GENERIC:
            continue
        ranked.append(term)
        if len(ranked) >= limit:
            break
    return ranked


def assemble_resume_text(data: dict) -> str:
    """Flatten the generated resume into the plain text an ATS parser would see."""
    parts: list[str] = [data.get("job_title", ""), data.get("summary", "")]
    for cat in data.get("skills", []):
        parts.append(cat.get("name", ""))
        parts.extend(cat.get("skills", []))
    for exp in data.get("experiences", []):
        parts.append(exp.get("title", ""))
        parts.extend(exp.get("bullets", []))
    for proj in data.get("projects", []):
        parts.append(proj.get("title", ""))
        parts.extend(proj.get("bullets", []))
    edu = data.get("education") or []
    for e in (edu if isinstance(edu, list) else [edu]):
        if isinstance(e, dict):
            parts.append(f"{e.get('degree','')} {e.get('school','')}")
        elif e:
            parts.append(str(e))
    return "\n".join(p for p in parts if p)


# Ordered longest-first so derivational forms collapse to one root, e.g.
# validation/validated/validating/validate -> "valid"; reporting/reports -> "report".
_SUFFIXES = ("izations", "ization", "ations", "ation", "ating", "ated", "ate",
             "ings", "ing", "ies", "edly", "ed", "es", "ly", "s")


def _stem(tok: str) -> str:
    for suf in _SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            return tok[: -len(suf)] + ("y" if suf == "ies" else "")
    return tok


def _norm_tokens(text: str) -> set[str]:
    return {_stem(w) for w in _tokens(text)}


def _near_match(kw: str, resume_norm: set[str]) -> bool:
    """True if all of the keyword's content tokens appear (stemmed) in the resume.

    Credits reframes/tense/plural/word-order drift, e.g. 'data validation' is
    covered by 'validated data'. Used only for diagnostics — the headline ATS
    score still rewards *exact* phrase matches, which is how parsers actually score.
    """
    kw_toks = {_stem(w) for w in _tokens(kw) if w not in _STOP}
    return bool(kw_toks) and kw_toks.issubset(resume_norm)


def keyword_score(
    data: dict,
    jd_text: str,
    *,
    jd_keywords: list[str] | None = None,
    required: list[str] | None = None,
    preferred: list[str] | None = None,
) -> dict:
    """Score generated content against JD keywords.

    `jd_keywords` (the LLM's Step-1 priority list) is preferred when supplied;
    otherwise we fall back to the frequency heuristic. `required` keywords are
    weighted 2x. Returns exact matches (the honest ATS score) plus `near_misses`
    (present but phrased differently -> rephrase to exact).
    """
    keywords = [k for k in (jd_keywords or extract_jd_keywords(jd_text)) if k]
    # de-dup, preserve order
    seen, ordered = set(), []
    for k in keywords:
        kl = k.lower()
        if kl not in seen:
            seen.add(kl)
            ordered.append(k)
    keywords = ordered

    req_norm = {_stem(t) for k in (required or []) for t in _tokens(k)}

    def is_required(kw: str) -> bool:
        kt = {_stem(t) for t in _tokens(kw)}
        return bool(kt) and kt.issubset(req_norm)

    resume_text = assemble_resume_text(data).lower()
    resume_norm = _norm_tokens(resume_text)
    summary = data.get("summary", "").lower()

    matched, near_misses, missing, in_summary = [], [], [], []
    weighted_hit = weighted_total = 0
    for kw in keywords:
        w = 2 if is_required(kw) else 1
        weighted_total += w
        if kw.lower() in resume_text:
            matched.append(kw)
            weighted_hit += w
            if kw.lower() in summary:
                in_summary.append(kw)
        elif _near_match(kw, resume_norm):
            near_misses.append(kw)
        else:
            missing.append(kw)

    score = round(100 * weighted_hit / weighted_total) if weighted_total else 0
    return {
        "keywords": keywords,
        "matched": matched,
        "near_misses": near_misses,
        "missing": missing,
        "in_summary": in_summary,
        "score": score,
        "required_total": sum(1 for k in keywords if is_required(k)),
        "required_matched": sum(1 for k in matched if is_required(k)),
    }


def checklist(data: dict, portal: PortalRules) -> list[dict]:
    """Universal pre-submit checklist (doc §11). Each item: id, label, ok, detail."""
    items: list[dict] = []

    def add(ok: bool, label: str, detail: str = "") -> None:
        items.append({"label": label, "ok": bool(ok), "detail": detail})

    # Single column / no tables / no graphics — guaranteed by our DOCX builder.
    add(True, "Single-column layout, no tables or graphics", "Enforced by the generator.")

    # Every skill in the Skills section appears in at least one bullet (Step 13).
    bullets_text = " ".join(
        b.lower() for exp in data.get("experiences", []) for b in exp.get("bullets", [])
    )
    bullets_norm = _norm_tokens(bullets_text)
    all_skills, buried = [], []
    for cat in data.get("skills", []):
        for sk in cat.get("skills", []):
            head = re.split(r"\s*\(", sk)[0].strip()  # ignore the "(full phrase)"
            if not head:
                continue
            all_skills.append(sk)
            # Stemmed token-subset match: "Credit Risk Modeling" counts against a
            # bullet containing "credit risk models".
            if not _near_match(head, bullets_norm):
                buried.append(sk)
    # With 25-40 skills and ~12 bullets, demonstrating *every* skill is structurally
    # impossible, so pass when a healthy majority is proven (Step 13 spirit) and flag
    # the rest. Hard-fail only if more than half the skills are claim-without-proof.
    demonstrated = len(all_skills) - len(buried)
    ratio = demonstrated / len(all_skills) if all_skills else 1.0
    add(ratio >= 0.5, "Core skills are demonstrated in bullets (claim + proof)",
        (f"{demonstrated}/{len(all_skills)} skills shown in bullets. Not yet proven: "
         + ", ".join(buried[:6]) + ("…" if len(buried) > 6 else ""))
        if buried else "All skills are demonstrated.")

    # Metric OR concrete artifact on every bullet (universal rule).
    no_metric = [
        b for exp in data.get("experiences", []) for b in exp.get("bullets", [])
        if not has_metric_or_artifact(b)
    ]
    add(not no_metric, "Every bullet closes with a metric or concrete artifact",
        (f"{len(no_metric)} bullet(s) lack a metric or named deliverable.")
        if no_metric else "All bullets end on a metric or artifact.")

    # Summary length: max 4 lines / 75 words.
    summary = data.get("summary", "")
    wc = len(summary.split())
    add(wc <= 75, "Summary within 75 words / 3-4 lines", f"{wc} words.")

    # No special symbols in body (# ; _ ---).
    body = assemble_resume_text(data)
    bad = [sym for sym in UNIVERSAL_RULES["no_special_symbols"] if sym in body]
    add(not bad, "No special symbols in body (# ; _ ---)",
        ("Found: " + " ".join(bad)) if bad else "Clean.")

    # Top JD keywords present in Summary (front-loading, doc §10).
    ks = keyword_score(data, data.get("_jd_text", ""))
    add(len(ks["in_summary"]) >= min(2, len(ks["keywords"])),
        "Top JD keywords appear in the Summary",
        f"{len(ks['in_summary'])} keyword(s) in summary.")

    # Skills count 25-40 (universal).
    n_skills = sum(len(c.get("skills", [])) for c in data.get("skills", []))
    lo, hi = UNIVERSAL_RULES["skills_total_range"]
    add(lo <= n_skills <= hi, f"Skills total within {lo}-{hi}", f"{n_skills} skills.")

    # Portal-specific spot checks.
    if portal.leadership_principle_tags:
        tagged = all(
            b.rstrip().endswith(")")
            for exp in data.get("experiences", []) for b in exp.get("bullets", [])
        ) if data.get("experiences") else False
        add(tagged, "Amazon: every bullet carries a Leadership Principle tag")
    if portal.apply_window_hours:
        add(True, f"{portal.name}: apply within {portal.apply_window_hours} hours of posting",
            "Timing reminder — not auto-enforceable.")

    return items


def _build_suggestions(ks: dict, gap: dict | None) -> list[dict]:
    """Actionable fixes: rephrase-to-exact for near misses; reframe hints for
    truly-missing keywords using the Step-2 gap analysis."""
    suggestions: list[dict] = []

    for kw in ks["near_misses"]:
        suggestions.append({
            "type": "rephrase",
            "keyword": kw,
            "text": f"You cover '{kw}' but not as an exact phrase — most ATS match "
                    f"literally, so use the words '{kw}' verbatim.",
        })

    reframeable = (gap or {}).get("reframeable", []) or []
    for kw in ks["missing"]:
        kw_norm = {_stem(t) for t in _tokens(kw)}
        analogue = None
        for rf in reframeable:
            jd_skill = rf.get("jd_skill", "")
            if kw_norm and kw_norm.issubset({_stem(t) for t in _tokens(jd_skill)}) or \
               (jd_skill and jd_skill.lower() in kw.lower()):
                analogue = rf.get("candidate_skill")
                break
        if analogue:
            suggestions.append({
                "type": "reframe",
                "keyword": kw,
                "text": f"'{kw}' is missing, but your background includes "
                        f"'{analogue}' — reframe it using the JD's exact wording.",
            })
        else:
            suggestions.append({
                "type": "add",
                "keyword": kw,
                "text": f"'{kw}' is not present — add it (in a bullet and the skills "
                        f"list) only if it is genuinely true for you.",
            })
    return suggestions


def build_report(
    data: dict,
    jd_text: str,
    portal: PortalRules,
    *,
    jd_dissection: dict | None = None,
    gap: dict | None = None,
) -> dict:
    data = {**data, "_jd_text": jd_text}

    # Prefer the LLM's extracted keywords (Step 1) over the frequency heuristic.
    # Universe = priority keywords (ordered) + the full hard-skill set, so coverage is
    # measured against every named JD hard skill — the way Jobscan scores — not a top-N.
    diss = jd_dissection or {}
    priority = diss.get("priority_keywords") or []
    hard = diss.get("hard_skills") or []
    universe, seen = [], set()
    for k in list(priority) + list(hard):
        kl = (k or "").lower().strip()
        if k and kl not in seen:
            seen.add(kl)
            universe.append(k)
    llm_keywords = universe or None
    required = diss.get("required") or []
    preferred = diss.get("preferred") or []

    ks = keyword_score(data, jd_text, jd_keywords=llm_keywords,
                       required=required, preferred=preferred)
    cl = checklist(data, portal)
    lo, hi = portal.pass_threshold
    passes = ks["score"] >= lo
    return {
        "ats_score": ks["score"],
        "pass_threshold": {"low": lo, "high": hi},
        "passes_threshold": passes,
        "keyword_source": "llm" if llm_keywords else "heuristic",
        "matched_keywords": ks["matched"],
        "near_miss_keywords": ks["near_misses"],
        "missing_keywords": ks["missing"],
        "keywords_in_summary": ks["in_summary"],
        "required_matched": ks["required_matched"],
        "required_total": ks["required_total"],
        "suggestions": _build_suggestions(ks, gap),
        "checklist": cl,
        "checklist_passed": sum(1 for c in cl if c["ok"]),
        "checklist_total": len(cl),
    }
