"""SQLite connection, PRAGMAs, schema DDL, and migrations.

PLAN §7.1, §7.6.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path


# Current schema version
SCHEMA_VERSION = 2

# Default DB path
DEFAULT_DB_DIR = Path.home() / ".termtype"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "termtype.db"


class NewerDatabaseError(Exception):
    """Raised when the DB's user_version exceeds the app's SCHEMA_VERSION."""


def get_db_path() -> Path:
    """Return the default database path."""
    return DEFAULT_DB_PATH


def open_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open (or create) the database with proper PRAGMAs and schema.

    Args:
        db_path: Path to the database file. None = default path.
                 Use ":memory:" for testing.

    Returns:
        A sqlite3.Connection with row_factory set.
    """
    if db_path is None:
        db_path = get_db_path()

    db_path = str(db_path)

    # Ensure parent directory exists (skip for :memory:)
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    if db_path == ":memory:":
        # In-memory DBs are never corrupt and have nothing to quarantine.
        conn = _connect(db_path)
        _ensure_schema(conn)
        return conn

    # A corrupt file can fail either at connect/PRAGMA time or at the explicit
    # integrity check. Treat both as corruption: quarantine and start fresh.
    try:
        conn = _connect(db_path)
        healthy = _is_healthy(conn)
    except sqlite3.DatabaseError:
        conn = None
        healthy = False

    if not healthy:
        conn = _quarantine_and_recreate(conn, db_path)

    # Create schema and run migrations
    _ensure_schema(conn)

    return conn


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a connection and apply the standard PRAGMAs."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=FULL")

    # macOS fullfsync
    if sys.platform == "darwin":
        conn.execute("PRAGMA fullfsync=ON")

    return conn


def _is_healthy(conn: sqlite3.Connection) -> bool:
    """Return True if PRAGMA integrity_check passes, False if corrupt/unreadable."""
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        return bool(result) and result[0] == "ok"
    except sqlite3.DatabaseError:
        return False


def _quarantine_and_recreate(conn: sqlite3.Connection | None, db_path: str) -> sqlite3.Connection:
    """Quarantine the corrupt DB file and return a fresh connection on a new empty DB."""
    if conn is not None:
        conn.close()
    ts = time.strftime("%Y%m%d_%H%M%S")
    corrupt_path = f"{db_path}.corrupt.{ts}"
    try:
        os.rename(db_path, corrupt_path)
    except OSError:
        pass
    # Log warning (data is unrecoverable; quarantined file is retained)
    print(f"WARNING: Database corrupted. Quarantined to {corrupt_path}. Starting fresh.", file=sys.stderr)
    # Fresh connection on the now-absent path → brand-new empty DB.
    return _connect(db_path)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist and run migrations."""
    current_version = conn.execute("PRAGMA user_version").fetchone()[0]

    if current_version > SCHEMA_VERSION:
        # Refuse to open: a downgrade would corrupt/lose data (PLAN §7.6).
        raise NewerDatabaseError(
            "This save was written by a newer version of TermType "
            f"(database version {current_version} > supported {SCHEMA_VERSION}). "
            "Please upgrade TermType to open it."
        )

    if current_version == 0:
        _create_schema_v1(conn)

    if current_version < SCHEMA_VERSION:
        # Run pending migrations
        _run_migrations(conn, current_version)


def _create_schema_v1(conn: sqlite3.Connection) -> None:
    """Create the v1 schema (PLAN §7.1)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY,
            display_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            created_at TEXT DEFAULT (datetime('now')),
            last_played TEXT
        );

        CREATE TABLE IF NOT EXISTS config (
            profile_id INTEGER PRIMARY KEY REFERENCES profile(id),
            language TEXT DEFAULT 'en',
            difficulty_numbers INTEGER DEFAULT 0,
            difficulty_accents INTEGER DEFAULT 0,
            difficulty_punctuation INTEGER DEFAULT 0,
            hard_lock INTEGER DEFAULT 0,
            no_backspace INTEGER DEFAULT 0,
            fog INTEGER DEFAULT 0,
            music_on INTEGER DEFAULT 0,
            music_mood TEXT DEFAULT 'retro',
            music_volume REAL DEFAULT 0.5,
            sfx_on INTEGER DEFAULT 1,
            sfx_volume REAL DEFAULT 0.7,
            reduced_motion INTEGER DEFAULT 0,
            active_theme TEXT DEFAULT 'default',
            enabled_packs TEXT DEFAULT '[]',
            json_extra TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS app_state (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS session (
            profile_id INTEGER PRIMARY KEY REFERENCES profile(id),
            level INTEGER DEFAULT 1,
            score INTEGER DEFAULT 0,
            story_position INTEGER DEFAULT 0,
            lives INTEGER DEFAULT 3,
            penalty_applied INTEGER DEFAULT 0,
            mode TEXT DEFAULT 'vocab',
            language TEXT DEFAULT 'en',
            option_flags TEXT DEFAULT '{}',
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS stats (
            profile_id INTEGER PRIMARY KEY REFERENCES profile(id),
            games_played INTEGER DEFAULT 0,
            total_keystrokes INTEGER DEFAULT 0,
            total_correct_keystrokes INTEGER DEFAULT 0,
            total_correct_chars INTEGER DEFAULT 0,
            total_seconds_played REAL DEFAULT 0,
            cumulative_score INTEGER DEFAULT 0,
            best_score INTEGER DEFAULT 0,
            highest_level INTEGER DEFAULT 0,
            best_wpm REAL DEFAULT 0,
            best_accuracy REAL DEFAULT 0,
            max_combo INTEGER DEFAULT 0,
            words_typed INTEGER DEFAULT 0,
            words_missed INTEGER DEFAULT 0,
            first_played TEXT,
            last_played TEXT
        );

        CREATE TABLE IF NOT EXISTS badge (
            profile_id INTEGER REFERENCES profile(id),
            badge TEXT NOT NULL,
            earned_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (profile_id, badge)
        );

        CREATE TABLE IF NOT EXISTS game_history (
            game_id TEXT PRIMARY KEY,
            profile_id INTEGER REFERENCES profile(id),
            played_at TEXT DEFAULT (datetime('now')),
            score INTEGER,
            wpm REAL,
            accuracy REAL,
            level INTEGER,
            words_typed INTEGER
        );

        CREATE TABLE IF NOT EXISTS score (
            game_id TEXT PRIMARY KEY,
            leaderboard_key TEXT NOT NULL,
            profile_id INTEGER REFERENCES profile(id),
            score INTEGER,
            peak_score_rate REAL,
            game_over_ts TEXT DEFAULT (datetime('now'))
        );

        PRAGMA user_version = 1;
    """)


def _run_migrations(conn: sqlite3.Connection, from_version: int) -> None:
    """Run pending schema migrations. Each migration commits its own version bump."""
    if from_version < 2:
        # v2: remember which story a resumable session belongs to
        conn.executescript(
            "ALTER TABLE session ADD COLUMN story_name TEXT;\n"
            "PRAGMA user_version = 2;"
        )


def backup_db(conn: sqlite3.Connection, db_path: str | Path | None = None) -> bool:
    """Create a VACUUM INTO backup. Returns True on success."""
    if db_path is None:
        db_path = get_db_path()
    backup_path = str(db_path) + ".bak"
    try:
        conn.execute(f"VACUUM INTO '{backup_path}'")
        return True
    except sqlite3.Error:
        return False
