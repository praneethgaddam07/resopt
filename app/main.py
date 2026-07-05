"""FastAPI app: stateless, bring-your-own-key résumé optimizer.

Privacy: the API key + résumé + JD are held only in memory for the duration of a
job and scrubbed immediately after. Nothing is written to disk or a database.
"""
from __future__ import annotations

import json
import os

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Depends
from fastapi.responses import Response, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .store import store
from .queue import enqueue, mode as queue_mode
from .ats.portals import list_portals, get_portal
from .ats.formatter import build_docx_bytes
from .workflow.extract import extract_text_from_file, regex_contact
from .workflow.assess import assess_qualification
from .workflow.cover_letter import (
    generate_cover_letter, cover_letter_text, build_cover_letter_docx)
from .workflow.tool_check import tool_coverage
from .llm.client import detect_provider, PROVIDER_LABELS, get_client
from .ratelimit import rate_limit
from . import hub_db

hub_db.init_db()


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

app = FastAPI(title="Resume Optimizer", version="1.0.0")

from pydantic import BaseModel
class HubJob(BaseModel):
    title: str
    company: str
    url: str
    jd_text: str
    ats_id: str
    score: int = 0

@app.post("/api/hub/add")
async def hub_add(job: HubJob):
    job_id = hub_db.add_job(
        title=job.title,
        company=job.company,
        url=job.url,
        jd_text=job.jd_text,
        ats_id=job.ats_id,
        score=job.score
    )
    return {"status": "ok", "job_id": job_id}

@app.get("/api/hub/jobs")
async def get_hub_jobs():
    return hub_db.get_jobs()

@app.delete("/api/hub/delete/{job_id}")
async def delete_hub_job(job_id: int):
    hub_db.delete_job(job_id)
    return {"status": "ok"}

@app.post("/api/hub/optimize/{job_id}")
async def hub_mark_optimized(job_id: int):
    hub_db.mark_optimized(job_id)
    return {"status": "ok"}

# --- Input-size guards: cap the memory / DoS window on the file + text endpoints ---
MAX_UPLOAD_BYTES = int(os.environ.get("RESOPT_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))    # 5 MB/file
MAX_REQUEST_BYTES = int(os.environ.get("RESOPT_MAX_REQUEST_BYTES", str(8 * 1024 * 1024)))  # 8 MB total
MAX_TEXT_CHARS = int(os.environ.get("RESOPT_MAX_TEXT_CHARS", str(200_000)))                # pasted text


@app.middleware("http")
async def _limit_request_body(request: Request, call_next):
    """Reject oversized requests early (honest Content-Length) before the body is parsed."""
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_REQUEST_BYTES:
        return JSONResponse({"detail": "Request too large."}, status_code=413)
    return await call_next(request)


# --- Browser-extension bridge -----------------------------------------------------
# The RESOPT Chrome extension's side panel runs at a chrome-extension:// origin and
# calls this engine on 127.0.0.1. Reflect ANY chrome-extension origin (never a website,
# so no site can reach the local engine), and answer Chrome's Private Network Access
# preflight so a browser-context request to localhost is permitted.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^chrome-extension://[a-z0-9]+$",
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=600,
)


@app.middleware("http")
async def _allow_private_network(request: Request, call_next):
    """Grant Chrome's Private Network Access preflight (localhost is a 'private' target)."""
    resp = await call_next(request)
    if request.method == "OPTIONS" and \
            request.headers.get("access-control-request-private-network") == "true":
        resp.headers["Access-Control-Allow-Private-Network"] = "true"
    return resp


async def _read_upload(f: UploadFile) -> bytes:
    """Read an upload with a hard byte cap so a huge/malicious file can't exhaust memory."""
    data = await f.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File too large. Max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    return data


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/health")
def health():
    return {"status": "ok", "queue": queue_mode(), "providers": PROVIDER_LABELS,
            "retention": "none"}


@app.get("/api/ping")
def ping():
    """Liveness probe for the browser extension — is the local engine running?
    The side panel calls this on open to pick State A (engine live) vs State C."""
    return {"ok": True, "app": "resopt", "version": __version__}


@app.get("/api/ats")
def ats_portals():
    return {"portals": list_portals()}


def _parse_counts(raw: str) -> list[int]:
    if not raw:
        return []
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        return []


async def _resolve_inputs(api_key: str, provider: str, resume: str,
                          resume_file: UploadFile | None, jd: str) -> tuple[str, str]:
    """Validate key/provider + get résumé text (paste or file). Raises HTTPException.

    Shared by the optimize, qualify, and cover-letter endpoints. The key + texts are
    used only within the request and never stored.
    """
    if not api_key.strip():
        raise HTTPException(400, "Enter your AI provider API key.")
    if len(jd) > MAX_TEXT_CHARS or len(resume or "") > MAX_TEXT_CHARS:
        raise HTTPException(413, "Input text too large.")
    prov = provider or detect_provider(api_key)
    if prov not in PROVIDER_LABELS:
        raise HTTPException(400, "Unrecognized API key. Use an Anthropic (sk-ant-…), "
                                 "OpenAI (sk-…), Gemini (AIza… or AQ…), Groq (gsk_…), "
                                 "or Perplexity (pplx-…) key.")
    if resume_file is not None and resume_file.filename:
        resume_text = extract_text_from_file(resume_file.filename, await _read_upload(resume_file))
    else:
        resume_text = resume
    if not resume_text.strip():
        raise HTTPException(400, "Provide a résumé file or paste résumé text.")
    if not jd.strip():
        raise HTTPException(400, "Provide a job description.")
    return prov, resume_text


def _safe(s: str, default: str) -> str:
    return ("".join(c for c in (s or "") if c.isalnum()) or default)


@app.post("/api/jobs", dependencies=[Depends(rate_limit)])
async def create_job(
    jd: str = Form(...),
    api_key: str = Form(...),
    provider: str = Form(""),
    resume: str = Form(""),
    resume_file: UploadFile | None = File(None),
    ats: str = Form("generic"),
    max_bullets: int = Form(20),
    company: str = Form("Company"),
    lastname: str = Form("Resume"),
    target_title: str = Form(""),
    economy: bool = Form(False),
    confirmed_tools: str = Form(""),
    fix_gaps_json: str = Form(""),  # fixable gaps carried over from the fit check
    name: str = Form(""), phone: str = Form(""), email: str = Form(""),
    linkedin: str = Form(""), location: str = Form(""),
    github: str = Form(""), portfolio: str = Form(""),
    education_json: str = Form(""), certs_json: str = Form(""),  # from the local Profile
):
    prov, resume_text = await _resolve_inputs(api_key, provider, resume, resume_file, jd)

    overrides = {k: v for k, v in {"name": name, "phone": phone, "email": email,
                                   "linkedin": linkedin, "location": location,
                                   "github": github, "portfolio": portfolio}.items() if v.strip()}

    def _json_list(raw: str) -> list:
        try:
            v = json.loads(raw) if raw.strip() else []
            return v if isinstance(v, list) else []
        except (ValueError, TypeError):
            return []
    job = store.create(
        company=company, lastname=lastname,
        request={
            "resume_text": resume_text, "jd_text": jd,
            "api_key": api_key, "provider": prov, "ats": ats,
            "bullet_counts": _parse_counts(""), "project_counts": _parse_counts(""),
            "max_bullets": max(6, min(max_bullets, 24)),
            "target_title": target_title, "contact_overrides": overrides,
            "economy": economy,  # True = Economy Mode (all-tier1); False = Precision Mode
            "confirmed_tools": [t.strip() for t in confirmed_tools.split(",") if t.strip()],
            "fix_gaps": [g for g in _json_list(fix_gaps_json) if isinstance(g, str)][:6],
            "profile_education": _json_list(education_json),  # from local Profile (overrides extraction)
            "profile_certs": _json_list(certs_json),
        },
    )
    enqueue(job.id)
    return {"id": job.id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found or expired")
    return JSONResponse(job.public_dict())


@app.get("/api/jobs/{job_id}/download")
def download(job_id: str):
    job = store.get(job_id)
    if job is None or job.status != "done":
        raise HTTPException(404, "Result not ready or expired")
    docx = store.get_result_docx(job_id)
    if not docx:
        raise HTTPException(404, "Result not ready or expired")
    return Response(docx, media_type=DOCX_MIME, headers={
        "Content-Disposition": f'attachment; filename="{job.filename or "resume.docx"}"'})


@app.post("/api/render")
async def render(request: Request):
    """Rebuild the document from user-edited content + section order. No LLM, no
    storage. `fmt`: "docx" (default — best for ATS parsing) or "pdf" (text-based,
    same layout — the human-facing copy)."""
    body = await request.json()
    data = body.get("data") or {}
    contact = body.get("contact") or {}
    portal = get_portal(body.get("ats", "generic"))
    order = body.get("section_order") or list(portal.section_order)
    fmt = "pdf" if str(body.get("fmt", "")).lower() == "pdf" else "docx"
    base = f"{_safe(body.get('lastname'), 'Resume')}_{_safe(body.get('company'), 'Company')}"
    if fmt == "pdf":
        from .ats.pdf_formatter import build_pdf_bytes
        blob, mime = build_pdf_bytes(data, contact, portal, section_order=order,
                                     style=body.get("style")), "application/pdf"
    else:
        blob, mime = build_docx_bytes(data, contact, portal, section_order=order,
                                      style=body.get("style")), DOCX_MIME
    return Response(blob, media_type=mime, headers={
        "Content-Disposition": f'attachment; filename="{base}.{fmt}"'})


@app.post("/api/qualify", dependencies=[Depends(rate_limit)])
async def qualify(
    jd: str = Form(...),
    api_key: str = Form(...),
    provider: str = Form(""),
    resume: str = Form(""),
    resume_file: UploadFile | None = File(None),
    economy: bool = Form(False),
):
    """Optional 'Am I qualified?' pre-check. Synchronous, one light call, then the key
    + texts are discarded with the request. Never blocks optimization."""
    prov, resume_text = await _resolve_inputs(api_key, provider, resume, resume_file, jd)
    client = get_client(api_key, prov, economy=economy)
    result = assess_qualification(resume_text, jd, client=client)
    return {"result": result, "provider": client.provider if not client.mock else "mock"}


@app.post("/api/extract-resume", dependencies=[Depends(rate_limit)])
async def extract_resume(resume_file: UploadFile = File(...)):
    """Extract plain text from an uploaded résumé (PDF/DOCX/TXT). No AI, no key,
    nothing stored — returns the text so the client keeps it on their own device."""
    if not resume_file.filename:
        raise HTTPException(400, "No file provided.")
    text = extract_text_from_file(resume_file.filename, await _read_upload(resume_file))
    if not text.strip():
        raise HTTPException(400, "Couldn't read any text from that file.")
    return {"filename": resume_file.filename, "text": text}


@app.post("/api/tool-coverage", dependencies=[Depends(rate_limit)])
async def tool_coverage_endpoint(
    jd: str = Form(...),
    api_key: str = Form(...),
    provider: str = Form(""),
    resume: str = Form(""),
    resume_file: UploadFile | None = File(None),
    economy: bool = Form(False),
):
    """Confirm-Your-Tools: honest tool coverage (matched / your-tool+category / gaps).
    Synchronous, one light call. The candidate ticks attested tools client-side, then
    sends them back to /api/jobs as `confirmed_tools`."""
    prov, resume_text = await _resolve_inputs(api_key, provider, resume, resume_file, jd)
    client = get_client(api_key, prov, economy=economy)
    report = tool_coverage(resume_text, jd, client=client)
    return {
        "matched": report.matched,
        "adjacent": [a.model_dump() for a in report.adjacent],
        "missing": report.missing,
        "provider": client.provider if not client.mock else "mock",
    }


@app.post("/api/cover-letter", dependencies=[Depends(rate_limit)])
async def cover_letter(
    jd: str = Form(...),
    api_key: str = Form(...),
    provider: str = Form(""),
    resume: str = Form(""),
    resume_file: UploadFile | None = File(None),
    company: str = Form("Company"),
    name: str = Form(""),
    target_title: str = Form(""),
    tone: str = Form("professional"),
    hiring_manager: str = Form(""),
    economy: bool = Form(False),
):
    """Generate a tailored cover letter. Synchronous; returns text + a downloadable .docx
    (base64). Names the company (unlike the résumé). Stateless — nothing is stored."""
    import base64

    prov, resume_text = await _resolve_inputs(api_key, provider, resume, resume_file, jd)
    client = get_client(api_key, prov, economy=economy)
    cand_name = name.strip() or (regex_contact(resume_text).get("name") or "").strip()
    letter = generate_cover_letter(
        resume_text, jd, client=client, company=company, candidate_name=cand_name,
        role=target_title, tone=tone, hiring_manager=hiring_manager)
    docx_bytes = build_cover_letter_docx(letter, candidate_name=cand_name)
    filename = f"{_safe(cand_name, 'CoverLetter')}_{_safe(company, 'Company')}_CoverLetter.docx"
    return {
        "text": cover_letter_text(letter),
        "letter": letter,
        "filename": filename,
        "docx_b64": base64.b64encode(docx_bytes).decode("ascii"),
        "provider": client.provider if not client.mock else "mock",
    }


if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
