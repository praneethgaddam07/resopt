"""Tests for the standalone Fit Check (/api/qualify) and Cover Letter (/api/cover-letter)
features. Run under FORCE_MOCK=1 (no real API key needed)."""
import base64

from fastapi.testclient import TestClient

from app.main import app
from app.workflow.assess import _normalize
from app.workflow.cover_letter import cover_letter_text, build_cover_letter_docx

client = TestClient(app)

_BASE = {
    "jd": "Data Analyst. Required: SQL, Python, ETL, reporting. Preferred: Snowflake.",
    "api_key": "sk-ant-test",
    "resume": "Jane Doe\njane@example.com\nData Analyst at Acme\n"
              "- Built SQL pipelines and cut report turnaround 80%",
}


def test_qualify_returns_verdict_and_optimize_signal():
    r = client.post("/api/qualify", data=_BASE)
    assert r.status_code == 200
    res = r.json()["result"]
    assert res["verdict"] in ("strong_fit", "qualified", "stretch", "not_a_match")
    assert res["verdict_label"]
    assert 0 <= res["fit_score"] <= 100
    # The candidate's decision signals are always present.
    assert isinstance(res["optimization_helps"], bool)
    assert isinstance(res["has_hard_blocker"], bool)
    assert "recommendation" in res
    assert "matched" in res["must_have_skills"]


def test_qualify_requires_resume_and_jd():
    assert client.post("/api/qualify", data={"jd": "x", "api_key": "sk-ant-test"}).status_code == 400
    assert client.post("/api/qualify", data={"resume": "x", "api_key": "sk-ant-test"}).status_code == 422  # jd required


def test_cover_letter_returns_text_and_docx():
    r = client.post("/api/cover-letter", data={**_BASE, "company": "Acme",
                                               "name": "Jane Doe", "target_title": "Data Analyst"})
    assert r.status_code == 200
    j = r.json()
    assert j["letter"]["paragraphs"] and len(j["letter"]["paragraphs"]) >= 3
    assert j["text"].startswith("Dear")
    assert j["filename"].endswith("_CoverLetter.docx")
    # docx is a valid, non-trivial ZIP (docx) payload
    raw = base64.b64decode(j["docx_b64"])
    assert raw[:2] == b"PK" and len(raw) > 2000


def test_cover_letter_names_company_but_strips_ai_tells():
    r = client.post("/api/cover-letter", data={**_BASE, "company": "Acme", "name": "Jane Doe"})
    text = r.json()["text"].lower()
    # Cover letters DO name the company (unlike résumés).
    assert "acme" in text or "your team" in text
    # AI-tell words are scrubbed.
    for w in ("delve", "spearhead", "synergy", "leverage", "cutting-edge"):
        assert w not in text


def test_normalize_derives_verdict_from_score_when_label_bad():
    out = _normalize({"fit_score": 85, "verdict": "??", "gaps": []})
    assert out["verdict"] == "strong_fit" and out["verdict_label"] == "Strong fit"
    out2 = _normalize({"fit_score": 20, "gaps": [{"severity": "blocker", "fixable_by_optimization": False}]})
    assert out2["verdict"] == "not_a_match" and out2["has_hard_blocker"] is True
    assert out2["optimization_helps"] is False  # only an un-fixable blocker -> say so


def test_cover_letter_docx_builder_is_self_contained():
    letter = {"greeting": "Dear Hiring Team,", "paragraphs": ["Para one.", "Para two."],
              "closing": "Sincerely,", "signature": "Jane Doe"}
    assert cover_letter_text(letter).startswith("Dear Hiring Team,")
    raw = build_cover_letter_docx(letter, candidate_name="Jane Doe")
    assert raw[:2] == b"PK"


# ---- Formatting / StyleOptions (ATS-safe style controls) ----
from app.ats.formatter import build_docx_bytes, StyleOptions
from app.ats.portals import get_portal

_RES = {
    "job_title": "Data Analyst", "summary": "Data Analyst who ships reliable reporting.",
    "skills": [{"name": "Core", "skills": ["SQL", "Python", "ETL"]}],
    "experiences": [{"title": "Analyst", "company": "Acme", "duration": "2021-2024",
                     "location": "TX", "bridge_line": "maps to role",
                     "bullets": ["Built SQL pipelines cutting turnaround 80%"] * 6}],
    "projects": [{"title": "Fraud Pipeline", "bullets": ["Analyzed 10,000+ claims with SQL"]}],
    "education": [{"degree": "B.S. IS", "school": "UT Dallas", "dates": "2020-2024", "gpa": "3.6"}],
}
_CONTACT = {"name": "Jane Doe", "email": "j@x.com", "linkedin": "linkedin.com/in/j"}


def _docx(style=None):
    return build_docx_bytes(_RES, _CONTACT, get_portal("generic"), style=style)


def test_default_and_custom_style_both_valid_docx():
    assert _docx()[:2] == b"PK"
    custom = {"font": "Georgia", "header_align": "center", "bullet": "–",
              "accent": "1F4E79", "size_name": 20, "education_order": "institution"}
    assert _docx(custom)[:2] == b"PK"


def test_styleoptions_from_dict_clamps_untrusted_input():
    st = StyleOptions.from_dict({"font": "Comic Sans", "size_body": 999,
                                 "header_align": "diagonal", "accent": "zzz", "bullet": "x"})
    assert st.font == "Calibri"          # non-allowlisted font -> safe default
    assert 8 <= st.size_body <= 14       # clamped
    assert st.header_align == "left"     # invalid -> default
    assert st.accent == ""               # invalid hex dropped
    assert st.bullet == "•"


def test_fit_one_page_compacts_margins_for_long_content():
    long = {**_RES, "experiences": [dict(_RES["experiences"][0],
            bullets=["Built SQL pipelines cutting turnaround 80%"] * 8) for _ in range(5)]}
    assert build_docx_bytes(long, _CONTACT, get_portal("generic"),
                            style={"fit_one_page": True})[:2] == b"PK"


# ---- Integrity Guardrail (metric preservation + anti-AI) ----
from app.workflow import validators
from app.workflow.validators import metrics, anti_ai


def test_metric_validator_strips_unbacked_number():
    # source has 18% and 75%; generated invents "92%" -> must be removed
    data = {"experiences": [{"bullets": ["Boosted recoveries 18% and accuracy to 92% reliably"]}],
            "projects": []}
    rep = validators.enforce(data, source_exp_bullets=["increased recoveries by 18%",
                                                       "cut time by 75%"], source_proj_bullets=[])
    assert rep.ok is False and rep.repaired == 1
    out = data["experiences"][0]["bullets"][0]
    assert "18%" in out and "92%" not in out          # real metric kept, invented one gone
    assert rep.issues[0].bad_metrics == ["92"]


def test_anti_ai_filter_removes_banned_word():
    data = {"experiences": [{"bullets": ["Spearheaded synergy across teams to leverage results"]}],
            "projects": []}
    rep = validators.enforce(data, source_exp_bullets=[], source_proj_bullets=[])
    out = data["experiences"][0]["bullets"][0].lower()
    assert rep.repaired == 1
    for w in ("spearhead", "synergy", "leverage"):
        assert w not in out


def test_clean_bullets_pass_unchanged():
    clean = {"experiences": [{"bullets": ["Built SQL pipelines, cutting turnaround by 80%"]}],
             "projects": []}
    rep = validators.enforce(clean, source_exp_bullets=["reduced turnaround by 80% using SQL"],
                             source_proj_bullets=[])
    assert rep.ok is True and rep.repaired == 0
    assert clean["experiences"][0]["bullets"][0] == "Built SQL pipelines, cutting turnaround by 80%"


def test_integrity_report_is_pydantic():
    rep = validators.enforce({"experiences": [], "projects": []}, [], [])
    assert rep.model_dump()["ok"] is True   # Pydantic model for typed exchange
    assert metrics.extract_numbers("up 18% to $1.2M") == {"18", "1.2"}
    assert anti_ai.ai_tell_hits("we will leverage synergy") == ["leverage", "synergy"]


# ---- Taxonomy resolver (truthful tool coverage, any field) ----
from app.workflow.taxonomy_resolver import resolve_coverage


def test_taxonomy_surfaces_real_and_never_invents():
    cand = ["SAS", "R", "Tableau", "Power BI", "SQL", "Python", "HubSpot"]
    jd = ["SAS", "SPSS", "Salesforce", "Photoshop", "Webi"]
    rep = resolve_coverage(cand, jd)
    assert "SAS" in rep.matched                                   # real match surfaced
    sf = next(a for a in rep.adjacent if a.jd_tool == "Salesforce")
    assert sf.category == "CRM" and "HubSpot" in sf.your_tools    # your tool, never "Salesforce"
    assert {"SAS", "R"} & set(next(a for a in rep.adjacent if a.jd_tool == "SPSS").your_tools)
    assert "Photoshop" in rep.missing                            # no basis -> honest gap


def test_taxonomy_no_basis_is_a_gap_not_a_claim():
    rep = resolve_coverage(["Python", "SQL"], ["Salesforce"])
    assert "Salesforce" in rep.missing and rep.adjacent == []


# ---- Confirm-Your-Tools (coverage endpoint + attested tools feed the writer) ----
def test_tool_coverage_endpoint_shape():
    r = client.post("/api/tool-coverage", data={
        "jd": "Data Analyst. Salesforce, Power BI, SQL, SAS.", "api_key": "sk-ant-test",
        "resume": "Analyst — built SQL reports in HubSpot and Tableau"})
    assert r.status_code == 200
    j = r.json()
    assert "matched" in j and "adjacent" in j and "missing" in j
    # adjacent entries carry the candidate's real tool + category, never the JD tool itself
    for a in j["adjacent"]:
        assert "jd_tool" in a and "category" in a and "your_tools" in a


def test_optimize_accepts_confirmed_tools():
    r = client.post("/api/jobs", data={
        "jd": "Data Analyst. Salesforce, SQL.", "api_key": "sk-ant-test",
        "resume": "Analyst — SQL reports in HubSpot, cut time 80%",
        "company": "Acme", "lastname": "Doe", "confirmed_tools": "Salesforce, Power BI"})
    assert r.status_code == 200 and r.json()["status"] == "queued"


def test_confirmed_tools_reach_the_writer_inventory():
    # confirmed tools are merged into the real skill inventory passed to TAILOR
    from app.workflow import engine
    import inspect
    src = inspect.getsource(engine.run_workflow)
    assert "confirmed_tools" in src


# ---- Local Profile (GitHub/portfolio + education/certs override) ----
import io as _io, json as _json, time as _time
import docx


def test_contact_renders_github_and_portfolio():
    raw = build_docx_bytes(_RES, {**_CONTACT, "github": "github.com/jane", "portfolio": "jane.dev"},
                           get_portal("generic"))
    text = "\n".join(p.text for p in docx.Document(_io.BytesIO(raw)).paragraphs)
    assert "github.com/jane" in text and "jane.dev" in text


def test_profile_fields_flow_into_resume():
    r = client.post("/api/jobs", data={
        "jd": "Data Analyst. SQL.", "api_key": "sk-ant-test",
        "resume": "Jane\nAnalyst\n- Built SQL reports, cut time 80%",
        "company": "Acme", "lastname": "Doe", "name": "Jane Doe",
        "github": "github.com/jane", "portfolio": "jane.dev",
        "education_json": _json.dumps([{"degree": "B.S. CS", "school": "UT Dallas", "dates": "2020-2024", "gpa": "3.6"}]),
        "certs_json": _json.dumps([{"name": "AWS SAA", "issuer": "Amazon", "url": "credly.com/x"}])})
    jid = r.json()["id"]
    for _ in range(80):
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("done", "error"):
            break
        _time.sleep(0.02)
    res = j["result"]
    assert res["contact"]["github"] == "github.com/jane" and res["contact"]["portfolio"] == "jane.dev"
    assert res["education"][0]["school"] == "UT Dallas"          # profile overrides extraction
    assert res["certifications"][0]["name"] == "AWS SAA"


def test_contact_urls_are_clickable_hyperlinks():
    import zipfile
    raw = build_docx_bytes(_RES, {**_CONTACT, "linkedin": "linkedin.com/in/jane",
                                   "github": "github.com/jane", "email": "jane@x.com"},
                           get_portal("generic"))
    z = zipfile.ZipFile(_io.BytesIO(raw))
    rels = z.read("word/_rels/document.xml.rels").decode()
    assert "https://linkedin.com/in/jane" in rels and "https://github.com/jane" in rels
    assert "mailto:jane@x.com" in rels                                    # email -> mailto
    assert z.read("word/document.xml").decode().count("<w:hyperlink") >= 3  # clickable


def test_clean_text_strips_pdf_separators():
    """Regression: PDF text with U+2028/U+2029/BOM crashed the provider HTTP layer
    (the "ascii codec cannot encode \\u2028" error). Both copies of the sanitizer
    must strip them while preserving accents, tabs, and spaces."""
    from app.workflow.extract import clean_text
    from app.llm.client import _clean_text

    raw = "Line one\u2028Line two\u2029Para\ufeff bom, accent \u00e9, tab\there"
    for fn in (clean_text, _clean_text):
        out = fn(raw)
        assert "\u2028" not in out and "\u2029" not in out and "\ufeff" not in out
        assert "\u00e9" in out               # accents preserved
        assert "\t" in out and " " in out     # whitespace preserved
        assert out.count("\n") >= 2           # separators became newlines\n


def test_clean_key_strips_paste_artifacts():
    """Regression: a U+2028 (or BOM/whitespace) in a pasted API key crashed the request
    with 'ascii codec can't encode \\u2028 in position 108' (the key goes in an ASCII
    header). _clean_key must strip it while leaving a valid key."""
    from app.llm.client import _clean_key
    bad = "sk-ant-api03-" + ("a" * 95) + chr(0x2028)
    out = _clean_key(bad)
    assert chr(0x2028) not in out
    assert out == "sk-ant-api03-" + ("a" * 95)
    assert _clean_key("  sk-ant-xyz\n") == "sk-ant-xyz"
