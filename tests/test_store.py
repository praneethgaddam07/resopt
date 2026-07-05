"""RedisJobStore: round-trip, docx handling, and the privacy invariant
(sensitive inputs must never be written to Redis). Uses an injected fake client,
so no Redis server is required."""
from app.store import RedisJobStore, JobStore


class FakeRedis:
    """Enough of the redis-py surface for the store: bytes on get, str/bytes on set."""

    def __init__(self):
        self.kv: dict[str, bytes] = {}

    def set(self, k, v, ex=None):
        self.kv[k] = v.encode() if isinstance(v, str) else v
        return True

    def get(self, k):
        return self.kv.get(k)

    def delete(self, *ks):
        for k in ks:
            self.kv.pop(k, None)

    def ping(self):
        return True


def test_redis_store_roundtrip_and_privacy():
    fake = FakeRedis()
    s = RedisJobStore(client=fake)
    SECRET_KEY = "sk-ant-SUPER-SECRET-KEY"
    SECRET_RESUME = "CLASSIFIED_RESUME_TEXT_zzz"

    job = s.create(
        company="Acme", lastname="Doe",
        request={"api_key": SECRET_KEY, "resume_text": SECRET_RESUME, "jd_text": "jd"},
    )
    # The returned job carries the request locally (for the in-process worker)...
    assert job.request["api_key"] == SECRET_KEY
    # ...and get() reconstructs durable fields + re-attaches the local request.
    got = s.get(job.id)
    assert got is not None and got.company == "Acme" and got.status == "queued"
    assert got.request and got.request["api_key"] == SECRET_KEY

    # PRIVACY INVARIANT: the key + résumé must not appear ANYWHERE in Redis.
    blob = b"".join(fake.kv.values())
    assert SECRET_KEY.encode() not in blob
    assert SECRET_RESUME.encode() not in blob

    # Output persists; docx lands in its own key and comes back via get_result_docx.
    s.update(job.id, status="done", progress_step=5, result={"summary": "ok"},
             filename="Doe_Acme.docx", docx=b"PKZIP-DOCX-BYTES")
    done = s.get(job.id)
    assert done.status == "done" and done.result == {"summary": "ok"}
    assert done.filename == "Doe_Acme.docx"
    assert s.get_result_docx(job.id) == b"PKZIP-DOCX-BYTES"

    # Scrub drops the sensitive inputs; the durable output remains available.
    s.scrub_inputs(job.id)
    assert s.get(job.id).request is None
    assert s.get(job.id).status == "done"


def test_redis_store_missing_returns_none():
    s = RedisJobStore(client=FakeRedis())
    assert s.get("nope") is None
    assert s.get_result_docx("nope") is None


def test_memory_store_has_get_result_docx():
    s = JobStore()
    job = s.create(company="C", lastname="L")
    s.update(job.id, docx=b"XYZ", status="done")
    assert s.get_result_docx(job.id) == b"XYZ"
