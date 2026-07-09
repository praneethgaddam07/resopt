import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "hub.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            company TEXT,
            url TEXT,
            jd_text TEXT,
            ats_id TEXT,
            status TEXT DEFAULT 'saved',
            score INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Additive migrations — each guarded so re-runs on an existing DB are no-ops.
    for ddl in (
        "ALTER TABLE jobs ADD COLUMN score INTEGER DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN applied INTEGER DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN resume_path TEXT",
        "ALTER TABLE jobs ADD COLUMN resume_label TEXT",
        "ALTER TABLE jobs ADD COLUMN updated_at TIMESTAMP",
    ):
        try:
            c.execute(ddl)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    conn.close()
    # NOTE: no auto-purge. The Hub is the user's own local job tracker on their own
    # machine (hub.db) — silently deleting saved/applied jobs would destroy the very
    # history they're tracking. Users remove jobs explicitly via delete_job().


def add_job(title, company, url, jd_text, ats_id, score=0):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO jobs (title, company, url, jd_text, ats_id, score) VALUES (?, ?, ?, ?, ?, ?)",
        (title, company, url, jd_text, ats_id, score),
    )
    job_id = c.lastrowid
    conn.commit()
    conn.close()
    return job_id


def get_jobs():
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM jobs ORDER BY applied ASC, created_at DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_job(job_id):
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def _touch(c, job_id):
    c.execute("UPDATE jobs SET updated_at = ? WHERE id = ?",
              (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), job_id))


def set_applied(job_id, applied):
    """Toggle the applied flag. Applied jobs float to the top of the list and keep
    any résumé the user saved for them."""
    conn = _connect()
    c = conn.cursor()
    status = 'applied' if applied else 'saved'
    c.execute("UPDATE jobs SET applied = ?, status = ? WHERE id = ?",
              (1 if applied else 0, status, job_id))
    _touch(c, job_id)
    conn.commit()
    conn.close()


def set_resume(job_id, path, label):
    """Record the on-device path of the résumé the user customized for this job."""
    conn = _connect()
    c = conn.cursor()
    c.execute("UPDATE jobs SET resume_path = ?, resume_label = ?, status = 'optimized' WHERE id = ?",
              (path, label, job_id))
    _touch(c, job_id)
    conn.commit()
    conn.close()


def update_score(job_id, score):
    conn = _connect()
    c = conn.cursor()
    c.execute("UPDATE jobs SET score = ? WHERE id = ?", (int(score), job_id))
    conn.commit()
    conn.close()


def mark_optimized(job_id):
    conn = _connect()
    c = conn.cursor()
    c.execute("UPDATE jobs SET status = 'optimized' WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()


def delete_job(job_id):
    conn = _connect()
    c = conn.cursor()
    c.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
