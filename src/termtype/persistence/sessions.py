"""Resumable session save, load, and clear.

PLAN §7.2.
"""
from __future__ import annotations

import json
from typing import Any

import sqlite3


def save_session(
    conn: sqlite3.Connection,
    profile_id: int,
    *,
    level: int = 1,
    score: int = 0,
    story_position: int = 0,
    story_name: str | None = None,
    lives: int = 3,
    penalty_applied: bool = False,
    mode: str = "vocab",
    language: str = "en",
    option_flags: dict[str, bool] | None = None,
) -> None:
    """Save (or overwrite) the resumable session for a profile."""
    conn.execute(
        """INSERT OR REPLACE INTO session
           (profile_id, level, score, story_position, story_name, lives,
            penalty_applied, mode, language, option_flags, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
        (
            profile_id, level, score, story_position, story_name, lives,
            1 if penalty_applied else 0,
            mode, language,
            json.dumps(option_flags or {}),
        ),
    )
    conn.commit()


def load_session(conn: sqlite3.Connection, profile_id: int) -> dict[str, Any] | None:
    """Load the resumable session for a profile, or None if none exists."""
    row = conn.execute(
        "SELECT * FROM session WHERE profile_id = ?",
        (profile_id,),
    ).fetchone()
    if row is None:
        return None

    result = dict(row)
    result["penalty_applied"] = bool(result.get("penalty_applied", 0))
    try:
        result["option_flags"] = json.loads(result.get("option_flags", "{}"))
    except (json.JSONDecodeError, TypeError):
        result["option_flags"] = {}
    return result


def clear_session(conn: sqlite3.Connection, profile_id: int) -> None:
    """Clear the resumable session for a profile (game over)."""
    conn.execute("DELETE FROM session WHERE profile_id = ?", (profile_id,))
    conn.commit()


def apply_resume_penalty(
    conn: sqlite3.Connection,
    profile_id: int,
    current_score: int,
) -> tuple[int, bool]:
    """Apply the -10% resume penalty if not already applied.

    Returns (new_score, penalty_was_applied).
    """
    session = load_session(conn, profile_id)
    if session is None:
        return current_score, False

    if session["penalty_applied"]:
        return current_score, False

    # Apply -10% penalty
    new_score = int(current_score * 0.9)
    conn.execute(
        "UPDATE session SET score = ?, penalty_applied = 1, updated_at = datetime('now') WHERE profile_id = ?",
        (new_score, profile_id),
    )
    conn.commit()
    return new_score, True
