"""Score calculation, combos, and peak-score-rate tracking.

Pure logic — no terminal, no asciimatics.
"""
from __future__ import annotations

from . import levels


# ── Per-character base values (PLAN §3.2) ─────────────────────────────────

_CHAR_WEIGHTS: dict[str, int] = {}
# a-z, A-Z = 10
for c in "abcdefghijklmnopqrstuvwxyz":
    _CHAR_WEIGHTS[c] = 10
    _CHAR_WEIGHTS[c.upper()] = 10
# digits = 12
for c in "0123456789":
    _CHAR_WEIGHTS[c] = 12
# accented vowels = 13
for c in "àèéìòùÀÈÉÌÒÙ":
    _CHAR_WEIGHTS[c] = 13
# punctuation = 14
for c in "!?,.:;'-\"()":
    _CHAR_WEIGHTS[c] = 14


def base_value(word: str) -> int:
    """Sum of per-character weights (PLAN §4.1)."""
    return sum(_CHAR_WEIGHTS.get(c, 10) for c in word)


def speed_bonus(time_taken: float, word_length: int) -> float:
    """Speed bonus factor: max(0.5, 2.0 - time_taken / expected_time).

    For 1-char words, forced to 1.0 (PLAN §4.1).
    """
    if word_length <= 1:
        return 1.0
    expected = levels.expected_time("a" * word_length)  # just needs length
    if expected <= 0:
        return 1.0
    return max(0.5, 2.0 - time_taken / expected)


def accuracy_multiplier(error_count: int) -> float:
    """Per-word accuracy factor: ACC_PER_ERROR ** errors, capped at 1.0."""
    return min(1.0, levels.ACC_PER_ERROR ** error_count)


def combo_factor(combo_count: int) -> float:
    """Combo bonus factor: 1 + min(combo_count, 10) * 0.05 (PLAN §4.2)."""
    return 1.0 + min(combo_count, 10) * 0.05


def word_score(
    word: str,
    time_taken: float,
    error_count: int,
    level: int,
    combo_count: int,
    *,
    in_red_zone: bool = False,
    is_bonus_wave: bool = False,
) -> int:
    """Full per-word score (PLAN §4.1).

    word_score = base_value × speed_bonus × accuracy_multiplier × level_multiplier
    final      = word_score × combo_factor + danger_flat

    During bonus wave, the bonus-wave multiplier is applied outside the stack.
    """
    bv = base_value(word)
    sb = speed_bonus(time_taken, len(word))
    am = accuracy_multiplier(error_count)
    lm = levels.level_multiplier(level)
    cf = combo_factor(combo_count)

    score = bv * sb * am * lm * cf

    # Danger flat (additive, outside the stack)
    if in_red_zone:
        score += levels.DANGER_FLAT

    # Bonus wave multiplier (outside the per-word stack)
    if is_bonus_wave:
        score *= levels.BONUS_WAVE_MULT

    return int(score)


def update_combo(
    combo_count: int,
    combo_shield: bool,
    typo_window: list[int],
    keystroke_index: int,
    *,
    clean_chars: int = 0,
    is_typo: bool = False,
    is_backspace: bool = False,
    is_drowned: bool = False,
    is_bonus_wave: bool = False,
    word_length: int = 0,
) -> tuple[int, bool, list[int]]:
    """Update combo state based on a keystroke event (PLAN §4.2).

    Args:
        combo_count: Current combo step counter.
        combo_shield: Whether a shield is held.
        typo_window: List of keystroke indices of recent uncorrected typos.
        keystroke_index: Current keystroke number.
        clean_chars: Number of clean characters added this event.
        is_typo: True if this was an uncorrected typo.
        is_backspace: True if this was a backspace correction.
        is_drowned: True if a word drowned.
        is_bonus_wave: True if a bonus wave is active.
        word_length: Length of the word being typed (for MIN_COMBO_WORD_LEN check).

    Returns:
        (new_combo_count, new_combo_shield, new_typo_window)
    """
    # Backspace correction: combo-safe (no change)
    if is_backspace:
        return combo_count, combo_shield, typo_window

    # Drowned word: reset combo (except during bonus wave)
    if is_drowned:
        if is_bonus_wave:
            return combo_count, combo_shield, typo_window
        return 0, False, []

    # Clean characters: advance combo
    if clean_chars > 0 and word_length >= levels.MIN_COMBO_WORD_LEN:
        combo_count += clean_chars // levels.COMBO_CHARS_PER_STEP

    # Uncorrected typo: tiered decay
    shield_consumed = False
    if is_typo:
        typo_window.append(keystroke_index)
        # Prune window to recent keystrokes
        cutoff = keystroke_index - levels.COMBO_TYPO_WINDOW
        typo_window = [t for t in typo_window if t > cutoff]

        typo_count_in_window = len(typo_window)
        if typo_count_in_window == 1:
            # First typo: decay by one tier
            combo_count = max(0, combo_count - 1)
        elif typo_count_in_window == 2:
            # Second typo: halve
            combo_count = combo_count // 2
        else:
            # Third+ typo: reset to 0
            if combo_shield:
                # Shield absorbs the reset, decays by one tier instead
                combo_count = max(0, combo_count - 1)
                combo_shield = False
                shield_consumed = True
            else:
                combo_count = 0

    # Combo shield: granted at COMBO_SHIELD_AT milestone
    # Don't re-grant in the same event it was consumed
    if combo_count >= levels.COMBO_SHIELD_AT and not combo_shield and not shield_consumed:
        combo_shield = True

    return combo_count, combo_shield, typo_window


def update_peak_score_rate(
    score_history: list[tuple[float, int]],
    current_time: float,
    points: int,
    is_bonus_wave: bool,
    peak_rate: float,
) -> float:
    """Track peak score rate over rolling 60-s windows (PLAN §3.1).

    Only non-bonus points count. Returns the updated peak rate.
    """
    # Bonus wave points contribute 0 to the rate
    if not is_bonus_wave and points > 0:
        score_history.append((current_time, points))

    # Prune entries older than 60s
    cutoff = current_time - 60.0
    score_history[:] = [(t, p) for t, p in score_history if t > cutoff]

    # Calculate current rate
    if score_history:
        total = sum(p for _, p in score_history)
        rate = total / 60.0
        peak_rate = max(peak_rate, rate)

    return peak_rate


def story_word_score(
    word: str,
    time_taken: float,
    error_count: int,
    *,
    is_stopword: bool = False,
) -> float:
    """Story-mode word score (PLAN §5.2).

    Stopwords down-weighted; speed_bonus clamped to [0.8, 1.2];
    no danger bonus.
    """
    bv = base_value(word)
    if is_stopword:
        bv = int(bv * levels.STORY_STOPWORD_WEIGHT)

    sb = speed_bonus(time_taken, len(word))
    sb = max(0.8, min(1.2, sb))  # clamped

    am = accuracy_multiplier(error_count)

    return bv * sb * am


def pace_chain_bonus(chain_len: int) -> int:
    """Escalating per-sentence pace-chain award (PLAN §5.2).

    Each consecutive sentence cleared on pace is worth more, capped so a long
    chapter can't run away. A broken chain (chain_len 0) is worth nothing.
    """
    if chain_len <= 0:
        return 0
    return levels.STORY_PACE_BONUS * min(chain_len, levels.STORY_PACE_CHAIN_CAP)


def chapter_fluency_score(wpm: float, accuracy_pct: float, max_pace_chain: int) -> int:
    """Chapter-end fluency = WPM × accuracy × pace-chain bonus (PLAN §5.2).

    The personal-best number to beat on a re-read. accuracy_pct is 0–100; the
    pace chain scales the result so missing pace genuinely costs the headline.
    """
    acc = max(0.0, min(1.0, accuracy_pct / 100.0))
    pace_factor = 1.0 + 0.1 * min(max_pace_chain, levels.STORY_PACE_CHAIN_CAP)
    return int(round(max(0.0, wpm) * acc * pace_factor))
