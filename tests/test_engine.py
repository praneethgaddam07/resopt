"""End-to-end engine test in mock mode (no API key needed)."""
from app.llm.client import get_client
from app.workflow.engine import run_workflow

RESUME = """Jane Doe
jane@example.com  555-123-4567  linkedin.com/in/janedoe
Data Analyst with 4 years building ETL pipelines and dashboards.
Reduced reporting time by 34% and improved data accuracy to 98%.
Skills: SQL, Python, Tableau, Excel.
Master of Science in Information Technology, State University, 2020.
"""

JD = """We need a Data Analyst skilled in SQL, Python, and Tableau to build
dashboards, run data validation, and automate reporting. SQL and data validation
are required. Experience with Tableau and stakeholder management preferred.
You will own reporting reliability and reduce manual processing.
"""


def test_workflow_mock_end_to_end():
    client = get_client()
    assert client.mock is True  # no key -> mock

    steps = []
    res = run_workflow(
        RESUME, JD, client=client, ats="workday",
        bullet_counts=[5, 3, 2], project_counts=[2, 2],
        progress_cb=lambda s, l: steps.append((s, l)),
    )

    # Structure
    assert res.data["job_title"]
    assert res.data["summary"]
    assert len(res.data["skills"]) == 4
    assert sum(len(c["skills"]) for c in res.data["skills"]) >= 25
    assert len(res.data["experiences"]) == 3
    assert [len(e["bullets"]) for e in res.data["experiences"]] == [5, 3, 2]
    assert all(e.get("bridge_line") for e in res.data["experiences"])

    # Analysis (the deeper workflow phases)
    assert res.analysis["problem"]["problem_statement"]
    assert res.analysis["bridge"]
    assert "reframeable" in res.analysis["gap_analysis"]

    # Report
    assert 0 <= res.report["ats_score"] <= 100
    assert res.report["checklist_total"] > 0
    # Progress callback fired through to completion.
    assert steps[-1][1] == "Done"


def test_amazon_lp_tags_present():
    client = get_client()
    res = run_workflow(RESUME, JD, client=client, ats="amazon",
                       bullet_counts=[3], project_counts=[])
    bullets = res.data["experiences"][0]["bullets"]
    assert all(b.rstrip().endswith(")") for b in bullets)  # LP tag in parentheses


def test_compact_skill_strips_glosses_keeps_acronyms():
    """Skills section bloat fix: drop descriptive parentheticals + proficiency
    qualifiers, keep true acronym expansions for ATS dual-matching."""
    from app.workflow.engine import _compact_skill
    assert _compact_skill("Tableau (interactive dashboard development)") == "Tableau"
    assert _compact_skill("Python (statistical modeling and machine learning)") == "Python"
    assert _compact_skill("PostgreSQL (relational database system)") == "PostgreSQL"
    assert _compact_skill("SQL (Structured Query Language) - advanced") == "SQL (Structured Query Language)"
    assert _compact_skill("ETL (Extract, Transform, Load) pipeline development") == "ETL (Extract, Transform, Load)"
    assert _compact_skill("AWS (Amazon Web Services) cloud infrastructure") == "AWS (Amazon Web Services)"
    assert _compact_skill("JIRA (project tracking)") == "JIRA"
    assert _compact_skill("Snowflake") == "Snowflake"
