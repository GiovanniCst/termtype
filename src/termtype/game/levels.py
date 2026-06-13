"""Difficulty model and tunable constants.

All values are pinned to TERM_TYPE_PLAN defaults.
"""
from __future__ import annotations

# ── Tunable constants (PLAN §4.1, §4.2, §3.1, §8.1) ──────────────────────

# Scoring
per_char_seconds: float = 0.50  # expected_time inter-char interval
BASE_FLOOR: float = 0.50        # minimum expected_time
DANGER_FLAT: int = 10           # flat bonus for red-zone clear
RED_ZONE_ROWS: int = 3          # rows from water to count as red zone
ACC_PER_ERROR: float = 0.85     # per-error accuracy multiplier

# Combo (PLAN §4.2)
COMBO_CHARS_PER_STEP: int = 5   # chars per combo step
MIN_COMBO_WORD_LEN: int = 2     # words shorter than this don't affect combo
COMBO_TYPO_WINDOW: int = 10     # keystroke-count window for combo decay
COMBO_SHIELD_AT: int = 25       # combo milestone granting a shield

# Bonus wave (PLAN §3.1)
BONUS_WAVE_EVERY: int = 5       # levels between bonus waves
BONUS_WAVE_DURATION: float = 8.0  # seconds
BONUS_WAVE_MULT: float = 2.0    # score multiplier during wave

# Plateau surges (PLAN §3.1)
PLATEAU_SURGE_EVERY: int = 20   # words between surges at plateau
PLATEAU_SURGE_RAMP: float = 0.05  # speed increase per surge

# Story mode (PLAN §5.2)
STORY_STOPWORD_WEIGHT: float = 0.25
STORY_PACE_BONUS: int = 25        # base per-sentence pace-chain award
STORY_PACE_CHAIN_CAP: int = 10    # escalation caps here
# In-order "flow": a small escalating bonus for clearing the reading-order
# frontier word. Kept tiny on purpose — chasing order must never tempt a player
# to let an urgent word drown (a drown forfeits far more via the pace chain).
STORY_IN_ORDER_BONUS: int = 2     # points per consecutive in-order clear
STORY_FLOW_CAP: int = 5           # escalation caps here (max +10)

# Story-mode side panel (HN skin): max width in columns of the right-hand panel;
# the playfield gets the rest. engine.play_cols and the renderer divider both read
# this so they stay in sync.
STORY_PANEL_COLS: int = 66

# HUD (PLAN §8.3)
HUD_HEART_GLYPH_MAX: int = 5

# Charts (PLAN §8.4)
FLAT_THRESHOLD: float = 0.01    # below this range, render flat row

# Spawn
SPAWN_FLOOR: int = 2            # minimum on-screen words
SPAWN_TIMER_BASE: float = 2.0   # base seconds between spawns

# Level progression (PLAN §3.1)
WORDS_PER_LEVEL: int = 10       # destroyed words per level-up

# Level multiplier (PLAN §4.1)
LEVEL_MULT_CAP: float = 2.4     # saturates at ~level 15
LEVEL_MULT_STEP: float = 0.1    # +10% per level

# Life-loss
DEFAULT_LIVES: int = 3

# Plateau
PLATEAU_LEVEL: int = 15         # difficulty plateaus here


# ── Per-level band table (PLAN §3.1) ─────────────────────────────────────

# Each band: (level_min, level_max, speed_range, max_simultaneous, complexity)
# speed_range is (min_rows_per_sec, max_rows_per_sec)
_BANDS: list[tuple[int, int, tuple[float, float], int, str]] = [
    # Levels 1-3: raise speed only, 2-3 words, short/simple
    (1,  3,  (0.8, 1.5),  3, "short"),
    # Levels 4-6: hold speed, reading-load climbs, longer words at 4
    (4,  6,  (1.5, 1.5),  4, "medium"),
    # Levels 7-9: ramp speed again, special chars at 7
    (7,  9,  (1.5, 2.2),  4, "complex"),
    # Levels 10+: fast, 5+ words
    (10, 14, (2.2, 3.0),  5, "complex"),
    # Plateau (≥15): caps
    (15, 99, (3.0, 3.0),  5, "complex"),
]


def level_multiplier(level: int) -> float:
    """Per-level score multiplier, saturating at LEVEL_MULT_CAP (PLAN §4.1)."""
    return 1.0 + min(level - 1, 14) * LEVEL_MULT_STEP


def band_for_level(level: int) -> tuple[int, int, tuple[float, float], int, str]:
    """Return the (level_min, level_max, speed_range, max_simultaneous, complexity) band for a level."""
    for band in _BANDS:
        if band[0] <= level <= band[1]:
            return band
    return _BANDS[-1]


def speed_range_for_level(level: int) -> tuple[float, float]:
    """Return (min_speed, max_speed) in rows/sec for the given level."""
    _, _, speed_range, _, _ = band_for_level(level)
    return speed_range


def max_simultaneous_for_level(level: int) -> int:
    """Return max on-screen words for the given level."""
    _, _, _, max_sim, _ = band_for_level(level)
    return max_sim


def complexity_for_level(level: int) -> str:
    """Return the complexity tier name for the given level."""
    _, _, _, _, complexity = band_for_level(level)
    return complexity


def expected_time(word: str) -> float:
    """Expected typing time in seconds for a word (PLAN §4.1).

    time_taken is measured from the locking keystroke to completion.
    expected_time = max(BASE_FLOOR, (len(word) - 1) * per_char_seconds).
    1-char words have expected_time = BASE_FLOOR (speed_bonus forced to 1.0 elsewhere).
    """
    return max(BASE_FLOOR, (len(word) - 1) * per_char_seconds)


def is_red_zone(word_row: float, water_row: float) -> bool:
    """True if the word is within RED_ZONE_ROWS of the water line."""
    return (water_row - word_row) <= RED_ZONE_ROWS


def is_bonus_wave(level: int) -> bool:
    """True if this level triggers a bonus wave (every BONUS_WAVE_EVERY levels)."""
    return level > 0 and level % BONUS_WAVE_EVERY == 0


def plateau_surge_params(depth: int) -> tuple[float, float]:
    """Return (speed_mult, spawn_mult) for a plateau surge at given depth.

    Each surge is slightly faster/denser than the last (PLAN §3.1).
    """
    speed_mult = 1.0 + depth * PLATEAU_SURGE_RAMP
    spawn_mult = 1.0 + depth * PLATEAU_SURGE_RAMP * 0.5
    return speed_mult, spawn_mult
