"""Simple CRM — tracks Feishu contacts who interact with the bot.

Stores in .autoservice/database/crm.db (SQLite). Auto-creates on first use.
Each message updates last_seen and message_count.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH = Path(".autoservice/database/crm.db")
_db: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    open_id TEXT PRIMARY KEY,
    name TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    email TEXT DEFAULT '',
    company TEXT DEFAULT '',
    department TEXT DEFAULT '',
    job_title TEXT DEFAULT '',
    source TEXT DEFAULT 'feishu',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    message_count INTEGER DEFAULT 0,
    notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    open_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    direction TEXT NOT NULL,  -- 'in' or 'out'
    text TEXT NOT NULL,
    ts TEXT NOT NULL,
    FOREIGN KEY (open_id) REFERENCES contacts(open_id)
);

CREATE INDEX IF NOT EXISTS idx_conversations_open_id ON conversations(open_id);
CREATE INDEX IF NOT EXISTS idx_conversations_ts ON conversations(ts);
"""


def _get_db() -> sqlite3.Connection:
    global _db
    if _db is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _db = sqlite3.connect(str(_DB_PATH))
        _db.row_factory = sqlite3.Row
        _db.executescript(SCHEMA)
    return _db


def upsert_contact(
    open_id: str,
    name: str = "",
    phone: str = "",
    email: str = "",
    company: str = "",
    department: str = "",
    job_title: str = "",
) -> dict:
    """Create or update a contact. Returns the contact record."""
    db = _get_db()
    now = datetime.now(tz=timezone.utc).isoformat()

    existing = db.execute(
        "SELECT * FROM contacts WHERE open_id = ?", (open_id,)
    ).fetchone()

    if existing is None:
        db.execute(
            """INSERT INTO contacts (open_id, name, phone, email, company, department, job_title, first_seen, last_seen, message_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (open_id, name, phone, email, company, department, job_title, now, now),
        )
    else:
        # Only update fields that have new non-empty values
        updates = {}
        if name and name != existing["name"]:
            updates["name"] = name
        if phone and phone != existing["phone"]:
            updates["phone"] = phone
        if email and email != existing["email"]:
            updates["email"] = email
        if company and company != existing["company"]:
            updates["company"] = company
        if department and department != existing["department"]:
            updates["department"] = department
        if job_title and job_title != existing["job_title"]:
            updates["job_title"] = job_title

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            db.execute(
                f"UPDATE contacts SET {set_clause}, last_seen = ? WHERE open_id = ?",
                (*updates.values(), now, open_id),
            )
        else:
            db.execute(
                "UPDATE contacts SET last_seen = ? WHERE open_id = ?",
                (now, open_id),
            )

    db.commit()
    return dict(db.execute("SELECT * FROM contacts WHERE open_id = ?", (open_id,)).fetchone())


def increment_message_count(open_id: str) -> None:
    """Bump message_count and last_seen for a contact."""
    db = _get_db()
    now = datetime.now(tz=timezone.utc).isoformat()
    db.execute(
        "UPDATE contacts SET message_count = message_count + 1, last_seen = ? WHERE open_id = ?",
        (now, open_id),
    )
    db.commit()


def log_message(open_id: str, chat_id: str, direction: str, text: str, ts: str = "") -> None:
    """Log a conversation message."""
    db = _get_db()
    if not ts:
        ts = datetime.now(tz=timezone.utc).isoformat()
    db.execute(
        "INSERT INTO conversations (open_id, chat_id, direction, text, ts) VALUES (?, ?, ?, ?, ?)",
        (open_id, chat_id, direction, text, ts),
    )
    db.commit()


def get_contact(open_id: str) -> dict | None:
    """Get a contact by open_id."""
    db = _get_db()
    row = db.execute("SELECT * FROM contacts WHERE open_id = ?", (open_id,)).fetchone()
    return dict(row) if row else None


def get_contact_history(open_id: str, limit: int = 50) -> list[dict]:
    """Get recent conversation history for a contact."""
    db = _get_db()
    rows = db.execute(
        "SELECT * FROM conversations WHERE open_id = ? ORDER BY ts DESC LIMIT ?",
        (open_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def list_contacts(limit: int = 100) -> list[dict]:
    """List all contacts, most recently active first."""
    db = _get_db()
    rows = db.execute(
        "SELECT * FROM contacts ORDER BY last_seen DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def search_contacts(query: str) -> list[dict]:
    """Search contacts by name, company, phone, or email."""
    db = _get_db()
    pattern = f"%{query}%"
    rows = db.execute(
        """SELECT * FROM contacts
           WHERE name LIKE ? OR company LIKE ? OR phone LIKE ? OR email LIKE ?
           ORDER BY last_seen DESC""",
        (pattern, pattern, pattern, pattern),
    ).fetchall()
    return [dict(r) for r in rows]
