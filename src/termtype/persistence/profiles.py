"""Profile CRUD, selection, and last-active tracking.

PLAN §7.3.
"""
from __future__ import annotations

import unicodedata
from typing import Any

import sqlite3

MAX_NAME_LENGTH = 32


def create_profile(conn: sqlite3.Connection, display_name: str) -> int:
    """Create a new profile. Returns the profile id.

    Raises ValueError on validation failure.
    """
    name = display_name.strip()
    if not name:
        raise ValueError("Profile name cannot be empty")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"Profile name too long (max {MAX_NAME_LENGTH})")

    name = unicodedata.normalize("NFC", name)

    try:
        cursor = conn.execute(
            "INSERT INTO profile (display_name) VALUES (?)",
            (name,),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError(f"Name '{name}' is already in use")


def list_profiles(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all profiles as list of dicts."""
    rows = conn.execute(
        "SELECT id, display_name, created_at, last_played FROM profile ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def get_profile(conn: sqlite3.Connection, profile_id: int) -> dict[str, Any] | None:
    """Get a profile by id, or None if not found."""
    row = conn.execute(
        "SELECT id, display_name, created_at, last_played FROM profile WHERE id = ?",
        (profile_id,),
    ).fetchone()
    return dict(row) if row else None


def rename_profile(conn: sqlite3.Connection, profile_id: int, new_name: str) -> None:
    """Rename a profile. Raises ValueError on failure."""
    name = new_name.strip()
    if not name:
        raise ValueError("Profile name cannot be empty")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"Profile name too long (max {MAX_NAME_LENGTH})")

    name = unicodedata.normalize("NFC", name)

    try:
        conn.execute(
            "UPDATE profile SET display_name = ? WHERE id = ?",
            (name, profile_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError(f"Name '{name}' is already in use")


def set_last_active(conn: sqlite3.Connection, profile_id: int) -> None:
    """Remember the last-active profile."""
    conn.execute(
        "INSERT OR REPLACE INTO app_state (key, value) VALUES ('last_active_profile_id', ?)",
        (str(profile_id),),
    )
    conn.commit()


def get_last_active(conn: sqlite3.Connection) -> int | None:
    """Get the last-active profile id, or None."""
    row = conn.execute(
        "SELECT value FROM app_state WHERE key = 'last_active_profile_id'"
    ).fetchone()
    if row:
        try:
            return int(row[0])
        except (ValueError, TypeError):
            return None
    return None


def touch_last_played(conn: sqlite3.Connection, profile_id: int, ts: str) -> None:
    """Update the profile's last_played timestamp."""
    conn.execute(
        "UPDATE profile SET last_played = ? WHERE id = ?",
        (ts, profile_id),
    )
    conn.commit()
