"""Pure lock-resolution and word-matching logic.

Input is plain chars + 'backspace'/'esc' tokens (never raw key codes).
No asciimatics import — fully unit-testable.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import Enum

from .state import GameState
from .entities import FallingWord
from . import levels


class RejectKind(Enum):
    """Two distinct reject cases (PLAN §2.2)."""
    NOTHING_THERE = "nothing_there"   # no word's first/next char matches
    MISTYPE = "mistype"               # genuine mistype of locked word


@dataclass
class MatchResult:
    """Result of processing a keystroke."""
    accepted: bool          # True if the keystroke advanced a word or completed it
    rejected: bool          # True if the keystroke was a reject
    reject_kind: RejectKind | None = None
    completed: bool = False   # True if a word was completed this keystroke
    completed_word: str | None = None  # text of the completed word
    is_backspace: bool = False
    is_noop: bool = False    # Enter/Space no-op
    lock_changed: bool = False  # True if lock switched to a different word
    abandoned: bool = False  # True if lock was abandoned (double-backspace/esc)


def process_keystroke(
    state: GameState,
    key: str,
    *,
    hard_lock: bool = False,
    no_backspace: bool = False,
    is_first_game: bool = False,
) -> MatchResult:
    """Process a single keystroke against the game state.

    Args:
        state: Current game state (mutated in place).
        key: A plain character ('a', 'é', '3', '!') or 'backspace'/'esc'.
        hard_lock: If True, no implicit lock switching.
        no_backspace: If True, backspace is treated as a reject.
        is_first_game: If True, 'nothing there' rejects don't count against accuracy.

    Returns:
        MatchResult describing what happened.
    """
    # ── Enter/Space = no-op ──
    if key in ("enter", "space"):
        return MatchResult(accepted=False, rejected=False, is_noop=True)

    # ── Esc = abandon lock ──
    if key == "esc":
        if state.locked_word_index is not None:
            _abandon_lock(state)
            return MatchResult(accepted=False, rejected=False, abandoned=True)
        return MatchResult(accepted=False, rejected=False, is_noop=True)

    # ── Backspace ──
    if key == "backspace":
        if no_backspace:
            # In no-backspace mode, backspace is a reject
            return _handle_reject(state, RejectKind.MISTYPE, is_first_game)

        if state.locked_word_index is not None:
            word = state.words[state.locked_word_index]
            if word.typed:
                # Delete last typed char (combo-safe, small accuracy ding)
                word.typed = word.typed[:-1]
                word.error_count += 1  # small accuracy ding
                return MatchResult(accepted=False, rejected=False, is_backspace=True)
            else:
                # Double-backspace on empty buffer = abandon
                _abandon_lock(state)
                return MatchResult(accepted=False, rejected=False, abandoned=True)
        else:
            # No lock, backspace is a no-op
            return MatchResult(accepted=False, rejected=False, is_noop=True)

    # ── Normalize the key ──
    key = unicodedata.normalize("NFC", key)
    if len(key) != 1:
        # Multi-char after normalization — shouldn't happen for valid input
        return MatchResult(accepted=False, rejected=False, is_noop=True)

    # ── No lock yet: try to lock onto a word ──
    if state.locked_word_index is None:
        return _try_lock(state, key, hard_lock, is_first_game)

    # ── Already locked: try to advance or switch ──
    return _advance_or_switch(state, key, hard_lock, is_first_game)


def _try_lock(state: GameState, key: str, hard_lock: bool, is_first_game: bool = False) -> MatchResult:
    """Try to lock onto the lowest word starting with key."""
    # Find the lowest (most urgent) word whose first char matches
    best_idx = state.find_lowest_matching(key)
    if best_idx is None:
        return _handle_reject(state, RejectKind.NOTHING_THERE, is_first_game)

    # Lock onto this word
    word = state.words[best_idx]
    state.locked_word_index = best_idx
    word.locked = True
    word.typed = key
    return MatchResult(accepted=True, rejected=False, lock_changed=True)


def _advance_or_switch(
    state: GameState,
    key: str,
    hard_lock: bool,
    is_first_game: bool,
) -> MatchResult:
    """Try to advance the locked word, or switch to a more urgent one."""
    locked_idx = state.locked_word_index
    if locked_idx is None or locked_idx >= len(state.words):
        state.locked_word_index = None
        return _try_lock(state, key, hard_lock)

    word = state.words[locked_idx]
    next_char = word.next_char

    # ── Direct match: advance the locked word ──
    if next_char and key == next_char:
        word.typed += key
        if word.is_complete:
            return _complete_word(state, word, locked_idx)
        return MatchResult(accepted=True, rejected=False)

    # ── Mismatch: check for switch or reject ──

    # Check if key matches a different word's first char
    switch_candidate = _find_switch_candidate(state, key, locked_idx)

    if switch_candidate is not None:
        # Urgency-gated switch check
        can_switch = _can_switch(state, word, switch_candidate, hard_lock)
        if can_switch:
            return _do_switch(state, word, locked_idx, switch_candidate, key)

    # ── Reject ──
    # When locked, a mismatch is always a "genuine mistype" of the locked word.
    # "Nothing there" only applies when no lock exists (handled in _try_lock).
    # No brute-forcing: a wrong key wipes all progress on this word, so the
    # player must retype it from the first character (the lock is kept).
    word.typed = ""
    return _handle_reject(state, RejectKind.MISTYPE, is_first_game)


def _find_switch_candidate(
    state: GameState,
    key: str,
    current_locked_idx: int,
) -> tuple[int, FallingWord] | None:
    """Find the most urgent (lowest) word starting with key, excluding current lock."""
    best_idx = None
    best_row = -1.0
    for i, w in enumerate(state.words):
        if i == current_locked_idx:
            continue
        if w.text and w.text[0] == key and w.row > best_row:
            best_row = w.row
            best_idx = i
    if best_idx is not None:
        return best_idx, state.words[best_idx]
    return None


def _can_switch(
    state: GameState,
    current_word: FallingWord,
    candidate: tuple[int, FallingWord],
    hard_lock: bool,
) -> bool:
    """Determine if switching from current_word to candidate is allowed.

    PLAN §2.2 urgency-gated switch guard:
    - Always allowed if candidate is in red zone OR is the lowest word on screen
    - Outside that case, only if we're 2+ chars into current word and
      candidate is strictly lower (higher row)
    - Hard lock mode: never allowed
    """
    if hard_lock:
        return False

    cand_idx, cand_word = candidate

    # Always allow if candidate is in red zone
    if levels.is_red_zone(cand_word.row, state.water_row):
        return True

    # Always allow if candidate is the lowest word on screen
    lowest_idx = None
    lowest_row = -1.0
    for i, w in enumerate(state.words):
        if w.row > lowest_row:
            lowest_row = w.row
            lowest_idx = i
    if cand_idx == lowest_idx:
        return True

    # Otherwise: only if we're 2+ chars into current word AND candidate is strictly lower
    chars_into_current = len(current_word.typed)
    if chars_into_current >= 2 and cand_word.row > current_word.row:
        return True

    return False


def _do_switch(
    state: GameState,
    old_word: FallingWord,
    old_idx: int,
    candidate: tuple[int, FallingWord],
    key: str,
) -> MatchResult:
    """Switch lock from old_word to candidate."""
    cand_idx, cand_word = candidate

    # Abandon old word (discard typed progress)
    old_word.locked = False
    old_word.typed = ""

    # Lock onto new word
    state.locked_word_index = cand_idx
    cand_word.locked = True
    cand_word.typed = key

    return MatchResult(accepted=True, rejected=False, lock_changed=True)


def _complete_word(state: GameState, word: FallingWord, idx: int) -> MatchResult:
    """Handle word completion."""
    word.locked = False
    state.locked_word_index = None
    return MatchResult(
        accepted=True,
        rejected=False,
        completed=True,
        completed_word=word.text,
    )


def _abandon_lock(state: GameState) -> None:
    """Abandon the current lock, discarding typed progress."""
    if state.locked_word_index is not None and state.locked_word_index < len(state.words):
        word = state.words[state.locked_word_index]
        word.locked = False
        word.typed = ""
    state.locked_word_index = None


def _handle_reject(
    state: GameState,
    kind: RejectKind,
    is_first_game: bool,
) -> MatchResult:
    """Handle a rejected keystroke.

    During the first game, 'nothing there' rejects don't count against accuracy.
    """
    if state.locked_word_index is not None and state.locked_word_index < len(state.words):
        state.words[state.locked_word_index].error_count += 1

    # First-game waiver for "nothing there" — not counted as a reject
    if kind == RejectKind.NOTHING_THERE and is_first_game:
        return MatchResult(accepted=False, rejected=False, reject_kind=kind)

    return MatchResult(accepted=False, rejected=True, reject_kind=kind)
