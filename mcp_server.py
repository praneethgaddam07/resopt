"""RESOPT as an MCP server — the connector model (no BYO API key).

The student runs this inside their OWN Claude (Claude Desktop / connectors), so THEIR
subscription's model does the generative work (rephrasing bullets, writing the summary).
This server contributes only the DETERMINISTIC engine — the parts that are our real moat
and need no LLM at all:

  • JD keyword extraction + ATS scoring        (app.workflow.scoring)
  • truthful tool coverage / taxonomy          (app.workflow.taxonomy_resolver)
  • integrity guard: metric-preservation + anti-AI  (app.workflow.validators)
  • the 8-portal ATS-safe .docx builder         (app.ats.formatter + app.ats.portals)

So there is NO API key and NO inference cost on our side. The host model reads the résumé,
calls `optimization_guide` to learn our method, drafts tailored content, then calls
`score_resume` / `check_integrity` to verify it, and finally `format_resume` to get the .docx.

Run (after `uv add "mcp[cli]"` / `pip install "mcp[cli]"`):
    python mcp_server.py
Then register it in Claude Desktop's claude_desktop_config.json (see README).
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import time

from app.ats.formatter import build_docx_bytes
from app.ats.portals import get_portal, list_portals
from app.workflow import scoring
from app.workflow import validators
from app.workflow.cover_letter import build_cover_letter_docx
from app.workflow.taxonomy_resolver import resolve_coverage

# Import the real FastMCP if present; otherwise a no-op stub so the tool functions stay
# importable/testable without the `mcp` package installed (CI, smoke tests).
try:
    from mcp.server.fastmcp import FastMCP
    # host/port matter only for the remote (streamable-http) mode; stdio ignores them.
    # Hosted endpoint: https://<host>/mcp  ·  file downloads: https://<host>/files/{token}
    # stateless_http=True: no server-held session state, so a restart / free-tier
    # spin-down / redeploy doesn't invalidate connected clients — each request is
    # self-contained. (Session-stateful mode 404s every client after a restart.)
    mcp = FastMCP("resopt", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")),
                  stateless_http=True)
    _HAS_MCP = True
except ImportError:  # pragma: no cover - only when mcp isn't installed
    _HAS_MCP = False

    class _Stub:
        def tool(self, *a, **k):
            return lambda f: f

        def prompt(self, *a, **k):
            return lambda f: f
    mcp = _Stub()


def _dump(obj):
    """Serialize a Pydantic model or plain object to a JSON-safe dict."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj


# --------------------- file delivery (local disk vs remote URL) ---------------------
# Local (Claude Desktop / stdio): write the .docx to the user's machine, return the path.
# Remote (hosted): we can't touch their disk — stash the bytes and return a short-lived
# download URL served by our own /files/{token} route. Set RESOPT_PUBLIC_URL to enable.
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PUBLIC_URL = os.environ.get("RESOPT_PUBLIC_URL", "").rstrip("/")
_FILE_TTL = 900  # seconds a generated file stays downloadable
_FILES: dict[str, tuple[str, bytes, float]] = {}
_FILES_LOCK = threading.Lock()

# Optional Redis so hosted download links survive restarts and work across instances.
# Unset REDIS_URL (or no redis installed) -> in-memory, single-instance (unchanged).
_REDIS = None
try:
    if os.environ.get("REDIS_URL"):
        import redis as _redis_lib
        _REDIS = _redis_lib.from_url(os.environ["REDIS_URL"])
        _REDIS.ping()
except Exception:  # pragma: no cover - redis missing or unreachable -> in-memory fallback
    _REDIS = None

# Local (stdio) writes are confined to this dir. A model-supplied out_path is advisory
# only — never allowed to escape it (no traversal, no absolute/system paths).
_SAFE_OUT_DIR = os.path.realpath(os.path.expanduser(os.environ.get("RESOPT_OUT_DIR", "~/Downloads")))


def _safe_dest(out_path: str, filename: str) -> str:
    """Resolve a save path INSIDE _SAFE_OUT_DIR. A model-supplied out_path is treated as
    a relative sub-path/filename only; anything that would escape the dir (``..``, an
    absolute or ``~`` path, a symlink) falls back to <safe_dir>/<filename>."""
    base = _SAFE_OUT_DIR
    rel = (out_path or "").strip().lstrip("/\\") or filename
    try:
        dest = os.path.realpath(os.path.join(base, rel))
        if os.path.commonpath([base, dest]) != base:
            dest = os.path.join(base, os.path.basename(filename))
    except (ValueError, OSError):
        dest = os.path.join(base, os.path.basename(filename))
    if os.path.isdir(dest) or dest.endswith(("/", os.sep)):
        dest = os.path.join(dest, os.path.basename(filename))
    return dest


def _reap() -> None:
    now = time.time()
    for t in [t for t, (_, _, exp) in _FILES.items() if exp < now]:
        _FILES.pop(t, None)


def _stash(filename: str, data: bytes) -> str:
    token = secrets.token_urlsafe(16)
    if _REDIS is not None:
        _REDIS.set(f"resopt:file:{token}", data, ex=_FILE_TTL)
        _REDIS.set(f"resopt:file:{token}:name", filename, ex=_FILE_TTL)
        return token
    with _FILES_LOCK:
        _reap()
        _FILES[token] = (filename, data, time.time() + _FILE_TTL)
    return token


def _fetch(token: str):
    """Return (filename, bytes) for a stashed file, or None if expired/absent."""
    if not token:
        return None
    if _REDIS is not None:
        data = _REDIS.get(f"resopt:file:{token}")
        if not data:
            return None
        name = _REDIS.get(f"resopt:file:{token}:name")
        if isinstance(name, bytes):
            name = name.decode("utf-8", "ignore")
        return (name or "RESOPT_resume.docx", data)
    with _FILES_LOCK:
        _reap()
        item = _FILES.get(token)
    return (item[0], item[1]) if item else None


def _deliver(filename: str, data: bytes, extra: dict | None = None, out_path: str = "") -> str:
    """Return the .docx to the user: a download URL when hosted, else a saved local path."""
    payload = dict(extra or {})
    payload["bytes"] = len(data)
    if _PUBLIC_URL:  # hosted / remote connector
        payload["download_url"] = f"{_PUBLIC_URL}/files/{_stash(filename, data)}"
    else:            # local stdio (Claude Desktop) — write to disk, confined to a safe dir
        dest = _safe_dest(out_path, filename)
        os.makedirs(os.path.dirname(dest) or _SAFE_OUT_DIR, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        payload["saved"] = dest
    return json.dumps(payload, ensure_ascii=False)


if _HAS_MCP:  # serve generated files over HTTP when running as a remote connector
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response

    @mcp.custom_route("/files/{token}", methods=["GET"])
    async def _download_file(request: "Request"):
        item = _fetch(request.path_params.get("token", ""))
        if not item:
            return JSONResponse({"error": "expired or not found"}, status_code=404)
        filename, data = item
        return Response(data, media_type=_DOCX_MIME,
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @mcp.custom_route("/health", methods=["GET"])
    async def _health(request: "Request"):
        return JSONResponse({"status": "ok", "service": "resopt-mcp"})


# --------------------------- tools ---------------------------

@mcp.tool()
def optimization_guide() -> str:
    """Read this FIRST. The RESOPT method: help the user's OWN AI produce a JD-tailored,
    ATS-ready résumé (and a cover letter if they ask), grounded only in their real experience.
    Never invents content. There is NO fit/qualification check — go straight to customizing."""
    return (
        "RESOPT method — tailor the user's REAL résumé to the job (and a cover letter if asked):\n"
        "1. DECODE the JD: the real problem behind the hire; required vs preferred skills; tone.\n"
        "2. MAP the candidate: for each required skill, is it a direct match, a defensible "
        "adjacent (call check_tool_coverage), or genuinely missing? Never feature what's missing.\n"
        "3. WRITE the résumé as a problem-solver, REPHRASING the candidate's REAL bullets — never "
        "invent achievements, tools, employers, or metrics. Surface the true tool that matches this "
        "JD (same work, same numbers). Each bullet: one sentence, 15-30 words, action verb first, "
        "ending in a real metric or named artifact.\n"
        "   SUMMARY: exactly 4 sentences, <=75 words. Open with the candidate's DEFENSIBLE title "
        "(don't inflate seniority). Claim a domain ONLY if the résumé shows it.\n"
        "   BANNED words (never use): delve, spearheaded, synergy, orchestrated, leverage, harness, "
        "foster, cutting-edge, tapestry, unwavering. BANNED openers: Responsible for, Worked on, "
        "Helped with, Assisted, Duties included, Tasked with.\n"
        "   EXAMPLES — imitate these transformations exactly (notice: same facts, same numbers, "
        "JD's vocabulary, metric last):\n"
        "   WEAK: 'Responsible for creating dashboards for the sales team.'\n"
        "   STRONG: 'Built 12 Power BI dashboards tracking pipeline conversion for 6 regional "
        "managers, cutting weekly report turnaround from 5 days to 1.'\n"
        "   WEAK: 'Worked on improving data quality using various tools.'\n"
        "   STRONG: 'Automated validation checks across 10K+ records with SQL and dbt, raising "
        "data accuracy to 98%.'\n"
        "   REFRAME (truthful facet-surfacing — same work, the JD's words): candidate bullet says "
        "'built a delinquency prioritization model' and the JD asks for risk analytics -> "
        "'Designed an operational risk-analytics model prioritizing 100K+ accounts, lifting "
        "recovery 18%.' Same model, same 18% — never a new fact.\n"
        "4. CRITIQUE before formatting: call check_resume_quality with the drafted résumé — it "
        "returns line-item issues (missing metrics, weak openers, banned words, repeated verbs, "
        "length). Fix ONLY what it names, in one pass.\n"
        "5. FORMAT the résumé: call format_resume with the final résumé, the ATS portal, and "
        "source_bullets = the candidate's ORIGINAL bullets (folds the integrity check in).\n"
        "6. SCORE AFTER customizing: THEN call score_resume ONCE to show the final ATS match score "
        "on the tailored résumé, and fix the top truthful gaps if any. Do NOT loop.\n"
        "COVER LETTER (only if the user asks): 3-4 short paragraphs, ~250-350 words, FIRST person, "
        "name the company, open with their need, use 1-2 of the candidate's REAL achievements with "
        "their exact metrics; same banned words apply. Then call format_cover_letter.\n"
        "PRESERVE every source metric EXACTLY — never round or inflate.\n"
        "TOKEN-FRUGAL (the user is spending their own AI usage): work in ONE pass; keep tool calls "
        "minimal; do NOT paste the full résumé/letter back into the chat — go straight to the "
        "format_* tool and give only a short summary of what changed."
    )


@mcp.tool()
def format_cover_letter(letter: dict, candidate_name: str = "", contact_line: str = "",
                        out_path: str = "") -> str:
    """Build a clean .docx cover letter from the drafted letter and save it to the user's machine.
    Call this AFTER writing the letter (name the company; 3-4 short paragraphs; real achievements;
    no AI-tell words). `letter` shape: {greeting, paragraphs:[..], closing, signature}.
    Returns a compact {saved, bytes} note."""
    docx_bytes = build_cover_letter_docx(letter, candidate_name=candidate_name,
                                         contact_line=contact_line)
    return _deliver("RESOPT_cover_letter.docx", docx_bytes, None, out_path)


@mcp.tool()
def list_ats_portals() -> str:
    """List the supported ATS portals (Workday, Taleo, ADP, Greenhouse, …) with their
    key, date format, and section-order rules. Use a returned `key` with format_resume."""
    return json.dumps(list_portals(), ensure_ascii=False)


@mcp.tool()
def extract_keywords(jd: str) -> str:
    """Extract the JD's priority keywords (deterministic, frequency + phrase ranked).
    Use these as the exact language to mirror in the résumé."""
    return json.dumps(scoring.extract_jd_keywords(jd, limit=25), ensure_ascii=False)


@mcp.tool()
def check_tool_coverage(candidate_skills: list[str], jd_tools: list[str]) -> str:
    """Truthfully map the candidate's real tools to the JD's required tools.
    Returns {matched, adjacent, missing}: `matched` = exact real matches; `adjacent` =
    a JD tool the candidate has a same-category real analogue for (surfaces the candidate's
    OWN tool, never the JD's); `missing` = no basis, leave as an honest gap. Never invents."""
    rep = resolve_coverage(candidate_skills, jd_tools)
    return json.dumps(_dump(rep), ensure_ascii=False)


@mcp.tool()
def check_resume_quality(resume: dict) -> str:
    """Deterministic line-item critique of a DRAFTED résumé — call this BEFORE format_resume,
    fix ONLY what it names, in one pass. Checks every bullet for: missing metric/artifact,
    length outside 15-30 words, weak openers, banned AI-tell words, and repeated opening verbs;
    plus summary length. Returns compact JSON: {ok, bullet_issues, repeated_openers, summary_issues}.

    `resume` shape: same as score_resume/format_resume."""
    issues, verbs = [], {}

    def check(bullets: list, where: str) -> None:
        for i, b in enumerate(bullets or [], 1):
            b = str(b or "")
            probs = []
            n = len(b.split())
            if not scoring.has_metric_or_artifact(b):
                probs.append("no metric or named artifact at the end")
            if n and (n < 12 or n > 32):
                probs.append(f"{n} words (aim 15-30)")
            wk = validators.anti_ai.weak_opener(b)
            if wk:
                probs.append(f"weak opener '{wk}'")
            tells = validators.anti_ai.ai_tell_hits(b)
            if tells:
                probs.append("banned words: " + ", ".join(tells[:3]))
            first = (b.split() or [""])[0].lower().strip(".,;:")
            if first:
                verbs.setdefault(first, []).append(f"{where} b{i}")
            if probs:
                issues.append({"where": f"{where} bullet {i}",
                               "bullet": " ".join(b.split()[:6]) + "…", "fix": probs})

    for xi, e in enumerate(resume.get("experiences", []) or [], 1):
        check(e.get("bullets"), f"experience {xi}")
    for pi, p in enumerate(resume.get("projects", []) or [], 1):
        check(p.get("bullets"), f"project {pi}")

    repeated = {v: locs for v, locs in verbs.items() if len(locs) > 1}
    summary = str(resume.get("summary", "") or "")
    summary_issues = []
    sw = len(summary.split())
    if sw > 75:
        summary_issues.append(f"summary is {sw} words (max 75)")
    s_tells = validators.anti_ai.ai_tell_hits(summary)
    if s_tells:
        summary_issues.append("summary has banned words: " + ", ".join(s_tells[:3]))
    out = {"ok": not (issues or repeated or summary_issues),
           "bullet_issues": issues[:12],
           "repeated_openers": repeated,
           "summary_issues": summary_issues}
    return json.dumps(out, ensure_ascii=False)


@mcp.prompt()
def optimize_my_resume(ats_portal: str = "generic") -> str:
    """Kick off the full RESOPT optimization flow on the résumé + job description in this chat."""
    return (
        "You are helping me tailor my RÉSUMÉ (shared in this chat) to the JOB DESCRIPTION "
        "(also in this chat) so it passes ATS screening truthfully.\n"
        "1. Call the resopt tool `optimization_guide` and follow its method exactly.\n"
        f"2. Target ATS portal: {ats_portal or 'generic'} (use `list_ats_portals` if unsure).\n"
        "3. Never invent experience, tools, employers, or metrics — rephrase my REAL content.\n"
        "4. Draft -> `check_resume_quality` -> fix named issues -> `format_resume` (with my "
        "original bullets as source_bullets) -> ONE `score_resume` pass -> give me the download "
        "and a 3-line summary of what changed."
    )


@mcp.tool()
def score_resume(resume: dict, jd: str, portal: str = "generic", verbose: bool = False) -> str:
    """Score a drafted résumé against the JD like an ATS would. Returns a COMPACT result by
    default (token-frugal): {ats_score, passes, missing_keywords, rephrase_to_exact}. Do ONE
    scoring pass, fix the top gaps you truthfully have, then format — don't loop repeatedly.
    Set verbose=true only if you need the full checklist + suggestions.

    `resume` shape: {job_title, summary, skills:[{name, skills:[..]}],
    experiences:[{title, company, duration, location, bridge_line, bullets:[..]}],
    projects:[{title, bullets:[..]}], education:[{degree, school, dates, gpa}], certifications:[..]}"""
    report = scoring.build_report(resume, jd, get_portal(portal))
    if verbose:
        return json.dumps(report, ensure_ascii=False)
    brief = {
        "ats_score": report["ats_score"],
        "passes": report["passes_threshold"],
        "missing_keywords": report["missing_keywords"][:6],       # add only if truthfully yours
        "rephrase_to_exact": report["near_miss_keywords"][:6],    # you have these — use exact JD words
    }
    return json.dumps(brief, ensure_ascii=False)


@mcp.tool()
def format_resume(resume: dict, contact: dict, portal: str = "generic",
                  out_path: str = "", style: dict | None = None,
                  source_bullets: list[str] | None = None) -> str:
    """Build the ATS-safe single-column .docx from the FINAL structured résumé and save it to
    the student's machine — and, in the SAME call, run the integrity guard so you don't spend
    a separate round-trip on it. Pass `source_bullets` (the candidate's ORIGINAL master-résumé
    bullets) and it will strip any invented metric or AI-tell word before building. Applies the
    portal's rules + optional ATS-safe style (font, sizes, alignment, bullet, margins, fit_one_page).

    `contact`: {name, email, phone, linkedin, location}. Returns a compact {saved, integrity} note."""
    integrity = None
    if source_bullets:
        rep = validators.enforce(resume, source_bullets, source_bullets)  # accept any real metric
        integrity = {"fixed": getattr(rep, "repaired", 0), "ok": getattr(rep, "ok", True)}
    docx_bytes = build_docx_bytes(resume, contact, get_portal(portal), style=style)
    return _deliver("RESOPT_resume.docx", docx_bytes, {"integrity": integrity}, out_path)


# ASGI app for hosting behind uvicorn (remote). Serves /mcp + /files + /health.
# Render start command:  uvicorn mcp_server:http_app --host 0.0.0.0 --port $PORT
if _HAS_MCP:
    http_app = mcp.streamable_http_app()


if __name__ == "__main__":  # pragma: no cover
    if not _HAS_MCP:
        raise SystemExit("Install the MCP SDK first:  pip install \"mcp[cli]\"")
    # Local (Claude Desktop): stdio. Remote (hosted connector): streamable-http.
    #   python mcp_server.py            -> stdio
    #   python mcp_server.py --http     -> streamable-http (set RESOPT_PUBLIC_URL too)
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if "--http" in sys.argv:
        transport = "streamable-http"
    mcp.run(transport=transport)
