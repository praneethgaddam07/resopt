"""Background dispatch via an in-process thread pool.

Stateless hosting target: a single instance with an in-memory store. The API
returns a job id immediately and the browser polls — long LLM work never blocks
a request. (No Redis/Celery needed for the BYO-key hosted model.)
"""
from __future__ import annotations

import atexit
import os
from concurrent.futures import ThreadPoolExecutor

from .tasks import process_job

_workers = int(os.environ.get("WORKER_THREADS", "4"))
_executor = ThreadPoolExecutor(max_workers=max(1, _workers), thread_name_prefix="optimize")
atexit.register(lambda: _executor.shutdown(wait=False))


def enqueue(job_id: str) -> None:
    _executor.submit(process_job, job_id)


def mode() -> str:
    return "in-process"
