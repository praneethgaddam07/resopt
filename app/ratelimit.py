"""Lightweight in-process rate limiter (per-client sliding window).

No external dependency (no Redis) — the same single-instance tradeoff the in-memory
job store makes. It stops a runaway loop or scraper from hammering the LLM-backed
endpoints. If RESOPT ever runs multiple instances, move this (and the job store) to a
shared backend so the budget is enforced across the fleet.
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

# Per-client limits (env-overridable). Generous enough for real use, tight enough to
# stop abuse. Disabled under FORCE_MOCK so the test suite isn't throttled.
_MAX = int(os.environ.get("RESOPT_RATE_LIMIT", "30"))        # requests ...
_WINDOW = float(os.environ.get("RESOPT_RATE_WINDOW", "60"))  # ... per this many seconds
_DISABLED = (os.environ.get("FORCE_MOCK") == "1"
             or os.environ.get("RESOPT_DISABLE_RATELIMIT") == "1")

_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def _client_key(request: Request) -> str:
    # Honor the proxy's forwarded IP (Render/Heroku sit behind one); else the peer IP.
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request) -> None:
    """FastAPI dependency: raise 429 when a client exceeds its window budget."""
    if _DISABLED:
        return
    now = time.time()
    cutoff = now - _WINDOW
    key = _client_key(request)
    with _lock:
        dq = _hits[key]
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) >= _MAX:
            raise HTTPException(429, "Too many requests — please wait a moment and try again.")
        dq.append(now)
        # Opportunistic cleanup so idle clients don't accumulate unbounded.
        if len(_hits) > 4096:
            for k in [k for k, d in _hits.items() if not d or d[-1] <= cutoff]:
                _hits.pop(k, None)
