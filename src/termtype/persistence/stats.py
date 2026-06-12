"""Lifetime stats: game-over commit, history, and badges.

PLAN §7.4, §7.5.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import sqlite3


def get_stats(conn: sqlite3.Connection, profile_id: int) -> dict[str, Any]:
    """Get lifetime stats for a profile. Returns zeros if no row exists."""
    row = conn.execute(
        "SELECT * FROM stats WHERE profile_id = ?",
        (profile_id,),
    ).fetchone()
    if row is None:
        return {
            "profile_id": profile_id,
            "games_played": 0,
            "total_keystrokes": 0,
            "total_correct_keystrokes": 0,
            "total_correct_chars": 0,
            "total_seconds_played": 0.0,
            "cumulative_score": 0,
            "best_score": 0,
            "highest_level": 0,
            "best_wpm": 0.0,
            "best_accuracy": 0.0,
            "max_combo": 0,
            "words_typed": 0,
            "words_missed": 0,
            "first_played": None,
            "last_played": None,
        }
    return dict(row)


def game_over_commit(
    conn: sqlite3.Connection,
    profile_id: int,
    game_id: str | None = None,
    *,
    score: int,
    wpm: float,
    accuracy: float,
    level: int,
    words_typed: int,
    words_missed: int,
    correct_chars: int,
    total_keystrokes: int,
    correct_keystrokes: int,
    seconds_played: float,
    max_combo: int,
    peak_score_rate: float,
    leaderboard_key: str,
    payload_ts: str,
    new_badges: set[str] | None = None,
) -> str:
    """Execute the single game-over commit transaction (PLAN §7.5).

    1. Merge stats
    2. Insert leaderboard entry
    3. Insert game_history
    4. Clear session

    Returns the game_id.
    """
    if game_id is None:
        game_id = str(uuid.uuid4())

    new_badges = new_badges or set()

    # Idempotency check: if game_id already exists in history, skip the merge
    existing = conn.execute(
        "SELECT 1 FROM game_history WHERE game_id = ?", (game_id,)
    ).fetchone()
    if existing:
        return game_id

    # Get current stats
    current = get_stats(conn, profile_id)

    # Compute merged values
    new_games = current["games_played"] + 1
    new_cumulative = current["cumulative_score"] + score
    new_best_score = max(current["best_score"], score)
    new_highest_level = max(current["highest_level"], level)
    new_best_wpm = max(current["best_wpm"], wpm)
    new_best_accuracy = max(current["best_accuracy"], accuracy)
    new_max_combo = max(current["max_combo"], max_combo)
    new_words_typed = current["words_typed"] + words_typed
    new_words_missed = current["words_missed"] + words_missed
    new_total_keystrokes = current["total_keystrokes"] + total_keystrokes
    new_correct_keystrokes = current["total_correct_keystrokes"] + correct_keystrokes
    new_correct_chars = current["total_correct_chars"] + correct_chars
    new_seconds = current["total_seconds_played"] + seconds_played

    # first_played: min of existing and new
    first_played = current["first_played"]
    if first_played is None or payload_ts < first_played:
        first_played = payload_ts
    # last_played: max
    last_played = payload_ts
    if current["last_played"] and current["last_played"] > last_played:
        last_played = current["last_played"]

    # Execute in a single transaction
    try:
        conn.execute("BEGIN")

        # 1. Upsert stats
        conn.execute(
            """INSERT INTO stats (
                profile_id, games_played, total_keystrokes, total_correct_keystrokes,
                total_correct_chars, total_seconds_played, cumulative_score,
                best_score, highest_level, best_wpm, best_accuracy, max_combo,
                words_typed, words_missed, first_played, last_played
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id) DO UPDATE SET
                games_played = excluded.games_played,
                total_keystrokes = excluded.total_keystrokes,
                total_correct_keystrokes = excluded.total_correct_keystrokes,
                total_correct_chars = excluded.total_correct_chars,
                total_seconds_played = excluded.total_seconds_played,
                cumulative_score = excluded.cumulative_score,
                best_score = excluded.best_score,
                highest_level = excluded.highest_level,
                best_wpm = excluded.best_wpm,
                best_accuracy = excluded.best_accuracy,
                max_combo = excluded.max_combo,
                words_typed = excluded.words_typed,
                words_missed = excluded.words_missed,
                first_played = excluded.first_played,
                last_played = excluded.last_played""",
            (
                profile_id, new_games, new_total_keystrokes, new_correct_keystrokes,
                new_correct_chars, new_seconds, new_cumulative,
                new_best_score, new_highest_level, new_best_wpm, new_best_accuracy,
                new_max_combo, new_words_typed, new_words_missed,
                first_played, last_played,
            ),
        )

        # 2. Insert leaderboard entry (INSERT OR IGNORE for idempotency)
        conn.execute(
            "INSERT OR IGNORE INTO score (game_id, leaderboard_key, profile_id, score, peak_score_rate, game_over_ts) VALUES (?, ?, ?, ?, ?, ?)",
            (game_id, leaderboard_key, profile_id, score, peak_score_rate, payload_ts),
        )

        # 3. Insert game_history (INSERT OR IGNORE for idempotency)
        conn.execute(
            "INSERT OR IGNORE INTO game_history (game_id, profile_id, played_at, score, wpm, accuracy, level, words_typed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (game_id, profile_id, payload_ts, score, wpm, accuracy, level, words_typed),
        )

        # 4. Clear session
        conn.execute("DELETE FROM session WHERE profile_id = ?", (profile_id,))

        # 5. Insert new badges
        for badge_id in new_badges:
            conn.execute(
                "INSERT OR IGNORE INTO badge (profile_id, badge, earned_at) VALUES (?, ?, ?)",
                (profile_id, badge_id, payload_ts),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return game_id


def get_earned_badges(conn: sqlite3.Connection, profile_id: int) -> set[str]:
    """Get all earned badge ids for a profile."""
    rows = conn.execute(
        "SELECT badge FROM badge WHERE profile_id = ?",
        (profile_id,),
    ).fetchall()
    return {r[0] for r in rows}


def get_game_history(
    conn: sqlite3.Connection,
    profile_id: int,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get recent game history for a profile."""
    rows = conn.execute(
        "SELECT * FROM game_history WHERE profile_id = ? ORDER BY played_at DESC LIMIT ?",
        (profile_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def reset_stats(conn: sqlite3.Connection, profile_id: int) -> None:
    """Reset lifetime stats for a profile."""
    conn.execute("DELETE FROM stats WHERE profile_id = ?", (profile_id,))
    conn.execute("DELETE FROM badge WHERE profile_id = ?", (profile_id,))
    conn.execute("DELETE FROM game_history WHERE profile_id = ?", (profile_id,))
    conn.execute("DELETE FROM score WHERE profile_id = ?", (profile_id,))
    conn.commit()


def get_recent_play_dates(conn: sqlite3.Connection, profile_id: int) -> list[str]:
    """Get recent play dates for streak calculation."""
    rows = conn.execute(
        "SELECT played_at FROM game_history WHERE profile_id = ? ORDER BY played_at DESC LIMIT 14",
        (profile_id,),
    ).fetchall()
    return [r[0] for r in rows]
