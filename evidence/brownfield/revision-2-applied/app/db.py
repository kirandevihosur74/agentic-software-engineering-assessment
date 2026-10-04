import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
    code TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    clicks INTEGER NOT NULL DEFAULT 0,
    expires_at REAL
)
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    conn = connect(db_path)
    try:
        conn.execute(SCHEMA)
        conn.commit()
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(links)").fetchall()]
        if "expires_at" not in cols:
            try:
                conn.execute("ALTER TABLE links ADD COLUMN expires_at REAL")
                conn.commit()
            except sqlite3.OperationalError as exc:
                # Another process may have migrated concurrently.
                if "duplicate column" not in str(exc).lower():
                    raise
    finally:
        conn.close()
