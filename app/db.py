import sqlite3
from pathlib import Path


def connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(database_path: Path) -> None:
    with connect(database_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('text', 'file', 'image')),
                content TEXT,
                original_filename TEXT,
                stored_filename TEXT,
                mime_type TEXT,
                size_bytes INTEGER,
                expires_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_messages_user_created
                ON messages(user_id, created_at DESC, id DESC);

            CREATE TABLE IF NOT EXISTS message_shares (
                message_id INTEGER PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                max_views INTEGER,
                view_count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
            );
            """
        )
        share_columns = {row["name"] for row in conn.execute("PRAGMA table_info(message_shares)")}
        if "max_views" not in share_columns:
            conn.execute("ALTER TABLE message_shares ADD COLUMN max_views INTEGER")
        if "view_count" not in share_columns:
            conn.execute("ALTER TABLE message_shares ADD COLUMN view_count INTEGER NOT NULL DEFAULT 0")
