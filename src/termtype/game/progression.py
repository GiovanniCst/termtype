"""Declarative badge and unlock tables with pure evaluation.

All progression logic is derived, never stored (PLAN §3.1).
No terminal, no wall-clock — deterministic from payload + history.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ── Badge table (PLAN §3.1) ──────────────────────────────────────────────

@dataclass(frozen=True)
class BadgeDef:
    id: str
    description: str


BADGES: list[BadgeDef] = [
    BadgeDef("level_10", "Reach level 10"),
    BadgeDef("plateau", "Reach the plateau cap (First Plateau)"),
    BadgeDef("combo_25", "Max combo ≥ 25"),
    BadgeDef("combo_50", "Max combo ≥ 50"),
    BadgeDef("word_100wpm", "Type a single word at ≥ 100 WPM"),
    BadgeDef("wave_clean", "Bonus wave ends with zero drowned words"),
    BadgeDef("wave_perfect", "Bonus wave ends with zero rejects (Perfect Wave)"),
    BadgeDef("streak_7", "Play on 7 consecutive calendar days"),
    BadgeDef("story_done", "Complete a story text"),
]

BADGE_IDS: set[str] = {b.id for b in BADGES}


# ── Unlock table (PLAN §3.1) ─────────────────────────────────────────────

@dataclass(frozen=True)
class UnlockDef:
    id: str
    kind: str  # "theme", "title", "pack", "mod"
    requirement: str  # badge id or stat field name
    requirement_value: int  # threshold (0 means "just have the badge")


UNLOCKS: list[UnlockDef] = [
    UnlockDef("theme_nebula", "theme", "words_typed", 1000),
    UnlockDef("theme_abyss", "theme", "words_typed", 5000),
    UnlockDef("title_retro", "title", "streak_7", 0),
    UnlockDef("pack_scifi", "pack", "words_typed", 2500),
    UnlockDef("pack_programming", "pack", "combo_25", 0),
    UnlockDef("mod_no_backspace", "mod", "combo_50", 0),
    UnlockDef("mod_fog", "mod", "level_10", 0),
]

UNLOCK_IDS: set[str] = {u.id for u in UNLOCKS}


# ── Badge evaluation (PLAN §3.1) ─────────────────────────────────────────

@dataclass
class GamePayload:
    """Data from a completed run, used for badge evaluation."""
    highest_level: int = 0
    max_combo: int = 0
    max_word_wpm: float = 0.0
    reached_plateau: bool = False
    story_completed: bool = False
    # Per bonus-wave stats
    waves_clean: int = 0  # waves with zero drowned
    waves_perfect: int = 0  # waves with zero rejects


def evaluate_badges(
    payload: GamePayload,
    lifetime_stats: dict[str, Any],
    earned: set[str],
    recent_play_dates: list[str],
) -> set[str]:
    """Evaluate which new badges are earned this run (PLAN §3.1).

    Deterministic — dates from payload_ts + game_history, never wall-clock.
    Returns only NEWLY earned badge ids (not already in `earned`).
    """
    new_badges: set[str] = set()

    # level_10: a run reaches level 10
    if payload.highest_level >= 10 and "level_10" not in earned:
        new_badges.add("level_10")

    # plateau: a run reaches the plateau cap
    if payload.reached_plateau and "plateau" not in earned:
        new_badges.add("plateau")

    # combo_25: run max combo ≥ 25
    if payload.max_combo >= 25 and "combo_25" not in earned:
        new_badges.add("combo_25")

    # combo_50: run max combo ≥ 50
    if payload.max_combo >= 50 and "combo_50" not in earned:
        new_badges.add("combo_50")

    # word_100wpm: a single word typed at ≥ 100 WPM
    if payload.max_word_wpm >= 100.0 and "word_100wpm" not in earned:
        new_badges.add("word_100wpm")

    # wave_clean: bonus wave ends with zero drowned
    if payload.waves_clean > 0 and "wave_clean" not in earned:
        new_badges.add("wave_clean")

    # wave_perfect: bonus wave ends with zero rejects
    if payload.waves_perfect > 0 and "wave_perfect" not in earned:
        new_badges.add("wave_perfect")

    # streak_7: games on 7 consecutive local calendar days
    if "streak_7" not in earned:
        if _check_streak_7(recent_play_dates):
            new_badges.add("streak_7")

    # story_done: a story text completed
    if payload.story_completed and "story_done" not in earned:
        new_badges.add("story_done")

    return new_badges


def _check_streak_7(dates: list[str]) -> bool:
    """Check if there are 7 consecutive calendar days in the date list.

    Dates are ISO 8601 strings (YYYY-MM-DD or full ISO).
    """
    if len(dates) < 7:
        return False

    # Extract just the date part and deduplicate
    from datetime import datetime, timedelta
    unique_dates = set()
    for d in dates:
        try:
            dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
            unique_dates.add(dt.date())
        except (ValueError, AttributeError):
            continue

    if len(unique_dates) < 7:
        return False

    sorted_dates = sorted(unique_dates)

    # Check for 7 consecutive days
    for i in range(len(sorted_dates) - 6):
        base = sorted_dates[i]
        consecutive = all(
            sorted_dates[i + j] == base + timedelta(days=j)
            for j in range(7)
        )
        if consecutive:
            return True

    return False


# ── Unlock derivation (PLAN §3.1) ────────────────────────────────────────

def available_unlocks(
    lifetime_stats: dict[str, Any],
    earned_badges: set[str],
) -> dict[str, bool]:
    """Derive which unlocks are available based on current stats and badges.

    Returns a dict of unlock_id -> available (True/False).
    Derived at call time — no storage.
    """
    result: dict[str, bool] = {}

    for unlock in UNLOCKS:
        req = unlock.requirement
        val = unlock.requirement_value

        if req in BADGE_IDS:
            # Requirement is a badge
            result[unlock.id] = req in earned_badges
        else:
            # Requirement is a stat field
            stat_val = lifetime_stats.get(req, 0)
            result[unlock.id] = stat_val >= val

    return result
