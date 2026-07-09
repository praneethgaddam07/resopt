"""The fit-check -> optimize gap loop (app engine).

Note: this file previously also covered the MCP connector's check_resume_quality
tool. The connector was retired when RESOPT consolidated to a single public repo,
so those tests were removed with it — the fix-gaps loop below lives in the app.
"""
from app.llm.client import get_client
from app.workflow.engine import run_workflow


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
