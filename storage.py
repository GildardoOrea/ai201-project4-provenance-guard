import json
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = "audit_log.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            content_id TEXT PRIMARY KEY,
            creator_id TEXT,
            text TEXT,
            attribution TEXT,
            confidence REAL,
            llm_score REAL,
            stylometric_score REAL,
            label TEXT,
            status TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id TEXT,
            event_type TEXT,
            timestamp TEXT,
            details TEXT
        )
    """)
    conn.commit()
    conn.close()


def new_content_id():
    return str(uuid.uuid4())


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def save_submission(content_id, creator_id, text, attribution, confidence,
                     llm_score, stylometric_score, label, status="classified"):
    conn = get_conn()
    conn.execute(
        """INSERT INTO submissions
           (content_id, creator_id, text, attribution, confidence, llm_score,
            stylometric_score, label, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (content_id, creator_id, text, attribution, confidence, llm_score,
         stylometric_score, label, status, now_iso()),
    )
    conn.commit()
    conn.close()


def get_submission(content_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM submissions WHERE content_id = ?", (content_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_submission_status(content_id, status):
    conn = get_conn()
    conn.execute(
        "UPDATE submissions SET status = ? WHERE content_id = ?",
        (status, content_id),
    )
    conn.commit()
    conn.close()


def log_event(content_id, event_type, details: dict):
    conn = get_conn()
    conn.execute(
        "INSERT INTO audit_log (content_id, event_type, timestamp, details) VALUES (?, ?, ?, ?)",
        (content_id, event_type, now_iso(), json.dumps(details)),
    )
    conn.commit()
    conn.close()


def get_log(limit=50):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    entries = []
    for r in rows:
        entry = dict(r)
        entry["details"] = json.loads(entry["details"])
        entries.append(entry)
    return entries
