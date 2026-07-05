"""Scoring accuracy upgrades + quality-gate repair helpers."""
from app.workflow.scoring import (
    keyword_score, build_report, _near_match, _norm_tokens, has_metric_or_artifact,
)
from app.workflow.engine import (
    _trim_to_words, _metricless_indices, _sanitize_symbols, _fit_counts, _attach_meta,
    _auto_distribute, _cap_total, _maximize_coverage,
)
from app.ats.portals import get_portal

JD = "Need SQL, data validation, Power BI, and stakeholder communication for reporting."


def test_near_match_credits_reframes():
    # "validated data" should cover the JD phrase "data validation" (stem + token set).
    assert _near_match("data validation", _norm_tokens("validated data daily"))
    assert not _near_match("power bi", _norm_tokens("tableau dashboards"))


def test_near_miss_vs_exact():
    data = {
        "job_title": "Analyst",
        "summary": "Analyst who validated data and built reporting.",
        "skills": [{"name": "Core", "skills": ["sql"]}],
        "experiences": [{"title": "Role", "bullets": ["Built reporting with sql by 30%."]}],
        "projects": [], "education": "",
    }
    ks = keyword_score(data, JD, jd_keywords=["sql", "data validation", "power bi"])
    assert "sql" in ks["matched"]
    assert "data validation" in ks["near_misses"]   # present but not the exact phrase
    assert "power bi" in ks["missing"]              # truly absent


def test_required_keywords_weighted():
    data = {"job_title": "A", "summary": "uses sql", "skills": [{"name": "C", "skills": ["sql"]}],
            "experiences": [{"title": "R", "bullets": ["Used sql for 30% gain."]}],
            "projects": [], "education": ""}
    # sql (required, present) vs two missing non-required -> required weighting lifts score.
    ks = keyword_score(data, JD, jd_keywords=["sql", "tableau", "spark"], required=["sql"])
    assert ks["required_total"] == 1 and ks["required_matched"] == 1
    assert ks["score"] > 33  # weighted: 2/(2+1+1)=50, not the unweighted 1/3


def test_suggestions_use_gap_reframe():
    data = {"job_title": "A", "summary": "x", "skills": [{"name": "C", "skills": ["x"]}],
            "experiences": [{"title": "R", "bullets": ["Did x by 10%."]}],
            "projects": [], "education": ""}
    diss = {"priority_keywords": ["power bi"], "required": ["power bi"], "preferred": []}
    gap = {"reframeable": [{"candidate_skill": "Tableau", "jd_skill": "Power BI"}]}
    rep = build_report(data, JD, get_portal("generic"), jd_dissection=diss, gap=gap)
    reframe = [s for s in rep["suggestions"] if s["type"] == "reframe"]
    assert reframe and "Tableau" in reframe[0]["text"]
    assert rep["keyword_source"] == "llm"


def test_trim_to_words():
    long = " ".join(f"w{i}" for i in range(90))
    out = _trim_to_words(long, 70)
    assert len(out.split()) == 70 and out.endswith(".")
    assert _trim_to_words("short one.", 70) == "short one."


def test_metricless_indices():
    exps = [{"bullets": ["Built dashboards reducing time by 34%.", "Oversaw routine duties."]}]
    assert _metricless_indices(exps) == [(0, 1)]  # only the bullet with no metric/artifact


def test_artifact_counts_as_outcome():
    assert has_metric_or_artifact("Produced a reusable query library for the team.")
    assert has_metric_or_artifact("Reduced cycle time by 34%.")
    assert not has_metric_or_artifact("Handled various ongoing responsibilities.")


def test_sanitize_strips_forbidden_symbols():
    assert ";" not in _sanitize_symbols("Built X; improved Y")
    assert "_" not in _sanitize_symbols("data_pipeline work")
    assert "#" not in _sanitize_symbols("ranked #1 overall")


def test_fit_counts_truncates_and_pads():
    assert _fit_counts([5, 3, 2], 2) == [5, 3]          # only 2 real jobs -> drop the 3rd slot
    assert _fit_counts([5], 3, default=2) == [5, 2, 2]  # 3 real jobs -> pad with default
    assert _fit_counts([], 0) == []


def test_auto_distribute_caps_and_front_loads():
    for n_exp in range(1, 6):
        for n_proj in range(0, 4):
            exp, proj = _auto_distribute(n_exp, n_proj, hi=20)
            assert len(exp) == n_exp
            assert sum(exp) + sum(proj) <= 20            # never exceeds the cap
            assert all(c >= 1 for c in exp + proj)
            if n_exp >= 2:
                assert exp[0] >= exp[-1]                  # most recent gets >= oldest


def test_auto_distribute_typical_two_jobs_two_projects():
    exp, proj = _auto_distribute(2, 2, hi=20)
    assert exp == [6, 5] and proj == [2, 2]              # 15 total, recency-weighted


def test_cap_total_trims_to_ceiling():
    exp, proj = _cap_total([6, 5, 4, 3], [2, 2, 2], 20)
    assert sum(exp) + sum(proj) <= 20


def test_coverage_injects_only_truthful_keywords():
    data = {"skills": [{"name": "Core", "skills": ["tableau"]}]}
    report = {
        "near_miss_keywords": ["data validation"],     # candidate demonstrates it -> inject
        "missing_keywords": ["power bi", "kubernetes"], # power bi reframeable; kubernetes no basis
    }
    analysis = {"required": ["data validation", "power bi", "kubernetes"],
                "priority_keywords": ["data validation", "power bi", "kubernetes"],
                "reframeable": [{"candidate_skill": "Tableau", "jd_skill": "Power BI"}]}
    changed = _maximize_coverage(data, report, analysis, real_skills=["Tableau", "SQL"])
    all_skills = [s.lower() for c in data["skills"] for s in c["skills"]]
    assert changed is True
    assert "data validation" in all_skills      # near-miss -> injected
    assert "power bi" in all_skills              # reframeable analogue -> injected
    assert "kubernetes" not in all_skills        # no basis -> NOT injected (no fabrication)


def test_attach_meta_uses_real_entries_only():
    # Résumé has 2 real jobs; the tailor step returned 4 -> output must be 2, with
    # real metadata preserved and rephrased bullets/bridge taken from the tailor step.
    real = [{"title": "Senior Analyst", "company": "ACME", "duration": "2021-Present",
             "location": "TX", "bullets": ["orig a"]},
            {"title": "Analyst", "company": "Bank", "duration": "2018-2021",
             "location": "TX", "bullets": ["orig b"]}]
    tailored = [{"bridge_line": "L1", "bullets": ["a.", "a2."]},
                {"bridge_line": "L2", "bullets": ["b."]},
                {"bridge_line": "x", "bullets": ["c."]}]
    out = _attach_meta(real, tailored, [5, 5])
    assert len(out) == 2                          # extras dropped
    assert out[0]["title"] == "Senior Analyst" and out[0]["company"] == "ACME"
    assert out[0]["bullets"] == ["a.", "a2."] and out[0]["bridge_line"] == "L1"
