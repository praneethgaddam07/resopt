"""Stateless, bring-your-own-key résumé-optimization service.

Package layout:
    app.main        FastAPI app + HTTP routes (submit / poll / download / render).
    app.store       In-memory, TTL-purged job store (no disk, no database).
    app.queue       In-process thread-pool dispatch.
    app.tasks       The background job (maps fine steps -> generic phases).
    app.llm         Multi-provider client (Anthropic / OpenAI / Gemini) + prompts.
    app.workflow    The tailoring engine, extraction, ATS scoring + checklist.
    app.ats         Per-portal rules + the ATS-safe .docx formatter.
"""

__version__ = "1.4.0"
