"""Small SQLite database (users.db) that stores quiz results and remembers returning users.

It is separate from the dish/menu database, so init_db.py is not affected.
The file and its tables are created automatically the first time the app starts.
"""
import os
import secrets
import sqlite3
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.db")


@contextmanager
def connect():
    """Open the database, commit on success, roll back on error, always close."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_user_db():
    """Create the tables if they don't exist yet (safe to run every time)."""
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                token      TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS quiz_results (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                spice    INTEGER NOT NULL CHECK (spice  BETWEEN 1 AND 10),
                sweet    INTEGER NOT NULL CHECK (sweet  BETWEEN 1 AND 10),
                savory   INTEGER NOT NULL CHECK (savory BETWEEN 1 AND 10),
                cuisines TEXT NOT NULL,              -- comma-separated, e.g. "indian,italian"
                taken_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP   -- UTC
            );

            CREATE INDEX IF NOT EXISTS idx_quiz_results_user
                ON quiz_results (user_id, id DESC);
            """
        )


def create_user():
    """Add a new user and return (user_id, token). The token goes in the browser cookie."""
    token = secrets.token_urlsafe(32)
    with connect() as conn:
        cur = conn.execute("INSERT INTO users (token) VALUES (?)", (token,))
        return cur.lastrowid, token


def get_user_by_token(token):
    """Return the user row for a cookie token, or None if it isn't recognized."""
    if not token:
        return None
    with connect() as conn:
        return conn.execute("SELECT * FROM users WHERE token = ?", (token,)).fetchone()


def touch_user(user_id):
    """Record that this user just visited."""
    with connect() as conn:
        conn.execute(
            "UPDATE users SET last_seen = CURRENT_TIMESTAMP WHERE id = ?", (user_id,)
        )


def save_quiz_result(user_id, spice, sweet, savory, cuisines):
    """Store one quiz submission. Every retake adds a new row, so history is kept."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO quiz_results (user_id, spice, sweet, savory, cuisines) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, spice, sweet, savory, ",".join(cuisines)),
        )


def get_latest_result(user_id):
    """Return the user's most recent quiz answers as a dict, or None if they never took it."""
    with connect() as conn:
        row = conn.execute(
            "SELECT spice, sweet, savory, cuisines, taken_at FROM quiz_results "
            "WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "spice": row["spice"],
        "sweet": row["sweet"],
        "savory": row["savory"],
        "cuisines": row["cuisines"].split(",") if row["cuisines"] else [],
        "taken_at": row["taken_at"],
    }