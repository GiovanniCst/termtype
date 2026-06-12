"""Shared leaderboard — insert and top-10 queries.

PLAN §7.1.
"""
from __future__ import annotations

from typing import Any

import sqlite3


def build_leaderboard_key(
    mode: str,
    language: str,
    flags: dict[str, bool],
) -> str:
    """Build the canonical leaderboard key (PLAN §7.1).

    Key = mode_language_sorted-flags (or mode_language_none).
    """
    # Gameplay-affecting flag allowlist
    allowed_flags = {
        "numbers", "accents", "punctuation",
        "pack_scifi", "pack_programming", "no_backspace", "fog",
    }

    active = sorted(
        k for k, v in flags.items()
        if v and k in allowed_flags
    )

    if not active:
        return f"{mode}_{language}_none"

    return f"{mode}_{language}_{'_'.join(active)}"


def get_top_scores(
    conn: sqlite3.Connection,
    leaderboard_key: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Get top scores for a leaderboard key."""
    rows = conn.execute(
        """SELECT s.game_id, s.profile_id, p.display_name, s.score, s.game_over_ts
           FROM score s
           JOIN profile p ON s.profile_id = p.id
           WHERE s.leaderboard_key = ?
           ORDER BY s.score DESC, s.game_over_ts ASC, s.game_id ASC
           LIMIT ?""",
        (leaderboard_key, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_top_rates(
    conn: sqlite3.Connection,
    leaderboard_key: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Get top peak-score-rate entries for a leaderboard key."""
    rows = conn.execute(
        """SELECT s.game_id, s.profile_id, p.display_name, s.peak_score_rate, s.game_over_ts
           FROM score s
           JOIN profile p ON s.profile_id = p.id
           WHERE s.leaderboard_key = ?
           ORDER BY s.peak_score_rate DESC, s.game_over_ts ASC, s.game_id ASC
           LIMIT ?""",
        (leaderboard_key, limit),
    ).fetchall()
    return [dict(r) for r in rows]
