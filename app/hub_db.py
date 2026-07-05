import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "hub.db")

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
    try:
        c.execute("ALTER TABLE jobs ADD COLUMN score INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass # column already exists
    conn.commit()
    conn.close()
    cleanup_old_jobs()

def cleanup_old_jobs():
    """Privacy guarantee: delete jobs older than 3 days"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    three_days_ago = (datetime.utcnow() - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("DELETE FROM jobs WHERE created_at < ?", (three_days_ago,))
    conn.commit()
    conn.close()

def add_job(title, company, url, jd_text, ats_id, score=0):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO jobs (title, company, url, jd_text, ats_id, score) VALUES (?, ?, ?, ?, ?, ?)",
        (title, company, url, jd_text, ats_id, score)
    )
    job_id = c.lastrowid
    conn.commit()
    conn.close()
    return job_id

def get_jobs():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM jobs ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def mark_optimized(job_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE jobs SET status = 'optimized' WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

def delete_job(job_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
