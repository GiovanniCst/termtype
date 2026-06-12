"""HUD rendering — single top row.

PLAN §8.3. Fits in 80 columns with truncation priority.
"""
from __future__ import annotations

from . import levels


def render_hud(
    level: int,
    score: int,
    lives: int,
    wpm: float,
    accuracy: float,
    combo_count: int,
    width: int = 80,
    *,
    ascii_mode: bool = False,
) -> str:
    """Render the HUD line.

    Truncation priority (PLAN §8.3):
    1. Lives and Score never truncate
    2. WPM abbreviates
    3. Acc abbreviates
    4. Combo label drops (keep xN)
    5. Level label drops (keep number)
    """
    # Lives display (ASCII fallback ♥ → *, PLAN §8.9)
    heart = "*" if ascii_mode else "♥"
    if lives <= levels.HUD_HEART_GLYPH_MAX:
        lives_str = heart * lives
    else:
        lives_str = f"{heart}x{lives}"

    # Score display
    score_str = f"Score {score:,}"

    # Always include: Level, Score, Lives
    parts = [f"Lvl {level}", score_str, lives_str]

    # Build from highest priority to lowest, check if it fits
    full_parts = [
        f"Lvl {level}",
        score_str,
        lives_str,
        f"Acc {accuracy:.0f}%",
        f"WPM {wpm:.0f}",
        f"x{combo_count}",
    ]

    # Try full
    line = "  ".join(full_parts)
    if len(line) <= width:
        return line

    # Progressive truncation
    # Drop WPM label
    reduced = [f"Lvl {level}", score_str, lives_str, f"Acc {accuracy:.0f}%", f"x{combo_count}"]
    line = "  ".join(reduced)
    if len(line) <= width:
        return line

    # Drop Acc
    reduced = [f"Lvl {level}", score_str, lives_str, f"x{combo_count}"]
    line = "  ".join(reduced)
    if len(line) <= width:
        return line

    # Drop combo label, keep xN
    reduced = [f"Lvl {level}", score_str, lives_str]
    line = "  ".join(reduced)
    if len(line) <= width:
        return line

    # Minimal: just level, score, lives
    return f"{level}  {score:,}  {lives_str}"
