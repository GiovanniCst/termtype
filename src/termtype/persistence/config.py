"""Per-profile config load and save.

PLAN §7.1.
"""
from __future__ import annotations

import json
from typing import Any

import sqlite3

# Default config values
DEFAULTS: dict[str, Any] = {
    "language": "en",
    "difficulty_numbers": 0,
    "difficulty_accents": 0,
    "difficulty_punctuation": 0,
    "hard_lock": 0,
    "no_backspace": 0,
    "fog": 0,
    "music_on": 0,
    "music_mood": "retro",
    "music_volume": 0.5,
    "sfx_on": 1,
    "sfx_volume": 0.7,
    "reduced_motion": 0,
    "active_theme": "default",
    "enabled_packs": "[]",
    "json_extra": "{}",
}


def load_config(conn: sqlite3.Connection, profile_id: int) -> dict[str, Any]:
    """Load config for a profile. Returns defaults for missing values."""
    row = conn.execute(
        "SELECT * FROM config WHERE profile_id = ?",
        (profile_id,),
    ).fetchone()

    if row is None:
        return dict(DEFAULTS)

    config = dict(row)
    # Merge with defaults for any missing columns
    result = dict(DEFAULTS)
    for key in result:
        if key in config and config[key] is not None:
            result[key] = config[key]

    # Clamp volumes
    result["music_volume"] = _clamp_volume(result.get("music_volume", 0.5))
    result["sfx_volume"] = _clamp_volume(result.get("sfx_volume", 0.7))

    return result


def save_config(conn: sqlite3.Connection, profile_id: int, config: dict[str, Any]) -> None:
    """Save config for a profile (upsert)."""
    # Clamp volumes before saving
    if "music_volume" in config:
        config["music_volume"] = _clamp_volume(config["music_volume"])
    if "sfx_volume" in config:
        config["sfx_volume"] = _clamp_volume(config["sfx_volume"])

    # Ensure JSON fields are strings
    if "enabled_packs" in config and isinstance(config["enabled_packs"], list):
        config["enabled_packs"] = json.dumps(config["enabled_packs"])
    if "json_extra" in config and isinstance(config["json_extra"], dict):
        config["json_extra"] = json.dumps(config["json_extra"])

    columns = list(config.keys())
    placeholders = ", ".join(["?"] * len(columns))
    updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "profile_id")

    sql = f"""
        INSERT INTO config (profile_id, {', '.join(columns)})
        VALUES (?, {placeholders})
        ON CONFLICT(profile_id) DO UPDATE SET {updates}
    """

    conn.execute(sql, [profile_id] + list(config.values()))
    conn.commit()


def _clamp_volume(value: Any) -> float:
    """Clamp volume to [0.0, 1.0], fallback to default on bad input."""
    try:
        v = float(value)
        if v != v:  # NaN check
            return 0.5
        return max(0.0, min(1.0, v))
    except (TypeError, ValueError):
        return 0.5
