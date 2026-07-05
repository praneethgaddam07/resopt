"""Keyword scoring + checklist."""
from app.workflow.scoring import extract_jd_keywords, build_report, keyword_score
from app.ats.portals import get_portal

JD = """Seeking a Data Analyst with strong SQL, Python, and Tableau. Must do data
validation and automate reporting. SQL is required. Tableau preferred."""


def test_keyword_extraction_skips_generic():
    kws = extract_jd_keywords(JD)
    assert any("sql" in k for k in kws)
    assert "communication" not in kws
    assert "teamwork" not in kws


def test_score_rewards_matching_content():
    good = {
        "job_title": "Data Analyst",
        "summary": "Data Analyst with sql python tableau and data validation reporting.",
        "skills": [{"name": "Core", "skills": ["sql", "python", "tableau", "data validation"]}],
        "experiences": [{"title": "Role", "bullets": ["Automated reporting using sql and tableau by 30%."]}],
        "projects": [], "education": "",
    }
    bad = {
        "job_title": "Generalist", "summary": "A motivated team player.",
        "skills": [{"name": "Core", "skills": ["misc"]}],
        "experiences": [{"title": "Role", "bullets": ["Did various things."]}],
        "projects": [], "education": "",
    }
    assert keyword_score(good, JD)["score"] > keyword_score(bad, JD)["score"]


def test_checklist_flags_missing_metric():
    data = {
        "job_title": "Data Analyst", "summary": "Short summary.",
        "skills": [{"name": "Core", "skills": ["sql"]}],
        "experiences": [{"title": "Role", "bullets": ["Did work with sql without any metric."]}],
        "projects": [], "education": "",
    }
    rep = build_report(data, JD, get_portal("generic"))
    labels = {c["label"]: c["ok"] for c in rep["checklist"]}
    metric_item = next(k for k in labels if "metric" in k.lower())
    assert labels[metric_item] is False
