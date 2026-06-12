"""Tests for word_matcher.py — lock model and word matching."""
import pytest
from termtype.game.word_matcher import process_keystroke, RejectKind
from termtype.game.state import GameState
from termtype.game.entities import FallingWord


def make_state(water_row=20.0, **kwargs) -> GameState:
    defaults = dict(word_pool=[], water_row=water_row)
    defaults.update(kwargs)
    return GameState(**defaults)


def add_word(state: GameState, text: str, row: float, x: float = 10.0, speed: float = 1.0) -> FallingWord:
    w = FallingWord(text=text, x=x, row=row, speed=speed)
    state.words.append(w)
    return w


class TestLockOnFirstMatch:
    def test_first_keystroke_locks(self):
        state = make_state()
        add_word(state, "hello", row=10.0)

        result = process_keystroke(state, "h")

        assert result.accepted
        assert result.lock_changed
        assert state.locked_word_index == 0
        assert state.words[0].typed == "h"
        assert state.words[0].locked

    def test_locks_to_lowest_matching(self):
        state = make_state()
        add_word(state, "hello", row=5.0)
        add_word(state, "help", row=10.0)  # lower (more urgent)

        result = process_keystroke(state, "h")

        assert state.locked_word_index == 1  # "help" is lower
        assert state.words[1].typed == "h"

    def test_no_match_rejects(self):
        state = make_state()
        add_word(state, "hello", row=10.0)

        result = process_keystroke(state, "z")

        assert result.rejected
        assert result.reject_kind == RejectKind.NOTHING_THERE


class TestAdvance:
    def test_correct_char_advances(self):
        state = make_state()
        add_word(state, "hello", row=10.0)
        process_keystroke(state, "h")

        result = process_keystroke(state, "e")

        assert result.accepted
        assert state.words[0].typed == "he"

    def test_wrong_char_rejects(self):
        state = make_state()
        add_word(state, "hello", row=10.0)
        process_keystroke(state, "h")

        result = process_keystroke(state, "z")

        assert result.rejected
        assert result.reject_kind == RejectKind.MISTYPE

    def test_completion(self):
        state = make_state()
        add_word(state, "hi", row=10.0)
        process_keystroke(state, "h")

        result = process_keystroke(state, "i")

        assert result.completed
        assert result.completed_word == "hi"
        assert result.accepted
        assert state.locked_word_index is None


class TestMistypeResetsWord:
    """A wrong key wipes progress on the locked word — no brute-forcing."""

    def test_mistype_clears_typed_progress(self):
        state = make_state()
        add_word(state, "hello", row=10.0)
        for ch in "hel":
            process_keystroke(state, ch)
        assert state.words[0].typed == "hel"

        result = process_keystroke(state, "z")  # wrong

        assert result.rejected
        assert state.words[0].typed == ""          # back to the beginning
        assert state.locked_word_index == 0        # still locked on the same word

    def test_must_restart_from_first_char(self):
        state = make_state()
        add_word(state, "hello", row=10.0)
        for ch in "hel":
            process_keystroke(state, ch)
        process_keystroke(state, "z")  # wipes progress

        # The next-expected char is mid-word 'l' — typing it now must reject
        assert process_keystroke(state, "l").rejected
        # Only the first char advances again
        assert process_keystroke(state, "h").accepted
        assert state.words[0].typed == "h"


class TestSoftLockSwitch:
    def test_switch_to_different_word_first_char(self):
        state = make_state()
        add_word(state, "hello", row=5.0)
        add_word(state, "world", row=10.0)

        # Lock onto "hello"
        process_keystroke(state, "h")
        assert state.locked_word_index == 0

        # Type "w" — switches to "world" (lower word, first char match)
        result = process_keystroke(state, "w")

        assert result.accepted
        assert result.lock_changed
        assert state.locked_word_index == 1
        assert state.words[1].typed == "w"
        # Old word should be abandoned
        assert state.words[0].typed == ""
        assert not state.words[0].locked


class TestUrgencyGatedGuard:
    def test_red_zone_always_allows_switch(self):
        """A committed word can be abandoned by typing a red-zone word's first letter."""
        state = make_state(water_row=20.0)
        add_word(state, "hello", row=5.0)
        add_word(state, "world", row=18.0)  # in red zone (3 rows from water)

        # Lock onto "hello" and advance to "hel"
        process_keystroke(state, "h")
        process_keystroke(state, "e")
        process_keystroke(state, "l")
        assert state.words[0].typed == "hel"

        # Type "w" — should switch because "world" is in red zone
        result = process_keystroke(state, "w")

        assert result.accepted
        assert result.lock_changed
        assert state.locked_word_index == 1

    def test_lowest_word_allows_switch(self):
        """Switching to the lowest word on screen is always allowed."""
        state = make_state(water_row=20.0)
        add_word(state, "hello", row=5.0)
        add_word(state, "world", row=15.0)  # lowest, not in red zone

        process_keystroke(state, "h")
        process_keystroke(state, "e")
        # At char 2+, can switch to strictly-lower word
        result = process_keystroke(state, "w")

        assert result.accepted
        assert result.lock_changed

    def test_higher_word_blocked_at_2_chars(self):
        """Can't switch to a higher (less urgent) word when 2+ chars in."""
        state = make_state(water_row=20.0)
        add_word(state, "hello", row=15.0)  # lower
        add_word(state, "world", row=5.0)   # higher

        process_keystroke(state, "h")
        process_keystroke(state, "e")

        # Try to switch to "world" (higher) — should be blocked
        result = process_keystroke(state, "w")

        assert result.rejected

    def test_char_1_switch_to_most_urgent(self):
        """On char 1, switch to the most-urgent first-character match."""
        state = make_state(water_row=20.0)
        add_word(state, "hello", row=5.0)
        add_word(state, "help", row=15.0)  # lower, also starts with h

        # Lock onto "hello" (first h found)
        process_keystroke(state, "h")
        # Actually it should lock to the lowest h, which is "help"
        assert state.locked_word_index == 1


class TestBackspace:
    def test_backspace_fixes_typo(self):
        state = make_state()
        add_word(state, "hello", row=10.0)
        process_keystroke(state, "h")
        process_keystroke(state, "e")

        result = process_keystroke(state, "backspace")

        assert result.is_backspace
        assert state.words[0].typed == "h"
        # error_count increased (small accuracy ding)
        assert state.words[0].error_count == 1

    def test_double_backspace_abandons(self):
        state = make_state()
        add_word(state, "hello", row=10.0)
        process_keystroke(state, "h")

        result = process_keystroke(state, "backspace")

        assert result.is_backspace
        assert state.words[0].typed == ""

        # Second backspace on empty buffer = abandon
        result = process_keystroke(state, "backspace")

        assert result.abandoned
        assert state.locked_word_index is None
        assert not state.words[0].locked

    def test_esc_abandons(self):
        state = make_state()
        add_word(state, "hello", row=10.0)
        process_keystroke(state, "h")
        process_keystroke(state, "e")

        result = process_keystroke(state, "esc")

        assert result.abandoned
        assert state.locked_word_index is None
        assert state.words[0].typed == ""

    def test_backspace_no_lock_is_noop(self):
        state = make_state()
        add_word(state, "hello", row=10.0)

        result = process_keystroke(state, "backspace")

        assert result.is_noop


class TestEnterSpaceNoop:
    def test_enter_is_noop(self):
        state = make_state()
        add_word(state, "hello", row=10.0)
        process_keystroke(state, "h")

        result = process_keystroke(state, "enter")

        assert result.is_noop
        assert not result.rejected

    def test_space_is_noop(self):
        state = make_state()
        add_word(state, "hello", row=10.0)

        result = process_keystroke(state, "space")

        assert result.is_noop
        assert not result.rejected


class TestHardLock:
    def test_hard_lock_rejects_switch(self):
        state = make_state(water_row=20.0)
        add_word(state, "hello", row=5.0)
        add_word(state, "world", row=18.0)  # in red zone

        process_keystroke(state, "h", hard_lock=True)

        # Even though "world" is in red zone, hard lock blocks switch
        result = process_keystroke(state, "w", hard_lock=True)

        assert result.rejected


class TestNoBackspaceMode:
    def test_backspace_is_reject(self):
        state = make_state()
        add_word(state, "hello", row=10.0)
        process_keystroke(state, "h")

        result = process_keystroke(state, "backspace", no_backspace=True)

        assert result.rejected
        assert result.reject_kind == RejectKind.MISTYPE
        # typed is unchanged
        assert state.words[0].typed == "h"


class TestFirstGameWaiver:
    def test_nothing_there_not_counted_first_game(self):
        state = make_state()
        add_word(state, "hello", row=10.0)

        result = process_keystroke(state, "z", is_first_game=True)

        # "nothing there" during first game is not counted as reject
        assert not result.rejected
        assert result.reject_kind == RejectKind.NOTHING_THERE

    def test_mistype_still_counted_first_game(self):
        state = make_state()
        add_word(state, "hello", row=10.0)
        process_keystroke(state, "h")

        result = process_keystroke(state, "z", is_first_game=True)

        assert result.rejected
        assert result.reject_kind == RejectKind.MISTYPE


class TestNFCNormalization:
    def test_accented_char_matches(self):
        state = make_state()
        add_word(state, "café", row=10.0)

        result = process_keystroke(state, "c")
        assert result.accepted
        assert state.words[0].typed == "c"

        process_keystroke(state, "a")
        process_keystroke(state, "f")

        # 'é' should match
        result = process_keystroke(state, "é")
        assert result.accepted
        assert result.completed
        assert result.completed_word == "café"
