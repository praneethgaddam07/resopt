"""Background job: run the workflow for one request, in memory, then scrub inputs."""
from __future__ import annotations

import re
import traceback

from .store import store
from .llm.client import LLMClient, get_client
from .workflow.engine import run_workflow
from .ats.portals import get_portal
from .ats.formatter import build_docx_bytes

# Friendly, non-revealing progress (we do NOT expose the internal 16-step process).
_PHASES = {
    1: "Reading your résumé",
    2: "Understanding the role",
    3: "Matching your experience",
    4: "Writing your résumé",
    5: "Scoring against the ATS",
}


def _safe(s: str, default: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", s or "") or default


def process_job(job_id: str) -> None:
    job = store.get(job_id)
    if job is None:
        return
    req = job.request or {}
    try:
        store.update(job_id, status="running", progress_label=_PHASES[1])

        def progress(step: int, _label: str) -> None:
            phase = min(5, max(1, step))  # engine emits 1..6; clamp to the 5 phases
            store.update(job_id, progress_step=phase, progress_label=_PHASES[phase])

        ats = req.get("ats", "generic")
        client: LLMClient = get_client(
            req.get("api_key", ""), req.get("provider", ""),
            economy=bool(req.get("economy")),  # Economy Mode: all-tier1 routing
        )
        result = run_workflow(
            req["resume_text"], req["jd_text"], client=client, ats=ats,
            bullet_counts=req.get("bullet_counts") or None,
            project_counts=req.get("project_counts") or None,
            max_bullets=req.get("max_bullets", 20),
            target_title=req.get("target_title", ""),
            company=job.company,
            confirmed_tools=req.get("confirmed_tools") or None,
            fix_gaps=req.get("fix_gaps") or None,
            progress_cb=progress,
        )

        contact = dict(result.contact)
        for k, v in (req.get("contact_overrides") or {}).items():
            if v:
                contact[k] = v
        # Local Profile overrides extracted education/certs when the user provided them.
        if req.get("profile_education"):
            contact["education"] = req["profile_education"]
        if req.get("profile_certs"):
            contact["certifications"] = req["profile_certs"]

        portal = get_portal(ats)
        docx_bytes = build_docx_bytes(result.data, contact, portal)
        filename = f"{_safe(job.lastname, 'Resume')}_{_safe(job.company, 'Company')}.docx"

        # Only the problem + score + the editable résumé are exposed (no 16-step internals).
        public_result = {
            "job_title": result.data["job_title"],
            "summary": result.data["summary"],
            "skills": result.data["skills"],
            "experiences": result.data["experiences"],
            "projects": result.data["projects"],
            "education": contact.get("education", []),
            "certifications": contact.get("certifications", []),
            "contact": {k: contact.get(k, "") for k in
                        ("name", "phone", "email", "linkedin", "location", "github", "portfolio")},
            "section_order": list(portal.section_order),
            "problem": (result.analysis.get("problem") or {}).get("problem_statement", ""),
            "report": result.report,
            "provider": client.provider if not client.mock else "mock",
        }
        store.update(job_id, status="done", progress_step=5, progress_label="Done",
                     result=public_result, docx=docx_bytes, filename=filename)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        store.update(job_id, status="error", error=f"{type(e).__name__}: {e}")
    finally:
        store.scrub_inputs(job_id)  # drop key + résumé + JD immediately
