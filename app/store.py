"""Job store: in-memory by default, Redis-backed when REDIS_URL is set.

Privacy by design: the user's API key + résumé + JD (the transient `request`) are
NEVER written to Redis — they live in process memory only for the duration of a job
and are scrubbed the instant processing finishes. Only the *generated* output
(status, the tailored-résumé JSON, and the .docx bytes) is persisted, with a short
TTL, so a result survives a restart and any instance can serve a poll/download.

Both backends share one surface: create / get / update / scrub_inputs / get_result_docx.
Unset REDIS_URL -> the in-memory single-instance store (unchanged behavior).
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field


JOB_TTL_SECONDS = 30 * 60      # forget everything after 30 minutes
_PURGE_EVERY = 120

# Non-sensitive fields mirrored to Redis. `request` (API key + résumé) and `docx`
# bytes are deliberately excluded — request stays in-process; docx gets its own key.
_DURABLE = ("id", "status", "progress_step", "progress_total", "progress_label",
            "company", "lastname", "result", "filename", "error",
            "created_at", "updated_at")


@dataclass
class Job:
    id: str
    status: str = "queued"            # queued | running | done | error
    progress_step: int = 0
    progress_total: int = 5
    progress_label: str = "Queued"
    company: str = "Company"
    lastname: str = "Resume"
    # Transient inputs — deleted as soon as processing finishes; NEVER persisted.
    request: dict | None = field(default=None, repr=False)
    # Outputs (in memory, or Redis when enabled).
    result: dict | None = None
    docx: bytes | None = field(default=None, repr=False)
    filename: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def public_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "progress": {
                "step": self.progress_step,
                "total": self.progress_total,
                "label": self.progress_label,
                "percent": round(100 * self.progress_step / max(self.progress_total, 1)),
            },
            "filename": self.filename,
            "result": self.result,
            "error": self.error,
            "download_url": (f"/api/jobs/{self.id}/download" if self.status == "done" else None),
        }


class JobStore:
    """In-process store (single instance). Correct + simplest when REDIS_URL is unset."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._start_purger()

    def create(self, **kwargs) -> Job:
        job = Job(id=uuid.uuid4().hex, **kwargs)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def get_result_docx(self, job_id: str) -> bytes | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.docx if job else None

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for k, v in fields.items():
                setattr(job, k, v)
            job.updated_at = time.time()

    def scrub_inputs(self, job_id: str) -> None:
        """Drop the key + résumé + JD the instant we no longer need them."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.request = None

    def _start_purger(self) -> None:
        def loop():
            while True:
                time.sleep(_PURGE_EVERY)
                cutoff = time.time() - JOB_TTL_SECONDS
                with self._lock:
                    for jid in [j for j, job in self._jobs.items() if job.updated_at < cutoff]:
                        self._jobs.pop(jid, None)
        threading.Thread(target=loop, daemon=True, name="job-purger").start()


class RedisJobStore:
    """Redis-backed store: generated output persists (TTL) and is readable from ANY
    instance, so results survive a restart and polls/downloads work behind a load
    balancer.

    Privacy invariant: the sensitive `request` (API key + résumé + JD) is held in a
    process-local map, NEVER in Redis. A job is created and processed on the same
    instance (the in-process worker reads `request` locally); every other instance can
    still serve status polls and the .docx download straight from Redis.
    """

    def __init__(self, client=None, *, url: str | None = None, ttl: int = JOB_TTL_SECONDS):
        if client is None:
            import redis  # lazy import: only needed in Redis mode
            client = redis.from_url(url or os.environ["REDIS_URL"])
        self._r = client
        self._ttl = ttl
        self._pending: dict[str, dict] = {}   # id -> sensitive request (THIS instance only)
        self._lock = threading.Lock()

    @staticmethod
    def _key(job_id: str) -> str:
        return f"resopt:job:{job_id}"

    @staticmethod
    def _dkey(job_id: str) -> str:
        return f"resopt:job:{job_id}:docx"

    def _save(self, job: Job) -> None:
        data = {f: getattr(job, f) for f in _DURABLE}   # excludes request + docx
        self._r.set(self._key(job.id), json.dumps(data), ex=self._ttl)

    def create(self, **kwargs) -> Job:
        req = kwargs.pop("request", None)
        job = Job(id=uuid.uuid4().hex, **kwargs)        # persisted job carries no request
        with self._lock:
            self._pending[job.id] = req
        self._save(job)
        job.request = req                               # for the local worker's convenience
        return job

    def get(self, job_id: str) -> Job | None:
        raw = self._r.get(self._key(job_id))
        if raw is None:
            return None
        job = Job(**json.loads(raw))
        with self._lock:
            job.request = self._pending.get(job_id)     # only present on the creating instance
        return job

    def get_result_docx(self, job_id: str) -> bytes | None:
        return self._r.get(self._dkey(job_id))

    def update(self, job_id: str, **fields) -> None:
        docx = fields.pop("docx", None)
        fields.pop("request", None)                     # never persist the sensitive inputs
        with self._lock:                                # serialize this store's read-modify-write
            raw = self._r.get(self._key(job_id))
            if raw is None:
                return
            data = json.loads(raw)
            for k, v in fields.items():
                if k in _DURABLE:
                    data[k] = v
            data["updated_at"] = time.time()
            self._r.set(self._key(job_id), json.dumps(data), ex=self._ttl)
        if docx is not None:
            self._r.set(self._dkey(job_id), docx, ex=self._ttl)

    def scrub_inputs(self, job_id: str) -> None:
        with self._lock:
            self._pending.pop(job_id, None)             # drop the API key + résumé immediately


def _make_store():
    url = os.environ.get("REDIS_URL")
    if url:
        try:
            s = RedisJobStore(url=url)
            s._r.ping()                                 # fail fast at boot if unreachable
            return s
        except Exception as e:  # pragma: no cover - fall OPEN to in-memory rather than crash
            print(f"[store] Redis unavailable ({e!r}); using in-memory store")
    return JobStore()


store = _make_store()
