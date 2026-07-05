"""API flow: submit -> poll -> download, plus the stateless /api/render editor path.
Runs in FORCE_MOCK mode (no real key)."""
import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

JD = ("Data Analyst needed with SQL, Python, Tableau. Build dashboards, do data "
      "validation, automate reporting. SQL required; Tableau preferred.")
RESUME = ("Jane Doe\njane@example.com 555-1234 linkedin.com/in/janedoe\n"
          "Data Analyst, 4 yrs. Reduced reporting time 34%. SQL, Python, Tableau.\n"
          "Master of Science in Information Technology, State University.")


def test_health_and_portals():
    h = client.get("/api/health").json()
    assert h["status"] == "ok"
    assert h["retention"] == "none"
    assert "anthropic" in h["providers"]
    assert any(p["key"] == "workday" for p in client.get("/api/ats").json()["portals"])


def test_requires_api_key():
    r = client.post("/api/jobs", data={"jd": JD, "resume": RESUME})
    assert r.status_code == 422  # api_key is required


def test_rejects_bad_key():
    r = client.post("/api/jobs", data={"jd": JD, "resume": RESUME, "api_key": "not-a-key"})
    assert r.status_code == 400


def test_submit_poll_download_and_render():
    r = client.post("/api/jobs", data={
        "jd": JD, "resume": RESUME, "api_key": "sk-ant-testkey", "ats": "workday",
        "company": "Acme", "lastname": "Doe", "target_title": "Data Analyst",
    })
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]

    status, j = None, None
    deadline = time.time() + 20
    while time.time() < deadline:
        j = client.get(f"/api/jobs/{job_id}").json()
        status = j["status"]
        if status in ("done", "error"):
            break
        time.sleep(0.3)
    assert status == "done", j

    res = j["result"]
    assert res["report"]["ats_score"] >= 0
    assert res["problem"]                              # the one internal thing we expose
    assert "16" not in str(res).lower() or "step" not in str(res).lower()  # internals hidden
    assert isinstance(res["education"], list)
    assert j["filename"] == "Doe_Acme.docx"

    dl = client.get(f"/api/jobs/{job_id}/download")
    assert dl.status_code == 200 and dl.content[:2] == b"PK"

    # Editor re-render: reorder sections + tweak, get a fresh docx, no LLM/storage.
    order = list(reversed(res["section_order"]))
    rr = client.post("/api/render", json={
        "ats": "workday", "company": "Acme", "lastname": "Doe",
        "section_order": order, "contact": res["contact"], "data": {
            "job_title": res["job_title"], "summary": "Edited summary.",
            "skills": res["skills"], "experiences": res["experiences"],
            "projects": res["projects"], "education": res["education"],
            "certifications": res["certifications"],
        },
    })
    assert rr.status_code == 200 and rr.content[:2] == b"PK"
