"""MCP quality critique tool + the fit-check -> optimize gap loop."""
import json

from mcp_server import check_resume_quality
from app.llm.client import get_client
from app.workflow.engine import run_workflow


def test_check_resume_quality_flags_real_problems():
    bad = {
        "summary": "word " * 80,  # over the 75-word cap
        "experiences": [{"bullets": [
            "Responsible for various things",                             # weak opener + no metric + short
            "Spearheaded synergy initiatives to leverage new approaches",  # banned AI-tells, no metric
        ]}],
        "projects": [],
    }
    out = json.loads(check_resume_quality(bad))
    assert not out["ok"]
    fixes = [f for i in out["bullet_issues"] for f in i["fix"]]
    assert any("weak opener" in f for f in fixes)
    assert any("banned words" in f for f in fixes)
    assert any("no metric" in f for f in fixes)
    assert out["summary_issues"]


def test_check_resume_quality_passes_clean_resume():
    good = {
        "summary": "Analyst who delivered measurable reporting reliability gains.",
        "experiences": [{"bullets": [
            "Built dashboards using SQL that reduced reporting time by 34% for 12 stakeholders monthly",
        ]}],
        "projects": [],
    }
    out = json.loads(check_resume_quality(good))
    assert out["ok"] and out["bullet_issues"] == [] and not out["summary_issues"]


def test_run_workflow_accepts_fix_gaps():
    # FORCE_MOCK=1 (conftest) -> deterministic pipeline; fix_gaps must thread through cleanly.
    client = get_client("")
    res = run_workflow(
        "Jane Doe\njane@x.com\nBuilt dashboards that cut reporting time by 34%.",
        "Data Analyst role needing SQL, Power BI, and reporting automation.",
        client=client,
        fix_gaps=["'Power BI' not shown as an exact match", "  ", None and "x"],
    )
    assert res.data["experiences"] and res.report["ats_score"] >= 0
